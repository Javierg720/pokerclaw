from fastapi import FastAPI, APIRouter, HTTPException, Depends, WebSocket, WebSocketDisconnect
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
import os
import logging
import uuid
import jwt
import bcrypt
import random
from pathlib import Path
from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import datetime, timezone
from game_engine import (
    create_deck, advance_game, best_hand,
    AGENT_PRESETS, AVATAR_URLS
)

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ['DB_NAME']]
JWT_SECRET = os.environ.get('JWT_SECRET', 'pokerclaw_fallback_secret')

app = FastAPI()
api_router = APIRouter(prefix="/api")
security = HTTPBearer(auto_error=False)

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# ─── Helpers ───

def create_token(user_id: str, username: str):
    return jwt.encode(
        {"user_id": user_id, "username": username, "exp": datetime.now(timezone.utc).timestamp() + 604800},
        JWT_SECRET, algorithm="HS256"
    )

async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)):
    if not credentials:
        raise HTTPException(status_code=401, detail="Not authenticated")
    try:
        payload = jwt.decode(credentials.credentials, JWT_SECRET, algorithms=["HS256"])
        user = await db.users.find_one({"id": payload["user_id"]}, {"_id": 0})
        if not user:
            raise HTTPException(status_code=401, detail="User not found")
        return user
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid token")

def sanitize_game_for_response(game, show_cards=False):
    """Remove deck and optionally hide hole cards"""
    g = {k: v for k, v in game.items() if k not in ('_id', 'deck')}
    if not show_cards and g.get('phase') not in ('showdown', 'complete'):
        for p in g.get('players', []):
            p['hole_cards'] = [None, None]
    return g


# ─── WebSocket Manager ───

class TableManager:
    def __init__(self):
        self.connections: dict[str, set] = {}

    async def connect(self, table_id: str, ws: WebSocket):
        await ws.accept()
        if table_id not in self.connections:
            self.connections[table_id] = set()
        self.connections[table_id].add(ws)
        await self.broadcast_spectators(table_id)

    async def disconnect(self, table_id: str, ws: WebSocket):
        self.connections.get(table_id, set()).discard(ws)
        await self.broadcast_spectators(table_id)

    def get_count(self, table_id: str) -> int:
        return len(self.connections.get(table_id, set()))

    async def broadcast_spectators(self, table_id: str):
        await self.broadcast(table_id, {"type": "spectators", "count": self.get_count(table_id)})

    async def broadcast_game_state(self, table_id: str, game: dict):
        sanitized = sanitize_game_for_response(game)
        await self.broadcast(table_id, {"type": "game_state", "game": sanitized})

    async def broadcast(self, table_id: str, message: dict):
        dead = set()
        for ws in self.connections.get(table_id, set()).copy():
            try:
                await ws.send_json(message)
            except Exception:
                dead.add(ws)
        self.connections.get(table_id, set()).difference_update(dead)

table_mgr = TableManager()


# ─── Models ───

class SignupRequest(BaseModel):
    username: str
    email: str
    password: str

class LoginRequest(BaseModel):
    email: str
    password: str

class BetRequest(BaseModel):
    game_id: str
    agent_id: str
    amount: int
    currency: str = "gc"

class PurchaseRequest(BaseModel):
    amount: int
    currency: str = "sc"

class CashoutRequest(BaseModel):
    amount: int

class TournamentBetRequest(BaseModel):
    tournament_id: str
    agent_id: str
    amount: int
    currency: str = "gc"


# ─── Auth ───

