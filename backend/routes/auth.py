import os
import secrets
import uuid

import bcrypt
from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile, File
from pydantic import BaseModel

from deps import db, create_token, get_current_user, login_limiter, signup_limiter, logger

router = APIRouter(prefix="/api")

MIN_PASSWORD_LEN = 8


# ── Request models ────────────────────────────────────────────────────────────

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


class ForgotPasswordRequest(BaseModel):
    email: str


class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str


# ── Avatar options ────────────────────────────────────────────────────────────

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


# ── Helpers ───────────────────────────────────────────────────────────────────

def _client_ip(request: Request) -> str:
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _validate_password(password: str) -> None:
    if len(password) < MIN_PASSWORD_LEN:
        raise HTTPException(
            status_code=400,
            detail=f"Password must be at least {MIN_PASSWORD_LEN} characters",
        )


# ── Signup / Login ────────────────────────────────────────────────────────────

@router.post("/human-auth/signup")
@router.post("/auth/signup")
async def signup(req: SignupRequest, request: Request):
    ip = _client_ip(request)
    if not await signup_limiter.is_allowed(ip):
        raise HTTPException(
            status_code=429,
            detail="Too many signup attempts from this address. Try again later.",
        )

    if req.role != "human":
        raise HTTPException(
            status_code=400,
            detail="OpenClaw agents must register through /api/agent-api/register",
        )

    _validate_password(req.password)

    if not req.username or not req.username.strip():
        raise HTTPException(status_code=400, detail="Username is required")
    if len(req.username) > 32:
        raise HTTPException(status_code=400, detail="Username must be 32 characters or fewer")

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
        "created_at": datetime.now(timezone.utc).isoformat(),
    }

    await db.users.insert_one(user)

    wallet = {
        "id": str(uuid.uuid4()), "user_id": user_id,
        "sc_balance": 0, "gc_balance": 5000,
        "sc_provenance_migrated": True,
        "crypto_addresses": None, "pending_deposits": [],
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.wallets.insert_one(wallet)

    token = create_token(user_id, req.username, req.role)
    return {
        "token": token,
        "user": {
            "id": user_id, "username": req.username,
            "email": req.email, "role": req.role,
            "agent_id": None, "avatar_url": None,
        },
        "agent": None,
    }


@router.post("/human-auth/login")
@router.post("/auth/login")
async def login(req: LoginRequest, request: Request):
    ip = _client_ip(request)
    if not await login_limiter.is_allowed(ip):
        raise HTTPException(
            status_code=429,
            detail="Too many login attempts from this address. Try again in 15 minutes.",
        )

    user = await db.users.find_one({"email": req.email}, {"_id": 0})
    if not user or not bcrypt.checkpw(req.password.encode(), user["password_hash"].encode()):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    if user.get("role", "human") != "human":
        raise HTTPException(
            status_code=403,
            detail="OpenClaw agents must use /api/agent-api/login",
        )

    role = user.get("role", "human")
    token = create_token(user["id"], user["username"], role)
    return {
        "token": token,
        "user": {
            "id": user["id"], "username": user["username"],
            "email": user["email"], "role": role,
            "agent_id": user.get("agent_id"),
            "avatar_url": user.get("avatar_url"),
        },
    }


# ── Forgot / reset password ───────────────────────────────────────────────────

@router.post("/auth/forgot-password")
async def forgot_password(req: ForgotPasswordRequest, request: Request):
    """Initiate a password-reset flow.

    Always returns 200 (with a generic message) to prevent email enumeration.

    In development (ENVIRONMENT != production) the reset token is returned in
    the response so you can test without wiring up an SMTP provider.
    In production, wire an SMTP provider and send the token via email instead.
    """
    ip = _client_ip(request)
    if not await login_limiter.is_allowed(ip):
        raise HTTPException(status_code=429, detail="Too many requests. Try again later.")

    user = await db.users.find_one({"email": req.email}, {"_id": 0})
    generic = {"message": "If that email address is registered you will receive a reset link shortly."}

    if not user or user.get("role") != "human":
        return generic  # don't reveal whether the email exists

    token = secrets.token_urlsafe(32)
    expires = (datetime.now(timezone.utc) + timedelta(minutes=15)).isoformat()

    await db.users.update_one(
        {"id": user["id"]},
        {"$set": {"password_reset_token": token, "password_reset_expires": expires}},
    )

    environment = os.environ.get("ENVIRONMENT", "development").strip().lower()
    logger.info("Password-reset token for %s: %s (expires %s)", req.email, token, expires)

    if environment != "production":
        # Surface token in dev so callers can test without SMTP.
        return {**generic, "dev_reset_token": token}

    # TODO: send the token via your SMTP provider here.
    # e.g. send_email(to=req.email, subject="Reset your PokerClaw password",
    #                 body=f"Token: {token}")
    return generic


@router.post("/auth/reset-password")
async def reset_password(req: ResetPasswordRequest, request: Request):
    """Complete a password-reset using the token from /auth/forgot-password."""
    ip = _client_ip(request)
    if not await login_limiter.is_allowed(ip):
        raise HTTPException(status_code=429, detail="Too many requests. Try again later.")

    _validate_password(req.new_password)

    user = await db.users.find_one({"password_reset_token": req.token}, {"_id": 0})
    if not user:
        raise HTTPException(status_code=400, detail="Invalid or expired reset token")

    expires_str = user.get("password_reset_expires", "")
    try:
        expires = datetime.fromisoformat(expires_str)
        if expires.tzinfo is None:
            expires = expires.replace(tzinfo=timezone.utc)
        if expires < datetime.now(timezone.utc):
            raise ValueError("expired")
    except (ValueError, TypeError):
        raise HTTPException(status_code=400, detail="Reset token has expired")

    hashed = bcrypt.hashpw(req.new_password.encode(), bcrypt.gensalt()).decode()
    await db.users.update_one(
        {"id": user["id"]},
        {
            "$set": {"password_hash": hashed},
            "$unset": {"password_reset_token": "", "password_reset_expires": ""},
        },
    )
    return {"message": "Password updated. You can now log in with your new password."}


# ── Profile ───────────────────────────────────────────────────────────────────

@router.get("/auth/me")
async def get_me(user=Depends(get_current_user)):
    result = {
        "id": user["id"], "username": user["username"],
        "email": user["email"], "role": user.get("role", "human"),
        "agent_id": user.get("agent_id"),
        "avatar_url": user.get("avatar_url"),
    }
    if user.get("agent_id"):
        agent = await db.agents.find_one({"id": user["agent_id"]}, {"_id": 0})
        if agent:
            result["agent"] = agent
    return result


@router.get("/auth/avatars")
async def get_avatar_options():
    return {"avatars": SPECTATOR_AVATARS}


@router.put("/auth/profile")
async def update_profile(req: ProfileUpdateRequest, user=Depends(get_current_user)):
    update = {}
    if req.avatar_url is not None:
        update["avatar_url"] = req.avatar_url
    if req.username is not None:
        if len(req.username) > 32:
            raise HTTPException(status_code=400, detail="Username must be 32 characters or fewer")
        if req.username != user["username"]:
            existing = await db.users.find_one({"username": req.username}, {"_id": 0})
            if existing:
                raise HTTPException(status_code=400, detail="Username taken")
        update["username"] = req.username
    if not update:
        raise HTTPException(status_code=400, detail="Nothing to update")
    await db.users.update_one({"id": user["id"]}, {"$set": update})
    updated = await db.users.find_one({"id": user["id"]}, {"_id": 0})
    return {
        "id": updated["id"], "username": updated["username"],
        "email": updated["email"], "role": updated.get("role", "human"),
        "avatar_url": updated.get("avatar_url"),
    }


UPLOAD_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "uploads", "avatars")
ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".gif"}
MAX_FILE_SIZE = 2 * 1024 * 1024  # 2 MB


@router.post("/auth/avatar/upload")
async def upload_avatar(file: UploadFile = File(...), user=Depends(get_current_user)):
    if not file.filename:
        raise HTTPException(status_code=400, detail="No file provided")

    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"File type {ext} not allowed. Use jpg, png, webp, or gif",
        )

    content = await file.read()
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(status_code=400, detail="File too large. Max 2 MB")

    filename = f"{user['id']}_{uuid.uuid4().hex[:8]}{ext}"
    filepath = os.path.join(UPLOAD_DIR, filename)
    os.makedirs(UPLOAD_DIR, exist_ok=True)

    with open(filepath, "wb") as f:
        f.write(content)

    avatar_url = f"/api/uploads/avatars/{filename}"
    await db.users.update_one({"id": user["id"]}, {"$set": {"avatar_url": avatar_url}})
    return {"avatar_url": avatar_url, "message": "Avatar uploaded successfully"}
