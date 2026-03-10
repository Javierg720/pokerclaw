from fastapi import APIRouter, HTTPException, Depends
from deps import db, get_current_user

router = APIRouter(prefix="/api")


@router.get("/agents")
async def list_agents():
    agents = await db.agents.find({}, {"_id": 0}).to_list(100)
    return agents


@router.get("/agents/my-agent")
async def get_my_agent(user=Depends(get_current_user)):
    if user.get('role') != 'agent':
        raise HTTPException(status_code=403, detail="Only agent accounts have agents")
    if not user.get('agent_id'):
        raise HTTPException(status_code=404, detail="No agent linked to account")
    agent = await db.agents.find_one({"id": user['agent_id']}, {"_id": 0})
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    wallet = await db.wallets.find_one({"user_id": user['id']}, {"_id": 0})
    return {
        "agent": agent,
        "wallet": {k: v for k, v in wallet.items() if k != "_id"} if wallet else None
    }


@router.get("/agents/my-agent/activity")
async def get_my_agent_activity(user=Depends(get_current_user)):
    if user.get('role') != 'agent' or not user.get('agent_id'):
        raise HTTPException(status_code=403, detail="Only agent accounts have activity")
    agent_id = user['agent_id']

    games = await db.games.find(
        {"players.agent_id": agent_id, "phase": {"$in": ["complete", "showdown"]}},
        {"_id": 0, "deck": 0}
    ).sort("completed_at", -1).to_list(20)

    activity = []
    for g in games:
        player = next((p for p in g.get('players', []) if p['agent_id'] == agent_id), None)
        if not player:
            continue
        won = g.get('winner_id') == agent_id
        opponents = [p['agent_name'] for p in g.get('players', []) if p['agent_id'] != agent_id and not p.get('folded')]
        activity.append({
            "game_id": g['id'], "table_id": g.get('table_id'),
            "result": "win" if won else "loss",
            "hand": g.get('winning_hand') if won else (player.get('hand_name') or 'Folded'),
            "pot": g.get('pot', 0),
            "final_pot": g.get('final_pot', 0) if won else 0,
            "house_rake": g.get('house_rake', 0) if won else 0,
            "opponents": opponents[:3],
            "completed_at": g.get('completed_at') or g.get('created_at'),
        })

    txns = await db.transactions.find(
        {"user_id": user['id'], "type": {"$in": ["game_winnings", "bet_won", "tournament_won"]}},
        {"_id": 0}
    ).sort("created_at", -1).to_list(10)

    return {"activity": activity, "earnings": txns}


@router.get("/agents/{agent_id}")
async def get_agent(agent_id: str):
    agent = await db.agents.find_one({"id": agent_id}, {"_id": 0})
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    return agent
