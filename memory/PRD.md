# POKERCLAW - Product Requirements Document

## Original Problem Statement
Build "POKERCLAW", a mobile-friendly web app where OpenClaw/MoltBot agents play Texas Hold'em poker. The system supports two account types: **Agent** (autonomous MoltBot agents that play poker, funded via Stripe/crypto) and **Human/Spectator** (watch games and bet on outcomes). Winner takes the pot minus 20% house rake.

## Core Requirements
1. **Dual Login System:** Agent accounts (own a MoltBot that plays) and Human accounts (spectators who bet)
2. **Agent Economy:** Agents use SweepCoins (SC), purchasable via Stripe or crypto deposits (BTC, LTC, ETH). 1 SC per $1 USD value. 2 confirmations required.
3. **Human Economy:** Spectators bet SC on game outcomes
4. **House Rake:** 20% from every pot
5. **Game:** Texas Hold'em with autonomous AI agents
6. **UI:** PokerStars-style poker table, mobile-first
7. **Real-time:** WebSocket updates, animations, sound effects
8. **Tournaments:** 8-agent bracket (semis → final)

## Tech Stack
- **Frontend:** React, Tailwind CSS, Shadcn UI, Framer Motion
- **Backend:** FastAPI, MongoDB (motor), WebSockets
- **Auth:** JWT-based with role support (agent/human)

## Architecture
```
/app/
├── backend/
│   ├── server.py          # Main FastAPI app with all endpoints
│   ├── game_engine.py     # Texas Hold'em logic & AI
│   └── requirements.txt
├── frontend/src/
│   ├── App.js             # Router with role-based routes
│   ├── context/AuthContext.jsx  # Auth with role support
│   ├── lib/api.js, sounds.js, useWebSocket.js
│   ├── components/Navigation.jsx, BettingPanel.jsx, PlayingCard.jsx
│   └── pages/
│       ├── AuthPage.jsx       # Dual role login/signup
│       ├── LobbyPage.jsx      # Role-aware lobby
│       ├── TablePage.jsx      # Poker table view
│       ├── AgentDashboard.jsx  # Agent management
│       ├── WalletPage.jsx     # Role-aware wallet
│       ├── TournamentPage.jsx # Tournament bracket
│       ├── LeaderboardPage.jsx
│       └── ProfilePage.jsx    # Role-aware profile
```

## What's Been Implemented

### Phase 0 (Previous Session) - Core MVP
- Full-stack scaffolding (FastAPI + React + MongoDB)
- User auth (JWT), game tables, Texas Hold'em game engine
- PokerStars-style poker table UI (4/5/6 players)
- CSS animations (card dealing, chip flying)
- Sound effects via Web Audio API
- WebSocket real-time updates
- Tournament mode (8-agent bracket)
- Leaderboard, wallet system

### Phase 1 (Current Session - Mar 10, 2026) - Dual Login System
- **Dual Auth:** Agent and Human/Spectator role selection on signup
- **Agent Creation:** Each agent user gets a unique MoltBot agent with random strategy & avatar
- **Crypto Wallets:** Agent users get generated BTC, LTC, ETH deposit addresses
- **Agent Dashboard:** Full dashboard showing agent card, stats, wallet, crypto addresses
- **Live Activity Feed:** Real-time feed on Agent Dashboard showing recent game results (wins/losses, hands, opponents, pot amounts) with auto-refresh every 8 seconds and manual refresh button
- **Recent Earnings:** Earnings feed showing SC credits from game winnings
- **Role-Based Navigation:** Agent nav (Lobby, Agent, Tourney, Wallet, Profile), Human nav (Lobby, Tourney, Wallet, Ranks, Profile)
- **Role-Aware UI:** Lobby banner, profile, wallet all adapt to user role
- **Winner Credits:** Agent owner wallets credited when their agent wins a game
- **Testing:** 100% pass rate on backend (20/20) and frontend

## Prioritized Backlog

### P0 - In Progress
- ~~Phase 1: Dual Login System~~ DONE

### P1 - Next Up
- Phase 2: Stripe integration for SweepCoin purchases
- Phase 3: Crypto deposit system (real monitoring, price feeds)
- Phase 4: Human spectator betting system improvements

### P2 - Future
- Real OpenClaw/MoltBot agent integration
- Chip movement animations
- Late join for tournaments
- Backend refactoring (split server.py into routers)
- Frontend refactoring (extract TablePage sub-components)

## DB Schema
- **users:** `{ id, username, email, password_hash, role, agent_id, created_at }`
- **agents:** `{ id, name, strategy, avatar_url, tagline, owner_id, is_house, wins, losses, total_games, total_chips_won }`
- **wallets:** `{ id, user_id, sc_balance, gc_balance, crypto_addresses, pending_deposits }`
- **tables:** `{ id, name, min_bet, max_bet, agent_ids, current_game_id, status }`
- **games:** `{ id, table_id, phase, players, community_cards, pot, deck, winner_id, house_rake, final_pot }`
- **tournaments:** `{ id, name, status, agent_ids, bracket, champion_id }`
- **bets/tournament_bets:** `{ id, user_id, game_id/tournament_id, agent_id, amount, currency, status, payout }`
- **transactions:** `{ id, user_id, type, amount, currency, description }`

## API Endpoints
- `POST /api/auth/signup` (with role & agent_name)
- `POST /api/auth/login`
- `GET /api/auth/me` (returns role & agent data)
- `GET /api/agents`, `GET /api/agents/my-agent`, `GET /api/agents/{id}`
- `GET /api/tables`, `GET /api/tables/{id}`, `POST /api/tables/{id}/start-game`
- `POST /api/games/{id}/advance`
- `POST /api/bets`, `GET /api/bets/my-bets`, `GET /api/bets/game/{id}`
- `GET /api/wallet`, `POST /api/wallet/purchase`, `POST /api/wallet/cashout`
- `GET /api/tournaments`, `POST /api/tournaments`, `POST /api/tournaments/{id}/advance`
- `POST /api/tournament-bets`
- `GET /api/leaderboard`
- `WS /api/ws/table/{table_id}`

## Test Credentials
- Agent: agent@test.com / test123
- Human: human@test.com / test123
