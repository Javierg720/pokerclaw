from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field
from typing import Literal
import uuid
import random
from datetime import datetime, timezone
from deps import db, require_agent, require_human
from game_engine import create_deck, advance_game

router = APIRouter(prefix="/api")


class TournamentBetRequest(BaseModel):
    tournament_id: str
    agent_id: str
    amount: int = Field(gt=0)
    currency: Literal["sc", "gc"] = "gc"


async def _create_tournament_game(agent_ids_list):
    agents = []
    for aid in agent_ids_list:
        agent = await db.agents.find_one({"id": aid}, {"_id": 0})
        if agent:
            agents.append(agent)

    deck = create_deck()
    game_id = str(uuid.uuid4())
    players = []
    for i, agent in enumerate(agents):
        players.append({
            "agent_id": agent['id'], "agent_name": agent['name'],
            "avatar_url": agent['avatar_url'], "strategy": agent['strategy'],
            "is_external": agent.get('is_external', False),
            "hole_cards": [], "chips": 1000, "current_bet": 0,
            "total_bet": 0, "folded": False, "is_dealer": i == 0,
            "hand_rank": 0, "hand_name": ""
        })

    game = {
        "id": game_id, "table_id": None, "phase": "waiting",
        "players": players, "community_cards": [], "pot": 0,
        "deck": deck, "dealer_index": 0, "actions_log": [],
        "current_actor": None, "turn_index": 0,
        "round_bet": 0, "round_phase": None, "last_action": None,
        "winner_id": None, "winner_name": None, "winning_hand": None,
        "house_rake": 0, "final_pot": 0,
        "created_at": datetime.now(timezone.utc).isoformat(), "completed_at": None
    }
    await db.games.insert_one(game)
    return game_id


async def _advance_tournament_game(game_id):
    game = await db.games.find_one({"id": game_id}, {"_id": 0})
    if not game or game['phase'] == 'complete':
        return game
    updated = advance_game(game)
    if updated['phase'] == 'complete':
        updated['completed_at'] = datetime.now(timezone.utc).isoformat()
    save_doc = {k: v for k, v in updated.items() if k != '_id'}
    await db.games.replace_one({"id": game_id}, save_doc)
    return updated


async def _play_tournament_game_to_completion(game_id, max_steps=200):
    for _ in range(max_steps):
        game = await _advance_tournament_game(game_id)
        if not game or game['phase'] == 'complete':
            return game
    return await db.games.find_one({"id": game_id}, {"_id": 0})


def _get_top2(game):
    if not game or not game.get('players'):
        return []
    active = [p for p in game['players'] if not p['folded']]
    folded = [p for p in game['players'] if p['folded']]
    ranked = active + folded
    return [p['agent_id'] for p in ranked[:2]]


@router.get("/tournaments")
async def list_tournaments():
    tournaments = await db.tournaments.find({}, {"_id": 0}).sort("created_at", -1).to_list(50)
    return tournaments


@router.get("/tournaments/{tournament_id}")
async def get_tournament(tournament_id: str):
    t = await db.tournaments.find_one({"id": tournament_id}, {"_id": 0})
    if not t:
        raise HTTPException(status_code=404, detail="Tournament not found")
    return t


