from fastapi import APIRouter, HTTPException, Depends, UploadFile, File
from pydantic import BaseModel
import uuid
import os
import bcrypt
from datetime import datetime, timezone
from deps import db, create_token, get_current_user

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


class ProfileUpdateRequest(BaseModel):
    avatar_url: str | None = None
    username: str | None = None


# Spectator avatar options
SPECTATOR_AVATARS = [
    "https://api.dicebear.com/7.x/bottts-neutral/svg?seed=claw1&backgroundColor=1a1a2e",
    "https://api.dicebear.com/7.x/bottts-neutral/svg?seed=claw2&backgroundColor=1a1a2e",
    "https://api.dicebear.com/7.x/bottts-neutral/svg?seed=claw3&backgroundColor=1a1a2e",
    "https://api.dicebear.com/7.x/bottts-neutral/svg?seed=claw4&backgroundColor=1a1a2e",
    "https://api.dicebear.com/7.x/bottts-neutral/svg?seed=claw5&backgroundColor=1a1a2e",
    "https://api.dicebear.com/7.x/bottts-neutral/svg?seed=claw6&backgroundColor=1a1a2e",
    "https://api.dicebear.com/7.x/bottts-neutral/svg?seed=poker1&backgroundColor=0d1117",
    "https://api.dicebear.com/7.x/bottts-neutral/svg?seed=poker2&backgroundColor=0d1117",
    "https://api.dicebear.com/7.x/bottts-neutral/svg?seed=poker3&backgroundColor=0d1117",
    "https://api.dicebear.com/7.x/bottts-neutral/svg?seed=poker4&backgroundColor=0d1117",
    "https://api.dicebear.com/7.x/bottts-neutral/svg?seed=poker5&backgroundColor=0d1117",
    "https://api.dicebear.com/7.x/bottts-neutral/svg?seed=poker6&backgroundColor=0d1117",
    "https://api.dicebear.com/7.x/thumbs/svg?seed=ace&backgroundColor=ff003c",
    "https://api.dicebear.com/7.x/thumbs/svg?seed=king&backgroundColor=00f0ff",
    "https://api.dicebear.com/7.x/thumbs/svg?seed=queen&backgroundColor=ffe600",
    "https://api.dicebear.com/7.x/thumbs/svg?seed=jack&backgroundColor=bd00ff",
]


@router.post("/human-auth/signup")
@router.post("/auth/signup")
async def signup(req: SignupRequest):
    if req.role != "human":
        raise HTTPException(
            status_code=400,
            detail="OpenClaw agents must register through /api/agent-api/register",
        )

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

    await db.users.insert_one(user)

    wallet = {
        "id": str(uuid.uuid4()), "user_id": user_id,
        "sc_balance": 0, "gc_balance": 1000,
        "crypto_addresses": None, "pending_deposits": [],
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    await db.wallets.insert_one(wallet)

    token = create_token(user_id, req.username, req.role)
    return {
        "token": token,
        "user": {
            "id": user_id, "username": req.username,
            "email": req.email, "role": req.role,
            "agent_id": user.get("agent_id"),
            "avatar_url": None,
        },
        "agent": None
    }


@router.post("/human-auth/login")
@router.post("/auth/login")
async def login(req: LoginRequest):
    user = await db.users.find_one({"email": req.email}, {"_id": 0})
    if not user or not bcrypt.checkpw(req.password.encode(), user['password_hash'].encode()):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    if user.get('role', 'human') != 'human':
        raise HTTPException(
            status_code=403,
            detail="OpenClaw agents must use /api/agent-api/login",
        )

    role = user.get('role', 'human')
    token = create_token(user['id'], user['username'], role)
    return {
        "token": token,
        "user": {
            "id": user['id'], "username": user['username'],
            "email": user['email'], "role": role,
            "agent_id": user.get('agent_id'),
            "avatar_url": user.get('avatar_url'),
        }
    }


@router.get("/auth/me")
async def get_me(user=Depends(get_current_user)):
    result = {
        "id": user['id'], "username": user['username'],
        "email": user['email'], "role": user.get('role', 'human'),
        "agent_id": user.get('agent_id'),
        "avatar_url": user.get('avatar_url'),
    }
    if user.get('agent_id'):
        agent = await db.agents.find_one({"id": user['agent_id']}, {"_id": 0})
        if agent:
            result['agent'] = agent
    return result


@router.get("/auth/avatars")
async def get_avatar_options():
    """Get available avatar options for profile customization."""
    return {"avatars": SPECTATOR_AVATARS}


@router.put("/auth/profile")
async def update_profile(req: ProfileUpdateRequest, user=Depends(get_current_user)):
    """Update user profile (avatar, username)."""
    update = {}
    if req.avatar_url is not None:
        update["avatar_url"] = req.avatar_url
    if req.username is not None:
        if req.username != user['username']:
            existing = await db.users.find_one({"username": req.username}, {"_id": 0})
            if existing:
                raise HTTPException(status_code=400, detail="Username taken")
        update["username"] = req.username
    if not update:
        raise HTTPException(status_code=400, detail="Nothing to update")
    await db.users.update_one({"id": user['id']}, {"$set": update})
    updated = await db.users.find_one({"id": user['id']}, {"_id": 0})
    return {
        "id": updated['id'], "username": updated['username'],
        "email": updated['email'], "role": updated.get('role', 'human'),
        "avatar_url": updated.get('avatar_url'),
    }


UPLOAD_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "uploads", "avatars")
ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".gif"}
MAX_FILE_SIZE = 2 * 1024 * 1024  # 2MB


@router.post("/auth/avatar/upload")
async def upload_avatar(file: UploadFile = File(...), user=Depends(get_current_user)):
    """Upload a custom avatar image. Max 2MB, jpg/png/webp/gif."""
    if not file.filename:
        raise HTTPException(status_code=400, detail="No file provided")

    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail=f"File type {ext} not allowed. Use jpg, png, webp, or gif")

    content = await file.read()
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(status_code=400, detail="File too large. Max 2MB")

    filename = f"{user['id']}_{uuid.uuid4().hex[:8]}{ext}"
    filepath = os.path.join(UPLOAD_DIR, filename)
    os.makedirs(UPLOAD_DIR, exist_ok=True)

    with open(filepath, "wb") as f:
        f.write(content)

    avatar_url = f"/api/uploads/avatars/{filename}"

    await db.users.update_one({"id": user['id']}, {"$set": {"avatar_url": avatar_url}})

    return {
        "avatar_url": avatar_url,
        "message": "Avatar uploaded successfully",
    }
