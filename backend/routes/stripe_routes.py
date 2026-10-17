"""Disabled compatibility routes for clients from the pre-sweepstakes build."""
from fastapi import APIRouter, Depends, HTTPException

from deps import get_current_user

router = APIRouter(prefix="/api")


@router.get("/stripe/packages")
async def get_stripe_packages():
    return []


@router.post("/stripe/checkout")
async def disabled_stripe_checkout(user=Depends(get_current_user)):
    raise HTTPException(
        status_code=410,
        detail="Stripe checkout is disabled for this sweepstakes product.",
    )


@router.get("/stripe/status/{session_id}")
async def disabled_stripe_status(session_id: str, user=Depends(get_current_user)):
    raise HTTPException(
        status_code=410,
        detail="Stripe checkout is disabled for this sweepstakes product.",
    )
