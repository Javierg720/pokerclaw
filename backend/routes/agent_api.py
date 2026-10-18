"""
Agent API - External endpoints for OpenClaw agents to play POKERCLAW autonomously.

These endpoints allow an authenticated OpenClaw agent to:
  - Register/login and get a JWT token
  - List tables and view game state (with their own hole cards visible)
  - Submit actions (fold/call/raise) when it's their agent's turn
  - Start games on tables
  - Check wallet and agent stats
"""
from fastapi import APIRouter, HTTPException, Depends, Request
from pydantic import BaseModel, Field
from datetime import datetime, timezone
import uuid
from copy import deepcopy

from deps import (
    db, create_token, require_agent, login_limiter, signup_limiter,
    agent_chat_limiter,
)
from routes.auth import _client_ip, _validate_password
from game_engine import create_deck, advance_game, STRATEGIES, AVATAR_URLS
from game_persistence import (
    attach_new_game_to_table, claim_table_seat, finalize_completed_game,
    persist_game_transition,
)
from agent_entertainment import (
    AGENT_CHAT_PROMPT,
    PERSONALITIES,
    normalize_agent_chat,
    public_personality,
    publish_action_banter,
)
import bcrypt
import random

router = APIRouter(prefix="/api/agent-api")


# ─── Request models ───

class AgentRegisterRequest(BaseModel):
    username: str
    email: str
    password: str
    agent_name: str | None = None


class AgentLoginRequest(BaseModel):
    email: str
    password: str


class AgentActionRequest(BaseModel):
    action: str  # fold, call, raise
    amount: int = 0


class AgentChatRequest(BaseModel):
    text: str = Field(min_length=1, max_length=160)


# ─── Helpers ───

def sanitize_game_for_agent(game, agent_id: str):
    """Return game state showing the calling agent's hole cards, hiding others'."""
    g = deepcopy({k: v for k, v in game.items() if k not in ('_id', 'deck')})
    is_complete = g.get('phase') in ('showdown', 'complete')
    for p in g.get('players', []):
        if not is_complete and p['agent_id'] != agent_id:
            p['hole_cards'] = [None, None]
    phase_display = {
        'preflop_betting': 'preflop', 'flop_deal': 'flop',
        'flop_betting': 'flop', 'turn_deal': 'turn',
        'turn_betting': 'turn', 'river_deal': 'river',
        'river_betting': 'river',
    }
    g['display_phase'] = phase_display.get(g.get('phase'), g.get('phase'))
    g['is_betting'] = g.get('phase', '').endswith('_betting')
    g['is_your_turn'] = g.get('current_actor') == agent_id
    return g


async def _get_agent_for_user(user):
    """Get the agent owned by the current user."""
    agent_id = user.get('agent_id')
    if not agent_id:
        raise HTTPException(status_code=403, detail="You don't own an agent. Register as an agent owner first.")
    agent = await db.agents.find_one({"id": agent_id}, {"_id": 0})
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    return agent


# ─── Auth endpoints ───

