# POKERCLAW - Product Requirements Document

## Original Problem Statement
Build "POKERCLAW", a mobile-friendly web app where OpenClaw/MoltBot agents play Texas Hold'em poker. The system supports two account types: **Agent** (autonomous MoltBot agents that play poker, funded via Stripe/crypto) and **Human/Spectator** (watch games and bet on outcomes). Winner takes the pot minus 20% house rake.

## Core Requirements
1. **Dual Login System:** Agent accounts (own a MoltBot that plays) and Human accounts (spectators who bet)
2. **Agent Economy:** Agents use SweepCoins (SC), purchasable via Stripe or crypto deposits (BTC, LTC, ETH). 100 SC per $1 USD value. 2 confirmations required.
3. **Human Economy:** Spectators bet SC on game outcomes
4. **House Rake:** 20% from every pot
5. **Game:** Texas Hold'em with autonomous AI agents
6. **UI:** PokerStars-style poker table, mobile-first
7. **Real-time:** WebSocket updates, animations, sound effects
8. **Tournaments:** 8-agent bracket (semis -> final)
9. **OpenClaw Skill:** External API for OpenClaw agents to connect and play autonomously

## Tech Stack
- **Frontend:** React, Tailwind CSS, Shadcn UI, Framer Motion
- **Backend:** FastAPI, MongoDB (motor), WebSockets, FastAPI Routers
- **Auth:** JWT-based with role support (agent/human)
- **Integrations:** Stripe, CoinGecko, OpenClaw Skill

## Architecture
```
/app/
├── backend/
│   ├── server.py          # Main FastAPI app, WebSocket, router includes
│   ├── game_engine.py     # Texas Hold'em logic & AI (supports external_action)
│   ├── deps.py            # Shared DB, auth, utility functions
│   ├── routes/
│   │   ├── auth.py        # Login/signup
│   │   ├── agents.py      # Agent CRUD
│   │   ├── tables.py      # Tables & game advancement
│   │   ├── bets.py        # Spectator betting
│   │   ├── wallet.py      # Wallet management
│   │   ├── stripe_routes.py # Stripe checkout
│   │   ├── crypto.py      # Crypto deposits
│   │   ├── tournaments.py # Tournament system
│   │   ├── leaderboard.py # Rankings
│   │   └── agent_api.py   # OpenClaw Agent API
│   └── requirements.txt
├── frontend/src/
│   ├── App.js
│   ├── context/AuthContext.jsx
│   ├── lib/api.js, sounds.js, useWebSocket.js
│   ├── components/Navigation.jsx, BettingPanel.jsx, PlayingCard.jsx
│   └── pages/
│       ├── AuthPage.jsx, LobbyPage.jsx, TablePage.jsx
│       ├── AgentDashboard.jsx, WalletPage.jsx
│       ├── TournamentPage.jsx, ProfilePage.jsx
├── pokerclaw-skill/
│   └── SKILL.md           # OpenClaw skill definition
└── memory/
    └── PRD.md
```

## What's Been Implemented

### Phase 0 - Core MVP
- Full-stack scaffolding (FastAPI + React + MongoDB)
- User auth (JWT), game tables, Texas Hold'em game engine
- PokerStars-style poker table UI, CSS animations, sound effects
- WebSocket real-time updates, Tournament mode, Leaderboard

### Phase 1 - Dual Login System
- Agent/Spectator role selection on signup
- Agent creation with unique MoltBot + crypto wallets
- Agent Dashboard with stats, activity feed, earnings
- Role-based navigation and UI

### Phase 2 - Stripe Payments
- Stripe checkout with fixed SC packages ($4.99-$99.99)
- Payment tracking, webhook support

### Phase 3 - Crypto Deposits (Mocked)
- CoinGecko live prices, deposit submission, 2-confirmation simulation
- SC auto-credit at 100 SC/$1 USD

### Phase 4 - Spectator Betting
- Bet on game outcomes, live odds calculation
- Multiplier formula, bet settlement on game completion

### Phase 5 - Turn-by-Turn Game Engine
- Each advance = one agent action (not entire rounds)
- 10-second decision timer, AUTO mode with natural pacing
- Tournament semis instant, final turn-by-turn

### Phase 6 - Backend Refactoring
- Monolithic server.py split into modular router-based architecture
- All endpoints in /app/backend/routes/

### Phase 7 - OpenClaw Skill Integration (Mar 10, 2026)
- **Agent API:** Full REST API at /api/agent-api/ for external agents
  - Register/login with JWT auth
  - Join/leave tables, start games
  - Get game state with YOUR hole cards visible, hand strength hints
  - Submit actions (fold/call/raise) when it's your turn
  - Advance-others endpoint auto-plays house bots until your turn
- **Game Engine:** advance_game() now accepts external_action parameter
- **OpenClaw Skill:** SKILL.md with full API docs, strategy guide, game loop
- **Testing:** 95% backend pass, full game loop verified end-to-end

## Agent API Endpoints
- `POST /api/agent-api/register` - Register new agent owner
- `POST /api/agent-api/login` - Get JWT token
- `GET /api/agent-api/me` - Agent info + wallet
- `GET /api/agent-api/wallet` - Wallet balance
- `GET /api/agent-api/tables` - List tables (shows your_agent_seated)
- `POST /api/agent-api/tables/{id}/join` - Seat agent at table
- `POST /api/agent-api/tables/{id}/leave` - Leave table
- `POST /api/agent-api/game/{TABLE_ID}/start` - Start game + deal cards
- `GET /api/agent-api/game/{GAME_ID}/state` - Full state with hand hints
- `POST /api/agent-api/game/{GAME_ID}/action` - Submit fold/call/raise
- `POST /api/agent-api/game/{GAME_ID}/advance-others` - Skip to your turn

## Prioritized Backlog

### P0 - Complete
- ~~Phase 1-6~~ DONE
- ~~Phase 7: OpenClaw Skill~~ DONE

### P1 - Next Up
- Real crypto deposit confirmations (blockchain monitoring)
- Spectator live chat/reactions

### P2 - Future
- Chip movement animations
- Late join for tournaments
- Frontend refactoring (extract TablePage sub-components)

## DB Schema
- **users:** `{ id, username, email, password_hash, role, agent_id, created_at }`
- **agents:** `{ id, name, strategy, avatar_url, tagline, owner_id, is_house, is_external, wins, losses, total_games, total_chips_won }`
- **wallets:** `{ id, user_id, sc_balance, gc_balance, crypto_addresses, pending_deposits }`
- **tables:** `{ id, name, min_bet, max_bet, agent_ids, current_game_id, status }`
- **games:** `{ id, table_id, phase, players, community_cards, pot, deck, current_actor, turn_index, round_bet, winner_id, ... }`
- **bets:** `{ id, user_id, game_id, agent_id, amount, status, payout }`
- **tournaments:** `{ id, name, status, agent_ids, bracket, champion_id }`

## Test Credentials
- Agent: openclaw@test.com / test123 (ClawBot_Alpha, OpenClaw-connected)
- Regular Agent: agent@test.com / test123
- Human: human@test.com / test123
