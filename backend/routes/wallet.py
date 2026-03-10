from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
import uuid
from datetime import datetime, timezone
from deps import db, get_current_user

router = APIRouter(prefix="/api")


class PurchaseRequest(BaseModel):
    amount: int
    currency: str = "sc"


class CashoutRequest(BaseModel):
    amount: int


@router.get("/wallet")
async def get_wallet(user=Depends(get_current_user)):
    wallet = await db.wallets.find_one({"user_id": user['id']}, {"_id": 0})
    if not wallet:
        raise HTTPException(status_code=404, detail="Wallet not found")
    return wallet


@router.post("/wallet/purchase")
async def purchase_coins(req: PurchaseRequest, user=Depends(get_current_user)):
    balance_field = f"{req.currency}_balance"
    await db.wallets.update_one({"user_id": user['id']}, {"$inc": {balance_field: req.amount}})
    await db.transactions.insert_one({
        "id": str(uuid.uuid4()), "user_id": user['id'],
        "type": "purchase", "amount": req.amount, "currency": req.currency,
        "description": f"Purchased {req.amount} {req.currency.upper()}",
        "created_at": datetime.now(timezone.utc).isoformat()
    })
    wallet = await db.wallets.find_one({"user_id": user['id']}, {"_id": 0})
    return wallet


@router.post("/wallet/cashout")
async def cashout(req: CashoutRequest, user=Depends(get_current_user)):
    wallet = await db.wallets.find_one({"user_id": user['id']}, {"_id": 0})
    if not wallet or wallet.get('sc_balance', 0) < req.amount:
        raise HTTPException(status_code=400, detail="Insufficient SC balance")
    if req.amount < 100:
        raise HTTPException(status_code=400, detail="Minimum cashout: 100 SC")

    await db.wallets.update_one({"user_id": user['id']}, {"$inc": {"sc_balance": -req.amount}})
    await db.transactions.insert_one({
        "id": str(uuid.uuid4()), "user_id": user['id'],
        "type": "cashout", "amount": -req.amount, "currency": "sc",
        "description": f"Cashout {req.amount} SC to crypto",
        "created_at": datetime.now(timezone.utc).isoformat()
    })
    wallet = await db.wallets.find_one({"user_id": user['id']}, {"_id": 0})
    return {"wallet": wallet, "message": "Cashout initiated"}


@router.get("/wallet/transactions")
async def get_transactions(user=Depends(get_current_user)):
    txns = await db.transactions.find(
        {"user_id": user['id']}, {"_id": 0}
    ).sort("created_at", -1).to_list(100)
    return txns
