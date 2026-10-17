from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
import httpx
import time
import logging
from deps import db, get_current_user
from typing import Dict

router = APIRouter(prefix="/api")
logger = logging.getLogger(__name__)

CRYPTO_COIN_IDS = {"btc": "bitcoin", "ltc": "litecoin", "eth": "ethereum"}
_price_cache: Dict[str, dict] = {}
_price_cache_time: float = 0
PRICE_CACHE_TTL = 60

# Blockchain explorer APIs for real tx verification
BLOCKCHAIN_APIS = {
    "btc": "https://blockstream.info/api/tx/{tx_hash}",
    "eth": "https://api.blockchair.com/ethereum/dashboards/transaction/{tx_hash}",
    "ltc": "https://api.blockcypher.com/v1/ltc/main/txs/{tx_hash}",
}


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


async def verify_tx_on_blockchain(crypto_type: str, tx_hash: str) -> dict:
    """
    Query real blockchain APIs to verify a transaction hash.
    Returns: {verified: bool, confirmations: int, amount: float, error: str}
    """
    api_url = BLOCKCHAIN_APIS.get(crypto_type)
    if not api_url:
        return {"verified": False, "confirmations": 0, "amount": 0, "error": "Unsupported crypto"}

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(api_url.format(tx_hash=tx_hash))

            if resp.status_code == 404:
                return {
                    "verified": False, "confirmations": 0, "amount": 0,
                    "error": "Transaction not found on blockchain",
                }

            if resp.status_code != 200:
                return {
                    "verified": False, "confirmations": 0, "amount": 0,
                    "error": f"Blockchain API returned {resp.status_code}",
                }

            data = resp.json()

            if crypto_type == "btc":
                # Blockstream API
                status = data.get("status", {})
                confirmed = status.get("confirmed", False)
                block_height = status.get("block_height", 0)
                if confirmed and block_height:
                    # Get current block height for confirmation count
                    tip_resp = await client.get("https://blockstream.info/api/blocks/tip/height")
                    tip_height = int(tip_resp.text) if tip_resp.status_code == 200 else block_height
                    confirmations = max(0, tip_height - block_height + 1)
                else:
                    confirmations = 0
                # Sum outputs in BTC
                total_out = sum(o.get("value", 0) for o in data.get("vout", [])) / 1e8
                return {"verified": True, "confirmations": confirmations, "amount": total_out, "error": None}

            elif crypto_type == "eth":
                # Blockchair API
                tx_data = data.get("data", {}).get(tx_hash.lower(), {}).get("transaction", {})
                if not tx_data:
                    tx_data = data.get("data", {}).get(tx_hash, {}).get("transaction", {})
                if not tx_data:
                    return {"verified": False, "confirmations": 0, "amount": 0, "error": "TX data not found"}
                block_id = tx_data.get("block_id", 0)
                if block_id and block_id > 0:
                    # Get latest block
                    stats_resp = await client.get("https://api.blockchair.com/ethereum/stats")
                    if stats_resp.status_code == 200:
                        best_block = stats_resp.json().get("data", {}).get("best_block_height", block_id)
                        confirmations = max(0, best_block - block_id + 1)
                    else:
                        confirmations = 1
                else:
                    confirmations = 0
                # Value in ETH (from wei)
                value_wei = tx_data.get("value", 0)
                amount = float(value_wei) / 1e18 if value_wei else 0
                return {"verified": True, "confirmations": confirmations, "amount": amount, "error": None}

            elif crypto_type == "ltc":
                # BlockCypher API
                confirmations = data.get("confirmations", 0)
                total_out = data.get("total", 0) / 1e8  # satoshis to LTC
                return {"verified": True, "confirmations": confirmations, "amount": total_out, "error": None}

    except httpx.TimeoutException:
        return {"verified": False, "confirmations": 0, "amount": 0, "error": "Blockchain API timeout"}
    except Exception as e:
        logger.error(f"Blockchain verification error for {crypto_type}/{tx_hash}: {e}")
        return {"verified": False, "confirmations": 0, "amount": 0, "error": str(e)}


@router.get("/crypto/prices")
async def crypto_prices():
    prices = await get_crypto_prices()
    return {"prices": prices, "rate": "100 SC per $1 USD"}


@router.post("/crypto/deposit")
async def submit_crypto_deposit(req: CryptoDepositRequest, user=Depends(get_current_user)):
    raise HTTPException(
        status_code=410,
        detail="Crypto deposits are disabled until custody-address verification is configured. Use Stripe checkout.",
    )


@router.get("/crypto/deposits")
async def get_crypto_deposits(user=Depends(get_current_user)):
    deposits = await db.crypto_deposits.find(
        {"user_id": user['id']}, {"_id": 0}
    ).sort("created_at", -1).to_list(50)
    return deposits


@router.post("/crypto/deposits/{deposit_id}/confirm")
async def simulate_confirm_deposit(deposit_id: str, user=Depends(get_current_user)):
    """Manual re-check of a deposit's blockchain status."""
    raise HTTPException(
        status_code=410,
        detail="Crypto deposit confirmation is disabled until custody-address verification is configured.",
    )


@router.get("/crypto/verify/{crypto_type}/{tx_hash}")
async def verify_transaction(crypto_type: str, tx_hash: str):
    """Public endpoint to verify any transaction on the blockchain."""
    if crypto_type not in CRYPTO_COIN_IDS:
        raise HTTPException(status_code=400, detail="Unsupported crypto")
    result = await verify_tx_on_blockchain(crypto_type, tx_hash)
    return result
