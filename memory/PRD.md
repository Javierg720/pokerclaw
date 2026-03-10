# PokerClaw - Product Requirements Document

## Original Problem Statement
POKERCLAW - A mobile-friendly web app where OpenClaw agents play poker for money. Texas Hold'em with sweepstakes coins (GC/SC). House keeps 20% of pots. Users watch AI agents play and bet on outcomes.

## Architecture
- **Frontend**: React + Tailwind + shadcn/ui
- **Backend**: FastAPI (Python)
- **Database**: MongoDB
- **Auth**: JWT-based

## User Personas
1. **Crypto-native gamers** - Want sweepstakes coins redeemable to crypto
2. **Poker enthusiasts** - Enjoy watching AI play Texas Hold'em
3. **AI/Agent enthusiasts** - Interested in OpenClaw agent strategies
4. **Casual bettors** - Want to bet on agent outcomes

## Core Requirements
- [x] JWT Authentication (signup/login)
- [x] 8 pre-seeded OpenClaw AI agents with unique strategies
- [x] 3 poker tables with different bet ranges
- [x] Texas Hold'em game engine with full hand evaluation
- [x] Game phases: waiting->preflop->flop->turn->river->showdown->complete
- [x] Agent AI decision-making (fold/call/raise based on strategy)
- [x] Sweepstakes coins (GC free, SC premium/redeemable)
- [x] Betting system (pari-mutuel with 20% house rake)
- [x] Wallet with purchase/cashout
- [x] Leaderboard (top agents + top bettors)
- [x] Mobile-first dark casino UI

## What's Been Implemented (March 10, 2026)
### Backend (17 endpoints, 100% tested)
- Auth: signup, login, me
- Agents: list all 8 agents
- Tables: list, get, start-game
- Games: get, advance
- Bets: place, my-bets, game-bets
- Wallet: get, purchase, cashout, transactions
- Leaderboard: top agents + bettors

### Frontend (6 pages)
- AuthPage: Login/Signup with PokerClaw branding
- LobbyPage: Browse 3 tables with LIVE/OPEN status
- TablePage: Full poker game view with cards, agents, actions, betting
- WalletPage: GC/SC balances, purchase, cashout, transaction history
- LeaderboardPage: Top agents + top bettors tabs
- ProfilePage: User info + logout

### Game Engine
- Full Texas Hold'em: deck, dealing, 5-card hand evaluation
- 6 agent strategies: aggressive, conservative, balanced, bluffer, tight_aggressive, loose_passive
- Community cards: flop (3), turn (1), river (1)
- Hand rankings: Royal Flush to High Card

## Prioritized Backlog
### P0
- Real-time game updates (WebSocket)
- OpenClaw SKILL.md integration for real agent connections

### P1
- Real crypto cashout via Stripe/crypto integration
- Game history page
- Agent profile pages with detailed stats
- Multi-table spectating

### P2
- Chat/commentary system
- Sound effects for card deals, wins
- Push notifications for big wins
- Tournament mode
