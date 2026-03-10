"""Shared database, auth, and utility dependencies for all routes."""
from fastapi import Depends, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv
from pathlib import Path
import os
import jwt
import hashlib
import logging
from datetime import datetime, timezone

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ['DB_NAME']]
JWT_SECRET = os.environ.get('JWT_SECRET', 'pokerclaw_fallback_secret')

security = HTTPBearer(auto_error=False)
logger = logging.getLogger(__name__)


def create_token(user_id: str, username: str, role: str = "human"):
    return jwt.encode(
        {"user_id": user_id, "username": username, "role": role,
         "exp": datetime.now(timezone.utc).timestamp() + 604800},
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


def generate_crypto_addresses(user_id: str):
    seed = hashlib.sha256(user_id.encode()).hexdigest()
    seed2 = hashlib.sha256((user_id + "salt2").encode()).hexdigest()
    seed3 = hashlib.sha256((user_id + "salt3").encode()).hexdigest()
    return {
        "btc": f"1{seed[:33].title()[:33]}",
        "ltc": f"L{seed2[5:38].title()[:33]}",
        "eth": f"0x{seed3[:40]}"
    }


def sanitize_game_for_response(game, show_cards=False):
    g = {k: v for k, v in game.items() if k not in ('_id', 'deck')}
    show = show_cards or g.get('phase') in ('showdown', 'complete')
    if not show:
        for p in g.get('players', []):
            p['hole_cards'] = [None, None]
    phase_display = {
        'preflop_betting': 'preflop', 'flop_deal': 'flop',
        'flop_betting': 'flop', 'turn_deal': 'turn',
        'turn_betting': 'turn', 'river_deal': 'river',
        'river_betting': 'river',
    }
    g['display_phase'] = phase_display.get(g.get('phase'), g.get('phase'))
    g['is_betting'] = g.get('phase', '').endswith('_betting')
    return g
