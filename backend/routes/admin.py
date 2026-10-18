"""Admin-only endpoints secured by the X-Admin-Secret request header.

These let a privileged operator set age, jurisdiction, and identity checks on
a user's sweepstakes profile and review crypto redemption requests.

In a full production deployment the PUT endpoint would be called by your
KYC/AML provider's webhook instead of a human operator.  The GET endpoint
is for support tooling.

Usage
-----
All requests must include the header:

    X-Admin-Secret: <value of ADMIN_SECRET env var>

Set ADMIN_SECRET in backend/.env (generate with
  python -c "import secrets; print(secrets.token_hex(32))"
).  If ADMIN_SECRET is not configured the endpoints return 503.
"""
import os
import uuid
from datetime import datetime, timezone
from decimal import Decimal

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field
from pymongo.errors import DuplicateKeyError, OperationFailure

from deps import client, db, logger
from routes.crypto import confirmation_requirements, verify_tx_on_blockchain

router = APIRouter(prefix="/api/admin")


# ── Auth guard ──────────────────────────────────────────────────────────────

def _check_admin_secret(x_admin_secret: str = Header(default="")) -> None:
    secret = os.environ.get("ADMIN_SECRET", "").strip()
    if not secret:
        raise HTTPException(
            status_code=503,
            detail=(
                "Admin API is not configured. "
                "Set ADMIN_SECRET in backend/.env and restart the server."
            ),
        )
    if x_admin_secret != secret:
        raise HTTPException(status_code=403, detail="Invalid admin secret")


# ── Request / response models ────────────────────────────────────────────────

class EligibilityUpdate(BaseModel):
    age_verified: bool | None = None
    jurisdiction_allowed: bool | None = None
    identity_verified: bool | None = None


class CryptoAddressUpdate(BaseModel):
    btc: str | None = Field(default=None, min_length=20, max_length=128)
    ltc: str | None = Field(default=None, min_length=20, max_length=128)
    eth: str | None = Field(default=None, pattern=r"^0x[0-9a-fA-F]{40}$")


class RedemptionCompletion(BaseModel):
    payout_tx_hash: str = Field(min_length=16, max_length=128)


class RedemptionRejection(BaseModel):
    reason: str = Field(min_length=3, max_length=300)


# ── Endpoints ────────────────────────────────────────────────────────────────

@router.put(
    "/crypto-addresses/{user_id}",
    summary="Assign unique operator-controlled deposit addresses to a wallet",
)
async def set_crypto_addresses(
    user_id: str,
    req: CryptoAddressUpdate,
    x_admin_secret: str = Header(default=""),
):
    _check_admin_secret(x_admin_secret)
    if req.btc is None and req.ltc is None and req.eth is None:
        raise HTTPException(status_code=400, detail="Provide at least one deposit address")
    user = await db.users.find_one({"id": user_id}, {"_id": 0})
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    addresses = {
        coin: value.strip()
        for coin, value in req.model_dump(exclude_none=True).items()
    }
    wallet = await db.wallets.find_one({"user_id": user_id}, {"_id": 0})
    if not wallet:
        raise HTTPException(status_code=404, detail="Wallet not found")
    current_addresses = wallet.get("crypto_addresses") or {}
    merged_addresses = {**current_addresses, **addresses}
    try:
        result = await db.wallets.update_one(
            {"user_id": user_id, "crypto_addresses": wallet.get("crypto_addresses")},
            {"$set": {"crypto_addresses": merged_addresses}},
        )
    except DuplicateKeyError as error:
        raise HTTPException(status_code=409, detail="A deposit address is already assigned to another wallet") from error
    if result.modified_count != 1:
        latest = await db.wallets.find_one({"user_id": user_id}, {"_id": 0})
        if latest and latest.get("crypto_addresses") == merged_addresses:
            return {"user_id": user_id, "crypto_addresses": merged_addresses}
        raise HTTPException(status_code=409, detail="Wallet address assignment changed; retry")
    wallet = await db.wallets.find_one({"user_id": user_id}, {"_id": 0, "crypto_addresses": 1})
    return {"user_id": user_id, "crypto_addresses": wallet.get("crypto_addresses", {})}