@router.post("/tournaments")
async def create_tournament(user=Depends(require_agent)):
    agents = await db.agents.find({}, {"_id": 0}).to_list(100)
    if len(agents) < 8:
        raise HTTPException(status_code=400, detail="Not enough agents (need 8)")

    own_agent_id = user.get("agent_id")
    own_agent = next((agent for agent in agents if agent["id"] == own_agent_id), None)
    if not own_agent:
        raise HTTPException(status_code=403, detail="OpenClaw agent profile required")

    opponents = [agent for agent in agents if agent["id"] != own_agent_id]
    selected = [own_agent, *random.sample(opponents, 7)]
    agent_ids = [a['id'] for a in selected]
    random.shuffle(agent_ids)

    names = [
        "Claw Championship", "MoltBot Masters", "Deep Stack Showdown",
        "Quantum Poker Open", "Neural Net Invitational", "Bluff League Finals"
    ]

    tournament = {
        "id": str(uuid.uuid4()), "name": random.choice(names),
        "status": "lobby", "agent_ids": agent_ids,
        "bracket": {
            "semi_1": {
                "agent_ids": agent_ids[:4], "game_id": None,
                "game_phase": None, "complete": False, "winners": []
            },
            "semi_2": {
                "agent_ids": agent_ids[4:8], "game_id": None,
                "game_phase": None, "complete": False, "winners": []
            },
            "final": {
                "agent_ids": [], "game_id": None,
                "game_phase": None, "complete": False, "winner": None
            },
        },
        "champion_id": None, "champion_name": None,
        "created_at": datetime.now(timezone.utc).isoformat(), "completed_at": None
    }
    await db.tournaments.insert_one(tournament)
    return {k: v for k, v in tournament.items() if k != '_id'}


class TournamentJoinRequest(BaseModel):
    slot_index: int  # 0-7, which slot to replace
    agent_id: str    # agent to place in that slot


@router.post("/tournaments/{tournament_id}/join")
async def join_tournament(tournament_id: str, req: TournamentJoinRequest, user=Depends(require_agent)):
    """Allow an agent to join/replace a slot in a tournament that hasn't started yet."""
    t = await db.tournaments.find_one({"id": tournament_id}, {"_id": 0})
    if not t:
        raise HTTPException(status_code=404, detail="Tournament not found")
    if t['status'] != 'lobby':
        raise HTTPException(status_code=400, detail="Tournament already started. Cannot join.")
    if req.slot_index < 0 or req.slot_index >= len(t['agent_ids']):
        raise HTTPException(status_code=400, detail="Invalid slot index")
    if req.agent_id != user.get("agent_id"):
        raise HTTPException(status_code=403, detail="You can only seat your own OpenClaw agent")

    agent = await db.agents.find_one({"id": req.agent_id}, {"_id": 0})
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    if req.agent_id in t['agent_ids']:
        raise HTTPException(status_code=400, detail="Agent already in tournament")

    t['agent_ids'][req.slot_index] = req.agent_id
    # Update bracket semi assignments
    t['bracket']['semi_1']['agent_ids'] = t['agent_ids'][:4]
    t['bracket']['semi_2']['agent_ids'] = t['agent_ids'][4:8]

    save_doc = {k: v for k, v in t.items() if k != '_id'}
    await db.tournaments.replace_one({"id": tournament_id}, save_doc)
    return save_doc


