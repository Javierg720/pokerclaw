"""Admin-only endpoints secured by the X-Admin-Secret request header.

These let a privileged operator manually set age_verified /
jurisdiction_allowed on a user's sweepstakes profile so that SC play
can be enabled for verified accounts.

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

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel

from deps import db

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


# ── Endpoints ────────────────────────────────────────────────────────────────

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

    if req.age_verified is None and req.jurisdiction_allowed is None:
        raise HTTPException(status_code=400, detail="Provide at least one field to update")

    update_set: dict = {"updated_at": datetime.now(timezone.utc).isoformat()}
    if req.age_verified is not None:
        update_set["age_verified"] = req.age_verified
    if req.jurisdiction_allowed is not None:
        update_set["jurisdiction_allowed"] = req.jurisdiction_allowed

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
            "self_excluded_until": (profile or {}).get("self_excluded_until"),
        })

    total = await db.users.count_documents({"role": "human"})
    return {"total": total, "skip": skip, "limit": limit, "users": result}