@router.put(
    "/eligibility/{user_id}",
    summary="Set age_verified / jurisdiction_allowed for a human user",
)
async def set_user_eligibility(
    user_id: str,
    req: EligibilityUpdate,
    x_admin_secret: str = Header(default=""),
):
    _check_admin_secret(x_admin_secret)

    user = await db.users.find_one({"id": user_id}, {"_id": 0})
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if user.get("role") != "human":
        raise HTTPException(
            status_code=400, detail="Eligibility flags only apply to human accounts"
        )

    if req.age_verified is None and req.jurisdiction_allowed is None and req.identity_verified is None:
        raise HTTPException(status_code=400, detail="Provide at least one field to update")

    update_set: dict = {"updated_at": datetime.now(timezone.utc).isoformat()}
    if req.age_verified is not None:
        update_set["age_verified"] = req.age_verified
    if req.jurisdiction_allowed is not None:
        update_set["jurisdiction_allowed"] = req.jurisdiction_allowed
    if req.identity_verified is not None:
        update_set["identity_verified"] = req.identity_verified

    now_iso = datetime.now(timezone.utc).isoformat()
    await db.sweepstakes_profiles.update_one(
        {"user_id": user_id},
        {
            "$set": update_set,
            "$setOnInsert": {
                "id": str(uuid.uuid4()),
                "user_id": user_id,
                "created_at": now_iso,
            },
        },
        upsert=True,
    )

    profile = await db.sweepstakes_profiles.find_one({"user_id": user_id}, {"_id": 0})
    return {
        "user_id": user_id,
        "username": user.get("username"),
        "age_verified": (profile or {}).get("age_verified", False),
        "jurisdiction_allowed": (profile or {}).get("jurisdiction_allowed", False),
        "identity_verified": (profile or {}).get("identity_verified", False),
        "self_excluded_until": (profile or {}).get("self_excluded_until"),
        "updated_at": (profile or {}).get("updated_at"),
    }


@router.get(
    "/eligibility/{user_id}",
    summary="Get current sweepstakes eligibility for a user",
)
async def get_user_eligibility(
    user_id: str,
    x_admin_secret: str = Header(default=""),
):
    _check_admin_secret(x_admin_secret)

    user = await db.users.find_one({"id": user_id}, {"_id": 0})
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    profile = await db.sweepstakes_profiles.find_one({"user_id": user_id}, {"_id": 0})
    return {
        "user_id": user_id,
        "username": user.get("username"),
        "email": user.get("email"),
        "role": user.get("role"),
        "age_verified": (profile or {}).get("age_verified", False),
        "jurisdiction_allowed": (profile or {}).get("jurisdiction_allowed", False),
        "identity_verified": (profile or {}).get("identity_verified", False),
        "self_excluded_until": (profile or {}).get("self_excluded_until"),
    }


@router.get(
    "/users",
    summary="List all human users with eligibility status (paginated)",
)
async def list_users(
    skip: int = 0,
    limit: int = 50,
    x_admin_secret: str = Header(default=""),
):
    _check_admin_secret(x_admin_secret)

    limit = min(limit, 200)
    users = (
        await db.users.find({"role": "human"}, {"_id": 0, "password_hash": 0, "password_reset_token": 0})
        .skip(skip)
        .limit(limit)
        .to_list(limit)
    )

    result = []
    for u in users:
        profile = await db.sweepstakes_profiles.find_one({"user_id": u["id"]}, {"_id": 0})
        result.append({
            "user_id": u["id"],
            "username": u.get("username"),
            "email": u.get("email"),
            "created_at": u.get("created_at"),
            "age_verified": (profile or {}).get("age_verified", False),
            "jurisdiction_allowed": (profile or {}).get("jurisdiction_allowed", False),
            "identity_verified": (profile or {}).get("identity_verified", False),
            "self_excluded_until": (profile or {}).get("self_excluded_until"),
        })

    total = await db.users.count_documents({"role": "human"})
    return {"total": total, "skip": skip, "limit": limit, "users": result}


@router.get("/redemptions", summary="List crypto redemption requests")
async def list_redemptions(
    status: str | None = None,
    skip: int = 0,
    limit: int = 50,
    x_admin_secret: str = Header(default=""),
):
    _check_admin_secret(x_admin_secret)
    query = {"status": status} if status else {}
    limit = min(limit, 200)
    redemptions = await db.crypto_redemptions.find(query, {"_id": 0}).sort(
        "created_at", -1
    ).skip(skip).limit(limit).to_list(limit)
    total = await db.crypto_redemptions.count_documents(query)
    return {"total": total, "skip": skip, "limit": limit, "redemptions": redemptions}


