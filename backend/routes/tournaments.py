from fastapi import APIRouter, HTTPException, Depends, Header
from pydantic import BaseModel, Field
from typing import Literal
import uuid
import random
from datetime import datetime, timezone
from deps import db, require_agent, require_human, get_current_user, bet_limiter
from game_engine import create_deck, advance_game
from agent_entertainment import public_personality
from sweepstakes import ensure_sc_play_eligible
from bet_settlement import settle_parimutuel_bets
from wagering import close_event_betting, place_wager
from game_persistence import persist_game_transition

router = APIRouter(prefix="/api")


class TournamentBetRequest(BaseModel):
    tournament_id: str
    agent_id: str
    amount: int = Field(gt=0)
    currency: Literal["sc", "gc"] = "gc"


class TablePilotLinkRequest(BaseModel):
    tournament_ids: list[str] = Field(min_length=1, max_length=50)


async def _persist_tournament_transition(tournament: dict, prior_status: str,
                                          expected_revision: int | None) -> None:
    """Save bracket changes, atomically closing betting on completion."""
    query = {
        "id": tournament["id"],
        "status": prior_status,
        "tournament_revision": (
            {"$exists": False} if expected_revision is None else expected_revision
        ),
    }
    fields = {
        key: value for key, value in tournament.items()
        if key not in {"_id", "id", "bet_sequence", "betting_closed",
                       "betting_closed_at", "tournament_revision"}
    }
    if tournament["status"] == "complete":
        # A wager transaction writes this same event document. Publishing the
        # winner and closing its betting window in one write prevents late
        # bets from entering the pool between completion and settlement.
        fields["betting_closed"] = True
        fields["betting_closed_at"] = datetime.now(timezone.utc).isoformat()
    result = await db.tournaments.update_one(
        query, {"$set": fields, "$inc": {"tournament_revision": 1}},
    )
    if result.modified_count != 1:
        raise HTTPException(status_code=409, detail="Tournament changed concurrently. Refresh and retry.")
    tournament["tournament_revision"] = (expected_revision or 0) + 1
    if tournament["status"] == "complete":
        tournament["betting_closed"] = True
        tournament["betting_closed_at"] = fields["betting_closed_at"]


async def _finalize_completed_tournament(tournament: dict) -> None:
    """Replay safe settlement after completion or a failed prior response."""
    if tournament.get("status") != "complete":
        return
    await close_event_betting("tournaments", tournament["id"])
    await settle_parimutuel_bets(
        "tournament_bets", {"tournament_id": tournament["id"]},
        tournament.get("champion_id"), "tournament_won",
        f"Won tournament bet on {tournament.get('champion_name')}",
    )


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
            "personality_key": agent.get('personality_key'),
            "personality": agent.get('personality') or public_personality(agent),
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
    expected_revision = game.get('game_revision')
    updated = advance_game(game)
    if updated['phase'] == 'complete':
        updated['completed_at'] = datetime.now(timezone.utc).isoformat()
    await persist_game_transition(updated, expected_revision)
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


@router.get("/table-pilot")
async def get_table_pilot_workspace(user=Depends(get_current_user)):
    workspace = await db.table_pilot_workspaces.find_one(
        {"user_id": user["id"]}, {"_id": 0}
    )
    tournament_ids = workspace.get("tournament_ids", []) if workspace else []
    tournaments = await db.tournaments.find(
        {"id": {"$in": tournament_ids}}, {"_id": 0}
    ).to_list(50)
    by_id = {item["id"]: item for item in tournaments}
    ordered = [by_id[item_id] for item_id in tournament_ids if item_id in by_id]
    return {
        "tournament_ids": tournament_ids,
        "tournaments": ordered,
        "updated_at": workspace.get("updated_at") if workspace else None,
    }


@router.post("/table-pilot/links")
async def link_table_pilot_tournaments(
    req: TablePilotLinkRequest,
    user=Depends(get_current_user),
):
    tournament_ids = list(dict.fromkeys(req.tournament_ids))
    existing = await db.tournaments.find(
        {"id": {"$in": tournament_ids}}, {"_id": 0, "id": 1}
    ).to_list(50)
    existing_ids = {item["id"] for item in existing}
    missing = [item_id for item_id in tournament_ids if item_id not in existing_ids]
    if missing:
        raise HTTPException(status_code=404, detail="One or more tournaments were not found")

    now = datetime.now(timezone.utc).isoformat()
    await db.table_pilot_workspaces.update_one(
        {"user_id": user["id"]},
        {
            "$setOnInsert": {"id": str(uuid.uuid4()), "user_id": user["id"]},
            "$set": {"updated_at": now},
            "$addToSet": {"tournament_ids": {"$each": tournament_ids}},
        },
        upsert=True,
    )
    return await get_table_pilot_workspace(user)


@router.delete("/table-pilot/links/{tournament_id}")
async def unlink_table_pilot_tournament(
    tournament_id: str,
    user=Depends(get_current_user),
):
    await db.table_pilot_workspaces.update_one(
        {"user_id": user["id"]},
        {
            "$pull": {"tournament_ids": tournament_id},
            "$set": {"updated_at": datetime.now(timezone.utc).isoformat()},
        },
    )
    return await get_table_pilot_workspace(user)


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

    prior_revision = t.get('tournament_revision')
    t['agent_ids'][req.slot_index] = req.agent_id
    # Update bracket semi assignments
    t['bracket']['semi_1']['agent_ids'] = t['agent_ids'][:4]
    t['bracket']['semi_2']['agent_ids'] = t['agent_ids'][4:8]

    await _persist_tournament_transition(t, 'lobby', prior_revision)
    return {k: v for k, v in t.items() if k != '_id'}


@router.post("/tournaments/{tournament_id}/advance")
async def advance_tournament(tournament_id: str, user=Depends(require_agent)):
    t = await db.tournaments.find_one({"id": tournament_id}, {"_id": 0})
    if not t:
        raise HTTPException(status_code=404, detail="Tournament not found")
    if user.get("agent_id") not in t.get("agent_ids", []):
        raise HTTPException(status_code=403, detail="Your OpenClaw agent is not in this tournament")
    if t['status'] == 'complete':
        await _finalize_completed_tournament(t)
        return t

    prior_status = t['status']
    prior_revision = t.get('tournament_revision')
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

    t['bracket'] = bracket
    await _persist_tournament_transition(t, prior_status, prior_revision)
    await _finalize_completed_tournament(t)
    return {k: v for k, v in t.items() if k != '_id'}


@router.post("/tournament-bets")
async def place_tournament_bet(
    req: TournamentBetRequest,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    user=Depends(require_human),
):
    if not await bet_limiter.is_allowed(user["id"]):
        raise HTTPException(status_code=429, detail="Bet rate limit exceeded. Max 60 bets per minute.")
    if not idempotency_key:
        raise HTTPException(status_code=400, detail="Idempotency-Key header is required")
    if req.currency == "sc":
        await ensure_sc_play_eligible(user)

    def validate_tournament(tournament: dict) -> None:
        if req.agent_id not in tournament["agent_ids"]:
            raise HTTPException(status_code=400, detail="Agent not in this tournament")

    bet = await place_wager(
        collection_name="tournament_bets",
        event_collection_name="tournaments",
        event_id=req.tournament_id,
        event_open_query={"status": {"$ne": "complete"}},
        validate_event=validate_tournament,
        user_id=user["id"],
        agent_id=req.agent_id,
        amount=req.amount,
        currency=req.currency,
        transaction_type="tournament_bet",
        idempotency_key=idempotency_key,
    )
    return {key: value for key, value in bet.items() if key != "_id"}
