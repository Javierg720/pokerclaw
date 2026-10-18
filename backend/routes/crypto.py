"""Verified on-chain deposits that atomically credit Sweepstakes Coins."""
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_DOWN
import logging
import os
import time
import uuid
from typing import Dict

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from pymongo.errors import DuplicateKeyError, OperationFailure

from deps import client, db, get_current_user
from sweepstakes import ensure_sc_play_eligible, public_config

router = APIRouter(prefix="/api")
logger = logging.getLogger(__name__)

CRYPTO_COIN_IDS = {"btc": "bitcoin", "ltc": "litecoin", "eth": "ethereum"}
_price_cache: Dict[str, dict] = {}
_price_cache_time: float = 0
PRICE_CACHE_TTL = 60
PRICE_MAX_STALE_SECONDS = 300

BLOCKCHAIN_APIS = {
    "btc": "https://blockstream.info/api/tx/{tx_hash}",
    "eth": "https://api.blockchair.com/ethereum/dashboards/transaction/{tx_hash}",
    "ltc": "https://api.blockcypher.com/v1/ltc/main/txs/{tx_hash}",
}


class CryptoDepositRequest(BaseModel):
    crypto_type: str
    tx_hash: str = Field(min_length=16, max_length=128)
    # Accepted for compatibility with older clients, but never trusted. The
    # credited amount is always derived from the destination output on-chain.
    amount_crypto: float | None = Field(default=None, gt=0)


def _flag(name: str, default: bool = False) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _positive_int(name: str, default: int) -> int:
    try:
        return max(1, int(os.environ.get(name, str(default))))
    except (TypeError, ValueError):
        return default


def _positive_decimal(name: str, default: str) -> Decimal:
    try:
        value = Decimal(os.environ.get(name, default))
        return value if value > 0 else Decimal(default)
    except (InvalidOperation, TypeError):
        return Decimal(default)


def confirmation_requirements() -> dict[str, int]:
    return {
        "btc": _positive_int("CRYPTO_BTC_CONFIRMATIONS", 2),
        "ltc": _positive_int("CRYPTO_LTC_CONFIRMATIONS", 6),
        "eth": _positive_int("CRYPTO_ETH_CONFIRMATIONS", 12),
    }


def crypto_funding_enabled() -> bool:
    return (
        public_config()["funding_enabled"]
        and _flag("CRYPTO_FUNDING_ENABLED")
    )


async def _wallet_deposit_addresses(user_id: str) -> dict[str, str]:
    wallet = await db.wallets.find_one({"user_id": user_id}, {"_id": 0, "crypto_addresses": 1})
    configured = (wallet or {}).get("crypto_addresses") or {}
    return {
        coin: str(configured[coin]).strip()
        for coin in CRYPTO_COIN_IDS
        if configured.get(coin)
    }


async def get_crypto_prices() -> dict[str, dict]:
    """Return a fresh or recently cached market quote; never invent a price."""
    global _price_cache, _price_cache_time
    now = time.time()
    if _price_cache and (now - _price_cache_time) < PRICE_CACHE_TTL:
        return _price_cache

    try:
        async with httpx.AsyncClient(timeout=10) as http:
            ids = ",".join(CRYPTO_COIN_IDS.values())
            response = await http.get(
                "https://api.coingecko.com/api/v3/simple/price",
                params={
                    "ids": ids,
                    "vs_currencies": "usd",
                    "include_24hr_change": "true",
                },
            )
            response.raise_for_status()
            data = response.json()
            prices = {
                short: {
                    "usd": data[coin_id]["usd"],
                    "change_24h": data[coin_id].get("usd_24h_change", 0),
                }
                for short, coin_id in CRYPTO_COIN_IDS.items()
                if coin_id in data and data[coin_id].get("usd", 0) > 0
            }
            if not prices:
                raise ValueError("Price provider returned no supported assets")
            _price_cache = prices
            _price_cache_time = now
            return prices
    except Exception as error:
        logger.warning("Crypto price provider error: %s", error)
        if _price_cache and (now - _price_cache_time) <= PRICE_MAX_STALE_SECONDS:
            return _price_cache
        raise HTTPException(
            status_code=503,
            detail="Crypto pricing is temporarily unavailable. No deposit was credited.",
        ) from error


