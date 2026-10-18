"""Real Mongo transaction race between spectator wagers and game completion."""
import asyncio
import os
import uuid

import pytest
from fastapi import HTTPException
from motor.motor_asyncio import AsyncIOMotorClient


TEST_MONGO_URL = os.environ.get("POKERCLAW_TEST_MONGO_URL", "")


@pytest.mark.skipif(not TEST_MONGO_URL, reason="requires a disposable replica set via POKERCLAW_TEST_MONGO_URL")
def test_concurrent_placement_and_game_close_never_loses_or_credits_extra_gc(monkeypatch):
    import bet_settlement
    import game_persistence
    import wagering

    async def run():
        client = AsyncIOMotorClient(TEST_MONGO_URL)
        database = client[f"pokerclaw_close_race_{uuid.uuid4().hex}"]
        monkeypatch.setattr(wagering, "client", client)
        monkeypatch.setattr(wagering, "db", database)
        monkeypatch.setattr(game_persistence, "db", database)
        monkeypatch.setattr(bet_settlement, "db", database)
        try:
            await database.games.insert_one({
                "id": "game", "phase": "preflop_betting", "bet_sequence": 0,
                "players": [{"agent_id": "winner"}, {"agent_id": "other"}],
            })
            await database.bets.create_index("id", unique=True)
            await database.wallets.create_index("user_id", unique=True)
            await database.transactions.create_index("id", unique=True)

            users = [f"bettor-{number}" for number in range(13)]
            await database.wallets.insert_many([
                {"user_id": user, "gc_balance": 1000} for user in users
            ])

            async def place(user, agent):
                return await wagering.place_wager(
                    collection_name="bets", event_collection_name="games",
                    event_id="game", event_open_query={"phase": {"$ne": "complete"}},
                    validate_event=lambda event: None, user_id=user,
                    agent_id=agent, amount=10, currency="gc",
                    transaction_type="bet_placed", idempotency_key=f"unique-{user}",
                )

            # One fully committed wager ensures the settlement pool is nonempty.
            first = await place(users[0], "winner")
            assert first["status"] == "pending"

            completed = {"id": "game", "phase": "complete", "winner_id": "winner", "players": []}
            tasks = [place(user, "winner" if idx % 2 == 0 else "other")
                     for idx, user in enumerate(users[1:], 1)]
            outcomes = await asyncio.gather(
                *tasks, game_persistence.persist_game_transition(completed, None),
                return_exceptions=True,
            )
            for outcome in outcomes[:-1]:
                if isinstance(outcome, Exception):
                    assert isinstance(outcome, HTTPException)
                    assert outcome.status_code in (409, 503)
            assert outcomes[-1] is None, f"game completion failed: {outcomes[-1]!r}"

            stored_game = await database.games.find_one({"id": "game"})
            assert stored_game["phase"] == "complete"
            assert stored_game["betting_closed"] is True
            bets = await database.bets.find({"game_id": "game"}).to_list(None)
            assert stored_game["bet_sequence"] == len(bets)

            await game_persistence.finalize_completed_game(completed)
            await game_persistence.finalize_completed_game(completed)
            settled = await database.bets.find({"game_id": "game"}).to_list(None)
            assert all(bet["status"] in {"won", "lost"} for bet in settled)
            for user in users:
                wallet = await database.wallets.find_one({"user_id": user})
                own_bets = [bet for bet in settled if bet["user_id"] == user]
                assert wallet["gc_balance"] == 1000 - sum(bet["amount"] for bet in own_bets) + sum(
                    bet["payout"] for bet in own_bets if bet["status"] == "won"
                )
                assert len(wallet.get("settled_bet_ids", [])) == sum(
                    bet["status"] == "won" for bet in own_bets
                )

            transactions = await database.transactions.find({}).to_list(None)
            assert len([entry for entry in transactions if entry["type"] == "bet_placed"]) == len(bets)
            assert len([entry for entry in transactions if entry["type"] == "bet_won"]) == sum(
                bet["status"] == "won" for bet in settled
            )
            with pytest.raises(HTTPException) as late:
                await place("post-completion", "winner")
            assert late.value.status_code == 409
        finally:
            await client.drop_database(database.name)
            client.close()

    asyncio.run(run())


@pytest.mark.skipif(not TEST_MONGO_URL, reason="requires a disposable replica set via POKERCLAW_TEST_MONGO_URL")
def test_simultaneous_joins_cannot_overfill_or_duplicate_table_seats(monkeypatch):
    import game_persistence

    async def run():
        client = AsyncIOMotorClient(TEST_MONGO_URL)
        database = client[f"pokerclaw_table_join_race_{uuid.uuid4().hex}"]
        monkeypatch.setattr(game_persistence, "db", database)
        try:
            await database.tables.insert_one({
                "id": "table", "agent_ids": [f"house-{n}" for n in range(7)],
                "current_game_id": None,
            })
            snapshot = await database.tables.find_one({"id": "table"}, {"_id": 0})
            outcomes = await asyncio.gather(*(
                game_persistence.claim_table_seat(snapshot, f"new-{n}")
                for n in range(20)
            ), return_exceptions=True)
            assert sum(outcome is None for outcome in outcomes) == 1
            assert all(
                outcome is None or (
                    isinstance(outcome, HTTPException) and outcome.status_code == 409
                ) for outcome in outcomes
            )
            stored = await database.tables.find_one({"id": "table"})
            assert len(stored["agent_ids"]) == 8
            assert len(set(stored["agent_ids"])) == 8
            with pytest.raises(HTTPException) as full:
                await game_persistence.claim_table_seat(stored, "extra")
            assert full.value.status_code == 400
        finally:
            await client.drop_database(database.name)
            client.close()

    asyncio.run(run())