@router.post("/redemptions/{redemption_id}/complete", summary="Verify and complete an on-chain payout")
async def complete_redemption(
    redemption_id: str,
    req: RedemptionCompletion,
    x_admin_secret: str = Header(default=""),
):
    _check_admin_secret(x_admin_secret)
    redemption = await db.crypto_redemptions.find_one({"id": redemption_id}, {"_id": 0})
    if not redemption:
        raise HTTPException(status_code=404, detail="Redemption not found")
    if redemption.get("status") == "paid":
        if redemption.get("payout_tx_hash") != req.payout_tx_hash.strip().lower():
            raise HTTPException(status_code=409, detail="Redemption was already completed with another transaction.")
        return redemption
    if redemption.get("status") != "review_pending":
        raise HTTPException(status_code=409, detail="Only pending redemptions can be completed.")

    tx_hash = req.payout_tx_hash.strip().lower()
    verification = await verify_tx_on_blockchain(
        redemption["crypto_type"], tx_hash, redemption["payout_address"],
    )
    if not verification["verified"]:
        raise HTTPException(status_code=400, detail=verification["error"])
    if Decimal(verification["amount"]) < Decimal(redemption["payout_crypto_amount"]):
        raise HTTPException(status_code=409, detail="The payout transaction sends less than the locked redemption amount.")
    required = confirmation_requirements()[redemption["crypto_type"]]
    if int(verification["confirmations"]) < required:
        raise HTTPException(
            status_code=409,
            detail=f"Payout has {verification['confirmations']}/{required} required confirmations.",
        )

    now = datetime.now(timezone.utc).isoformat()
    try:
        result = await db.crypto_redemptions.update_one(
            {"id": redemption_id, "status": "review_pending"},
            {"$set": {
                "status": "paid",
                "payout_tx_hash": tx_hash,
                "payout_confirmations": int(verification["confirmations"]),
                "paid_at": now,
            }},
        )
    except DuplicateKeyError as error:
        raise HTTPException(status_code=409, detail="That payout transaction is already assigned to another redemption.") from error
    if result.modified_count != 1:
        latest = await db.crypto_redemptions.find_one({"id": redemption_id}, {"_id": 0})
        if latest and latest.get("status") == "paid" and latest.get("payout_tx_hash") == tx_hash:
            return latest
        raise HTTPException(status_code=409, detail="Redemption status changed; reload before retrying.")
    return await db.crypto_redemptions.find_one({"id": redemption_id}, {"_id": 0})


@router.post("/redemptions/{redemption_id}/reject", summary="Reject and atomically refund an SC redemption")
async def reject_redemption(
    redemption_id: str,
    req: RedemptionRejection,
    x_admin_secret: str = Header(default=""),
):
    _check_admin_secret(x_admin_secret)
    now = datetime.now(timezone.utc).isoformat()

    async def commit_rejection(session):
        redemption = await db.crypto_redemptions.find_one({"id": redemption_id}, {"_id": 0}, session=session)
        if not redemption:
            raise HTTPException(status_code=404, detail="Redemption not found")
        if redemption.get("status") == "rejected":
            return redemption
        if redemption.get("status") != "review_pending":
            raise HTTPException(status_code=409, detail="Only pending redemptions can be rejected.")
        result = await db.crypto_redemptions.update_one(
            {"id": redemption_id, "status": "review_pending"},
            {"$set": {"status": "rejected", "rejection_reason": req.reason.strip(), "rejected_at": now}},
            session=session,
        )
        if result.modified_count != 1:
            raise HTTPException(status_code=409, detail="Redemption status changed; reload before retrying.")
        wallet_result = await db.wallets.update_one(
            {"user_id": redemption["user_id"]},
            {"$inc": {"sc_balance": redemption["sc_amount"]}},
            session=session,
        )
        if wallet_result.modified_count != 1:
            raise RuntimeError("Redemption wallet not found")
        await db.transactions.insert_one(
            {
                "id": f"redemption-refund:{redemption_id}",
                "user_id": redemption["user_id"],
                "type": "crypto_redemption_refund",
                "amount": redemption["sc_amount"],
                "currency": "sc",
                "description": f"Refunded rejected {redemption['crypto_type'].upper()} redemption",
                "created_at": now,
            },
            session=session,
        )
        return {**redemption, "status": "rejected", "rejection_reason": req.reason.strip(), "rejected_at": now}

    try:
        async with await client.start_session() as session:
            return await session.with_transaction(commit_rejection)
    except OperationFailure as error:
        logger.warning("Redemption rejection transaction failed safely: %s", error)
        raise HTTPException(status_code=503, detail="Redemption rejection could not be committed atomically.") from error