def _matching_output_amount(crypto_type: str, data: dict, address: str) -> Decimal:
    """Extract only value paid to the configured custody address."""
    if crypto_type == "btc":
        satoshis = sum(
            int(output.get("value", 0))
            for output in data.get("vout", [])
            if output.get("scriptpubkey_address") == address
        )
        return Decimal(satoshis) / Decimal(100_000_000)

    if crypto_type == "ltc":
        satoshis = sum(
            int(output.get("value", 0))
            for output in data.get("outputs", [])
            if address in output.get("addresses", [])
        )
        return Decimal(satoshis) / Decimal(100_000_000)

    recipient = str(data.get("recipient") or data.get("to") or "")
    if recipient.lower() != address.lower():
        return Decimal(0)
    return Decimal(str(data.get("value", 0))) / Decimal(10**18)


def _is_self_spend(crypto_type: str, data: dict, address: str) -> bool:
    """Reject wallet sweeps whose change returns to the deposit address."""
    if crypto_type == "btc":
        return any(
            (item.get("prevout") or {}).get("scriptpubkey_address") == address
            for item in data.get("vin", [])
        )
    if crypto_type == "ltc":
        return any(address in item.get("addresses", []) for item in data.get("inputs", []))
    sender = str(data.get("sender") or data.get("from") or "")
    return sender.lower() == address.lower()


async def verify_tx_on_blockchain(crypto_type: str, tx_hash: str, address: str) -> dict:
    """Verify a transaction and the amount delivered to the configured address."""
    api_url = BLOCKCHAIN_APIS.get(crypto_type)
    if not api_url:
        return {"verified": False, "confirmations": 0, "amount": "0", "error": "Unsupported crypto"}

    try:
        async with httpx.AsyncClient(timeout=15) as http:
            response = await http.get(api_url.format(tx_hash=tx_hash))
            if response.status_code == 404:
                return {"verified": False, "confirmations": 0, "amount": "0", "error": "Transaction not found"}
            response.raise_for_status()
            data = response.json()

            if crypto_type == "btc":
                if _is_self_spend("btc", data, address):
                    return {"verified": False, "confirmations": 0, "amount": "0", "error": "Wallet change is not a deposit"}
                status = data.get("status", {})
                block_height = status.get("block_height")
                confirmations = 0
                if status.get("confirmed") and block_height:
                    tip = await http.get("https://blockstream.info/api/blocks/tip/height")
                    tip.raise_for_status()
                    confirmations = max(0, int(tip.text) - int(block_height) + 1)
                amount = _matching_output_amount("btc", data, address)

            elif crypto_type == "ltc":
                if data.get("double_spend"):
                    return {"verified": False, "confirmations": 0, "amount": "0", "error": "Double-spend flagged"}
                if _is_self_spend("ltc", data, address):
                    return {"verified": False, "confirmations": 0, "amount": "0", "error": "Wallet change is not a deposit"}
                confirmations = int(data.get("confirmations", 0))
                amount = _matching_output_amount("ltc", data, address)

            else:
                entry = data.get("data", {}).get(tx_hash.lower()) or data.get("data", {}).get(tx_hash)
                transaction = (entry or {}).get("transaction", {})
                if not transaction or transaction.get("failed"):
                    return {"verified": False, "confirmations": 0, "amount": "0", "error": "Transaction failed or missing"}
                if _is_self_spend("eth", transaction, address):
                    return {"verified": False, "confirmations": 0, "amount": "0", "error": "Self-transfer is not a deposit"}
                block_id = int(transaction.get("block_id") or 0)
                confirmations = 0
                if block_id:
                    stats = await http.get("https://api.blockchair.com/ethereum/stats")
                    stats.raise_for_status()
                    best = int(stats.json().get("data", {}).get("best_block_height", block_id))
                    confirmations = max(0, best - block_id + 1)
                amount = _matching_output_amount("eth", transaction, address)

            if amount <= 0:
                return {
                    "verified": False,
                    "confirmations": confirmations,
                    "amount": "0",
                    "error": "Transaction does not pay the assigned deposit address",
                }
            return {
                "verified": True,
                "confirmations": confirmations,
                "amount": format(amount, "f"),
                "error": None,
            }
    except httpx.TimeoutException:
        return {"verified": False, "confirmations": 0, "amount": "0", "error": "Blockchain API timeout"}
    except Exception as error:
        logger.error("Blockchain verification error for %s/%s: %s", crypto_type, tx_hash, error)
        return {"verified": False, "confirmations": 0, "amount": "0", "error": "Blockchain verification failed"}


