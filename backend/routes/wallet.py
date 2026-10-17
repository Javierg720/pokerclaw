from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
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
    raise HTTPException(
        status_code=410,
        detail="Direct balance purchases are disabled. Use Stripe checkout.",
    )


@router.post("/wallet/cashout")
async def cashout(req: CashoutRequest, user=Depends(get_current_user)):
    raise HTTPException(
        status_code=410,
        detail="Cashout is disabled until a verified payout provider is configured.",
    )


@router.get("/wallet/transactions")
async def get_transactions(user=Depends(get_current_user)):
    txns = await db.transactions.find(
        {"user_id": user['id']}, {"_id": 0}
    ).sort("created_at", -1).to_list(100)
    return txns
