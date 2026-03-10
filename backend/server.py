from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request
from starlette.middleware.cors import CORSMiddleware
from deps import db, client, logger
from game_engine import AGENT_PRESETS, AVATAR_URLS
import os
import uuid
import json
import asyncio
import logging
from datetime import datetime, timezone
from emergentintegrations.payments.stripe.checkout import StripeCheckout

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

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

app = FastAPI()


# ─── WebSocket Manager ───

class TableManager:
    def __init__(self):
        self.connections: dict[str, list[WebSocket]] = {}

    async def connect(self, table_id: str, ws: WebSocket):
        await ws.accept()
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


table_manager = TableManager()


# ─── WebSocket endpoint ───

@app.websocket("/api/ws/table/{table_id}")
async def websocket_table(websocket: WebSocket, table_id: str):
    await table_manager.connect(table_id, websocket)
    try:
        count = table_manager.spectator_count(table_id)
        await table_manager.broadcast(table_id, {"type": "spectator_count", "count": count})
        while True:
            data = await websocket.receive_text()
            try:
                msg = json.loads(data)
                if msg.get("type") == "ping":
                    await websocket.send_json({"type": "pong"})
            except json.JSONDecodeError:
                pass
    except WebSocketDisconnect:
        table_manager.disconnect(table_id, websocket)
        count = table_manager.spectator_count(table_id)
        await table_manager.broadcast(table_id, {"type": "spectator_count", "count": count})


# ─── Stripe Webhook (must be on app, not api_router) ───

@app.post("/api/webhook/stripe")
async def stripe_webhook(request: Request):
    payload = await request.body()
    sig = request.headers.get("Stripe-Signature")

    stripe_key = os.environ.get("STRIPE_API_KEY")
    if not stripe_key:
        return {"status": "error", "message": "Stripe not configured"}

    stripe_checkout = StripeCheckout(api_key=stripe_key)

    try:
        event = await stripe_checkout.handle_webhook(payload, sig)
    except Exception as e:
        logger.error(f"Webhook error: {e}")
        return {"status": "error"}

    if event.event_type == "checkout.session.completed" and event.payment_status == "paid":
        session_id = event.session_id
        pt = await db.payment_transactions.find_one({"session_id": session_id}, {"_id": 0})
        if pt and pt["payment_status"] != "paid":
            sc_amount = pt["sc_amount"]
            await db.wallets.update_one(
                {"user_id": pt["user_id"]}, {"$inc": {"sc_balance": sc_amount}})
            await db.payment_transactions.update_one(
                {"session_id": session_id},
                {"$set": {"payment_status": "paid", "status": "complete",
                          "completed_at": datetime.now(timezone.utc).isoformat()}})
            await db.transactions.insert_one({
                "id": str(uuid.uuid4()), "user_id": pt["user_id"],
                "type": "stripe_purchase", "amount": sc_amount, "currency": "sc",
                "description": f"Purchased {sc_amount} SC via Stripe (${pt['amount_usd']})",
                "created_at": datetime.now(timezone.utc).isoformat()
            })

    return {"status": "ok"}


# ─── Startup - Seed Data ───

@app.on_event("startup")
async def seed_data():
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

app.add_middleware(
    CORSMiddleware,
    allow_origins=os.environ.get('CORS_ORIGINS', '*').split(','),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()
