from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from starlette.middleware.cors import CORSMiddleware
from deps import db, client, ensure_database_indexes, logger, get_user_from_token
from game_engine import AGENT_PRESETS, AVATAR_URLS
import os
import uuid
import json
import asyncio
import logging
from datetime import datetime, timezone

# ─── Route imports ───
from routes.auth import router as auth_router
from routes.agents import router as agents_router
from routes.tables import router as tables_router
from routes.bets import router as bets_router
from routes.wallet import router as wallet_router
from routes.stripe_routes import router as stripe_router
from routes.crypto import router as crypto_router
from routes.tournaments import router as tournaments_router
from routes.leaderboard import router as leaderboard_router
from routes.agent_api import router as agent_api_router
from routes.sweepstakes import router as sweepstakes_router
from routes.admin import router as admin_router
from sweepstakes import quarantine_legacy_human_sc

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

app = FastAPI(title="PokerClaw API")

# ─── Serve uploaded avatars as static files ───
UPLOAD_DIR = os.path.join(os.path.dirname(__file__), "uploads", "avatars")
os.makedirs(UPLOAD_DIR, exist_ok=True)
app.mount("/api/uploads/avatars", StaticFiles(directory=UPLOAD_DIR), name="avatar_uploads")


# ─── WebSocket Manager ───

class TableManager:
    def __init__(self):
        self.connections: dict[str, list[WebSocket]] = {}
        self.chat_history: dict[str, list[dict]] = {}

    def connect(self, table_id: str, ws: WebSocket):
        if table_id not in self.connections:
            self.connections[table_id] = []
        self.connections[table_id].append(ws)

    def disconnect(self, table_id: str, ws: WebSocket):
        if table_id in self.connections:
            self.connections[table_id] = [c for c in self.connections[table_id] if c != ws]
            if not self.connections[table_id]:
                del self.connections[table_id]

    async def broadcast(self, table_id: str, message: dict):
        if table_id not in self.connections:
            return
        dead = []
        for ws in self.connections[table_id]:
            try:
                await ws.send_json(message)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(table_id, ws)

    def spectator_count(self, table_id: str) -> int:
        return len(self.connections.get(table_id, []))

    def add_chat(self, table_id: str, msg: dict):
        if table_id not in self.chat_history:
            self.chat_history[table_id] = []
        self.chat_history[table_id].append(msg)
        # Keep last 50 messages
        self.chat_history[table_id] = self.chat_history[table_id][-50:]

    def get_chat(self, table_id: str) -> list:
        return self.chat_history.get(table_id, [])


table_manager = TableManager()


# ─── WebSocket endpoint ───

@app.websocket("/api/ws/table/{table_id}")
async def websocket_table(websocket: WebSocket, table_id: str):
    await websocket.accept()
    try:
        auth_message = json.loads(await asyncio.wait_for(websocket.receive_text(), timeout=5))
        if auth_message.get("type") != "auth" or not auth_message.get("token"):
            await websocket.close(code=1008, reason="Authentication required")
            return
        user = await get_user_from_token(auth_message["token"])
    except Exception:
        await websocket.close(code=1008, reason="Invalid authentication")
        return

    table_manager.connect(table_id, websocket)
    try:
        count = table_manager.spectator_count(table_id)
        await table_manager.broadcast(table_id, {"type": "spectator_count", "count": count})
        # Send chat history on connect
        history = table_manager.get_chat(table_id)
        if history:
            await websocket.send_json({"type": "chat_history", "messages": history})
        while True:
            data = await websocket.receive_text()
            try:
                msg = json.loads(data)
                if msg.get("type") == "ping":
                    await websocket.send_json({"type": "pong"})
                elif msg.get("type") == "chat":
                    text = msg.get("text", "")[:200]  # Limit length
                    if text.strip():
                        chat_msg = {
                            "type": "chat",
                            "username": user.get("username", "Spectator"),
                            "text": text,
                            "timestamp": datetime.now(timezone.utc).isoformat(),
                        }
                        table_manager.add_chat(table_id, chat_msg)
                        await table_manager.broadcast(table_id, chat_msg)
                elif msg.get("type") == "reaction":
                    emoji = msg.get("emoji", "")
                    if emoji in ("fire", "skull", "clap", "eyes", "money", "crown"):
                        await table_manager.broadcast(table_id, {
                            "type": "reaction",
                            "emoji": emoji,
                            "username": user.get("username", ""),
                        })
            except json.JSONDecodeError:
                pass
    except WebSocketDisconnect:
        table_manager.disconnect(table_id, websocket)
        count = table_manager.spectator_count(table_id)
        await table_manager.broadcast(table_id, {"type": "spectator_count", "count": count})


