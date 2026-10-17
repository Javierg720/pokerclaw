# ─────────────────────────────────────────────────────────────────────────────
# PokerClaw frontend Docker image (multi-stage)
# ─────────────────────────────────────────────────────────────────────────────

# ── Stage 1: build the React app ─────────────────────────────────────────────
FROM node:18-alpine AS builder

WORKDIR /app

COPY package.json yarn.lock ./
RUN yarn install --frozen-lockfile

COPY . .

# When REACT_APP_BACKEND_URL is empty the frontend uses a relative /api path,
# which is proxied to the backend by nginx.  This is the recommended setup
# when both containers are behind the same nginx reverse proxy.
# For standalone setups set: --build-arg REACT_APP_BACKEND_URL=http://your-backend:8001
ARG REACT_APP_BACKEND_URL=""
ENV REACT_APP_BACKEND_URL=$REACT_APP_BACKEND_URL

RUN yarn build

# ── Stage 2: serve with nginx ─────────────────────────────────────────────────
FROM nginx:1.25-alpine

COPY --from=builder /app/build /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
