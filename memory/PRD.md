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

### Phase 2 (Current Session - Mar 10, 2026) - Stripe Payments
- **Stripe Checkout:** Full integration using emergentintegrations library with sk_test_emergent
- **Fixed SC Packages:** 4 packages (50 SC/$4.99, 200 SC/$14.99, 500 SC/$34.99, 1000 SC/$59.99) defined server-side only
- **Checkout Flow:** Frontend sends package_id + origin_url → Backend creates Stripe session → User redirected to Stripe → Return with session_id → Frontend polls status → SC credited
- **Payment Transactions:** payment_transactions collection tracks all Stripe sessions
- **Webhook Support:** POST /api/webhook/stripe handles Stripe events as backup to polling
- **Security:** Amounts never sent from frontend, dynamic success/cancel URLs, idempotent credit processing
- **Testing:** 100% pass rate on backend (17/17) and frontend

### Phase 3 (Current Session - Mar 10, 2026) - Crypto Deposit System
- **CoinGecko Integration:** Live BTC/LTC/ETH → USD price feed with 60s caching and fallback prices
- **Deposit Flow:** Agents submit tx_hash + crypto amount → Backend calculates SC at 100 SC/$1 USD using live price → Pending status with 0/2 confirmations
- **2-Confirmation System:** Each confirmation increments count; at 2/2 confirmations, SC is auto-credited to wallet
- **Duplicate Protection:** Same tx_hash cannot be submitted twice
- **Frontend:** Live price ticker, deposit form per crypto, pending/confirmed deposits with status tracking
- **Testing:** 100% pass rate on backend (21/21) and frontend

### Phase 5 (Current Session - Mar 10, 2026) - Turn-by-Turn Agent Decisions
- **Game Engine Rewrite:** Each `advance_game` call processes ONE agent's action (fold/call/raise) instead of entire rounds
- **Phase Flow:** waiting → preflop_betting → flop_deal → flop_betting → turn_deal → turn_betting → river_deal → river_betting → showdown → complete
- **Current Actor Tracking:** `current_actor` field shows which agent is deciding; `last_action` shows what they did
- **10-Second Decision Timer:** Frontend shows countdown with "THINKING" badge and glowing ring on active agent
- **AUTO Mode:** Auto-advances with 2-8 second random delays per agent for natural pacing
- **Tournament Fix:** Semis play to instant completion, final plays turn-by-turn for spectator viewing
- **Testing:** 100% pass rate - backend (10/10 games + 8/8 tournaments) and all frontend flows
- **Live Odds:** GET /api/bets/game/{id}/odds calculates real-time multipliers based on bet pool distribution
- **Multiplier Formula:** (total_pool * 0.8) / agent_pool; default = active_players * 0.8 for unbacked agents
- **Enhanced BettingPanel:** Agent selection cards with avatars, multipliers, pool % bars, bet slider (10-1000 SC), potential win display
- **Live Odds Ticker:** Scrollable bar at top of table showing all agents' odds during active games
- **Your Bets Tracking:** Shows placed bets with LIVE/WON/LOST status per game
- **Bet Pool Info:** Shown on game completion alongside winner details
- **Testing:** 100% pass rate on backend (14/14) and all frontend flows

### P0 - Complete
- ~~Phase 1: Dual Login System~~ DONE
- ~~Phase 2: Stripe Integration~~ DONE
- ~~Phase 3: Crypto Deposit System~~ DONE
- ~~Phase 4: Spectator Betting~~ DONE

### P1 - Next Up
- Real OpenClaw/MoltBot agent integration

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
