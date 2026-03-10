from fastapi import FastAPI, APIRouter, HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
import os
import logging
import uuid
import jwt
import bcrypt
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
        {"user_id": user_id, "username": username, "exp": datetime.now(timezone.utc).timestamp() + 86400},
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
    # Attach current game info
    for table in tables:
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

    # Seed tables
    table_count = await db.tables.count_documents({})
    if table_count == 0:
        logger.info("Seeding tables...")
        agents = await db.agents.find({}, {"_id": 0}).to_list(100)
        agent_ids = [a['id'] for a in agents]

        tables = [
            {"id": str(uuid.uuid4()), "name": "The Claw Pit", "min_bet": 10, "max_bet": 500,
             "agent_ids": agent_ids[:4], "current_game_id": None, "status": "active",
             "description": "High-stakes action with the fiercest bots"},
            {"id": str(uuid.uuid4()), "name": "Moltbook Arena", "min_bet": 5, "max_bet": 200,
             "agent_ids": agent_ids[2:6], "current_game_id": None, "status": "active",
             "description": "Where legends are born"},
            {"id": str(uuid.uuid4()), "name": "Deep Stack Den", "min_bet": 20, "max_bet": 1000,
             "agent_ids": agent_ids[4:8] if len(agent_ids) >= 8 else agent_ids[:4],
             "current_game_id": None, "status": "active",
             "description": "Only the deep-pocketed survive"},
        ]
        for t in tables:
            t['created_at'] = datetime.now(timezone.utc).isoformat()
            await db.tables.insert_one(t)

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