def _public_deposit(deposit: dict) -> dict:
    return {key: value for key, value in deposit.items() if key not in {"_id", "user_id"}}


async def _assert_deposit_allowed(user: dict) -> dict[str, str]:
    if not crypto_funding_enabled():
        raise HTTPException(status_code=503, detail="Crypto funding is not configured for this deployment.")
    if user.get("role") == "human":
        await ensure_sc_play_eligible(user)
    addresses = await _wallet_deposit_addresses(user["id"])
    if not addresses:
        raise HTTPException(status_code=503, detail="No unique crypto deposit address is assigned to this wallet.")
    return addresses


async def _refresh_and_credit(deposit: dict) -> dict:
    address = (await _wallet_deposit_addresses(deposit["user_id"])).get(deposit["crypto_type"])
    if not address or address != deposit["deposit_address"]:
        raise HTTPException(status_code=503, detail="The configured deposit address changed; contact support.")

    verification = await verify_tx_on_blockchain(deposit["crypto_type"], deposit["tx_hash"], address)
    if not verification["verified"]:
        raise HTTPException(status_code=400, detail=verification["error"])
    observed_amount = Decimal(verification["amount"])
    if observed_amount < Decimal(deposit["amount_crypto"]):
        raise HTTPException(status_code=409, detail="The verified payment amount is lower than the recorded deposit.")

    confirmations = int(verification["confirmations"])
    required = int(deposit["required_confirmations"])
    if confirmations < required:
        await db.crypto_deposits.update_one(
            {"id": deposit["id"], "status": "pending"},
            {"$set": {"confirmations": confirmations, "last_checked_at": datetime.now(timezone.utc).isoformat()}},
        )
        return {**deposit, "confirmations": confirmations, "status": "pending", "sc_credited": 0}

    async def commit_credit(session):
        current = await db.crypto_deposits.find_one(
            {"id": deposit["id"], "user_id": deposit["user_id"]}, {"_id": 0}, session=session,
        )
        if not current:
            raise HTTPException(status_code=404, detail="Deposit not found")
        if current.get("status") == "confirmed":
            return {**current, "sc_credited": 0}

        now = datetime.now(timezone.utc).isoformat()
        result = await db.crypto_deposits.update_one(
            {"id": deposit["id"], "status": "pending"},
            {"$set": {"status": "confirmed", "confirmations": confirmations, "confirmed_at": now, "last_checked_at": now}},
            session=session,
        )
        if result.modified_count != 1:
            latest = await db.crypto_deposits.find_one({"id": deposit["id"]}, {"_id": 0}, session=session)
            return {**latest, "sc_credited": 0}

        wallet_result = await db.wallets.update_one(
            {"user_id": deposit["user_id"]},
            {"$inc": {"sc_balance": deposit["sc_amount"]}},
            session=session,
        )
        if wallet_result.modified_count != 1:
            raise RuntimeError("Deposit wallet not found")
        await db.transactions.insert_one(
            {
                "id": f"crypto:{deposit['id']}",
                "user_id": deposit["user_id"],
                "type": "crypto_deposit",
                "amount": deposit["sc_amount"],
                "currency": "sc",
                "description": f"Verified {deposit['crypto_type'].upper()} deposit",
                "created_at": now,
            },
            session=session,
        )
        return {**current, "status": "confirmed", "confirmations": confirmations, "confirmed_at": now, "sc_credited": deposit["sc_amount"]}

    try:
        async with await client.start_session() as session:
            return await session.with_transaction(commit_credit)
    except OperationFailure as error:
        logger.warning("Crypto deposit transaction failed safely: %s", error)
        raise HTTPException(status_code=503, detail="Deposit credit could not be committed atomically. Retry safely.") from error


