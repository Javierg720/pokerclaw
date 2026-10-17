from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field
from typing import Literal
import uuid
from datetime import datetime, timezone
from deps import db, require_human

router = APIRouter(prefix="/api")


class BetRequest(BaseModel):
    game_id: str
    agent_id: str
    amount: int = Field(gt=0)
    currency: Literal["sc", "gc"] = "sc"


@router.post("/bets")
async def place_bet(req: BetRequest, user=Depends(require_human)):
    game = await db.games.find_one({"id": req.game_id}, {"_id": 0})
    if not game:
        raise HTTPException(status_code=404, detail="Game not found")
    if game['phase'] in ('showdown', 'complete'):
        raise HTTPException(status_code=400, detail="Betting is closed for this game")

    agent_in_game = any(p['agent_id'] == req.agent_id for p in game.get('players', []))
    if not agent_in_game:
        raise HTTPException(status_code=400, detail="Agent not in this game")

    balance_field = f"{req.currency}_balance"
    result = await db.wallets.update_one(
        {"user_id": user['id'], balance_field: {"$gte": req.amount}},
        {"$inc": {balance_field: -req.amount}},
    )
    if result.modified_count != 1:
        raise HTTPException(status_code=400, detail="Insufficient balance")

    bet = {
        "id": str(uuid.uuid4()), "user_id": user['id'],
        "game_id": req.game_id, "agent_id": req.agent_id,
        "amount": req.amount, "currency": req.currency,
        "status": "pending", "payout": 0,
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    await db.bets.insert_one(bet)

    await db.transactions.insert_one({
        "id": str(uuid.uuid4()), "user_id": user['id'],
        "type": "bet_placed", "amount": -req.amount, "currency": req.currency,
        "description": "Bet on game",
        "created_at": datetime.now(timezone.utc).isoformat()
    })

    return {k: v for k, v in bet.items() if k != '_id'}


@router.get("/bets/my-bets")
async def get_my_bets(user=Depends(require_human)):
    bets = await db.bets.find({"user_id": user['id']}, {"_id": 0}).sort("created_at", -1).to_list(100)
    return bets


@router.get("/bets/game/{game_id}")
async def get_game_bets(game_id: str):
    bets = await db.bets.find({"game_id": game_id}, {"_id": 0}).to_list(1000)
    return [
        {k: v for k, v in bet.items() if k != "user_id"}
        for bet in bets
    ]


@router.get("/bets/game/{game_id}/odds")
async def get_game_odds(game_id: str):
    bets = await db.bets.find({"game_id": game_id, "status": "pending"}, {"_id": 0}).to_list(1000)
    game = await db.games.find_one({"id": game_id}, {"_id": 0})
    if not game:
        raise HTTPException(status_code=404, detail="Game not found")

    total_pool = sum(b['amount'] for b in bets)
    agent_pools = {}
    agent_bet_counts = {}
    for b in bets:
        agent_pools[b['agent_id']] = agent_pools.get(b['agent_id'], 0) + b['amount']
        agent_bet_counts[b['agent_id']] = agent_bet_counts.get(b['agent_id'], 0) + 1

    odds = []
    for p in game.get('players', []):
        aid = p['agent_id']
        pool = agent_pools.get(aid, 0)
        bets_count = agent_bet_counts.get(aid, 0)
        if total_pool > 0 and pool > 0:
            multiplier = round((total_pool * 0.8) / pool, 2)
        else:
            active = len([pp for pp in game['players'] if not pp.get('folded')])
            multiplier = round(active * 0.8, 2) if active > 0 else 1.0

        pct = round((pool / total_pool) * 100, 1) if total_pool > 0 else 0
        odds.append({
            "agent_id": aid, "agent_name": p['agent_name'],
            "avatar_url": p.get('avatar_url'), "pool": pool,
            "bets_count": bets_count, "pct": pct,
            "multiplier": multiplier, "folded": p.get('folded', False),
        })

    return {"total_pool": total_pool, "total_bets": len(bets), "odds": odds}