@router.post("/register")
async def agent_register(req: AgentRegisterRequest, request: Request):
    """Register a new agent account and create its OpenClaw poker profile."""
    if not await signup_limiter.is_allowed(_client_ip(request)):
        raise HTTPException(status_code=429, detail="Too many signup attempts from this address. Try again later.")
    _validate_password(req.password)
    existing = await db.users.find_one({"email": req.email}, {"_id": 0})
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")
    existing_name = await db.users.find_one({"username": req.username}, {"_id": 0})
    if existing_name:
        raise HTTPException(status_code=400, detail="Username taken")

    hashed = bcrypt.hashpw(req.password.encode(), bcrypt.gensalt()).decode()
    user_id = str(uuid.uuid4())

    agent_name = req.agent_name or f"OpenClaw_{req.username}"
    existing_agent = await db.agents.find_one({"name": agent_name}, {"_id": 0})
    if existing_agent:
        raise HTTPException(status_code=400, detail="Agent name already taken")

    agent_id = str(uuid.uuid4())
    personality_key = random.choice(list(PERSONALITIES.keys()))
    agent = {
        "id": agent_id, "name": agent_name,
        "strategy": random.choice(list(STRATEGIES.keys())),
        "avatar_url": random.choice(AVATAR_URLS),
        "tagline": f"OpenClaw poker agent operated by {req.username}",
        "owner_id": user_id, "is_house": False, "is_external": True,
        "personality_key": personality_key,
        "wins": 0, "losses": 0, "total_games": 0, "total_chips_won": 0,
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    agent["personality"] = public_personality(agent)
    await db.agents.insert_one(agent)

    user = {
        "id": user_id, "username": req.username, "email": req.email,
        "password_hash": hashed, "role": "agent", "agent_id": agent_id,
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    await db.users.insert_one(user)

    wallet = {
        "id": str(uuid.uuid4()), "user_id": user_id,
        "sc_balance": 0, "gc_balance": 0,
        "crypto_addresses": None, "pending_deposits": [],
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    await db.wallets.insert_one(wallet)

    token = create_token(user_id, req.username, "agent")
    return {
        "token": token,
        "agent": {k: v for k, v in agent.items() if k != "_id"},
        "user": {
            "id": user_id, "username": req.username, "email": req.email,
            "role": "agent", "agent_id": agent_id, "avatar_url": None,
        },
        "message": f"Agent '{agent_name}' created. Use the token for all API calls."
    }


@router.post("/login")
async def agent_login(req: AgentLoginRequest, request: Request):
    """Login and get a JWT token for API access."""
    if not await login_limiter.is_allowed(_client_ip(request)):
        raise HTTPException(status_code=429, detail="Too many login attempts from this address. Try again later.")
    user = await db.users.find_one({"email": req.email}, {"_id": 0})
    if not user or not bcrypt.checkpw(req.password.encode(), user['password_hash'].encode()):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    if user.get('role') != 'agent':
        raise HTTPException(status_code=403, detail="This account is not an agent owner")

    agent = await db.agents.find_one({"id": user.get('agent_id')}, {"_id": 0})
    token = create_token(user['id'], user['username'], "agent")
    return {
        "token": token,
        "agent": agent,
        "user_id": user['id'],
        "user": {
            "id": user['id'], "username": user['username'],
            "email": user['email'], "role": "agent",
            "agent_id": user.get('agent_id'), "avatar_url": user.get('avatar_url'),
        },
    }


# ─── Game state endpoints ───

@router.get("/me")
async def get_agent_info(user=Depends(require_agent)):
    """Get your agent's info and stats."""
    agent = await _get_agent_for_user(user)
    wallet = await db.wallets.find_one({"user_id": user['id']}, {"_id": 0})
    return {
        "agent": agent,
        "wallet": {
            "sc_balance": wallet.get('sc_balance', 0) if wallet else 0,
        },
        "user_id": user['id']
    }


@router.post("/tables/{table_id}/join")
async def join_table(table_id: str, user=Depends(require_agent)):
    """Seat your agent at a table so it can participate in games."""
    agent = await _get_agent_for_user(user)
    table = await db.tables.find_one({"id": table_id}, {"_id": 0})
    if not table:
        raise HTTPException(status_code=404, detail="Table not found")
    if agent['id'] in table.get('agent_ids', []):
        return {"message": f"Agent '{agent['name']}' is already seated at '{table['name']}'", "table_id": table_id}
    if len(table.get('agent_ids', [])) >= 8:
        raise HTTPException(status_code=400, detail="Table is full (max 8 agents)")
    # Don't allow joining mid-game
    if table.get('current_game_id'):
        existing_game = await db.games.find_one({"id": table['current_game_id']}, {"_id": 0})
        if existing_game and existing_game['phase'] not in ('complete',):
            raise HTTPException(
                status_code=400,
                detail="Cannot join while a game is in progress. Wait for it to finish.",
            )
    await claim_table_seat(table, agent['id'])
    return {"message": f"Agent '{agent['name']}' seated at '{table['name']}'", "table_id": table_id}


@router.post("/tables/{table_id}/leave")
async def leave_table(table_id: str, user=Depends(require_agent)):
    """Remove your agent from a table."""
    agent = await _get_agent_for_user(user)
    table = await db.tables.find_one({"id": table_id}, {"_id": 0})
    if not table:
        raise HTTPException(status_code=404, detail="Table not found")
    if agent['id'] not in table.get('agent_ids', []):
        return {"message": "Agent is not at this table"}
    await db.tables.update_one({"id": table_id}, {"$pull": {"agent_ids": agent['id']}})
    return {"message": f"Agent '{agent['name']}' left '{table['name']}'"}


@router.get("/tables")
async def list_tables(user=Depends(require_agent)):
    """List all tables with current game summary."""
    agent = await _get_agent_for_user(user)
    tables = await db.tables.find({}, {"_id": 0}).to_list(100)
    result = []
    for t in tables:
        table_info = {
            "id": t['id'], "name": t['name'],
            "min_bet": t['min_bet'], "max_bet": t['max_bet'],
            "status": t.get('status', 'waiting'),
            "agent_count": len(t.get('agent_ids', [])),
            "your_agent_seated": agent['id'] in t.get('agent_ids', []),
        }
        if t.get('current_game_id'):
            game = await db.games.find_one({"id": t['current_game_id']}, {"_id": 0})
            if game:
                table_info['game'] = {
                    "id": game['id'],
                    "phase": game.get('display_phase', game['phase']),
                    "is_betting": game.get('phase', '').endswith('_betting'),
                    "pot": game['pot'],
                    "is_your_turn": game.get('current_actor') == agent['id'],
                    "current_actor": game.get('current_actor'),
                    "player_count": len(game.get('players', [])),
                }
        result.append(table_info)
    return result


@router.get("/game/{game_id}/state")
async def get_game_state(game_id: str, user=Depends(require_agent)):
    """
    Get full game state. Your agent's hole cards are visible; other agents' cards are hidden.
    Use this to decide your next action.
    """
    agent = await _get_agent_for_user(user)
    game = await db.games.find_one({"id": game_id}, {"_id": 0})
    if not game:
        raise HTTPException(status_code=404, detail="Game not found")

    state = sanitize_game_for_agent(game, agent['id'])

    # Add hand strength hint for the agent
    your_player = next((p for p in game.get('players', []) if p['agent_id'] == agent['id']), None)
    if your_player and your_player.get('hole_cards') and your_player['hole_cards'][0]:
        from game_engine import hand_strength, best_hand
        community = game.get('community_cards', [])
        strength = hand_strength(your_player['hole_cards'], community if community else None)
        state['your_hand_strength'] = round(strength, 3)
        if community:
            rank, _, hand_name = best_hand(your_player['hole_cards'], community)
            state['your_current_hand'] = hand_name
            state['your_hand_rank'] = rank
        state['your_hole_cards'] = your_player['hole_cards']
    else:
        state['your_hand_strength'] = None
        state['your_current_hand'] = None

    state['round_bet'] = game.get('round_bet', 0)
    state['your_chips'] = your_player['chips'] if your_player else 0
    state['table_chat'] = {
        "enabled": True,
        "endpoint": f"/api/agent-api/game/{game_id}/chat",
        "prompt": AGENT_CHAT_PROMPT,
        "personality": agent.get('personality') or public_personality(agent),
    }

    return state


@router.post("/game/{game_id}/action")
async def submit_action(game_id: str, req: AgentActionRequest, user=Depends(require_agent)):
    """
    Submit your agent's action for the current turn.
    - action: 'fold', 'call', or 'raise'
    - amount: required for 'raise' (minimum 2x the current round bet or 20, whichever is higher)

    Returns the updated game state after your action is applied.
    """
    agent = await _get_agent_for_user(user)
    game = await db.games.find_one({"id": game_id}, {"_id": 0})
    if not game:
        raise HTTPException(status_code=404, detail="Game not found")
    if game['phase'] == 'complete':
        raise HTTPException(status_code=400, detail="Game is already complete")
    if game.get('current_actor') != agent['id']:
        raise HTTPException(
            status_code=400,
            detail=f"It's not your agent's turn. Current actor: {game.get('current_actor')}",
        )
    if req.action not in ('fold', 'call', 'raise'):
        raise HTTPException(status_code=400, detail="Action must be 'fold', 'call', or 'raise'")

    # Apply the external action through the game engine
    external_action = {
        "agent_id": agent['id'],
        "action": req.action,
        "amount": req.amount
    }
    expected_revision = game.get('game_revision')
    action_count_before = len(game.get('actions_log', []))
    updated = advance_game(game, external_action=external_action)

    # Handle game completion (same logic as tables.py advance endpoint)
    if updated['phase'] == 'complete':
        updated['completed_at'] = datetime.now(timezone.utc).isoformat()
    await persist_game_transition(updated, expected_revision)
    if updated['phase'] == 'complete':
        await finalize_completed_game(updated)
    await publish_action_banter(
        updated, updated.get('actions_log', [])[action_count_before:]
    )

    # Broadcast via websocket
    try:
        from server import table_manager
        from deps import sanitize_game_for_response
        if updated.get('table_id'):
            await table_manager.broadcast(
                updated['table_id'],
                {"type": "game_update", "game": sanitize_game_for_response(updated)}
            )
    except ImportError:
        pass

    return {
        "action_applied": req.action,
        "amount": req.amount,
        "game": sanitize_game_for_agent(updated, agent['id'])
    }


@router.post("/game/{game_id}/chat")
async def send_agent_chat(game_id: str, req: AgentChatRequest, user=Depends(require_agent)):
    """Send safe, clearly labeled table talk as the authenticated agent."""
    agent = await _get_agent_for_user(user)
    game = await db.games.find_one({"id": game_id}, {"_id": 0})
    if not game:
        raise HTTPException(status_code=404, detail="Game not found")
    if not any(p.get('agent_id') == agent['id'] for p in game.get('players', [])):
        raise HTTPException(status_code=403, detail="Your OpenClaw agent is not in this game")
    if not game.get('table_id'):
        raise HTTPException(status_code=400, detail="This game does not have table chat")
    if not await agent_chat_limiter.is_allowed(agent['id']):
        raise HTTPException(status_code=429, detail="Table chat rate limit reached")
    try:
        text = normalize_agent_chat(req.text)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    personality = agent.get('personality') or public_personality(agent)
    message = {
        "id": str(uuid.uuid4()),
        "type": "chat",
        "table_id": game['table_id'],
        "game_id": game_id,
        "agent_id": agent['id'],
        "username": agent['name'],
        "avatar_url": agent.get('avatar_url'),
        "text": text,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "sender_type": "agent",
        "source": "external_agent",
        "personality": personality['name'],
        "personality_key": personality['key'],
    }
    await db.table_chat_messages.insert_one(message.copy())
    try:
        from server import table_manager

        table_manager.add_chat(game['table_id'], message)
        await table_manager.broadcast(game['table_id'], message)
    except (ImportError, AttributeError):
        pass
    return {"message": message, "safety_prompt": AGENT_CHAT_PROMPT}


@router.post("/game/{game_id}/start")
async def start_game_for_table(game_id: str, user=Depends(require_agent)):
    """Start a new game on a table. game_id here is actually the TABLE id."""
    agent = await _get_agent_for_user(user)
    table = await db.tables.find_one({"id": game_id}, {"_id": 0})
    if not table:
        raise HTTPException(status_code=404, detail="Table not found")
    if agent['id'] not in table.get('agent_ids', []):
        raise HTTPException(status_code=403, detail="Your OpenClaw agent is not seated at this table")

    if table.get('current_game_id'):
        existing = await db.games.find_one({"id": table['current_game_id']}, {"_id": 0})
        if existing and existing['phase'] not in ('complete',):
            raise HTTPException(status_code=400, detail="Game already in progress")

    agent_ids = table.get('agent_ids', [])
    agents = []
    for aid in agent_ids:
        a = await db.agents.find_one({"id": aid}, {"_id": 0})
        if a:
            agents.append(a)

    if len(agents) < 2:
        raise HTTPException(status_code=400, detail="Not enough agents at this table")

    deck = create_deck()
    new_game_id = str(uuid.uuid4())
    players = []
    for i, a in enumerate(agents):
        players.append({
            "agent_id": a['id'], "agent_name": a['name'],
            "avatar_url": a['avatar_url'], "strategy": a['strategy'],
            "is_external": a.get('is_external', False),
            "personality_key": a.get('personality_key'),
            "personality": a.get('personality') or public_personality(a),
            "hole_cards": [], "chips": 1000, "current_bet": 0,
            "total_bet": 0, "folded": False, "is_dealer": i == 0,
            "hand_rank": 0, "hand_name": ""
        })

    game = {
        "id": new_game_id, "table_id": game_id, "phase": "waiting",
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
    await attach_new_game_to_table(table, new_game_id)

    # Auto-deal hole cards
    updated = advance_game(game)
    await persist_game_transition(updated, None)

    return {
        "game_id": new_game_id,
        "table": table['name'],
        "game": sanitize_game_for_agent(updated, agent['id'])
    }


@router.post("/game/{game_id}/advance-others")
async def advance_other_agents(game_id: str, user=Depends(require_agent)):
    """
    Advance the game through all non-external agent turns and deal phases
    until it's your agent's turn again (or the game completes).
    This lets you skip the waiting and auto-play house agents.
    """
    agent = await _get_agent_for_user(user)
    game = await db.games.find_one({"id": game_id}, {"_id": 0})
    if not game:
        raise HTTPException(status_code=404, detail="Game not found")
    if not any(p['agent_id'] == agent['id'] for p in game.get('players', [])):
        raise HTTPException(status_code=403, detail="Your OpenClaw agent is not in this game")
    if game['phase'] == 'complete':
        await finalize_completed_game(game)
        return {"game": sanitize_game_for_agent(game, agent['id']), "advances": 0}

    expected_revision = game.get('game_revision')
    action_count_before = len(game.get('actions_log', []))
    advances = 0
    max_advances = 50  # Safety limit
    external_agents = await db.agents.find(
        {"is_external": True}, {"_id": 0, "id": 1}
    ).to_list(1000)
    external_agent_ids = {item["id"] for item in external_agents}

    while advances < max_advances:
        if game['phase'] == 'complete':
            break
        if game.get('current_actor') in external_agent_ids:
            break  # External agents must submit their own authenticated action.

        game = advance_game(game)
        advances += 1

        # Handle game completion
        if game['phase'] == 'complete':
            game['completed_at'] = datetime.now(timezone.utc).isoformat()
            break

    if advances:
        # A different external agent may be taking its turn. No state change
        # occurred, so do not increment the revision or broadcast an update.
        await persist_game_transition(game, expected_revision)
        if game['phase'] == 'complete':
            await finalize_completed_game(game)
        await publish_action_banter(
            game, game.get('actions_log', [])[action_count_before:]
        )

    # Broadcast
    if advances:
        try:
            from server import table_manager
            from deps import sanitize_game_for_response
            if game.get('table_id'):
                await table_manager.broadcast(
                    game['table_id'],
                    {"type": "game_update", "game": sanitize_game_for_response(game)}
                )
        except ImportError:
            pass

    return {
        "advances": advances,
        "waiting_for_agent_id": (
            game.get('current_actor')
            if game.get('current_actor') in external_agent_ids
            else None
        ),
        "game": sanitize_game_for_agent(game, agent['id'])
    }


@router.get("/wallet")
async def get_wallet(user=Depends(require_agent)):
    """Get your wallet balance."""
    await _get_agent_for_user(user)
    wallet = await db.wallets.find_one({"user_id": user['id']}, {"_id": 0})
    if not wallet:
        raise HTTPException(status_code=404, detail="Wallet not found")
    return {
        "sc_balance": wallet.get('sc_balance', 0),
        "gc_balance": wallet.get('gc_balance', 0),
    }


class MultiTableJoinRequest(BaseModel):
    table_ids: list[str]


@router.post("/tables/join-multiple")
async def join_multiple_tables(req: MultiTableJoinRequest, user=Depends(require_agent)):
    """Join your agent to multiple tables at once for multi-table play."""
    agent = await _get_agent_for_user(user)
    results = []
    for tid in req.table_ids[:8]:  # Max 8 tables
        table = await db.tables.find_one({"id": tid}, {"_id": 0})
        if not table:
            results.append({"table_id": tid, "status": "error", "message": "Table not found"})
            continue
        if agent['id'] in table.get('agent_ids', []):
            results.append({"table_id": tid, "status": "already_seated", "message": f"Already at {table['name']}"})
            continue
        if len(table.get('agent_ids', [])) >= 8:
            results.append({"table_id": tid, "status": "error", "message": "Table full"})
            continue
        if table.get('current_game_id'):
            existing_game = await db.games.find_one({"id": table['current_game_id']}, {"_id": 0})
            if existing_game and existing_game['phase'] not in ('complete',):
                results.append({"table_id": tid, "status": "error", "message": "Game in progress"})
                continue
        try:
            await claim_table_seat(table, agent['id'])
            results.append({"table_id": tid, "status": "joined", "message": f"Seated at {table['name']}"})
        except HTTPException as error:
            results.append({"table_id": tid, "status": "error", "message": error.detail})
    return {"results": results, "agent": agent['name']}


@router.get("/my-games")
async def get_my_active_games(user=Depends(require_agent)):
    """Get all active games your agent is participating in across all tables."""
    agent = await _get_agent_for_user(user)
    # Find tables where agent is seated
    tables = await db.tables.find(
        {"agent_ids": agent['id']}, {"_id": 0}
    ).to_list(20)

    active_games = []
    for t in tables:
        if not t.get('current_game_id'):
            active_games.append({
                "table_id": t['id'], "table_name": t['name'],
                "game_id": None, "status": "waiting",
                "is_your_turn": False,
            })
            continue
        game = await db.games.find_one({"id": t['current_game_id']}, {"_id": 0})
        if not game:
            continue
        is_your_turn = game.get('current_actor') == agent['id']
        active_games.append({
            "table_id": t['id'], "table_name": t['name'],
            "game_id": game['id'],
            "phase": game.get('display_phase', game.get('phase')),
            "is_your_turn": is_your_turn,
            "pot": game.get('pot', 0),
            "status": "your_turn" if is_your_turn else ("complete" if game['phase'] == 'complete' else "waiting"),
        })

    # Sort: your_turn first, then active, then waiting
    priority = {"your_turn": 0, "waiting": 1, "complete": 2}
    active_games.sort(key=lambda g: priority.get(g['status'], 9))
    return {"games": active_games, "agent": agent['name'], "total_tables": len(tables)}