@router.get("/crypto/prices")
async def crypto_prices(user=Depends(get_current_user)):
    addresses = await _wallet_deposit_addresses(user["id"])
    funding_enabled = crypto_funding_enabled() and bool(addresses)
    redemption_enabled = user.get("role") == "human" and public_config()["redemption_enabled"]
    prices = await get_crypto_prices() if funding_enabled or redemption_enabled else {}
    return {
        "prices": prices,
        "funding_enabled": funding_enabled,
        "redemption_enabled": redemption_enabled,
        "rate": f"{format(_positive_decimal('SC_PER_USD', '100'), 'f')} SC per $1 USD" if funding_enabled or redemption_enabled else None,
        "sc_per_usd": float(_positive_decimal("SC_PER_USD", "100")) if funding_enabled or redemption_enabled else None,
        "deposit_addresses": addresses,
        "required_confirmations": {coin: confirmation_requirements()[coin] for coin in addresses},
    }


@router.post("/crypto/deposit")
async def submit_crypto_deposit(req: CryptoDepositRequest, user=Depends(get_current_user)):
    addresses = await _assert_deposit_allowed(user)
    crypto_type = req.crypto_type.strip().lower()
    tx_hash = req.tx_hash.strip().lower()
    address = addresses.get(crypto_type)
    if not address:
        raise HTTPException(status_code=400, detail="That cryptocurrency is not configured for deposits.")

    verification = await verify_tx_on_blockchain(crypto_type, tx_hash, address)
    if not verification["verified"]:
        raise HTTPException(status_code=400, detail=verification["error"])
    amount = Decimal(verification["amount"])
    prices = await get_crypto_prices()
    if crypto_type not in prices:
        raise HTTPException(status_code=503, detail="A verified price is not available for that cryptocurrency.")
    usd_price = Decimal(str(prices[crypto_type]["usd"]))
    sc_per_usd = _positive_decimal("SC_PER_USD", "100")
    sc_amount = int((amount * usd_price * sc_per_usd).quantize(Decimal("1"), rounding=ROUND_DOWN))
    if sc_amount < 1:
        raise HTTPException(status_code=400, detail="Deposit value is below the one-SC minimum.")

    deposit = {
        "id": str(uuid.uuid5(uuid.NAMESPACE_URL, f"crypto:{crypto_type}:{tx_hash.lower()}")),
        "user_id": user["id"],
        "crypto_type": crypto_type,
        "tx_hash": tx_hash,
        "deposit_address": address,
        "amount_crypto": format(amount, "f"),
        "usd_price": format(usd_price, "f"),
        "sc_per_usd": format(sc_per_usd, "f"),
        "sc_amount": sc_amount,
        "confirmations": int(verification["confirmations"]),
        "required_confirmations": confirmation_requirements()[crypto_type],
        "status": "pending",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    try:
        await db.crypto_deposits.insert_one(deposit)
    except DuplicateKeyError:
        existing = await db.crypto_deposits.find_one(
            {"crypto_type": crypto_type, "tx_hash": tx_hash}, {"_id": 0},
        )
        if not existing or existing.get("user_id") != user["id"]:
            raise HTTPException(status_code=409, detail="That transaction has already been claimed.")
        deposit = existing

    refreshed = await _refresh_and_credit(deposit)
    return _public_deposit(refreshed)


@router.get("/crypto/deposits")
async def get_crypto_deposits(user=Depends(get_current_user)):
    deposits = await db.crypto_deposits.find(
        {"user_id": user["id"]}, {"_id": 0, "user_id": 0}
    ).sort("created_at", -1).to_list(50)
    return deposits


@router.post("/crypto/deposits/{deposit_id}/confirm")
async def confirm_deposit(deposit_id: str, user=Depends(get_current_user)):
    await _assert_deposit_allowed(user)
    deposit = await db.crypto_deposits.find_one(
        {"id": deposit_id, "user_id": user["id"]}, {"_id": 0},
    )
    if not deposit:
        raise HTTPException(status_code=404, detail="Deposit not found")
    if deposit.get("status") == "confirmed":
        return _public_deposit({**deposit, "sc_credited": 0})
    return _public_deposit(await _refresh_and_credit(deposit))


@router.get("/crypto/verify/{crypto_type}/{tx_hash}")
async def verify_transaction(crypto_type: str, tx_hash: str, user=Depends(get_current_user)):
    """Verify that a transaction pays this deployment's configured address."""
    crypto_type = crypto_type.lower()
    address = (await _wallet_deposit_addresses(user["id"])).get(crypto_type)
    if not address:
        raise HTTPException(status_code=400, detail="Unsupported or unconfigured cryptocurrency")
    return await verify_tx_on_blockchain(crypto_type, tx_hash, address)
