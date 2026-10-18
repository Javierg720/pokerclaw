from fastapi import APIRouter, HTTPException, Depends
from deps import db, require_agent
from agent_entertainment import POLICY_VERSION, public_personality

router = APIRouter(prefix="/api")


@router.get("/agents")
async def list_agents():
    agents = await db.agents.find({}, {"_id": 0}).to_list(100)
    return agents


@router.get("/agents/my-agent")
async def get_my_agent(user=Depends(require_agent)):
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
async def get_my_agent_activity(user=Depends(require_agent)):
    if not user.get('agent_id'):
        raise HTTPException(status_code=403, detail="Agent profile required")
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


@router.get("/games/{game_id}/transparency")
async def get_game_transparency(game_id: str):
    """Public AI Intel: policy metadata, lifetime record, and safe action logs.

    This endpoint never returns the deck, private cards, hand-strength scores,
    RNG values, hidden prompts, or chain-of-thought.
    """
    game = await db.games.find_one({"id": game_id}, {"_id": 0, "deck": 0})
    if not game:
        raise HTTPException(status_code=404, detail="Game not found")

    actions = game.get("actions_log", [])
    profiles = []
    for player in game.get("players", []):
        agent = await db.agents.find_one(
            {"id": player.get("agent_id")},
            {"_id": 0, "id": 1, "name": 1, "avatar_url": 1, "tagline": 1,
             "strategy": 1, "personality": 1, "personality_key": 1,
             "is_external": 1, "wins": 1, "losses": 1, "total_games": 1,
             "total_chips_won": 1},
        ) or player
        agent_actions = [a for a in actions if a.get("agent_id") == player.get("agent_id")]
        counts = {name: sum(1 for a in agent_actions if a.get("action") == name)
                  for name in ("raise", "call", "fold")}
        games = int(agent.get("total_games", 0))
        wins = int(agent.get("wins", 0))
        source = "external_agent" if agent.get("is_external") else "pokerclaw_policy"
        profiles.append({
            "agent_id": player.get("agent_id"),
            "name": player.get("agent_name") or agent.get("name"),
            "avatar_url": player.get("avatar_url") or agent.get("avatar_url"),
            "tagline": agent.get("tagline", ""),
            "strategy": player.get("strategy") or agent.get("strategy", "balanced"),
            "personality": player.get("personality") or agent.get("personality") or public_personality(agent),
            "decision_source": source,
            "policy_version": "external-agent" if source == "external_agent" else POLICY_VERSION,
            "stats": {
                "wins": wins,
                "losses": int(agent.get("losses", 0)),
                "total_games": games,
                "win_rate": round(wins / games * 100, 1) if games else 0,
                "total_chips_won": int(agent.get("total_chips_won", 0)),
            },
            "hand_action_mix": counts,
        })

    public_decisions = [
        {key: action.get(key) for key in (
            "decision_id", "agent_id", "agent_name", "action", "amount",
            "decision_source", "policy_version", "strategy", "phase",
            "reason_code", "public_explanation", "pot_before",
            "round_bet_before",
        )}
        for action in actions[-20:]
    ]
    return {
        "game_id": game_id,
        "table_id": game.get("table_id"),
        "disclosure": (
            "Public explanations summarize policy and observable table state. "
            "Private cards, hidden calculations, and chain-of-thought are never exposed."
        ),
        "agents": profiles,
        "decisions": public_decisions,
    }