@app.post("/api/webhook/stripe")
async def disabled_stripe_webhook():
    raise HTTPException(
        status_code=410,
        detail="Stripe is not a supported funding provider for this sweepstakes product.",
    )


# ─── Startup - Seed Data ───

@app.on_event("startup")
async def seed_data():
    await ensure_database_indexes()
    await quarantine_legacy_human_sc()
    agent_count = await db.agents.count_documents({"is_house": True})
    if agent_count == 0:
        old_count = await db.agents.count_documents({})
        if old_count > 0:
            await db.agents.update_many(
                {"is_house": {"$exists": False}},
                {"$set": {"is_house": True, "owner_id": None}}
            )
            logger.info(f"Tagged {old_count} existing agents as house agents")
        else:
            logger.info("Seeding house agents...")
            for preset in AGENT_PRESETS:
                agent = {
                    "id": str(uuid.uuid4()), "name": preset['name'],
                    "strategy": preset['strategy'],
                    "avatar_url": AVATAR_URLS[preset['avatar_index']],
                    "tagline": preset['tagline'], "owner_id": None, "is_house": True,
                    "wins": 0, "losses": 0, "total_games": 0, "total_chips_won": 0,
                    "created_at": datetime.now(timezone.utc).isoformat()
                }
                await db.agents.insert_one(agent)

    # Seed/update tables
    agents = await db.agents.find({}, {"_id": 0}).to_list(100)
    table_configs = [
        {"name": "The Claw Pit", "agent_count": 4, "min_bet": 10, "max_bet": 500},
        {"name": "Moltbook Arena", "agent_count": 5, "min_bet": 25, "max_bet": 1000},
        {"name": "Deep Stack Den", "agent_count": 6, "min_bet": 50, "max_bet": 2000},
    ]

    for cfg in table_configs:
        existing = await db.tables.find_one({"name": cfg['name']}, {"_id": 0})
        if not existing and len(agents) >= cfg['agent_count']:
            selected = [a['id'] for a in agents[:cfg['agent_count']]]
            table = {
                "id": str(uuid.uuid4()), "name": cfg['name'],
                "min_bet": cfg['min_bet'], "max_bet": cfg['max_bet'],
                "agent_ids": selected, "current_game_id": None, "status": "waiting",
                "created_at": datetime.now(timezone.utc).isoformat()
            }
            await db.tables.insert_one(table)

    logger.info("PokerClaw backend ready!")


# ─── Include Routers + CORS ───

app.include_router(auth_router)
app.include_router(agents_router)
app.include_router(tables_router)
app.include_router(bets_router)
app.include_router(wallet_router)
app.include_router(stripe_router)
app.include_router(crypto_router)
app.include_router(tournaments_router)
app.include_router(leaderboard_router)
app.include_router(agent_api_router)
app.include_router(sweepstakes_router)
app.include_router(admin_router)

# ─── CORS ──────────────────────────────────────────────────────────────────
# In production (ENVIRONMENT=production) CORS_ORIGINS must be set explicitly.
# Wildcard origins are rejected in production to prevent credential leakage.
_environment = os.environ.get("ENVIRONMENT", "development").strip().lower()
_cors_raw = os.environ.get("CORS_ORIGINS", "").strip()

if not _cors_raw:
    if _environment == "production":
        raise SystemExit(
            "\n\nPokerClaw: CORS_ORIGINS must be set in production.\n"
            "Example: CORS_ORIGINS=https://pokerclaw.yourdomain.com\n"
            "Wildcard '*' is not allowed in production.\n"
        )
    # Development default — allow the standard CRA dev server and Docker nginx
    _cors_origins = ["http://localhost:3000", "http://localhost:80", "http://localhost"]
else:
    _cors_origins = [o.strip() for o in _cors_raw.split(",") if o.strip()]
    if "*" in _cors_origins and _environment == "production":
        raise SystemExit(
            "\n\nPokerClaw: Wildcard CORS origin ('*') is not allowed in production.\n"
            "Set CORS_ORIGINS to your actual frontend domain(s).\n"
        )

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()