@router.post("/tournaments/{tournament_id}/advance")
async def advance_tournament(tournament_id: str, user=Depends(require_agent)):
    t = await db.tournaments.find_one({"id": tournament_id}, {"_id": 0})
    if not t:
        raise HTTPException(status_code=404, detail="Tournament not found")
    if t['status'] == 'complete':
        raise HTTPException(status_code=400, detail="Tournament already complete")
    if user.get("agent_id") not in t.get("agent_ids", []):
        raise HTTPException(status_code=403, detail="Your OpenClaw agent is not in this tournament")

    bracket = t['bracket']

    if t['status'] == 'lobby':
        gid1 = await _create_tournament_game(bracket['semi_1']['agent_ids'])
        gid2 = await _create_tournament_game(bracket['semi_2']['agent_ids'])
        bracket['semi_1']['game_id'] = gid1
        bracket['semi_2']['game_id'] = gid2

        game1 = await _play_tournament_game_to_completion(gid1)
        game2 = await _play_tournament_game_to_completion(gid2)

        bracket['semi_1']['game_phase'] = 'complete'
        bracket['semi_1']['complete'] = True
        bracket['semi_1']['winners'] = _get_top2(game1)

        bracket['semi_2']['game_phase'] = 'complete'
        bracket['semi_2']['complete'] = True
        bracket['semi_2']['winners'] = _get_top2(game2)

        final_agents = bracket['semi_1']['winners'] + bracket['semi_2']['winners']
        bracket['final']['agent_ids'] = final_agents
        gid_final = await _create_tournament_game(final_agents)
        bracket['final']['game_id'] = gid_final
        bracket['final']['game_phase'] = 'waiting'
        t['status'] = 'final'

    elif t['status'] == 'final':
        final = bracket['final']
        if not final['complete'] and final['game_id']:
            game = await _advance_tournament_game(final['game_id'])
            display_phase = {
                'preflop_betting': 'preflop', 'flop_deal': 'flop',
                'flop_betting': 'flop', 'turn_deal': 'turn',
                'turn_betting': 'turn', 'river_deal': 'river',
                'river_betting': 'river',
            }
            final['game_phase'] = display_phase.get(game['phase'], game['phase']) if game else None
            if game and game['phase'] == 'complete':
                final['complete'] = True
                final['winner'] = game.get('winner_id')
                t['champion_id'] = game.get('winner_id')
                t['champion_name'] = game.get('winner_name')
                t['status'] = 'complete'
                t['completed_at'] = datetime.now(timezone.utc).isoformat()

                bets = await db.tournament_bets.find(
                    {"tournament_id": tournament_id, "status": "pending"}, {"_id": 0}
                ).to_list(1000)
                total_pool = sum(b['amount'] for b in bets)
                winning_bets = [b for b in bets if b['agent_id'] == t['champion_id']]
                total_winning = sum(b['amount'] for b in winning_bets)

                for bet in bets:
                    if bet['agent_id'] == t['champion_id'] and total_winning > 0:
                        payout = int((bet['amount'] / total_winning) * total_pool * 0.8)
                        await db.tournament_bets.update_one(
                            {"id": bet['id']}, {"$set": {"status": "won", "payout": payout}})
                        cf = f"{bet['currency']}_balance"
                        await db.wallets.update_one({"user_id": bet['user_id']}, {"$inc": {cf: payout}})
                        await db.transactions.insert_one({
                            "id": str(uuid.uuid4()), "user_id": bet['user_id'],
                            "type": "tournament_won", "amount": payout,
                            "currency": bet['currency'],
                            "description": f"Won tournament bet on {t['champion_name']}",
                            "created_at": datetime.now(timezone.utc).isoformat()
                        })
                    else:
                        await db.tournament_bets.update_one(
                            {"id": bet['id']}, {"$set": {"status": "lost", "payout": 0}})

    t['bracket'] = bracket
    save_doc = {k: v for k, v in t.items() if k != '_id'}
    await db.tournaments.replace_one({"id": tournament_id}, save_doc)
    return save_doc


@router.post("/tournament-bets")
async def place_tournament_bet(req: TournamentBetRequest, user=Depends(require_human)):
    t = await db.tournaments.find_one({"id": req.tournament_id}, {"_id": 0})
    if not t:
        raise HTTPException(status_code=404, detail="Tournament not found")
    if t['status'] == 'complete':
        raise HTTPException(status_code=400, detail="Tournament already complete")
    if req.agent_id not in t['agent_ids']:
        raise HTTPException(status_code=400, detail="Agent not in this tournament")

    balance_field = f"{req.currency}_balance"
    result = await db.wallets.update_one(
        {"user_id": user['id'], balance_field: {"$gte": req.amount}},
        {"$inc": {balance_field: -req.amount}},
    )
    if result.modified_count != 1:
        raise HTTPException(status_code=400, detail="Insufficient balance")

    bet = {
        "id": str(uuid.uuid4()), "user_id": user['id'],
        "tournament_id": req.tournament_id, "agent_id": req.agent_id,
        "amount": req.amount, "currency": req.currency,
        "status": "pending", "payout": 0,
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    await db.tournament_bets.insert_one(bet)

    await db.transactions.insert_one({
        "id": str(uuid.uuid4()), "user_id": user['id'],
        "type": "tournament_bet", "amount": -req.amount, "currency": req.currency,
        "description": "Tournament bet placed",
        "created_at": datetime.now(timezone.utc).isoformat()
    })

    return {k: v for k, v in bet.items() if k != '_id'}
