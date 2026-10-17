# ─────────────────────────────────────────────────────────────────────────────
# PokerClaw backend Docker image
# ─────────────────────────────────────────────────────────────────────────────
FROM python:3.11-slim

# Security: run as non-root
RUN addgroup --system pokerclaw && adduser --system --ingroup pokerclaw pokerclaw

WORKDIR /app

# Install dependencies first (layer-cached unless requirements.txt changes)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source
COPY . .

# Uploads directory (avatars) — must be writable at runtime
RUN mkdir -p uploads/avatars && chown -R pokerclaw:pokerclaw /app

USER pokerclaw

EXPOSE 8001

# Graceful shutdown: let in-flight requests finish before the container exits.
# Railway (and other PaaS) inject $PORT; fall back to 8001 for local Docker.
CMD uvicorn server:app \
    --host 0.0.0.0 \
    --port ${PORT:-8001} \
    --timeout-graceful-shutdown 10
