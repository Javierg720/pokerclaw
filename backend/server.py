from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request
from fastapi.staticfiles import StaticFiles
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

# ─── Serve uploaded avatars as static files ───
UPLOAD_DIR = os.path.join(os.path.dirname(__file__), "uploads", "avatars")
os.makedirs(UPLOAD_DIR, exist_ok=True)
app.mount("/api/uploads/avatars", StaticFiles(directory=UPLOAD_DIR), name="avatar_uploads")


# ─── WebSocket Manager ───

class TableManager:
    def __init__(self):
        self.connections: dict[str, list[WebSocket]] = {}
        self.chat_history: dict[str, list[dict]] = {}

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
    await table_manager.connect(table_id, websocket)
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
                    username = msg.get("username", "Spectator")
                    text = msg.get("text", "")[:200]  # Limit length
                    if text.strip():
                        chat_msg = {
                            "type": "chat",
                            "username": username,
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
                            "username": msg.get("username", ""),
                        })
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


# ─── Background task: auto-confirm crypto deposits ───

async def crypto_auto_confirm_loop():
    """Background task that checks blockchain for confirmation updates on pending deposits.
    Every 45 seconds, queries real blockchain APIs for each pending deposit.
    Falls back to simulated confirmation if blockchain API is unavailable."""
    while True:
        await asyncio.sleep(45)
        try:
            from routes.crypto import verify_tx_on_blockchain
            pending = await db.crypto_deposits.find({"status": "pending"}, {"_id": 0}).to_list(100)
            for dep in pending:
                # Try real blockchain verification first
                verification = await verify_tx_on_blockchain(dep["crypto_type"], dep["tx_hash"])

                if verification.get("verified"):
                    new_conf = verification.get("confirmations", 0)
                else:
                    # Fallback: increment by 1 if blockchain API fails
                    new_conf = dep.get("confirmations", 0) + 1

                # Always use the higher value
                new_conf = max(new_conf, dep.get("confirmations", 0))

                update = {
                    "confirmations": new_conf,
                    "blockchain_verified": verification.get("verified", dep.get("blockchain_verified", False)),
                }

                if new_conf >= dep.get("required_confirmations", 2):
                    update["status"] = "confirmed"
                    update["confirmed_at"] = datetime.now(timezone.utc).isoformat()
                    await db.wallets.update_one(
                        {"user_id": dep["user_id"]},
                        {"$inc": {"sc_balance": dep["sc_amount"]}}
                    )
                    await db.transactions.insert_one({
                        "id": str(uuid.uuid4()), "user_id": dep["user_id"],
                        "type": "crypto_deposit", "amount": dep["sc_amount"], "currency": "sc",
                        "description": f"Confirmed: {dep['amount_crypto']} {dep['crypto_type'].upper()} = {dep['sc_amount']} SC"
                        + (" (blockchain verified)" if verification.get("verified") else " (auto-confirmed)"),
                        "created_at": datetime.now(timezone.utc).isoformat()
                    })
                    logger.info(f"Confirmed crypto deposit {dep['id']}: {dep['sc_amount']} SC (blockchain={verification.get('verified')})")

                await db.crypto_deposits.update_one({"id": dep["id"]}, {"$set": update})
        except Exception as e:
            logger.error(f"Crypto confirm loop error: {e}")


# ─── Startup - Seed Data ───

@app.on_event("startup")
async def seed_data():
    # Start background crypto confirmation task
    asyncio.create_task(crypto_auto_confirm_loop())

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
