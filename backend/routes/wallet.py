from datetime import datetime, timezone
from decimal import Decimal, ROUND_DOWN
import os
import re
import uuid

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field
from pymongo.errors import DuplicateKeyError, OperationFailure

from deps import client, db, get_current_user, logger, require_human
from routes.crypto import CRYPTO_COIN_IDS, get_crypto_prices
from sweepstakes import ensure_redemption_eligible, public_config

router = APIRouter(prefix="/api")


class PurchaseRequest(BaseModel):
    amount: int
    currency: str = "sc"


class CashoutRequest(BaseModel):
    amount: int = Field(gt=0)
    crypto_type: str = ""
    payout_address: str = Field(default="", max_length=128)


_ADDRESS_PATTERNS = {
    "btc": re.compile(r"^(bc1[a-zA-HJ-NP-Z0-9]{25,87}|[13][a-km-zA-HJ-NP-Z1-9]{25,34})$"),
    "ltc": re.compile(r"^(ltc1[a-zA-HJ-NP-Z0-9]{25,87}|[LM3][a-km-zA-HJ-NP-Z1-9]{25,34})$"),
    "eth": re.compile(r"^0x[0-9a-fA-F]{40}$"),
}
_CHAIN_DECIMALS = {"btc": 8, "ltc": 8, "eth": 18}


def validate_payout_address(crypto_type: str, address: str) -> str:
    normalized = address.strip()
    pattern = _ADDRESS_PATTERNS.get(crypto_type)
    if not pattern or not pattern.fullmatch(normalized):
        raise HTTPException(
            status_code=400,
            detail=f"Enter a valid native {crypto_type.upper()} receiving address and confirm the Coinbase network matches.",
        )
    return normalized


def redemption_quote(
    sc_amount: int,
    sc_per_usd: Decimal,
    crypto_usd: Decimal,
    crypto_type: str,
) -> tuple[Decimal, Decimal]:
    usd_value = Decimal(sc_amount) / sc_per_usd
    quantum = Decimal(1).scaleb(-_CHAIN_DECIMALS[crypto_type])
    crypto_amount = (usd_value / crypto_usd).quantize(quantum, rounding=ROUND_DOWN)
    if crypto_amount <= 0:
        raise HTTPException(status_code=400, detail="Redemption is below the minimum payable amount for that asset.")
    return usd_value, crypto_amount


def _public_redemption(redemption: dict) -> dict:
    return {
        key: value for key, value in redemption.items()
        if key not in {"_id", "user_id", "idempotency_key"}
    }


@router.get("/wallet")
async def get_wallet(user=Depends(get_current_user)):
    wallet = await db.wallets.find_one({"user_id": user['id']}, {"_id": 0})
    if not wallet:
        raise HTTPException(status_code=404, detail="Wallet not found")
    return wallet


@router.post("/wallet/purchase")
async def purchase_coins(req: PurchaseRequest, user=Depends(get_current_user)):
    raise HTTPException(
        status_code=410,
        detail=(
            "Direct balance purchases are disabled. Production funding requires "
            "an approved sweepstakes provider and purchased-GC/promotional-SC packaging."
        ),
    )