@pytest.mark.skipif(not TEST_MONGO_URL, reason="requires a disposable replica set via POKERCLAW_TEST_MONGO_URL")
def test_tournament_close_races_wagers_and_completed_settlement_replays(monkeypatch):
    import bet_settlement
    import wagering
    from routes import tournaments

    async def run():
        client = AsyncIOMotorClient(TEST_MONGO_URL)
        database = client[f"pokerclaw_tournament_race_{uuid.uuid4().hex}"]
        monkeypatch.setattr(wagering, "client", client)
        monkeypatch.setattr(wagering, "db", database)
        monkeypatch.setattr(tournaments, "db", database)
        monkeypatch.setattr(bet_settlement, "db", database)
        original_settle = tournaments.settle_parimutuel_bets
        try:
            await database.tournaments.insert_one({
                "id": "event", "status": "final", "agent_ids": ["winner", "other"],
                "bracket": {}, "bet_sequence": 0, "tournament_revision": 0,
            })
            await database.tournament_bets.create_index("id", unique=True)
            await database.transactions.create_index("id", unique=True)
            await database.wallets.create_index("user_id", unique=True)
            users = [f"spectator-{index}" for index in range(13)]
            await database.wallets.insert_many([
                {"user_id": user, "gc_balance": 1000} for user in users
            ])

            async def place(user, agent):
                return await wagering.place_wager(
                    collection_name="tournament_bets", event_collection_name="tournaments",
                    event_id="event", event_open_query={"status": {"$ne": "complete"}},
                    validate_event=lambda event: None, user_id=user,
                    agent_id=agent, amount=10, currency="gc",
                    transaction_type="tournament_bet", idempotency_key=f"key-{user}",
                )

            await place(users[0], "winner")
            completed = {
                "id": "event", "status": "complete", "agent_ids": ["winner", "other"],
                "champion_id": "winner", "champion_name": "Winner", "bracket": {},
            }
            attempts = [place(user, "winner" if index % 2 == 0 else "other")
                        for index, user in enumerate(users[1:], 1)]
            outcomes = await asyncio.gather(
                *attempts,
                tournaments._persist_tournament_transition(completed, "final", 0),
                return_exceptions=True,
            )
            assert outcomes[-1] is None, f"completion failed: {outcomes[-1]!r}"
            for outcome in outcomes[:-1]:
                if isinstance(outcome, Exception):
                    assert isinstance(outcome, HTTPException)
                    assert outcome.status_code in (409, 503)

            event = await database.tournaments.find_one({"id": "event"})
            bets = await database.tournament_bets.find({"tournament_id": "event"}).to_list(None)
            assert event["status"] == "complete"
            assert event["betting_closed"] is True
            assert event["bet_sequence"] == len(bets)
            with pytest.raises(HTTPException) as late:
                await place("late-spectator", "winner")
            assert late.value.status_code == 409

            async def simulated_outage(*_args, **_kwargs):
                raise RuntimeError("test-only settlement interruption")

            monkeypatch.setattr(tournaments, "settle_parimutuel_bets", simulated_outage)
            with pytest.raises(RuntimeError, match="settlement interruption"):
                await tournaments._finalize_completed_tournament(completed)
            monkeypatch.setattr(tournaments, "settle_parimutuel_bets", original_settle)

            # A new advance request can recover from the interrupted settlement.
            await tournaments.advance_tournament("event", {"agent_id": "winner"})
            await tournaments.advance_tournament("event", {"agent_id": "winner"})
            settled = await database.tournament_bets.find({"tournament_id": "event"}).to_list(None)
            assert len(settled) == len(bets)
            assert all(bet["status"] in ("won", "lost") for bet in settled)
            for user in users:
                wallet = await database.wallets.find_one({"user_id": user})
                own = [bet for bet in settled if bet["user_id"] == user]
                assert wallet["gc_balance"] == 1000 - sum(bet["amount"] for bet in own) + sum(
                    bet["payout"] for bet in own if bet["status"] == "won"
                )
            entries = await database.transactions.find({}).to_list(None)
            assert len([entry for entry in entries if entry["type"] == "tournament_bet"]) == len(bets)
            assert len([entry for entry in entries if entry["type"] == "tournament_won"]) == sum(
                bet["status"] == "won" for bet in settled
            )
        finally:
            await client.drop_database(database.name)
            client.close()

    asyncio.run(run())
