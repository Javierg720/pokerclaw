from datetime import datetime, timedelta, timezone
import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from pymongo.errors import DuplicateKeyError

from deps import db, require_human
from sweepstakes import get_eligibility, longest_self_exclusion, public_config

router = APIRouter(prefix="/api")


class SelfExcludeRequest(BaseModel):
    days: int | None = Field(default=None, ge=1, le=3650)


async def _upsert_daily_claim_ledger(user_id: str, claim: dict) -> None:
    for currency, amount, description in (
        ("gc", claim["gc_amount"], "Daily free Gold Coins"),
        ("sc", claim["sc_amount"], "Daily free promotional Sweepstakes Coins"),
    ):
        if not amount:
            continue
        transaction_id = f"daily-claim:{user_id}:{claim['date']}:{currency}"
        transaction = {
            "id": transaction_id,
            "user_id": user_id,
            "type": "daily_free_claim",
            "amount": amount,
            "currency": currency,
            "description": description,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        try:
            await db.transactions.update_one(
                {"id": transaction_id}, {"$setOnInsert": transaction}, upsert=True,
            )
        except DuplicateKeyError:
            existing = await db.transactions.find_one({"id": transaction_id}, {"_id": 0})
            if not existing or any(
                existing.get(key) != transaction[key]
                for key in ("user_id", "type", "amount", "currency", "description")
            ):
                raise


@router.get("/sweepstakes/config")
async def get_sweepstakes_config():
    return public_config()


@router.get("/sweepstakes/status")
async def get_sweepstakes_status(user=Depends(require_human)):
    return {
        "config": public_config(),
        "eligibility": await get_eligibility(user["id"]),
    }


@router.post("/sweepstakes/daily-claim")
async def claim_daily_coins(user=Depends(require_human)):
    """Grant the daily free entry path without any purchase."""
    config = public_config()
    eligibility = await get_eligibility(user["id"])
    today = datetime.now(timezone.utc).date().isoformat()
    sc_amount = (
        config["daily_sc_amount"]
        if config["sc_play_enabled"] and eligibility["eligible"]
        else 0
    )
    claim = {
        "date": today,
        "gc_amount": config["daily_gc_amount"],
        "sc_amount": sc_amount,
    }
    increments = {"gc_balance": claim["gc_amount"]}
    if sc_amount:
        increments["sc_balance"] = sc_amount

    result = await db.wallets.update_one(
        {
            "user_id": user["id"],
            "last_daily_claim_date": {"$ne": today},
        },
        {
            "$inc": increments,
            "$set": {
                "last_daily_claim_date": today,
                "daily_claim_award": claim,
            },
        },
    )
    if result.modified_count == 1:
        await _upsert_daily_claim_ledger(user["id"], claim)
    else:
        wallet = await db.wallets.find_one({"user_id": user["id"]}, {"_id": 0})
        stored_claim = (wallet or {}).get("daily_claim_award")
        if stored_claim and stored_claim.get("date") == today:
            await _upsert_daily_claim_ledger(user["id"], stored_claim)
        raise HTTPException(status_code=409, detail="Daily free coins already claimed.")

    return {
        "gc_credited": claim["gc_amount"],
        "sc_credited": claim["sc_amount"],
        "claim_date": today,
        "sc_withheld_reasons": [] if sc_amount else eligibility["reasons"],
    }


@router.post("/sweepstakes/self-exclude")
async def self_exclude(req: SelfExcludeRequest, user=Depends(require_human)):
    now = datetime.now(timezone.utc)
    requested = "permanent" if req.days is None else (now + timedelta(days=req.days)).isoformat()
    for _ in range(3):
        profile = await db.sweepstakes_profiles.find_one({"user_id": user["id"]}, {"_id": 0})
        current = (profile or {}).get("self_excluded_until")
        until = longest_self_exclusion(current, requested)
        if until == current:
            return {"self_excluded": True, "self_excluded_until": until}
        query = {"user_id": user["id"]}
        query["self_excluded_until"] = current or {"$exists": False}
        try:
            result = await db.sweepstakes_profiles.update_one(
                query,
                {
                    "$set": {
                        "self_excluded_until": until,
                        "self_excluded_at": now.isoformat(),
                        "updated_at": now.isoformat(),
                    },
                    "$inc": {"eligibility_version": 1},
                    "$setOnInsert": {
                        "id": str(uuid.uuid4()), "user_id": user["id"],
                        "age_verified": False, "jurisdiction_allowed": False,
                        "created_at": now.isoformat(),
                    },
                },
                upsert=profile is None,
            )
        except DuplicateKeyError:
            continue
        if result.modified_count == 1:
            return {"self_excluded": True, "self_excluded_until": until}
    raise HTTPException(status_code=409, detail="Self-exclusion update conflicted; retry the request.")