@router.post("/wallet/cashout")
async def cashout(
    req: CashoutRequest,
    idempotency_key: str = Header(default="", alias="Idempotency-Key"),
    user=Depends(require_human),
):
    await ensure_redemption_eligible(user)
    key = idempotency_key.strip()
    if not key or len(key) > 128:
        raise HTTPException(status_code=400, detail="A valid Idempotency-Key header is required.")

    crypto_type = req.crypto_type.strip().lower()
    if crypto_type not in CRYPTO_COIN_IDS:
        raise HTTPException(status_code=400, detail="Choose BTC, LTC, or ETH for redemption.")
    address = validate_payout_address(crypto_type, req.payout_address)
    config = public_config()
    minimum = max(1, int(config["minimum_redemption_sc"]))
    if req.amount < minimum:
        raise HTTPException(status_code=400, detail=f"Minimum redemption is {minimum:,} SC.")

    prices = await get_crypto_prices()
    if crypto_type not in prices:
        raise HTTPException(status_code=503, detail="A verified market quote is unavailable for that asset.")
    try:
        sc_per_usd = Decimal(os.environ.get("SC_PER_USD", "100"))
    except Exception as error:
        raise HTTPException(status_code=503, detail="SC redemption rate is not configured.") from error
    if sc_per_usd <= 0:
        raise HTTPException(status_code=503, detail="SC redemption rate is not configured.")
    crypto_usd = Decimal(str(prices[crypto_type]["usd"]))
    usd_value, crypto_amount = redemption_quote(req.amount, sc_per_usd, crypto_usd, crypto_type)
    redemption_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"redemption:{user['id']}:{key}"))
    now = datetime.now(timezone.utc).isoformat()

    redemption = {
        "id": redemption_id,
        "user_id": user["id"],
        "idempotency_key": key,
        "sc_amount": req.amount,
        "sc_per_usd": format(sc_per_usd, "f"),
        "usd_value": format(usd_value, ".2f"),
        "crypto_type": crypto_type,
        "quote_price_usd": format(crypto_usd, "f"),
        "payout_crypto_amount": format(crypto_amount, "f"),
        "payout_address": address,
        "status": "review_pending",
        "created_at": now,
    }

    async def commit_redemption(session):
        existing = await db.crypto_redemptions.find_one({"id": redemption_id}, {"_id": 0}, session=session)
        if existing:
            if any(existing.get(field) != redemption[field] for field in ("sc_amount", "crypto_type", "payout_address")):
                raise HTTPException(status_code=409, detail="Idempotency-Key was reused with different redemption details.")
            return existing

        wallet_result = await db.wallets.update_one(
            {"user_id": user["id"], "sc_balance": {"$gte": req.amount}},
            {"$inc": {"sc_balance": -req.amount}},
            session=session,
        )
        if wallet_result.modified_count != 1:
            raise HTTPException(status_code=409, detail="Insufficient available SC balance.")
        await db.crypto_redemptions.insert_one(redemption, session=session)
        await db.transactions.insert_one(
            {
                "id": f"redemption-hold:{redemption_id}",
                "user_id": user["id"],
                "type": "crypto_redemption_hold",
                "amount": -req.amount,
                "currency": "sc",
                "description": f"SC reserved for {crypto_type.upper()} redemption",
                "created_at": now,
            },
            session=session,
        )
        return redemption

    try:
        async with await client.start_session() as session:
            committed = await session.with_transaction(commit_redemption)
    except DuplicateKeyError:
        committed = await db.crypto_redemptions.find_one(
            {"user_id": user["id"], "idempotency_key": key}, {"_id": 0},
        )
        if not committed or any(
            committed.get(field) != redemption[field]
            for field in ("sc_amount", "crypto_type", "payout_address")
        ):
            raise HTTPException(status_code=409, detail="Idempotency-Key was reused with different redemption details.")
    except OperationFailure as error:
        logger.warning("Crypto redemption transaction failed safely: %s", error)
        raise HTTPException(
            status_code=503,
            detail="Redemption could not be reserved atomically. Retry with the same Idempotency-Key.",
        ) from error
    return _public_redemption(committed)


@router.get("/wallet/redemptions")
async def get_redemptions(user=Depends(require_human)):
    redemptions = await db.crypto_redemptions.find(
        {"user_id": user["id"]}, {"_id": 0, "user_id": 0, "idempotency_key": 0}
    ).sort("created_at", -1).to_list(50)
    return redemptions


@router.get("/wallet/transactions")
async def get_transactions(user=Depends(get_current_user)):
    txns = await db.transactions.find(
        {"user_id": user['id']}, {"_id": 0}
    ).sort("created_at", -1).to_list(100)
    return txns
