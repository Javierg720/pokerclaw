from fastapi import APIRouter, HTTPException, Depends
import uuid
from datetime import datetime, timezone
from deps import db, require_agent, sanitize_game_for_response
from game_engine import create_deck, advance_game
from agent_entertainment import publish_action_banter, public_personality
from game_persistence import (
    attach_new_game_to_table, finalize_completed_game, persist_game_transition,
)

router = APIRouter(prefix="/api")


@router.get("/tables")
async def list_tables():
    tables = await db.tables.find({}, {"_id": 0}).to_list(100)
    for t in tables:
        if t.get('current_game_id'):
            game = await db.games.find_one({"id": t['current_game_id']}, {"_id": 0})
            t['current_game'] = sanitize_game_for_response(game) if game else None
        else:
            t['current_game'] = None
    return tables


@router.get("/tables/{table_id}")
async def get_table(table_id: str):
    table = await db.tables.find_one({"id": table_id}, {"_id": 0})
    if not table:
        raise HTTPException(status_code=404, detail="Table not found")
    if table.get('current_game_id'):
        game = await db.games.find_one({"id": table['current_game_id']}, {"_id": 0})
        table['current_game'] = sanitize_game_for_response(game) if game else None
    else:
        table['current_game'] = None
    return table


@router.post("/tables/{table_id}/start-game")
async def start_game(table_id: str, user=Depends(require_agent)):
    table = await db.tables.find_one({"id": table_id}, {"_id": 0})
    if not table:
        raise HTTPException(status_code=404, detail="Table not found")
    if user.get('agent_id') not in table.get('agent_ids', []):
        raise HTTPException(status_code=403, detail="Your OpenClaw agent is not seated at this table")

    if table.get('current_game_id'):
        existing = await db.games.find_one({"id": table['current_game_id']}, {"_id": 0})
        if existing and existing['phase'] not in ('complete',):
            raise HTTPException(status_code=400, detail="Game already in progress")

    agent_ids = table.get('agent_ids', [])
    agents = []
    for aid in agent_ids:
        agent = await db.agents.find_one({"id": aid}, {"_id": 0})
        if agent:
            agents.append(agent)

    if len(agents) < 2:
        raise HTTPException(status_code=400, detail="Not enough agents")

    deck = create_deck()
    game_id = str(uuid.uuid4())
    players = []
    for i, agent in enumerate(agents):
        players.append({
            "agent_id": agent['id'], "agent_name": agent['name'],
            "avatar_url": agent['avatar_url'], "strategy": agent['strategy'],
            "is_external": agent.get('is_external', False),
            "personality_key": agent.get('personality_key'),
            "personality": agent.get('personality') or public_personality(agent),
            "hole_cards": [], "chips": 1000, "current_bet": 0,
            "total_bet": 0, "folded": False, "is_dealer": i == 0,
            "hand_rank": 0, "hand_name": ""
        })

    game = {
        "id": game_id, "table_id": table_id, "phase": "waiting",
        "players": players, "community_cards": [], "pot": 0,
        "deck": deck, "dealer_index": 0, "actions_log": [],
        "current_actor": None, "turn_index": 0,
        "round_bet": 0, "round_phase": None, "last_action": None,
        "winner_id": None, "winner_name": None, "winning_hand": None,
        "house_rake": 0, "final_pot": 0,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "completed_at": None
    }
    await db.games.insert_one(game)
    await attach_new_game_to_table(table, game_id)
    return sanitize_game_for_response(game)


@router.get("/games/{game_id}")
async def get_game(game_id: str):
    game = await db.games.find_one({"id": game_id}, {"_id": 0})
    if not game:
        raise HTTPException(status_code=404, detail="Game not found")
    return sanitize_game_for_response(game)


@router.post("/games/{game_id}/advance")
async def advance_game_endpoint(game_id: str, user=Depends(require_agent)):
    game = await db.games.find_one({"id": game_id}, {"_id": 0})
    if not game:
        raise HTTPException(status_code=404, detail="Game not found")
    if not any(p['agent_id'] == user.get('agent_id') for p in game.get('players', [])):
        raise HTTPException(status_code=403, detail="Your OpenClaw agent is not in this game")
    if game['phase'] == 'complete':
        await finalize_completed_game(game)
        return sanitize_game_for_response(game)
    current_actor = game.get('current_actor')
    if current_actor:
        actor = await db.agents.find_one({"id": current_actor}, {"_id": 0, "is_external": 1})
        if actor and actor.get('is_external'):
            raise HTTPException(
                status_code=409,
                detail="Waiting for the current OpenClaw agent to submit its authenticated action",
            )

    action_count_before = len(game.get('actions_log', []))
    expected_revision = game.get('game_revision')
    updated = advance_game(game)

    if updated['phase'] == 'complete':
        updated['completed_at'] = datetime.now(timezone.utc).isoformat()
    await persist_game_transition(updated, expected_revision)
    if updated['phase'] == 'complete':
        await finalize_completed_game(updated)
    new_actions = updated.get('actions_log', [])[action_count_before:]
    await publish_action_banter(updated, new_actions)

    # Broadcast via websocket
    try:
        from server import table_manager
        if updated.get('table_id'):
            await table_manager.broadcast(
                updated['table_id'],
                {"type": "game_update", "game": sanitize_game_for_response(updated)}
            )
    except ImportError:
        pass

    return sanitize_game_for_response(updated)


@router.get("/tables/{table_id}/chat-log")
async def get_table_chat_log(table_id: str):
    if not await db.tables.find_one({"id": table_id}, {"_id": 0, "id": 1}):
        raise HTTPException(status_code=404, detail="Table not found")
    messages = await db.table_chat_messages.find(
        {"table_id": table_id}, {"_id": 0}
    ).sort("timestamp", -1).to_list(50)
    messages.reverse()
    return {"messages": messages}
