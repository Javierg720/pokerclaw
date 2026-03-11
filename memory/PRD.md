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
10. **Spectator Chat:** Real-time chat and emoji reactions on game tables
11. **Auto Crypto Confirmations:** Background task simulating blockchain confirmations

## Tech Stack
- **Frontend:** React, Tailwind CSS, Shadcn UI, Framer Motion
- **Backend:** FastAPI, MongoDB (motor), WebSockets, FastAPI Routers
- **Auth:** JWT-based with role support (agent/human)
- **Integrations:** Stripe, CoinGecko, OpenClaw Skill

## Architecture
```
/app/
├── backend/
│   ├── server.py              # Main app, WebSocket (chat+reactions), crypto bg task
│   ├── game_engine.py         # Texas Hold'em logic (supports external_action)
│   ├── deps.py                # Shared DB, auth, utilities
│   ├── routes/
│   │   ├── auth.py, agents.py, tables.py, bets.py, wallet.py
│   │   ├── stripe_routes.py, crypto.py, tournaments.py
│   │   ├── leaderboard.py, agent_api.py
│   └── requirements.txt
├── frontend/src/
│   ├── App.js, App.css
│   ├── components/
│   │   ├── Navigation.jsx, BettingPanel.jsx, PlayingCard.jsx
│   │   └── ChatPanel.jsx          # Extracted spectator chat component
│   ├── pages/
│   │   ├── AuthPage.jsx, LobbyPage.jsx, TablePage.jsx
│   │   ├── AgentDashboard.jsx, WalletPage.jsx
│   │   ├── TournamentPage.jsx, ProfilePage.jsx
│   ├── context/AuthContext.jsx
│   └── lib/api.js, sounds.js, useWebSocket.js
├── pokerclaw-skill/
│   └── SKILL.md               # OpenClaw skill definition
└── memory/PRD.md
```

## What's Been Implemented (All Complete)

### Phase 1 - Core MVP & Dual Login
- Full-stack scaffolding, JWT auth, game tables, Texas Hold'em engine
- PokerStars-style table UI, CSS animations, sound effects, WebSocket real-time
- Agent/Spectator role selection, Agent Dashboard with stats & activity

### Phase 2 - Stripe & Crypto
- Stripe checkout with SC packages ($4.99-$99.99)
- CoinGecko live prices, deposit submission, auto-confirmation (30s bg task)

### Phase 3 - Betting & Game Engine
- Spectator betting with live odds, turn-by-turn 10s timer, tournaments

### Phase 4 - Backend Refactoring
- Monolithic server.py split into modular router-based architecture

### Phase 5 - OpenClaw Skill (Mar 10, 2026)
- Agent API (11 endpoints), SKILL.md for ClawHub

### Phase 6 - Feature Batch (Mar 11, 2026)
- **Spectator Live Chat:** WebSocket-based real-time chat + 6 emoji reactions
- **Crypto Auto-Confirmations:** Background loop auto-confirms deposits every 30s
- **Chip Animations:** Enhanced CSS animations (fly-in, collect, pot pulse)
- **Tournament Late Join:** Swap agents before tournament starts
- **Frontend Refactoring:** Extracted ChatPanel component from TablePage
- **Spectator Leaderboard:** Rankings for top bettors with win rate, total won, net profit
- **Profile Avatar Customization:** 16 DiceBear robot avatars, edit button, save to profile
- **OpenClaw Skill Ready:** SKILL.md prepared for ClawHub publishing with correct frontmatter

## MOCKED Systems
- **AI Agent Decisions:** Simulated via strategy-based logic in game_engine.py
- **Crypto Confirmations:** Auto-simulated by background task (not real blockchain)

## Prioritized Backlog
- All features requested have been implemented.
- Publish OpenClaw skill to ClawHub
- Real blockchain monitoring for crypto deposits

## DB Schema
- **users:** `{ id, username, email, password_hash, role, agent_id }`
- **agents:** `{ id, name, strategy, avatar_url, owner_id, is_house, is_external, wins, losses }`
- **wallets:** `{ id, user_id, sc_balance, gc_balance, crypto_addresses }`
- **tables:** `{ id, name, min_bet, max_bet, agent_ids, current_game_id, status }`
- **games:** `{ id, table_id, phase, players, community_cards, pot, deck, current_actor, turn_index }`
- **bets/tournament_bets:** `{ id, user_id, game_id/tournament_id, agent_id, amount, status }`
- **crypto_deposits:** `{ id, user_id, tx_hash, amount_crypto, confirmations, status }`

## Test Credentials
- Agent: openclaw@test.com / test123 (ClawBot_Alpha)
- Human: uitester@test.com / test123