@api_router.post("/auth/signup")
async def signup(req: SignupRequest):
    existing = await db.users.find_one({"email": req.email}, {"_id": 0})
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")
    existing_name = await db.users.find_one({"username": req.username}, {"_id": 0})
    if existing_name:
        raise HTTPException(status_code=400, detail="Username taken")

    hashed = bcrypt.hashpw(req.password.encode(), bcrypt.gensalt()).decode()
    user_id = str(uuid.uuid4())
    user = {
        "id": user_id,
        "username": req.username,
        "email": req.email,
        "password_hash": hashed,
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    await db.users.insert_one(user)

    # Create wallet with starting balance
    wallet = {
        "id": str(uuid.uuid4()),
        "user_id": user_id,
        "gc_balance": 10000,
        "sc_balance": 100,
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    await db.wallets.insert_one(wallet)

    # Welcome bonus transaction
    await db.transactions.insert_one({
        "id": str(uuid.uuid4()),
        "user_id": user_id,
        "type": "bonus",
        "amount": 10000,
        "currency": "gc",
        "description": "Welcome bonus - Gold Coins",
        "created_at": datetime.now(timezone.utc).isoformat()
    })
    await db.transactions.insert_one({
        "id": str(uuid.uuid4()),
        "user_id": user_id,
        "type": "bonus",
        "amount": 100,
        "currency": "sc",
        "description": "Welcome bonus - Sweepstakes Coins",
        "created_at": datetime.now(timezone.utc).isoformat()
    })

    token = create_token(user_id, req.username)
    return {
        "token": token,
        "user": {"id": user_id, "username": req.username, "email": req.email}
    }


@api_router.post("/auth/login")
async def login(req: LoginRequest):
    user = await db.users.find_one({"email": req.email}, {"_id": 0})
    if not user or not bcrypt.checkpw(req.password.encode(), user['password_hash'].encode()):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    token = create_token(user['id'], user['username'])
    return {
        "token": token,
        "user": {"id": user['id'], "username": user['username'], "email": user['email']}
    }


@api_router.get("/auth/me")
async def get_me(user=Depends(get_current_user)):
    return {"id": user['id'], "username": user['username'], "email": user['email']}


# ─── Agents ───

@api_router.get("/agents")
async def list_agents():
    agents = await db.agents.find({}, {"_id": 0}).to_list(100)
    return agents


# ─── Tables ───

@api_router.get("/tables")
async def list_tables():
    tables = await db.tables.find({}, {"_id": 0}).to_list(100)
    for table in tables:
        table['spectators'] = table_mgr.get_count(table['id'])
        if table.get('current_game_id'):
            game = await db.games.find_one({"id": table['current_game_id']}, {"_id": 0, "deck": 0})
            if game:
                table['current_game'] = {
                    "id": game['id'],
                    "phase": game['phase'],
                    "pot": game['pot'],
                    "player_count": len(game.get('players', []))
                }
    return tables


@api_router.get("/tables/{table_id}")
async def get_table(table_id: str):
    table = await db.tables.find_one({"id": table_id}, {"_id": 0})
    if not table:
        raise HTTPException(status_code=404, detail="Table not found")

    if table.get('current_game_id'):
        game = await db.games.find_one({"id": table['current_game_id']}, {"_id": 0})
        if game:
            table['current_game'] = sanitize_game_for_response(game)
    return table


# ─── Games ───

@api_router.post("/tables/{table_id}/start-game")
async def start_game(table_id: str, user=Depends(get_current_user)):
    table = await db.tables.find_one({"id": table_id}, {"_id": 0})
    if not table:
        raise HTTPException(status_code=404, detail="Table not found")

    # Check if there's an active game
    if table.get('current_game_id'):
        existing = await db.games.find_one({"id": table['current_game_id']}, {"_id": 0})
        if existing and existing['phase'] not in ('complete', 'showdown'):
            raise HTTPException(status_code=400, detail="Game already in progress")

    # Get agents for this table
    agents = []
    for aid in table['agent_ids']:
        agent = await db.agents.find_one({"id": aid}, {"_id": 0})
        if agent:
            agents.append(agent)

    deck = create_deck()
    game_id = str(uuid.uuid4())
    players = []
    for i, agent in enumerate(agents):
        players.append({
            "agent_id": agent['id'],
            "agent_name": agent['name'],
            "avatar_url": agent['avatar_url'],
            "strategy": agent['strategy'],
            "hole_cards": [],
            "chips": 1000,
            "current_bet": 0,
            "total_bet": 0,
            "folded": False,
            "is_dealer": i == 0,
            "hand_rank": 0,
            "hand_name": ""
        })

    game = {
        "id": game_id,
        "table_id": table_id,
        "phase": "waiting",
        "players": players,
        "community_cards": [],
        "pot": 0,
        "deck": deck,
        "dealer_index": 0,
        "actions_log": [],
        "winner_id": None,
        "winner_name": None,
        "winning_hand": None,
        "house_rake": 0,
        "final_pot": 0,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "completed_at": None
    }

    await db.games.insert_one(game)
    await db.tables.update_one({"id": table_id}, {"$set": {"current_game_id": game_id}})

    await table_mgr.broadcast_game_state(table_id, game)
    return sanitize_game_for_response(game)


@api_router.get("/games/{game_id}")
async def get_game(game_id: str):
    game = await db.games.find_one({"id": game_id}, {"_id": 0})
    if not game:
        raise HTTPException(status_code=404, detail="Game not found")
    return sanitize_game_for_response(game)


@api_router.post("/games/{game_id}/advance")
async def advance_game_endpoint(game_id: str, user=Depends(get_current_user)):
    game = await db.games.find_one({"id": game_id}, {"_id": 0})
    if not game:
        raise HTTPException(status_code=404, detail="Game not found")
    if game['phase'] == 'complete':
        raise HTTPException(status_code=400, detail="Game already complete")

    # Advance the game
    updated = advance_game(game)

    if updated['phase'] == 'complete':
        updated['completed_at'] = datetime.now(timezone.utc).isoformat()
        # Update agent stats
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

        # Settle bets
        bets = await db.bets.find({"game_id": game_id, "status": "pending"}, {"_id": 0}).to_list(1000)
        total_bet_pool = sum(b['amount'] for b in bets)
        winning_bets = [b for b in bets if b['agent_id'] == updated.get('winner_id')]
        total_winning_bets = sum(b['amount'] for b in winning_bets)

        for bet in bets:
            if bet['agent_id'] == updated.get('winner_id') and total_winning_bets > 0:
                payout = int((bet['amount'] / total_winning_bets) * total_bet_pool * 0.8)
                await db.bets.update_one({"id": bet['id']}, {"$set": {"status": "won", "payout": payout}})
                currency_field = f"{bet['currency']}_balance"
                await db.wallets.update_one(
                    {"user_id": bet['user_id']},
                    {"$inc": {currency_field: payout}}
                )
                await db.transactions.insert_one({
                    "id": str(uuid.uuid4()),
                    "user_id": bet['user_id'],
                    "type": "bet_won",
                    "amount": payout,
                    "currency": bet['currency'],
                    "description": f"Won bet on {updated.get('winner_name', 'agent')}",
                    "created_at": datetime.now(timezone.utc).isoformat()
                })
            else:
                await db.bets.update_one({"id": bet['id']}, {"$set": {"status": "lost", "payout": 0}})

    # Save to DB (remove _id if present to avoid issues)
    save_doc = {k: v for k, v in updated.items() if k != '_id'}
    await db.games.replace_one({"id": game_id}, save_doc)

    # Broadcast to spectators
    table_id = updated.get('table_id')
    if table_id:
        await table_mgr.broadcast_game_state(table_id, updated)

    return sanitize_game_for_response(updated)


# ─── Bets ───

@api_router.post("/bets")
async def place_bet(req: BetRequest, user=Depends(get_current_user)):
    game = await db.games.find_one({"id": req.game_id}, {"_id": 0})
    if not game:
        raise HTTPException(status_code=404, detail="Game not found")
    if game['phase'] in ('showdown', 'complete'):
        raise HTTPException(status_code=400, detail="Cannot bet on completed game")

    # Check agent is in game
    agent_ids = [p['agent_id'] for p in game['players']]
    if req.agent_id not in agent_ids:
        raise HTTPException(status_code=400, detail="Agent not in this game")

    # Check wallet balance
    wallet = await db.wallets.find_one({"user_id": user['id']}, {"_id": 0})
    if not wallet:
        raise HTTPException(status_code=400, detail="Wallet not found")

    balance_field = f"{req.currency}_balance"
    if wallet.get(balance_field, 0) < req.amount:
        raise HTTPException(status_code=400, detail="Insufficient balance")

    # Deduct from wallet
    await db.wallets.update_one(
        {"user_id": user['id']},
        {"$inc": {balance_field: -req.amount}}
    )

    bet_id = str(uuid.uuid4())
    bet = {
        "id": bet_id,
        "user_id": user['id'],
        "username": user['username'],
        "game_id": req.game_id,
        "agent_id": req.agent_id,
        "amount": req.amount,
        "currency": req.currency,
        "status": "pending",
        "payout": 0,
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    await db.bets.insert_one(bet)

    # Record transaction
    await db.transactions.insert_one({
        "id": str(uuid.uuid4()),
        "user_id": user['id'],
        "type": "bet_placed",
        "amount": -req.amount,
        "currency": req.currency,
        "description": f"Bet on game {req.game_id[:8]}...",
        "created_at": datetime.now(timezone.utc).isoformat()
    })

    return {"id": bet_id, "status": "pending", "amount": req.amount}


@api_router.get("/bets/my-bets")
async def get_my_bets(user=Depends(get_current_user)):
    bets = await db.bets.find({"user_id": user['id']}, {"_id": 0}).sort("created_at", -1).to_list(100)
    return bets


@api_router.get("/bets/game/{game_id}")
async def get_game_bets(game_id: str):
    bets = await db.bets.find({"game_id": game_id}, {"_id": 0}).to_list(1000)
    return bets


# ─── Wallet ───

@api_router.get("/wallet")
async def get_wallet(user=Depends(get_current_user)):
    wallet = await db.wallets.find_one({"user_id": user['id']}, {"_id": 0})
    if not wallet:
        raise HTTPException(status_code=404, detail="Wallet not found")
    return wallet


@api_router.post("/wallet/purchase")
async def purchase_coins(req: PurchaseRequest, user=Depends(get_current_user)):
    currency_field = f"{req.currency}_balance"
    await db.wallets.update_one(
        {"user_id": user['id']},
        {"$inc": {currency_field: req.amount}}
    )
    await db.transactions.insert_one({
        "id": str(uuid.uuid4()),
        "user_id": user['id'],
        "type": "purchase",
        "amount": req.amount,
        "currency": req.currency,
        "description": f"Purchased {req.amount} {req.currency.upper()}",
        "created_at": datetime.now(timezone.utc).isoformat()
    })
    wallet = await db.wallets.find_one({"user_id": user['id']}, {"_id": 0})
    return wallet


@api_router.post("/wallet/cashout")
async def cashout(req: CashoutRequest, user=Depends(get_current_user)):
    wallet = await db.wallets.find_one({"user_id": user['id']}, {"_id": 0})
    if not wallet or wallet.get('sc_balance', 0) < req.amount:
        raise HTTPException(status_code=400, detail="Insufficient SC balance")

    await db.wallets.update_one(
        {"user_id": user['id']},
        {"$inc": {"sc_balance": -req.amount}}
    )
    await db.transactions.insert_one({
        "id": str(uuid.uuid4()),
        "user_id": user['id'],
        "type": "cashout",
        "amount": -req.amount,
        "currency": "sc",
        "description": f"Cashout {req.amount} SC to crypto (pending)",
        "created_at": datetime.now(timezone.utc).isoformat()
    })
    wallet = await db.wallets.find_one({"user_id": user['id']}, {"_id": 0})
    return {"message": "Cashout initiated", "wallet": wallet}


@api_router.get("/wallet/transactions")
async def get_transactions(user=Depends(get_current_user)):
    txns = await db.transactions.find(
        {"user_id": user['id']}, {"_id": 0}
    ).sort("created_at", -1).to_list(100)
    return txns


# ─── Leaderboard ───

@api_router.get("/leaderboard")
async def get_leaderboard():
    # Top agents by wins
    agents = await db.agents.find({}, {"_id": 0}).sort("wins", -1).to_list(20)

    # Top bettors by total winnings (aggregate)
    pipeline = [
        {"$match": {"status": "won"}},
        {"$group": {"_id": "$user_id", "username": {"$first": "$username"}, "total_won": {"$sum": "$payout"}, "bets_won": {"$sum": 1}}},
        {"$sort": {"total_won": -1}},
        {"$limit": 20}
    ]
    top_bettors = await db.bets.aggregate(pipeline).to_list(20)
    for b in top_bettors:
        b['user_id'] = b.pop('_id')

    return {"top_agents": agents, "top_bettors": top_bettors}


# ─── WebSocket ───

@app.websocket("/api/ws/table/{table_id}")
async def websocket_table(websocket: WebSocket, table_id: str):
    await table_mgr.connect(table_id, websocket)
    try:
        table = await db.tables.find_one({"id": table_id}, {"_id": 0})
        if table and table.get('current_game_id'):
            game = await db.games.find_one({"id": table['current_game_id']}, {"_id": 0})
            if game:
                await websocket.send_json({"type": "game_state", "game": sanitize_game_for_response(game)})

        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        await table_mgr.disconnect(table_id, websocket)
    except Exception:
        await table_mgr.disconnect(table_id, websocket)


# ─── Tournaments ───

TOURNEY_NAMES = [
    "Claw Championship", "Moltbook Masters", "Deep Stack Showdown",
    "OpenClaw Open", "Agent Arena Finals", "Bot Battle Royale",
]

@api_router.get("/tournaments")
async def list_tournaments():
    return await db.tournaments.find({}, {"_id": 0}).sort("created_at", -1).to_list(50)


@api_router.get("/tournaments/{tournament_id}")
async def get_tournament(tournament_id: str):
    t = await db.tournaments.find_one({"id": tournament_id}, {"_id": 0})
    if not t:
        raise HTTPException(status_code=404, detail="Tournament not found")
    return t


@api_router.post("/tournaments")
async def create_tournament(user=Depends(get_current_user)):
    agents = await db.agents.find({}, {"_id": 0}).to_list(100)
    if len(agents) < 8:
        raise HTTPException(status_code=400, detail="Need at least 8 agents")

    picked = random.sample(agents, 8)
    random.shuffle(picked)
    agent_ids = [a['id'] for a in picked]

    tid = str(uuid.uuid4())
    tournament = {
        "id": tid,
        "name": random.choice(TOURNEY_NAMES),
        "status": "lobby",
        "agent_ids": agent_ids,
        "bracket": {
            "semi_1": {"agent_ids": agent_ids[:4], "game_id": None, "winners": [], "complete": False, "game_phase": None},
            "semi_2": {"agent_ids": agent_ids[4:], "game_id": None, "winners": [], "complete": False, "game_phase": None},
            "final": {"agent_ids": [], "game_id": None, "winner": None, "complete": False, "game_phase": None},
        },
        "champion_id": None,
        "champion_name": None,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "completed_at": None,
    }
    await db.tournaments.insert_one(tournament)
    return {k: v for k, v in tournament.items() if k != '_id'}


async def _create_tournament_game(agent_ids_list):
    """Create and fully play a tournament game, return the game doc."""
    agents = []
    for aid in agent_ids_list:
        agent = await db.agents.find_one({"id": aid}, {"_id": 0})
        if agent:
            agents.append(agent)

    deck = create_deck()
    game_id = str(uuid.uuid4())
    players = []
    for i, agent in enumerate(agents):
        players.append({
            "agent_id": agent['id'], "agent_name": agent['name'],
            "avatar_url": agent['avatar_url'], "strategy": agent['strategy'],
            "hole_cards": [], "chips": 1000, "current_bet": 0,
            "total_bet": 0, "folded": False, "is_dealer": i == 0,
            "hand_rank": 0, "hand_name": ""
        })

    game = {
        "id": game_id, "table_id": None, "phase": "waiting",
        "players": players, "community_cards": [], "pot": 0,
        "deck": deck, "dealer_index": 0, "actions_log": [],
        "winner_id": None, "winner_name": None, "winning_hand": None,
        "house_rake": 0, "final_pot": 0,
        "created_at": datetime.now(timezone.utc).isoformat(), "completed_at": None
    }
    await db.games.insert_one(game)
    return game_id


async def _advance_tournament_game(game_id):
    """Advance a tournament game by one phase, return updated game."""
    game = await db.games.find_one({"id": game_id}, {"_id": 0})
    if not game or game['phase'] == 'complete':
        return game

    updated = advance_game(game)
    if updated['phase'] == 'complete':
        updated['completed_at'] = datetime.now(timezone.utc).isoformat()

    save_doc = {k: v for k, v in updated.items() if k != '_id'}
    await db.games.replace_one({"id": game_id}, save_doc)
    return updated


def _get_top2(game):
    """Get top 2 agent_ids from a completed game (winner + runner-up)."""
    if not game or game['phase'] != 'complete':
        return []
    winner_id = game.get('winner_id')
    players = game.get('players', [])
    active = [p for p in players if not p.get('folded') and p['agent_id'] != winner_id]
    active.sort(key=lambda p: (p.get('hand_rank', 0), p.get('chips', 0)), reverse=True)
    runner_id = active[0]['agent_id'] if active else (players[0]['agent_id'] if players else None)
    result = [winner_id]
    if runner_id and runner_id != winner_id:
        result.append(runner_id)
    return result


@api_router.post("/tournaments/{tournament_id}/advance")
async def advance_tournament(tournament_id: str, user=Depends(get_current_user)):
    t = await db.tournaments.find_one({"id": tournament_id}, {"_id": 0})
    if not t:
        raise HTTPException(status_code=404, detail="Tournament not found")
    if t['status'] == 'complete':
        raise HTTPException(status_code=400, detail="Tournament already complete")

    bracket = t['bracket']

    if t['status'] == 'lobby':
        # Start semi-finals: create games
        gid1 = await _create_tournament_game(bracket['semi_1']['agent_ids'])
        gid2 = await _create_tournament_game(bracket['semi_2']['agent_ids'])
        bracket['semi_1']['game_id'] = gid1
        bracket['semi_2']['game_id'] = gid2
        bracket['semi_1']['game_phase'] = 'waiting'
        bracket['semi_2']['game_phase'] = 'waiting'
        t['status'] = 'semis'

    elif t['status'] == 'semis':
        # Advance semi games
        for semi_key in ['semi_1', 'semi_2']:
            semi = bracket[semi_key]
            if not semi['complete'] and semi['game_id']:
                game = await _advance_tournament_game(semi['game_id'])
                semi['game_phase'] = game.get('phase', 'unknown') if game else None
                if game and game['phase'] == 'complete':
                    semi['complete'] = True
                    semi['winners'] = _get_top2(game)

        # If both semis done, create final
        if bracket['semi_1']['complete'] and bracket['semi_2']['complete']:
            final_agents = bracket['semi_1']['winners'] + bracket['semi_2']['winners']
            bracket['final']['agent_ids'] = final_agents
            gid_final = await _create_tournament_game(final_agents)
            bracket['final']['game_id'] = gid_final
            bracket['final']['game_phase'] = 'waiting'
            t['status'] = 'final'

    elif t['status'] == 'final':
        final = bracket['final']
        if not final['complete'] and final['game_id']:
            game = await _advance_tournament_game(final['game_id'])
            final['game_phase'] = game.get('phase', 'unknown') if game else None
            if game and game['phase'] == 'complete':
                final['complete'] = True
                final['winner'] = game.get('winner_id')
                t['champion_id'] = game.get('winner_id')
                t['champion_name'] = game.get('winner_name')
                t['status'] = 'complete'
                t['completed_at'] = datetime.now(timezone.utc).isoformat()

                # Settle tournament bets
                bets = await db.tournament_bets.find(
                    {"tournament_id": tournament_id, "status": "pending"}, {"_id": 0}
                ).to_list(1000)
                total_pool = sum(b['amount'] for b in bets)
                winning_bets = [b for b in bets if b['agent_id'] == t['champion_id']]
                total_winning = sum(b['amount'] for b in winning_bets)

                for bet in bets:
                    if bet['agent_id'] == t['champion_id'] and total_winning > 0:
                        payout = int((bet['amount'] / total_winning) * total_pool * 0.8)
                        await db.tournament_bets.update_one(
                            {"id": bet['id']}, {"$set": {"status": "won", "payout": payout}})
                        cf = f"{bet['currency']}_balance"
                        await db.wallets.update_one({"user_id": bet['user_id']}, {"$inc": {cf: payout}})
                        await db.transactions.insert_one({
                            "id": str(uuid.uuid4()), "user_id": bet['user_id'],
                            "type": "tournament_won", "amount": payout,
                            "currency": bet['currency'],
                            "description": f"Won tournament bet on {t['champion_name']}",
                            "created_at": datetime.now(timezone.utc).isoformat()
                        })
                    else:
                        await db.tournament_bets.update_one(
                            {"id": bet['id']}, {"$set": {"status": "lost", "payout": 0}})

    t['bracket'] = bracket
    save_doc = {k: v for k, v in t.items() if k != '_id'}
    await db.tournaments.replace_one({"id": tournament_id}, save_doc)
    return save_doc


@api_router.post("/tournament-bets")
async def place_tournament_bet(req: TournamentBetRequest, user=Depends(get_current_user)):
    t = await db.tournaments.find_one({"id": req.tournament_id}, {"_id": 0})
    if not t:
        raise HTTPException(status_code=404, detail="Tournament not found")
    if t['status'] == 'complete':
        raise HTTPException(status_code=400, detail="Tournament already complete")

    # Check agent is in tournament
    if req.agent_id not in t.get('agent_ids', []):
        raise HTTPException(status_code=400, detail="Agent not in this tournament")

    wallet = await db.wallets.find_one({"user_id": user['id']}, {"_id": 0})
    cf = f"{req.currency}_balance"
    if not wallet or wallet.get(cf, 0) < req.amount:
        raise HTTPException(status_code=400, detail="Insufficient balance")

    await db.wallets.update_one({"user_id": user['id']}, {"$inc": {cf: -req.amount}})

    bet = {
        "id": str(uuid.uuid4()), "user_id": user['id'], "username": user['username'],
        "tournament_id": req.tournament_id, "agent_id": req.agent_id,
        "amount": req.amount, "currency": req.currency,
        "status": "pending", "payout": 0,
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    await db.tournament_bets.insert_one(bet)

    await db.transactions.insert_one({
        "id": str(uuid.uuid4()), "user_id": user['id'],
        "type": "tournament_bet", "amount": -req.amount,
        "currency": req.currency,
        "description": f"Tournament bet placed",
        "created_at": datetime.now(timezone.utc).isoformat()
    })
    return {"id": bet['id'], "status": "pending"}


# ─── Startup - Seed Data ───

@app.on_event("startup")
async def seed_data():
    # Seed agents
    agent_count = await db.agents.count_documents({})
    if agent_count == 0:
        logger.info("Seeding agents...")
        for preset in AGENT_PRESETS:
            agent = {
                "id": str(uuid.uuid4()),
                "name": preset['name'],
                "strategy": preset['strategy'],
                "avatar_url": AVATAR_URLS[preset['avatar_index']],
                "tagline": preset['tagline'],
                "wins": 0,
                "losses": 0,
                "total_games": 0,
                "total_chips_won": 0,
                "created_at": datetime.now(timezone.utc).isoformat()
            }
            await db.agents.insert_one(agent)

    # Seed/update tables
    table_count = await db.tables.count_documents({})
    agents = await db.agents.find({}, {"_id": 0}).to_list(100)
    agent_ids = [a['id'] for a in agents]

    tables_config = [
        {"name": "The Claw Pit", "min_bet": 10, "max_bet": 500,
         "agent_slice": (0, 4), "description": "High-stakes action with the fiercest bots"},
        {"name": "Moltbook Arena", "min_bet": 5, "max_bet": 200,
         "agent_slice": (0, 5), "description": "5-way battle where legends are born"},
        {"name": "Deep Stack Den", "min_bet": 20, "max_bet": 1000,
         "agent_slice": (0, 6), "description": "6-handed deep-pocket showdown"},
    ]

    for config in tables_config:
        existing = await db.tables.find_one({"name": config["name"]}, {"_id": 0})
        target_ids = agent_ids[config["agent_slice"][0]:config["agent_slice"][1]]

        if existing:
            if len(existing.get("agent_ids", [])) != len(target_ids):
                await db.tables.update_one(
                    {"name": config["name"]},
                    {"$set": {"agent_ids": target_ids, "description": config["description"],
                              "current_game_id": None}}
                )
                logger.info(f"Updated {config['name']} to {len(target_ids)} agents")
        else:
            table = {
                "id": str(uuid.uuid4()),
                "name": config["name"],
                "min_bet": config["min_bet"],
                "max_bet": config["max_bet"],
                "agent_ids": target_ids,
                "current_game_id": None,
                "status": "active",
                "description": config["description"],
                "created_at": datetime.now(timezone.utc).isoformat()
            }
            await db.tables.insert_one(table)

    logger.info("PokerClaw backend ready!")


# ─── Include Router + CORS ───

app.include_router(api_router)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get('CORS_ORIGINS', '*').split(','),
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()
