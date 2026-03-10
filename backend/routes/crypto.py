from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
import os
import uuid
import httpx
import time
import logging
from datetime import datetime, timezone
from deps import db, get_current_user
from typing import Dict

router = APIRouter(prefix="/api")
logger = logging.getLogger(__name__)

CRYPTO_COIN_IDS = {"btc": "bitcoin", "ltc": "litecoin", "eth": "ethereum"}
_price_cache: Dict[str, dict] = {}
_price_cache_time: float = 0
PRICE_CACHE_TTL = 60


class CryptoDepositRequest(BaseModel):
    crypto_type: str
    tx_hash: str
    amount_crypto: float


async def get_crypto_prices():
    global _price_cache, _price_cache_time
    now = time.time()
    if _price_cache and (now - _price_cache_time) < PRICE_CACHE_TTL:
        return _price_cache

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            ids = ",".join(CRYPTO_COIN_IDS.values())
            resp = await client.get(
                f"https://api.coingecko.com/api/v3/simple/price?ids={ids}&vs_currencies=usd&include_24hr_change=true"
            )
            if resp.status_code == 200:
                data = resp.json()
                prices = {}
                for short, coin_id in CRYPTO_COIN_IDS.items():
                    if coin_id in data:
                        prices[short] = {
                            "usd": data[coin_id].get("usd", 0),
                            "change_24h": data[coin_id].get("usd_24h_change", 0),
                        }
                _price_cache = prices
                _price_cache_time = now
                return prices
    except Exception as e:
        logger.warning(f"CoinGecko API error: {e}")

    if _price_cache:
        return _price_cache
    return {
        "btc": {"usd": 97000, "change_24h": 0},
        "ltc": {"usd": 130, "change_24h": 0},
        "eth": {"usd": 3500, "change_24h": 0},
    }


@router.get("/crypto/prices")
async def crypto_prices():
    prices = await get_crypto_prices()
    return {"prices": prices, "rate": "100 SC per $1 USD"}


@router.post("/crypto/deposit")
async def submit_crypto_deposit(req: CryptoDepositRequest, user=Depends(get_current_user)):
    if user.get('role') != 'agent':
        raise HTTPException(status_code=403, detail="Only agent accounts can deposit crypto")
    if req.crypto_type not in CRYPTO_COIN_IDS:
        raise HTTPException(status_code=400, detail="Unsupported crypto. Use btc, ltc, or eth")
    if req.amount_crypto <= 0:
        raise HTTPException(status_code=400, detail="Amount must be positive")

    existing = await db.crypto_deposits.find_one({"tx_hash": req.tx_hash}, {"_id": 0})
    if existing:
        raise HTTPException(status_code=400, detail="Transaction already submitted")

    prices = await get_crypto_prices()
    price_usd = prices.get(req.crypto_type, {}).get("usd", 0)
    if price_usd <= 0:
        raise HTTPException(status_code=500, detail="Unable to fetch crypto price")

    usd_value = req.amount_crypto * price_usd
    sc_amount = int(usd_value * 100)

    deposit = {
        "id": str(uuid.uuid4()), "user_id": user['id'],
        "crypto_type": req.crypto_type, "tx_hash": req.tx_hash,
        "amount_crypto": req.amount_crypto, "price_usd_at_submit": price_usd,
        "usd_value": round(usd_value, 2), "sc_amount": sc_amount,
        "confirmations": 0, "required_confirmations": 2, "status": "pending",
        "created_at": datetime.now(timezone.utc).isoformat(), "confirmed_at": None,
    }
    await db.crypto_deposits.insert_one(deposit)

    return {
        "deposit_id": deposit["id"], "crypto_type": req.crypto_type,
        "amount_crypto": req.amount_crypto, "price_usd": price_usd,
        "usd_value": round(usd_value, 2), "sc_amount": sc_amount,
        "status": "pending",
        "message": f"Deposit submitted. {sc_amount} SC will be credited after 2 confirmations."
    }


@router.get("/crypto/deposits")
async def get_crypto_deposits(user=Depends(get_current_user)):
    deposits = await db.crypto_deposits.find(
        {"user_id": user['id']}, {"_id": 0}
    ).sort("created_at", -1).to_list(50)
    return deposits


@router.post("/crypto/deposits/{deposit_id}/confirm")
async def simulate_confirm_deposit(deposit_id: str, user=Depends(get_current_user)):
    deposit = await db.crypto_deposits.find_one(
        {"id": deposit_id, "user_id": user['id']}, {"_id": 0}
    )
    if not deposit:
        raise HTTPException(status_code=404, detail="Deposit not found")
    if deposit["status"] == "confirmed":
        raise HTTPException(status_code=400, detail="Deposit already confirmed")

    new_confirmations = deposit["confirmations"] + 1
    update = {"confirmations": new_confirmations}

    if new_confirmations >= deposit["required_confirmations"]:
        update["status"] = "confirmed"
        update["confirmed_at"] = datetime.now(timezone.utc).isoformat()
        await db.wallets.update_one(
            {"user_id": user['id']},
            {"$inc": {"sc_balance": deposit["sc_amount"]}}
        )
        await db.transactions.insert_one({
            "id": str(uuid.uuid4()), "user_id": user['id'],
            "type": "crypto_deposit", "amount": deposit["sc_amount"], "currency": "sc",
            "description": f"Crypto deposit: {deposit['amount_crypto']} {deposit['crypto_type'].upper()} (${deposit['usd_value']}) = {deposit['sc_amount']} SC",
            "created_at": datetime.now(timezone.utc).isoformat()
        })

    await db.crypto_deposits.update_one({"id": deposit_id}, {"$set": update})

    return {
        "deposit_id": deposit_id, "confirmations": new_confirmations,
        "required": deposit["required_confirmations"],
        "status": update.get("status", "pending"),
        "sc_credited": deposit["sc_amount"] if update.get("status") == "confirmed" else 0,
    }
