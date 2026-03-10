"""
Agent API - External endpoints for OpenClaw agents to play POKERCLAW autonomously.

These endpoints allow an authenticated OpenClaw agent to:
  - Register/login and get a JWT token
  - List tables and view game state (with their own hole cards visible)
  - Submit actions (fold/call/raise) when it's their agent's turn
  - Start games on tables
  - Check wallet and agent stats
"""
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from datetime import datetime, timezone
import uuid

from deps import db, create_token, get_current_user, generate_crypto_addresses
from game_engine import create_deck, advance_game, STRATEGIES, AVATAR_URLS, HAND_NAMES
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


# ─── Helpers ───

def sanitize_game_for_agent(game, agent_id: str):
    """Return game state showing the calling agent's hole cards, hiding others'."""
    g = {k: v for k, v in game.items() if k not in ('_id', 'deck')}
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
async def agent_register(req: AgentRegisterRequest):
    """Register a new agent owner account. Creates a MoltBot agent automatically."""
    existing = await db.users.find_one({"email": req.email}, {"_id": 0})
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")
    existing_name = await db.users.find_one({"username": req.username}, {"_id": 0})
    if existing_name:
        raise HTTPException(status_code=400, detail="Username taken")

    hashed = bcrypt.hashpw(req.password.encode(), bcrypt.gensalt()).decode()
    user_id = str(uuid.uuid4())

    agent_name = req.agent_name or f"MoltBot_{req.username}"
    existing_agent = await db.agents.find_one({"name": agent_name}, {"_id": 0})
    if existing_agent:
        raise HTTPException(status_code=400, detail="Agent name already taken")

    agent_id = str(uuid.uuid4())
    agent = {
        "id": agent_id, "name": agent_name,
        "strategy": random.choice(list(STRATEGIES.keys())),
        "avatar_url": random.choice(AVATAR_URLS),
        "tagline": f"OpenClaw-powered MoltBot owned by {req.username}",
        "owner_id": user_id, "is_house": False, "is_external": True,
        "wins": 0, "losses": 0, "total_games": 0, "total_chips_won": 0,
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    await db.agents.insert_one(agent)

    user = {
        "id": user_id, "username": req.username, "email": req.email,
        "password_hash": hashed, "role": "agent", "agent_id": agent_id,
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    await db.users.insert_one(user)

    crypto_addresses = generate_crypto_addresses(user_id)
    wallet = {
        "id": str(uuid.uuid4()), "user_id": user_id,
        "sc_balance": 0, "gc_balance": 0,
        "crypto_addresses": crypto_addresses, "pending_deposits": [],
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    await db.wallets.insert_one(wallet)

    token = create_token(user_id, req.username, "agent")
    return {
        "token": token,
        "agent": {k: v for k, v in agent.items() if k != "_id"},
        "message": f"Agent '{agent_name}' created. Use the token for all API calls."
    }


@router.post("/login")
async def agent_login(req: AgentLoginRequest):
    """Login and get a JWT token for API access."""
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
        "user_id": user['id']
    }


# ─── Game state endpoints ───

@router.get("/me")
async def get_agent_info(user=Depends(get_current_user)):
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
async def join_table(table_id: str, user=Depends(get_current_user)):
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
            raise HTTPException(status_code=400, detail="Cannot join while a game is in progress. Wait for it to finish.")
    await db.tables.update_one({"id": table_id}, {"$push": {"agent_ids": agent['id']}})
    return {"message": f"Agent '{agent['name']}' seated at '{table['name']}'", "table_id": table_id}


@router.post("/tables/{table_id}/leave")
async def leave_table(table_id: str, user=Depends(get_current_user)):
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
async def list_tables(user=Depends(get_current_user)):
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
async def get_game_state(game_id: str, user=Depends(get_current_user)):
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

    return state


@router.post("/game/{game_id}/action")
async def submit_action(game_id: str, req: AgentActionRequest, user=Depends(get_current_user)):
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
        raise HTTPException(status_code=400, detail=f"It's not your agent's turn. Current actor: {game.get('current_actor')}")
    if req.action not in ('fold', 'call', 'raise'):
        raise HTTPException(status_code=400, detail="Action must be 'fold', 'call', or 'raise'")

    # Apply the external action through the game engine
    external_action = {
        "agent_id": agent['id'],
        "action": req.action,
        "amount": req.amount
    }
    updated = advance_game(game, external_action=external_action)

    # Handle game completion (same logic as tables.py advance endpoint)
    if updated['phase'] == 'complete':
        updated['completed_at'] = datetime.now(timezone.utc).isoformat()
        if updated.get('winner_id'):
            await db.agents.update_one(
                {"id": updated['winner_id']},
                {"$inc": {"wins": 1, "total_games": 1, "total_chips_won": updated.get('final_pot', 0)}}
            )
            for p in updated['players']:
                if p['agent_id'] != updated['winner_id']:
                    await db.agents.update_one(
                        {"id": p['agent_id']},
                        {"$inc": {"losses": 1, "total_games": 1}}
                    )
            winner_agent = await db.agents.find_one({"id": updated['winner_id']}, {"_id": 0})
            if winner_agent and winner_agent.get('owner_id'):
                winnings = updated.get('final_pot', 0)
                sc_credit = max(1, winnings // 10)
                await db.wallets.update_one(
                    {"user_id": winner_agent['owner_id']},
                    {"$inc": {"sc_balance": sc_credit}}
                )
                await db.transactions.insert_one({
                    "id": str(uuid.uuid4()),
                    "user_id": winner_agent['owner_id'],
                    "type": "game_winnings", "amount": sc_credit, "currency": "sc",
                    "description": f"{winner_agent['name']} won {winnings} chips (pot after 20% rake)",
                    "created_at": datetime.now(timezone.utc).isoformat()
                })

            # Settle spectator bets
            bets = await db.bets.find({"game_id": game_id, "status": "pending"}, {"_id": 0}).to_list(1000)
            total_pool = sum(b['amount'] for b in bets)
            winning_bets = [b for b in bets if b['agent_id'] == updated.get('winner_id')]
            total_winning = sum(b['amount'] for b in winning_bets)
            for bet in bets:
                if bet['agent_id'] == updated.get('winner_id') and total_winning > 0:
                    payout = int((bet['amount'] / total_winning) * total_pool * 0.8)
                    await db.bets.update_one({"id": bet['id']}, {"$set": {"status": "won", "payout": payout}})
                    cf = f"{bet['currency']}_balance"
                    await db.wallets.update_one({"user_id": bet['user_id']}, {"$inc": {cf: payout}})
                else:
                    await db.bets.update_one({"id": bet['id']}, {"$set": {"status": "lost", "payout": 0}})

            if updated.get('table_id'):
                await db.tables.update_one({"id": updated['table_id']}, {"$set": {"status": "waiting"}})

    save_doc = {k: v for k, v in updated.items() if k != '_id'}
    await db.games.replace_one({"id": game_id}, save_doc)

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


@router.post("/game/{game_id}/start")
async def start_game_for_table(game_id: str, user=Depends(get_current_user)):
    """Start a new game on a table. game_id here is actually the TABLE id."""
    agent = await _get_agent_for_user(user)
    table = await db.tables.find_one({"id": game_id}, {"_id": 0})
    if not table:
        raise HTTPException(status_code=404, detail="Table not found")

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
    await db.tables.update_one({"id": game_id}, {"$set": {"current_game_id": new_game_id, "status": "playing"}})

    # Auto-deal hole cards
    updated = advance_game(game)
    save_doc = {k: v for k, v in updated.items() if k != '_id'}
    await db.games.replace_one({"id": new_game_id}, save_doc)

    return {
        "game_id": new_game_id,
        "table": table['name'],
        "game": sanitize_game_for_agent(updated, agent['id'])
    }


@router.post("/game/{game_id}/advance-others")
async def advance_other_agents(game_id: str, user=Depends(get_current_user)):
    """
    Advance the game through all non-external agent turns and deal phases
    until it's your agent's turn again (or the game completes).
    This lets you skip the waiting and auto-play house agents.
    """
    agent = await _get_agent_for_user(user)
    game = await db.games.find_one({"id": game_id}, {"_id": 0})
    if not game:
        raise HTTPException(status_code=404, detail="Game not found")
    if game['phase'] == 'complete':
        return {"game": sanitize_game_for_agent(game, agent['id']), "advances": 0}

    advances = 0
    max_advances = 50  # Safety limit

    while advances < max_advances:
        if game['phase'] == 'complete':
            break
        if game.get('current_actor') == agent['id']:
            break  # It's your turn, stop advancing

        game = advance_game(game)
        advances += 1

        # Handle game completion
        if game['phase'] == 'complete':
            game['completed_at'] = datetime.now(timezone.utc).isoformat()
            if game.get('winner_id'):
                await db.agents.update_one(
                    {"id": game['winner_id']},
                    {"$inc": {"wins": 1, "total_games": 1, "total_chips_won": game.get('final_pot', 0)}}
                )
                for p in game['players']:
                    if p['agent_id'] != game['winner_id']:
                        await db.agents.update_one(
                            {"id": p['agent_id']},
                            {"$inc": {"losses": 1, "total_games": 1}}
                        )
                winner_agent = await db.agents.find_one({"id": game['winner_id']}, {"_id": 0})
                if winner_agent and winner_agent.get('owner_id'):
                    winnings = game.get('final_pot', 0)
                    sc_credit = max(1, winnings // 10)
                    await db.wallets.update_one(
                        {"user_id": winner_agent['owner_id']},
                        {"$inc": {"sc_balance": sc_credit}}
                    )
                if game.get('table_id'):
                    await db.tables.update_one({"id": game['table_id']}, {"$set": {"status": "waiting"}})
            break

    save_doc = {k: v for k, v in game.items() if k != '_id'}
    await db.games.replace_one({"id": game_id}, save_doc)

    # Broadcast
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
        "game": sanitize_game_for_agent(game, agent['id'])
    }


@router.get("/wallet")
async def get_wallet(user=Depends(get_current_user)):
    """Get your wallet balance."""
    await _get_agent_for_user(user)
    wallet = await db.wallets.find_one({"user_id": user['id']}, {"_id": 0})
    if not wallet:
        raise HTTPException(status_code=404, detail="Wallet not found")
    return {
        "sc_balance": wallet.get('sc_balance', 0),
        "gc_balance": wallet.get('gc_balance', 0),
    }
