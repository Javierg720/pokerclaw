"""Sweepstakes configuration and eligibility checks.

Real-money-adjacent features are deliberately fail-closed. Enabling a flag does
not replace legal review, geolocation, identity verification, or an approved
payment/payout provider.
"""
import os
from datetime import datetime, timezone

from fastapi import HTTPException

from deps import db


def _flag(name: str, default: bool = False) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _nonnegative_int(name: str, default: int) -> int:
    try:
        return max(0, int(os.environ.get(name, str(default))))
    except (TypeError, ValueError):
        return 0


def public_config() -> dict:
    daily_sc_amount = _nonnegative_int("DAILY_FREE_SC", 1)
    free_entry_enabled = _flag("SWEEPSTAKES_NO_PURCHASE_ENTRY_ENABLED", True)
    sc_play_requested = _flag("SWEEPSTAKES_PLAY_ENABLED")
    # Release gate: wager accounting and jurisdiction verification still need
    # live/adversarial certification. Operator flags must never bypass this.
    sc_play_enabled = False
    sc_play_blocked_reason = (
        "SC play is unavailable in this GC-only release pending verified "
        "eligibility, accounting, and legal approval. Environment flags cannot enable it."
    )
    redemption_requested = _flag("SWEEPSTAKES_REDEMPTION_ENABLED")
    redemption_enabled = False
    return {
        "model": "purchased_gc_with_promotional_sc",
        "no_purchase_necessary": True,
        "gc_redeemable": False,
        "sc_play_enabled": sc_play_enabled,
        "sc_play_requested": sc_play_requested,
        "sc_play_blocked_reason": sc_play_blocked_reason,
        "funding_enabled": False,
        "redemption_enabled": redemption_enabled,
        "redemption_requested": redemption_requested,
        "redemption_blocked_reason": None if redemption_enabled else (
            "Crypto redemption is unavailable in this GC-only release."
        ),
        "minimum_redemption_sc": max(1, _nonnegative_int("CRYPTO_REDEMPTION_MIN_SC", 2500)),
        "daily_gc_amount": _nonnegative_int("DAILY_FREE_GC", 1000),
        "daily_sc_amount": daily_sc_amount,
        "minimum_age": max(18, _nonnegative_int("SWEEPSTAKES_MINIMUM_AGE", 21)),
        "free_entry_enabled": free_entry_enabled,
    }


def _active_self_exclusion(profile: dict | None) -> bool:
    if not profile or not profile.get("self_excluded_until"):
        return False
    if profile["self_excluded_until"] == "permanent":
        return True
    try:
        until = datetime.fromisoformat(profile["self_excluded_until"])
        if until.tzinfo is None:
            until = until.replace(tzinfo=timezone.utc)
        return until > datetime.now(timezone.utc)
    except (TypeError, ValueError):
        return True


def longest_self_exclusion(current: str | None, requested: str) -> str:
    if current == "permanent" or requested == "permanent":
        return "permanent"
    if current and current >= requested:
        return current
    return requested


def eligibility_from_profile(profile: dict | None) -> dict:
    profile = profile or {}
    reasons = []
    if not profile.get("age_verified"):
        reasons.append("age_verification_required")
    if not profile.get("jurisdiction_allowed"):
        reasons.append("allowed_jurisdiction_required")
    if _active_self_exclusion(profile):
        reasons.append("self_excluded")
    return {
        "eligible": not reasons,
        "reasons": reasons,
        "age_verified": bool(profile.get("age_verified")),
        "jurisdiction_allowed": bool(profile.get("jurisdiction_allowed")),
        "identity_verified": bool(profile.get("identity_verified")),
        "self_excluded": _active_self_exclusion(profile),
    }


async def get_eligibility(user_id: str) -> dict:
    profile = await db.sweepstakes_profiles.find_one(
        {"user_id": user_id}, {"_id": 0}
    )
    return eligibility_from_profile(profile)


async def quarantine_legacy_human_sc() -> None:
    """Move pre-sweepstakes human SC out of the playable balance exactly once."""
    humans = await db.users.find({"role": "human"}, {"_id": 0, "id": 1}).to_list(None)
    for human in humans:
        wallet = await db.wallets.find_one({"user_id": human["id"]}, {"_id": 0})
        if not wallet or wallet.get("sc_provenance_migrated"):
            continue
        legacy_amount = wallet.get("sc_balance", 0)
        result = await db.wallets.update_one(
            {
                "user_id": human["id"],
                "sc_provenance_migrated": {"$ne": True},
                "sc_balance": legacy_amount,
            },
            {
                "$inc": {"sc_balance": -legacy_amount, "legacy_sc_balance": legacy_amount},
                "$set": {"sc_provenance_migrated": True},
            },
        )
        if result.modified_count != 1:
            raise RuntimeError(f"Could not quarantine legacy SC for human wallet {human['id']}")


async def ensure_sc_play_eligible(user: dict) -> None:
    config = public_config()
    if not config["sc_play_enabled"]:
        raise HTTPException(
            status_code=403,
            detail="Sweepstakes Coin play is not enabled for this deployment.",
        )
    eligibility = await get_eligibility(user["id"])
    if not eligibility["eligible"]:
        raise HTTPException(
            status_code=403,
            detail={
                "message": "Sweepstakes eligibility requirements are not satisfied.",
                "reasons": eligibility["reasons"],
            },
        )


async def ensure_redemption_eligible(user: dict) -> None:
    config = public_config()
    if not config["redemption_enabled"]:
        raise HTTPException(status_code=410, detail="Crypto redemption is not enabled for this deployment.")
    await ensure_sc_play_eligible(user)
    profile = await db.sweepstakes_profiles.find_one(
        {"user_id": user["id"]}, {"_id": 0, "identity_verified": 1}
    )
    if not (profile or {}).get("identity_verified"):
        raise HTTPException(status_code=403, detail="Identity verification is required before redemption.")
    eligibility = await get_eligibility(user["id"])
    if not eligibility["eligible"]:
        raise HTTPException(
            status_code=403,
            detail={
                "message": "Sweepstakes eligibility requirements are not satisfied.",
                "reasons": eligibility["reasons"],
            },
        )
