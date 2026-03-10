from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
import uuid
import bcrypt
import random
from datetime import datetime, timezone
from deps import db, create_token, get_current_user, generate_crypto_addresses
from game_engine import STRATEGIES, AVATAR_URLS

router = APIRouter(prefix="/api")


class SignupRequest(BaseModel):
    username: str
    email: str
    password: str
    role: str = "human"
    agent_name: str | None = None


class LoginRequest(BaseModel):
    email: str
    password: str


@router.post("/auth/signup")
async def signup(req: SignupRequest):
    if req.role not in ("agent", "human"):
        raise HTTPException(status_code=400, detail="Role must be 'agent' or 'human'")

    existing = await db.users.find_one({"email": req.email}, {"_id": 0})
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")
    existing_name = await db.users.find_one({"username": req.username}, {"_id": 0})
    if existing_name:
        raise HTTPException(status_code=400, detail="Username taken")

    hashed = bcrypt.hashpw(req.password.encode(), bcrypt.gensalt()).decode()
    user_id = str(uuid.uuid4())
    user = {
        "id": user_id, "username": req.username, "email": req.email,
        "password_hash": hashed, "role": req.role, "agent_id": None,
        "created_at": datetime.now(timezone.utc).isoformat()
    }

    agent_data = None
    if req.role == "agent":
        agent_name = req.agent_name or f"MoltBot_{req.username}"
        existing_agent = await db.agents.find_one({"name": agent_name}, {"_id": 0})
        if existing_agent:
            raise HTTPException(status_code=400, detail="Agent name already taken")

        strategies = list(STRATEGIES.keys())
        agent_id = str(uuid.uuid4())
        agent = {
            "id": agent_id, "name": agent_name,
            "strategy": random.choice(strategies),
            "avatar_url": random.choice(AVATAR_URLS),
            "tagline": f"Autonomous MoltBot agent owned by {req.username}",
            "owner_id": user_id, "is_house": False,
            "wins": 0, "losses": 0, "total_games": 0, "total_chips_won": 0,
            "created_at": datetime.now(timezone.utc).isoformat()
        }
        await db.agents.insert_one(agent)
        user["agent_id"] = agent_id
        agent_data = {k: v for k, v in agent.items() if k != "_id"}

    await db.users.insert_one(user)

    crypto_addresses = generate_crypto_addresses(user_id) if req.role == "agent" else None
    wallet = {
        "id": str(uuid.uuid4()), "user_id": user_id,
        "sc_balance": 0, "gc_balance": 0,
        "crypto_addresses": crypto_addresses, "pending_deposits": [],
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    await db.wallets.insert_one(wallet)

    token = create_token(user_id, req.username, req.role)
    return {
        "token": token,
        "user": {
            "id": user_id, "username": req.username,
            "email": req.email, "role": req.role,
            "agent_id": user.get("agent_id")
        },
        "agent": agent_data
    }


@router.post("/auth/login")
async def login(req: LoginRequest):
    user = await db.users.find_one({"email": req.email}, {"_id": 0})
    if not user or not bcrypt.checkpw(req.password.encode(), user['password_hash'].encode()):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    role = user.get('role', 'human')
    token = create_token(user['id'], user['username'], role)
    return {
        "token": token,
        "user": {
            "id": user['id'], "username": user['username'],
            "email": user['email'], "role": role,
            "agent_id": user.get('agent_id')
        }
    }


@router.get("/auth/me")
async def get_me(user=Depends(get_current_user)):
    result = {
        "id": user['id'], "username": user['username'],
        "email": user['email'], "role": user.get('role', 'human'),
        "agent_id": user.get('agent_id')
    }
    if user.get('agent_id'):
        agent = await db.agents.find_one({"id": user['agent_id']}, {"_id": 0})
        if agent:
            result['agent'] = agent
    return result
