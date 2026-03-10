from fastapi import APIRouter, HTTPException, Depends, Request
from pydantic import BaseModel
import os
import uuid
from datetime import datetime, timezone
from deps import db, get_current_user, logger
from emergentintegrations.payments.stripe.checkout import (
    StripeCheckout, CheckoutSessionRequest
)

router = APIRouter(prefix="/api")

SC_PACKAGES = {
    "sc_499": {"sc_amount": 499, "price_usd": 4.99, "label": "499 SweepCoins"},
    "sc_999": {"sc_amount": 999, "price_usd": 9.99, "label": "999 SweepCoins"},
    "sc_1999": {"sc_amount": 1999, "price_usd": 19.99, "label": "1,999 SweepCoins"},
    "sc_4999": {"sc_amount": 4999, "price_usd": 49.99, "label": "4,999 SweepCoins"},
    "sc_9999": {"sc_amount": 9999, "price_usd": 99.99, "label": "9,999 SweepCoins"},
}


class StripeCheckoutRequest_(BaseModel):
    package_id: str
    origin_url: str


@router.get("/stripe/packages")
async def get_stripe_packages():
    return [
        {"id": k, "sc_amount": v["sc_amount"], "price_usd": v["price_usd"], "label": v["label"]}
        for k, v in SC_PACKAGES.items()
    ]


@router.post("/stripe/checkout")
async def create_stripe_checkout(req: StripeCheckoutRequest_, http_request: Request, user=Depends(get_current_user)):
    pkg = SC_PACKAGES.get(req.package_id)
    if not pkg:
        raise HTTPException(status_code=400, detail="Invalid package")

    stripe_key = os.environ.get("STRIPE_API_KEY")
    if not stripe_key:
        raise HTTPException(status_code=500, detail="Stripe not configured")

    host_url = str(http_request.base_url).rstrip("/")
    webhook_url = f"{host_url}/api/webhook/stripe"
    stripe_checkout = StripeCheckout(api_key=stripe_key, webhook_url=webhook_url)

    origin = req.origin_url.rstrip("/")
    success_url = f"{origin}/wallet?session_id={{CHECKOUT_SESSION_ID}}&status=success"
    cancel_url = f"{origin}/wallet?status=cancelled"

    metadata = {
        "user_id": user["id"], "username": user.get("username", ""),
        "package_id": req.package_id, "sc_amount": str(pkg["sc_amount"]),
    }

    checkout_req = CheckoutSessionRequest(
        amount=float(pkg["price_usd"]), currency="usd",
        success_url=success_url, cancel_url=cancel_url, metadata=metadata,
    )

    session = await stripe_checkout.create_checkout_session(checkout_req)

    await db.payment_transactions.insert_one({
        "id": str(uuid.uuid4()), "session_id": session.session_id,
        "user_id": user["id"], "package_id": req.package_id,
        "sc_amount": pkg["sc_amount"], "amount_usd": pkg["price_usd"],
        "payment_status": "pending", "status": "initiated",
        "metadata": metadata,
        "created_at": datetime.now(timezone.utc).isoformat(), "completed_at": None,
    })

    return {"url": session.url, "session_id": session.session_id}


@router.get("/stripe/status/{session_id}")
async def get_stripe_status(session_id: str, user=Depends(get_current_user)):
    stripe_key = os.environ.get("STRIPE_API_KEY")
    if not stripe_key:
        raise HTTPException(status_code=500, detail="Stripe not configured")

    stripe_checkout = StripeCheckout(api_key=stripe_key)
    status = await stripe_checkout.get_checkout_status(session_id)

    pt = await db.payment_transactions.find_one({"session_id": session_id}, {"_id": 0})
    if not pt:
        raise HTTPException(status_code=404, detail="Transaction not found")

    if pt["payment_status"] != "paid" and status.payment_status == "paid":
        sc_amount = pt["sc_amount"]
        await db.wallets.update_one({"user_id": pt["user_id"]}, {"$inc": {"sc_balance": sc_amount}})
        await db.payment_transactions.update_one(
            {"session_id": session_id},
            {"$set": {"payment_status": "paid", "status": "complete",
                      "completed_at": datetime.now(timezone.utc).isoformat()}}
        )
        await db.transactions.insert_one({
            "id": str(uuid.uuid4()), "user_id": pt["user_id"],
            "type": "stripe_purchase", "amount": sc_amount, "currency": "sc",
            "description": f"Purchased {sc_amount} SC via Stripe (${pt['amount_usd']})",
            "created_at": datetime.now(timezone.utc).isoformat()
        })
    elif status.payment_status != "paid":
        await db.payment_transactions.update_one(
            {"session_id": session_id},
            {"$set": {"payment_status": status.payment_status, "status": status.status}}
        )

    return {
        "status": status.status, "payment_status": status.payment_status,
        "sc_amount": pt["sc_amount"], "amount_usd": pt["amount_usd"],
    }
