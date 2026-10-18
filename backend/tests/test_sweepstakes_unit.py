import asyncio
import os
import sys
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
import pytest
from fastapi import HTTPException
from fastapi.websockets import WebSocketDisconnect
from pymongo.errors import DuplicateKeyError


os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "pokerclaw_test")
os.environ.setdefault("JWT_SECRET", "unit-test-secret-that-is-not-used-in-production")

import sweepstakes  # noqa: E402
import bet_settlement  # noqa: E402
import game_persistence  # noqa: E402
import deps  # noqa: E402
import wagering  # noqa: E402
from routes import crypto  # noqa: E402
from routes import wallet  # noqa: E402
from routes import agent_api  # noqa: E402
from routes import tournaments as tournament_routes  # noqa: E402
from routes.auth import _client_ip  # noqa: E402
from routes import sweepstakes as sweepstakes_routes  # noqa: E402
from routes.bets import BetRequest, place_bet  # noqa: E402
from routes.tournaments import TournamentBetRequest, place_tournament_bet  # noqa: E402
from routes.stripe_routes import (  # noqa: E402
    disabled_stripe_checkout,
    disabled_stripe_status,
    get_stripe_packages,
)


class _UpdateResult:
    def __init__(self, modified_count):
        self.modified_count = modified_count


def _matches(document, query):
    for key, expected in query.items():
        actual = document.get(key)
        if isinstance(expected, dict):
            if "$exists" in expected and (key in document) != expected["$exists"]:
                return False
            if "$in" in expected and actual not in expected["$in"]:
                return False
            if "$nin" in expected and actual in expected["$nin"]:
                return False
            if "$ne" in expected:
                prohibited = expected["$ne"]
                if actual == prohibited or (isinstance(actual, list) and prohibited in actual):
                    return False
            if "$gte" in expected and (actual is None or actual < expected["$gte"]):
                return False
        elif actual != expected:
            return False
    return True


class _Cursor:
    def __init__(self, documents):
        self.documents = documents

    async def to_list(self, _limit):
        return [document.copy() for document in self.documents]

    def sort(self, *_args):
        return self


class _Collection:
    def __init__(self, documents=()):
        self.documents = [document.copy() for document in documents]
        self.indexes = []

    def find(self, query, _projection=None):
        return _Cursor([document for document in self.documents if _matches(document, query)])

    async def find_one(self, query, _projection=None, session=None):
        document = next((item for item in self.documents if _matches(item, query)), None)
        return document.copy() if document else None

    async def update_one(self, query, update, upsert=False, session=None):
        await asyncio.sleep(0)
        document = next((item for item in self.documents if _matches(item, query)), None)
        inserted = False
        if document is None:
            if not upsert:
                return _UpdateResult(0)
            document = {
                key: value for key, value in query.items()
                if not isinstance(value, dict)
            }
            self.documents.append(document)
            inserted = True

        for key, value in update.get("$set", {}).items():
            document[key] = value
        for key, value in update.get("$inc", {}).items():
            document[key] = document.get(key, 0) + value
        for key, value in update.get("$addToSet", {}).items():
            if value not in document.setdefault(key, []):
                document[key].append(value)
        if inserted:
            for key, value in update.get("$setOnInsert", {}).items():
                document[key] = value
        return _UpdateResult(1)

    async def insert_many(self, documents):
        self.documents.extend(document.copy() for document in documents)

    async def insert_one(self, document, session=None):
        if any(item.get("id") == document.get("id") for item in self.documents):
            raise DuplicateKeyError("duplicate id")
        self.documents.append(document.copy())

    async def delete_one(self, query):
        document = next((item for item in self.documents if _matches(item, query)), None)
        if document is None:
            return _UpdateResult(0)
        self.documents.remove(document)
        return _UpdateResult(1)

    async def replace_one(self, query, document):
        existing = next((item for item in self.documents if _matches(item, query)), None)
        if existing is None:
            return _UpdateResult(0)
        self.documents[self.documents.index(existing)] = document.copy()
        return _UpdateResult(1)

    async def create_index(self, field, unique, name, **options):
        self.indexes.append((field, unique, name, options))


class _Session:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    def start_transaction(self):
        return self

    async def with_transaction(self, callback):
        return await callback(self)


class _Client:
    async def start_session(self):
        return _Session()


async def _no_op_close_event_betting(*_args):
    return None


class _Database:
    def __init__(self, **collections):
        self._collections = {
            name: _Collection(documents) for name, documents in collections.items()
        }

    def __getitem__(self, name):
        return self._collections[name]

    def __getattr__(self, name):
        return self._collections[name]


def test_sweepstakes_features_are_fail_closed_by_default(monkeypatch):
    for name in (
        "SWEEPSTAKES_PLAY_ENABLED",
        "SWEEPSTAKES_FUNDING_ENABLED",
        "SWEEPSTAKES_REDEMPTION_ENABLED",
        "CRYPTO_PAYOUTS_ENABLED",
    ):
        monkeypatch.delenv(name, raising=False)

    config = sweepstakes.public_config()
    assert config["model"] == "purchased_gc_with_promotional_sc"
    assert config["no_purchase_necessary"] is True
    assert config["gc_redeemable"] is False
    assert config["sc_play_enabled"] is False
    assert config["funding_enabled"] is False
    assert config["redemption_enabled"] is False
    monkeypatch.setenv("SWEEPSTAKES_REDEMPTION_ENABLED", "true")
    monkeypatch.setenv("CRYPTO_PAYOUTS_ENABLED", "true")
    assert sweepstakes.public_config()["redemption_enabled"] is False
    assert BetRequest(game_id="game", agent_id="agent", amount=10).currency == "gc"


def test_sc_cannot_be_enabled_by_environment_flags(monkeypatch):
    monkeypatch.setenv("SWEEPSTAKES_PLAY_ENABLED", "true")
    monkeypatch.setenv("DAILY_FREE_SC", "1")
    monkeypatch.setenv("SWEEPSTAKES_NO_PURCHASE_ENTRY_ENABLED", "true")
    assert sweepstakes.public_config()["sc_play_enabled"] is False
    monkeypatch.setenv("SWEEPSTAKES_FUNDING_ENABLED", "true")
    monkeypatch.setenv("SWEEPSTAKES_REDEMPTION_ENABLED", "true")
    assert sweepstakes.public_config()["redemption_enabled"] is False
    monkeypatch.setenv("CRYPTO_PAYOUTS_ENABLED", "true")
    config = sweepstakes.public_config()
    assert config["funding_enabled"] is False
    assert config["redemption_enabled"] is False
    assert config["sc_play_requested"] is True
    assert "Environment flags cannot enable it" in config["sc_play_blocked_reason"]
    monkeypatch.setenv("CRYPTO_FUNDING_ENABLED", "true")
    assert crypto.crypto_funding_enabled() is False


def test_self_exclusion_is_monotonic():
    later = "2030-01-02T00:00:00+00:00"
    earlier = "2030-01-01T00:00:00+00:00"
    assert sweepstakes.longest_self_exclusion("permanent", later) == "permanent"
    assert sweepstakes.longest_self_exclusion(later, earlier) == later
    assert sweepstakes.longest_self_exclusion(earlier, "permanent") == "permanent"


def test_legacy_human_sc_is_quarantined_without_touching_agent_balances(monkeypatch):
    database = _Database(
        users=[{"id": "human", "role": "human"}, {"id": "agent", "role": "agent"}],
        wallets=[
            {"user_id": "human", "sc_balance": 50},
            {"user_id": "agent", "sc_balance": 70},
        ],
    )
    monkeypatch.setattr(sweepstakes, "db", database)

    asyncio.run(sweepstakes.quarantine_legacy_human_sc())
    asyncio.run(sweepstakes.quarantine_legacy_human_sc())

    human_wallet, agent_wallet = database.wallets.documents
    assert human_wallet["sc_balance"] == 0
    assert human_wallet["legacy_sc_balance"] == 50
    assert human_wallet["sc_provenance_migrated"] is True
    assert agent_wallet["sc_balance"] == 70


def test_eligibility_requires_age_region_and_no_self_exclusion():
    assert sweepstakes.eligibility_from_profile(None)["eligible"] is False

    eligible = sweepstakes.eligibility_from_profile({
        "age_verified": True,
        "jurisdiction_allowed": True,
    })
    assert eligible["eligible"] is True

    excluded = sweepstakes.eligibility_from_profile({
        "age_verified": True,
        "jurisdiction_allowed": True,
        "self_excluded_until": (datetime.now(timezone.utc) + timedelta(days=30)).isoformat(),
    })
    assert excluded["eligible"] is False
    assert "self_excluded" in excluded["reasons"]


def test_sc_play_rejects_when_launch_switch_is_off(monkeypatch):
    monkeypatch.setenv("SWEEPSTAKES_PLAY_ENABLED", "false")
    with pytest.raises(HTTPException) as error:
        asyncio.run(sweepstakes.ensure_sc_play_eligible({"id": "human-1"}))
    assert error.value.status_code == 403


def test_sc_play_rejects_verified_profiles_until_release_gate_is_removed(monkeypatch):
    monkeypatch.setenv("SWEEPSTAKES_PLAY_ENABLED", "true")
    monkeypatch.setenv("DAILY_FREE_SC", "1")
    monkeypatch.setenv("SWEEPSTAKES_NO_PURCHASE_ENTRY_ENABLED", "true")

    verified_db = _Database(sweepstakes_profiles=[{
        "user_id": "human-1",
        "age_verified": True,
        "jurisdiction_allowed": True,
    }])
    monkeypatch.setattr(sweepstakes, "db", verified_db)
    with pytest.raises(HTTPException) as error:
        asyncio.run(sweepstakes.ensure_sc_play_eligible({"id": "human-1"}))
    assert error.value.status_code == 403


def test_wager_replay_is_idempotent_and_closed_events_reject_new_wagers(monkeypatch):
    database = _Database(
        games=[{"id": "game", "phase": "waiting", "players": [{"agent_id": "agent"}]}],
        wallets=[{"user_id": "human", "gc_balance": 100}],
        bets=[],
        transactions=[],
    )
    monkeypatch.setattr(wagering, "db", database)
    monkeypatch.setattr(wagering, "client", _Client())

    async def place(key):
        return await wagering.place_wager(
            collection_name="bets",
            event_collection_name="games",
            event_id="game",
            event_open_query={"phase": {"$nin": ["showdown", "complete"]}},
            validate_event=lambda game: None,
            user_id="human",
            agent_id="agent",
            amount=10,
            currency="gc",
            transaction_type="bet_placed",
            idempotency_key=key,
        )

    first = asyncio.run(place("retry-key"))
    replay = asyncio.run(place("retry-key"))
    assert replay["id"] == first["id"]
    assert database.wallets.documents[0]["gc_balance"] == 90
    assert len(database.bets.documents) == 1
    assert len(database.transactions.documents) == 1

    asyncio.run(wagering.close_event_betting("games", "game"))
    with pytest.raises(HTTPException) as error:
        asyncio.run(place("after-close"))
    assert error.value.status_code == 409


def test_untrusted_forwarded_headers_do_not_set_the_rate_limit_identity(monkeypatch):
    request = SimpleNamespace(
        headers={"X-Forwarded-For": "198.51.100.9"},
        client=SimpleNamespace(host="203.0.113.9"),
    )
    monkeypatch.delenv("TRUSTED_PROXY_IPS", raising=False)
    assert _client_ip(request) == "203.0.113.9"
    monkeypatch.setenv("TRUSTED_PROXY_IPS", "203.0.113.9")
    assert _client_ip(request) == "198.51.100.9"


def test_wager_endpoints_require_an_idempotency_key():
    user = {"id": "idempotency-required"}
    with pytest.raises(HTTPException) as game_error:
        asyncio.run(place_bet(BetRequest(game_id="game", agent_id="agent", amount=10), None, user))
    assert game_error.value.status_code == 400

    with pytest.raises(HTTPException) as tournament_error:
        asyncio.run(place_tournament_bet(
            TournamentBetRequest(tournament_id="tournament", agent_id="agent", amount=10),
            None,
            user,
        ))
    assert tournament_error.value.status_code == 400


def test_stripe_compatibility_routes_cannot_create_or_credit_payments():
    assert asyncio.run(get_stripe_packages()) == []
    with pytest.raises(HTTPException) as checkout_error:
        asyncio.run(disabled_stripe_checkout({"id": "human-1"}))
    assert checkout_error.value.status_code == 410

    with pytest.raises(HTTPException) as status_error:
        asyncio.run(disabled_stripe_status("cs_test", {"id": "human-1"}))
    assert status_error.value.status_code == 410


def test_settlement_is_currency_isolated_and_duplicate_safe(monkeypatch):
    database = _Database(
        bets=[
            {"id": "gc-win", "user_id": "human-1", "agent_id": "winner",
             "amount": 100, "currency": "gc", "status": "pending"},
            {"id": "gc-loss", "user_id": "human-2", "agent_id": "other",
             "amount": 100, "currency": "gc", "status": "pending"},
            {"id": "sc-win", "user_id": "human-1", "agent_id": "winner",
             "amount": 10, "currency": "sc", "status": "pending"},
            {"id": "sc-loss", "user_id": "human-3", "agent_id": "other",
             "amount": 90, "currency": "sc", "status": "pending"},
        ],
        wallets=[
            {"user_id": "human-1", "gc_balance": 0, "sc_balance": 0},
            {"user_id": "human-2", "gc_balance": 0, "sc_balance": 0},
            {"user_id": "human-3", "gc_balance": 0, "sc_balance": 0},
        ],
        transactions=[],
    )
    monkeypatch.setattr(bet_settlement, "db", database)

    async def settle_twice():
        await asyncio.gather(
            bet_settlement.settle_parimutuel_bets("bets", {"game_id": "game"}, "winner", "bet_won", "Won game"),
            bet_settlement.settle_parimutuel_bets("bets", {"game_id": "game"}, "winner", "bet_won", "Won game"),
        )

    for bet in database.bets.documents:
        bet["game_id"] = "game"
    asyncio.run(settle_twice())

    winner_wallet = database.wallets.documents[0]
    assert winner_wallet["gc_balance"] == 160
    assert winner_wallet["sc_balance"] == 80
    assert set(winner_wallet["settled_bet_ids"]) == {"gc-win", "sc-win"}
    assert {bet["id"]: bet["payout"] for bet in database.bets.documents} == {
        "gc-win": 160, "gc-loss": 0, "sc-win": 80, "sc-loss": 0,
    }
    assert {transaction["id"] for transaction in database.transactions.documents} == {
        "settlement:gc-win", "settlement:sc-win",
    }

    # Simulate a retry after the wallet update committed but before its ledger write.
    database.bets.documents.append({
        "id": "recovery", "user_id": "human-1", "game_id": "game",
        "agent_id": "winner", "amount": 50, "currency": "gc", "status": "settling",
    })
    winner_wallet["settled_bet_ids"].append("recovery")
    asyncio.run(bet_settlement.settle_parimutuel_bets(
        "bets", {"game_id": "game"}, "winner", "bet_won", "Won game",
    ))
    assert winner_wallet["gc_balance"] == 160
    assert any(
        transaction["id"] == "settlement:recovery"
        for transaction in database.transactions.documents
    )


def test_agent_game_result_is_idempotent_under_concurrent_completion(monkeypatch):
    database = _Database(
        agents=[
            {"id": "winner", "name": "Winner", "owner_id": "owner", "wins": 0,
             "losses": 0, "total_games": 0, "total_chips_won": 0},
            {"id": "loser", "name": "Loser", "owner_id": None, "wins": 0,
             "losses": 0, "total_games": 0, "total_chips_won": 0},
        ],
        wallets=[{"user_id": "owner", "sc_balance": 0}],
        transactions=[],
    )
    monkeypatch.setattr(bet_settlement, "db", database)
    monkeypatch.setattr(
        bet_settlement, "public_config", lambda: {"sc_play_enabled": True},
    )
    game = {
        "id": "completed-game",
        "winner_id": "winner",
        "final_pot": 200,
        "players": [{"agent_id": "winner"}, {"agent_id": "loser"}],
    }

    async def record_twice():
        await asyncio.gather(
            bet_settlement.record_agent_game_result(game),
            bet_settlement.record_agent_game_result(game),
        )

    asyncio.run(record_twice())

    winner, loser = database.agents.documents
    assert winner["wins"] == 1
    assert winner["total_games"] == 1
    assert winner["total_chips_won"] == 200
    assert loser["losses"] == 1
    assert loser["total_games"] == 1
    assert database.wallets.documents[0]["sc_balance"] == 20
    assert database.wallets.documents[0]["credited_game_ids"] == ["completed-game"]
    assert [item["id"] for item in database.transactions.documents] == [
        "game-win:completed-game"
    ]


def test_agent_game_result_does_not_credit_sc_while_sc_play_is_disabled(monkeypatch):
    database = _Database(
        agents=[
            {"id": "winner", "name": "Winner", "owner_id": "owner", "wins": 0,
             "losses": 0, "total_games": 0, "total_chips_won": 0},
            {"id": "loser", "name": "Loser", "owner_id": None, "wins": 0,
             "losses": 0, "total_games": 0, "total_chips_won": 0},
        ],
        wallets=[{"user_id": "owner", "sc_balance": 0}],
        transactions=[],
    )
    monkeypatch.setattr(bet_settlement, "db", database)
    monkeypatch.setattr(
        bet_settlement, "public_config", lambda: {"sc_play_enabled": False},
    )
    game = {
        "id": "gc-only-game",
        "winner_id": "winner",
        "final_pot": 200,
        "players": [{"agent_id": "winner"}, {"agent_id": "loser"}],
    }

    asyncio.run(bet_settlement.record_agent_game_result(game))

    assert database.agents.documents[0]["wins"] == 1
    assert database.agents.documents[1]["losses"] == 1
    assert database.wallets.documents[0]["sc_balance"] == 0
    assert "credited_game_ids" not in database.wallets.documents[0]
    assert database.transactions.documents == []


def test_settlement_retry_uses_the_immutable_event_pool(monkeypatch):
    database = _Database(
        bets=[
            {"id": "won-first", "user_id": "human-1", "game_id": "game",
             "agent_id": "winner", "amount": 100, "currency": "gc", "status": "won", "payout": 160},
            {"id": "lost", "user_id": "human-2", "game_id": "game",
             "agent_id": "other", "amount": 200, "currency": "gc", "status": "lost", "payout": 0},
            {"id": "retry", "user_id": "human-3", "game_id": "game",
             "agent_id": "winner", "amount": 100, "currency": "gc", "status": "settling", "payout": 160},
        ],
        wallets=[
            {"user_id": "human-1", "gc_balance": 160, "settled_bet_ids": ["won-first"]},
            {"user_id": "human-3", "gc_balance": 0},
        ],
        transactions=[],
    )
    monkeypatch.setattr(bet_settlement, "db", database)

    asyncio.run(bet_settlement.settle_parimutuel_bets(
        "bets", {"game_id": "game"}, "winner", "bet_won", "Won game",
    ))

    retry = next(bet for bet in database.bets.documents if bet["id"] == "retry")
    retry_wallet = next(
        wallet for wallet in database.wallets.documents if wallet["user_id"] == "human-3"
    )
    assert retry["status"] == "won"
    assert retry["payout"] == 160
    assert retry_wallet["gc_balance"] == 160


def test_settlement_uses_every_bet_beyond_one_thousand(monkeypatch):
    bets = [
        {"id": f"loss-{number}", "user_id": f"loss-user-{number}", "game_id": "game",
         "agent_id": "other", "amount": 1, "currency": "gc", "status": "pending"}
        for number in range(1001)
    ]
    bets.append({
        "id": "winner", "user_id": "winner-user", "game_id": "game",
        "agent_id": "winner", "amount": 1, "currency": "gc", "status": "pending",
    })
    database = _Database(
        bets=bets,
        wallets=[{"user_id": "winner-user", "gc_balance": 0}],
        transactions=[],
    )
    monkeypatch.setattr(bet_settlement, "db", database)

    asyncio.run(bet_settlement.settle_parimutuel_bets(
        "bets", {"game_id": "game"}, "winner", "bet_won", "Won game",
    ))

    assert database.wallets.documents[0]["gc_balance"] == int(1002 * 0.8)


def test_settlement_keeps_a_recoverable_state_when_the_wallet_is_missing(monkeypatch):
    database = _Database(
        bets=[{
            "id": "missing-wallet", "user_id": "missing", "game_id": "game",
            "agent_id": "winner", "amount": 100, "currency": "gc", "status": "pending",
        }],
        wallets=[],
        transactions=[],
    )
    monkeypatch.setattr(bet_settlement, "db", database)

    with pytest.raises(RuntimeError, match="wallet credit failed"):
        asyncio.run(bet_settlement.settle_parimutuel_bets(
            "bets", {"game_id": "game"}, "winner", "bet_won", "Won game",
        ))

    assert database.bets.documents[0]["status"] == "settling"
    assert database.transactions.documents == []


def test_agent_auto_advance_settles_spectator_bets(monkeypatch):
    database = _Database(
        games=[{
            "id": "game", "phase": "waiting", "current_actor": None,
            "players": [{"agent_id": "external"}, {"agent_id": "winner"}],
            "table_id": None,
        }],
        agents=[
            {"id": "external", "is_external": True},
            {"id": "winner", "is_external": False},
        ],
        wallets=[],
        tables=[],
    )
    settlements = []

    async def record_settlement(*args):
        settlements.append(args)

    monkeypatch.setattr(agent_api, "db", database)
    monkeypatch.setattr(bet_settlement, "db", database)
    monkeypatch.setattr(game_persistence, "db", database)
    monkeypatch.setattr(game_persistence, "close_event_betting", _no_op_close_event_betting)
    monkeypatch.setattr(
        agent_api,
        "advance_game",
        lambda game: {**game, "phase": "complete", "winner_id": "winner", "final_pot": 100},
    )
    monkeypatch.setattr(game_persistence, "settle_parimutuel_bets", record_settlement)
    monkeypatch.setitem(sys.modules, "server", SimpleNamespace(table_manager=None))

    asyncio.run(agent_api.advance_other_agents(
        "game", {"id": "owner", "agent_id": "external"},
    ))

    assert settlements == [("bets", {"game_id": "game"}, "winner", "bet_won", "Won bet on game")]


def test_game_transition_preserves_wagers_and_rejects_stale_turns(monkeypatch):
    database = _Database(games=[{
        "id": "game", "phase": "preflop_betting", "game_revision": 3,
        "bet_sequence": 8, "betting_closed": False, "players": [],
    }])
    monkeypatch.setattr(game_persistence, "db", database)
    stale_snapshot = {
        "id": "game", "phase": "flop_betting", "game_revision": 3,
        "bet_sequence": 6, "betting_closed": False, "players": [],
    }

    asyncio.run(game_persistence.persist_game_transition(stale_snapshot, 3))
    stored = database.games.documents[0]
    assert stored["phase"] == "flop_betting"
    assert stored["game_revision"] == 4
    assert stored["bet_sequence"] == 8
    assert stored["betting_closed"] is False

    with pytest.raises(HTTPException) as exc:
        asyncio.run(game_persistence.persist_game_transition(
            {**stale_snapshot, "phase": "river_betting"}, 3,
        ))
    assert exc.value.status_code == 409
    assert stored["phase"] == "flop_betting"


def test_table_start_claims_only_one_current_game(monkeypatch):
    table = {"id": "table", "current_game_id": "old", "agent_ids": ["a", "b"]}
    database = _Database(
        games=[{"id": "new-one"}, {"id": "new-two"}],
        tables=[table],
    )
    monkeypatch.setattr(game_persistence, "db", database)
    asyncio.run(game_persistence.attach_new_game_to_table(table, "new-one"))
    assert database.tables.documents[0]["current_game_id"] == "new-one"

    with pytest.raises(HTTPException) as exc:
        asyncio.run(game_persistence.attach_new_game_to_table(table, "new-two"))
    assert exc.value.status_code == 409
    assert database.tables.documents[0]["current_game_id"] == "new-one"
    assert [game["id"] for game in database.games.documents] == ["new-one"]


def test_only_human_websocket_sessions_can_publish_spectator_chat(monkeypatch):
    import server

    database = _Database(table_chat_messages=[])
    monkeypatch.setattr(server, "db", database)
    monkeypatch.setattr(server, "table_manager", server.TableManager())

    async def authenticate(token):
        return {"role": token, "username": "Logged In"}

    monkeypatch.setattr(server, "get_user_from_token", authenticate)

    class Socket:
        def __init__(self, role):
            self.messages = iter([
                '{"type":"auth","token":"' + role + '"}',
                '{"type":"chat","text":"hello"}',
                '{"type":"reaction","emoji":"clap"}',
            ])
            self.sent = []

        async def accept(self):
            pass

        async def receive_text(self):
            try:
                return next(self.messages)
            except StopIteration:
                raise WebSocketDisconnect(code=1000)

        async def send_json(self, payload):
            self.sent.append(payload)

    agent_socket = Socket("agent")
    asyncio.run(server.websocket_table(agent_socket, "table"))
    assert database.table_chat_messages.documents == []
    assert not any(item.get("type") in {"chat", "reaction"} for item in agent_socket.sent)

    human_socket = Socket("human")
    asyncio.run(server.websocket_table(human_socket, "table"))
    assert len(database.table_chat_messages.documents) == 1
    assert database.table_chat_messages.documents[0]["sender_type"] == "human"
    assert any(item.get("type") == "reaction" for item in human_socket.sent)


def test_terminal_transition_atomically_closes_betting(monkeypatch):
    database = _Database(games=[{"id": "game", "phase": "river_betting", "bet_sequence": 3}])
    monkeypatch.setattr(game_persistence, "db", database)
    completed = {"id": "game", "phase": "complete", "winner_id": "winner"}
    asyncio.run(game_persistence.persist_game_transition(completed, None))
    stored = database.games.documents[0]
    assert stored["betting_closed"] is True
    assert stored["bet_sequence"] == 3
    assert stored["game_revision"] == 1

    with pytest.raises(HTTPException) as exc:
        asyncio.run(game_persistence.persist_game_transition(
            {"id": "game", "phase": "river_betting"}, 1,
        ))
    assert exc.value.status_code == 409
    assert stored["phase"] == "complete"


def test_advancing_other_agents_does_not_write_when_waiting_on_external_agent(monkeypatch):
    database = _Database(
        agents=[{"id": "mine"}, {"id": "another-external", "is_external": True}],
        games=[{
            "id": "game", "phase": "preflop_betting", "game_revision": 7,
            "current_actor": "another-external", "players": [
                {"agent_id": "mine", "hole_cards": []},
                {"agent_id": "another-external", "hole_cards": []},
            ],
        }],
    )
    monkeypatch.setattr(agent_api, "db", database)
    async def unexpected_write(*_args, **_kwargs):
        pytest.fail("A waiting turn must not persist a new game revision")

    monkeypatch.setattr(agent_api, "persist_game_transition", unexpected_write)
    result = asyncio.run(agent_api.advance_other_agents("game", {"agent_id": "mine"}))
    assert result["advances"] == 0
    assert result["waiting_for_agent_id"] == "another-external"
    assert database.games.documents[0]["game_revision"] == 7


def test_tournament_transition_preserves_bet_barrier_and_checks_revision(monkeypatch):
    database = _Database(tournaments=[{
        "id": "tournament", "status": "final", "bet_sequence": 7,
        "betting_closed": True, "tournament_revision": 2,
        "bracket": {"winner": None},
    }])
    monkeypatch.setattr(tournament_routes, "db", database)
    new_state = {
        "id": "tournament", "status": "complete", "bet_sequence": 4,
        "betting_closed": False, "tournament_revision": 2,
        "bracket": {"winner": "winner"},
    }
    asyncio.run(tournament_routes._persist_tournament_transition(new_state, "final", 2))
    stored = database.tournaments.documents[0]
    assert stored["status"] == "complete"
    assert stored["bracket"]["winner"] == "winner"
    assert stored["bet_sequence"] == 7
    assert stored["betting_closed"] is True
    assert stored["betting_closed_at"]
    assert new_state["betting_closed"] is True
    assert stored["tournament_revision"] == 3
    with pytest.raises(HTTPException) as exc:
        asyncio.run(tournament_routes._persist_tournament_transition(
            {**new_state, "status": "final"}, "final", 2,
        ))
    assert exc.value.status_code == 409
    assert stored["status"] == "complete"


def test_completed_game_replay_credits_winner_and_stats_once(monkeypatch):
    game = {
        "id": "game", "phase": "complete", "winner_id": "winner",
        "players": [{"agent_id": "winner"}, {"agent_id": "loser"}],
        "final_pot": 100, "table_id": "table",
    }
    database = _Database(
        games=[{**game, "betting_closed": True}],
        bets=[
            {"id": "winning-bet", "user_id": "viewer", "game_id": "game",
             "agent_id": "winner", "amount": 100, "currency": "gc", "status": "pending"},
            {"id": "losing-bet", "user_id": "other", "game_id": "game",
             "agent_id": "loser", "amount": 100, "currency": "gc", "status": "pending"},
        ],
        agents=[{"id": "winner"}, {"id": "loser"}],
        wallets=[{"user_id": "viewer", "gc_balance": 0}],
        transactions=[],
        tables=[{"id": "table", "current_game_id": "game", "status": "playing"}],
    )
    monkeypatch.setattr(game_persistence, "db", database)
    monkeypatch.setattr(bet_settlement, "db", database)
    monkeypatch.setattr(wagering, "db", database)

    asyncio.run(game_persistence.finalize_completed_game(game))
    asyncio.run(game_persistence.finalize_completed_game(game))

    assert database.wallets.documents[0]["gc_balance"] == 160
    assert len(database.transactions.documents) == 1
    assert database.bets.documents[0]["status"] == "won"
    assert database.bets.documents[1]["status"] == "lost"
    assert database.agents.documents[0]["wins"] == 1
    assert database.agents.documents[0]["total_games"] == 1
    assert database.agents.documents[1]["losses"] == 1
    assert database.tables.documents[0]["status"] == "waiting"


def test_completed_game_recovers_after_ledger_write_failure(monkeypatch):
    database = _Database(
        games=[{"id": "game", "phase": "complete", "betting_closed": True}],
        bets=[{"id": "winning-bet", "user_id": "viewer", "game_id": "game",
               "agent_id": "winner", "amount": 20, "currency": "gc", "status": "pending"}],
        wallets=[{"user_id": "viewer", "gc_balance": 0}],
        transactions=[],
    )
    monkeypatch.setattr(game_persistence, "db", database)
    monkeypatch.setattr(bet_settlement, "db", database)
    monkeypatch.setattr(wagering, "db", database)
    original_update = database.transactions.update_one
    failures = 0

    async def fail_once(*args, **kwargs):
        nonlocal failures
        if failures == 0:
            failures += 1
            raise RuntimeError("simulated ledger outage")
        return await original_update(*args, **kwargs)

    monkeypatch.setattr(database.transactions, "update_one", fail_once)
    game = {"id": "game", "phase": "complete", "winner_id": "winner", "players": []}
    with pytest.raises(RuntimeError, match="simulated ledger outage"):
        asyncio.run(game_persistence.finalize_completed_game(game))
    assert database.wallets.documents[0]["gc_balance"] == 16
    assert database.bets.documents[0]["status"] == "settling"

    asyncio.run(game_persistence.finalize_completed_game(game))
    asyncio.run(game_persistence.finalize_completed_game(game))
    assert database.wallets.documents[0]["gc_balance"] == 16
    assert database.bets.documents[0]["status"] == "won"
    assert len(database.transactions.documents) == 1


def test_database_indexes_cover_idempotent_wallet_and_ledger_keys(monkeypatch):
    database = _Database(
        # Core idempotency collections (assertions below target these)
        wallets=[], bets=[], tournament_bets=[], transactions=[], sweepstakes_profiles=[],
        # Additional collections indexed by ensure_database_indexes for lookup performance
        users=[], agents=[], games=[], table_pilot_workspaces=[],
        crypto_deposits=[], crypto_redemptions=[], table_chat_messages=[],
    )
    monkeypatch.setattr(deps, "db", database)

    asyncio.run(deps.ensure_database_indexes())

    # Verify the idempotency-critical collections have the right indexes
    assert ("id", True, "wallet_id_unique", {}) in database.wallets.indexes
    assert ("user_id", True, "wallet_user_id_unique", {}) in database.wallets.indexes
    assert database.bets.indexes == [("id", True, "bet_id_unique", {})]
    assert database.tournament_bets.indexes == [("id", True, "tournament_bet_id_unique", {})]
    assert database.transactions.indexes == [("id", True, "transaction_id_unique", {})]
    assert database.sweepstakes_profiles.indexes == [
        ("user_id", True, "sweepstakes_profile_user_id_unique", {})
    ]
    assert database.table_pilot_workspaces.indexes == [
        ("user_id", True, "table_pilot_user_unique", {})
    ]
    assert ("id", True, "crypto_deposit_id_unique", {}) in database.crypto_deposits.indexes
    assert ([('crypto_type', 1), ('tx_hash', 1)], True, "crypto_transaction_claim_unique", {}) in database.crypto_deposits.indexes
    assert ("id", True, "crypto_redemption_id_unique", {}) in database.crypto_redemptions.indexes
    assert ([('user_id', 1), ('idempotency_key', 1)], True, "crypto_redemption_user_idempotency_unique", {}) in database.crypto_redemptions.indexes
    assert ("payout_tx_hash", True, "crypto_redemption_payout_tx_hash_unique", {"sparse": True}) in database.crypto_redemptions.indexes
    assert ("id", True, "table_chat_message_id_unique", {}) in database.table_chat_messages.indexes
    assert ("action_id", True, "table_chat_action_id_unique", {"sparse": True}) in database.table_chat_messages.indexes


def test_redemption_quote_and_native_address_validation():
    usd_value, btc_amount = wallet.redemption_quote(
        2500, wallet.Decimal("100"), wallet.Decimal("50000"), "btc",
    )
    assert usd_value == wallet.Decimal("25")
    assert btc_amount == wallet.Decimal("0.00050000")
    assert wallet.validate_payout_address(
        "eth", "0x1111111111111111111111111111111111111111"
    ) == "0x1111111111111111111111111111111111111111"
    with pytest.raises(HTTPException):
        wallet.validate_payout_address("btc", "0x1111111111111111111111111111111111111111")


def test_redemption_requires_identity_verification(monkeypatch):
    monkeypatch.setenv("SWEEPSTAKES_PLAY_ENABLED", "true")
    monkeypatch.setenv("SWEEPSTAKES_NO_PURCHASE_ENTRY_ENABLED", "true")
    monkeypatch.setenv("SWEEPSTAKES_REDEMPTION_ENABLED", "true")
    monkeypatch.setenv("CRYPTO_PAYOUTS_ENABLED", "true")
    # Exercise dormant eligibility checks while the public SC gate stays off.
    monkeypatch.setattr(sweepstakes, "public_config", lambda: {
        "sc_play_enabled": True, "redemption_enabled": True,
    })
    database = _Database(sweepstakes_profiles=[{
        "user_id": "human",
        "age_verified": True,
        "jurisdiction_allowed": True,
        "identity_verified": False,
    }])
    monkeypatch.setattr(sweepstakes, "db", database)
    with pytest.raises(HTTPException) as error:
        asyncio.run(sweepstakes.ensure_redemption_eligible({"id": "human", "role": "human"}))
    assert error.value.status_code == 403
    database.sweepstakes_profiles.documents[0]["identity_verified"] = True
    asyncio.run(sweepstakes.ensure_redemption_eligible({"id": "human", "role": "human"}))


def test_redemption_reserves_sc_once_for_idempotent_replay(monkeypatch):
    monkeypatch.setenv("CRYPTO_REDEMPTION_MIN_SC", "2500")
    monkeypatch.setenv("SC_PER_USD", "100")
    database = _Database(
        wallets=[{"user_id": "human", "sc_balance": 5000}],
        crypto_redemptions=[],
        transactions=[],
    )

    async def eligible(_user):
        return None

    async def prices():
        return {"btc": {"usd": 50000, "change_24h": 0}}

    monkeypatch.setattr(wallet, "db", database)
    monkeypatch.setattr(wallet, "client", _Client())
    monkeypatch.setattr(wallet, "ensure_redemption_eligible", eligible)
    monkeypatch.setattr(wallet, "get_crypto_prices", prices)
    request = wallet.CashoutRequest(
        amount=2500,
        crypto_type="btc",
        payout_address="bc1q234567890123456789012345678901234567890",
    )
    user = {"id": "human", "role": "human"}
    first = asyncio.run(wallet.cashout(request, "same-key", user))
    replay = asyncio.run(wallet.cashout(request, "same-key", user))

    assert replay["id"] == first["id"]
    assert database.wallets.documents[0]["sc_balance"] == 2500
    assert len(database.crypto_redemptions.documents) == 1
    assert len(database.transactions.documents) == 1


def test_crypto_amount_extraction_counts_only_the_assigned_address():
    btc = {
        "vout": [
            {"scriptpubkey_address": "mine", "value": 125_000},
            {"scriptpubkey_address": "change", "value": 900_000},
        ]
    }
    ltc = {
        "outputs": [
            {"addresses": ["mine"], "value": 250_000},
            {"addresses": ["change"], "value": 800_000},
        ]
    }
    eth = {"recipient": "0xAbC", "value": "3000000000000000000"}
    assert crypto._matching_output_amount("btc", btc, "mine") == crypto.Decimal("0.00125")
    assert crypto._matching_output_amount("ltc", ltc, "mine") == crypto.Decimal("0.0025")
    assert crypto._matching_output_amount("eth", eth, "0xabc") == crypto.Decimal("3")
    assert crypto._matching_output_amount("eth", eth, "0xdef") == 0


def test_crypto_wallet_change_is_not_treated_as_a_new_deposit():
    assert crypto._is_self_spend("btc", {
        "vin": [{"prevout": {"scriptpubkey_address": "mine"}}],
    }, "mine") is True
    assert crypto._is_self_spend("ltc", {
        "inputs": [{"addresses": ["mine"]}],
    }, "mine") is True
    assert crypto._is_self_spend("eth", {
        "sender": "0xAbC", "recipient": "0xabc",
    }, "0xabc") is True


def test_crypto_credit_is_atomic_and_idempotent_under_concurrent_confirmation(monkeypatch):
    deposit = {
        "id": "deposit-1",
        "user_id": "human-1",
        "crypto_type": "btc",
        "tx_hash": "a" * 64,
        "deposit_address": "unique-user-address",
        "amount_crypto": "0.001",
        "sc_amount": 100,
        "confirmations": 0,
        "required_confirmations": 2,
        "status": "pending",
    }
    database = _Database(
        wallets=[{
            "user_id": "human-1", "sc_balance": 0,
            "crypto_addresses": {"btc": "unique-user-address"},
        }],
        crypto_deposits=[deposit],
        transactions=[],
    )
    monkeypatch.setattr(crypto, "db", database)
    monkeypatch.setattr(crypto, "client", _Client())

    async def verified(*_args):
        await asyncio.sleep(0)
        return {"verified": True, "confirmations": 3, "amount": "0.001", "error": None}

    monkeypatch.setattr(crypto, "verify_tx_on_blockchain", verified)

    async def confirm_twice():
        return await asyncio.gather(
            crypto._refresh_and_credit(deposit),
            crypto._refresh_and_credit(deposit),
        )

    results = asyncio.run(confirm_twice())
    assert database.wallets.documents[0]["sc_balance"] == 100
    assert len(database.transactions.documents) == 1
    assert database.transactions.documents[0]["id"] == "crypto:deposit-1"
    assert sum(result["sc_credited"] for result in results) == 100


def test_daily_claim_is_atomic_and_sc_stays_withheld_when_ineligible(monkeypatch):
    database = _Database(
        wallets=[{"user_id": "human-1", "gc_balance": 0, "sc_balance": 0}],
        transactions=[],
        sweepstakes_profiles=[],
    )
    monkeypatch.setattr(sweepstakes_routes, "db", database)
    monkeypatch.setattr(sweepstakes_routes, "public_config", lambda: {
        "daily_gc_amount": 1000,
        "daily_sc_amount": 1,
        "sc_play_enabled": False,
    })

    async def ineligible(_user_id):
        return {"eligible": False, "reasons": ["age_verification_required"]}

    monkeypatch.setattr(sweepstakes_routes, "get_eligibility", ineligible)
    claim = asyncio.run(sweepstakes_routes.claim_daily_coins({"id": "human-1"}))

    assert claim["gc_credited"] == 1000
    assert claim["sc_credited"] == 0
    assert database.wallets.documents[0]["gc_balance"] == 1000
    assert database.wallets.documents[0]["sc_balance"] == 0
    assert database.wallets.documents[0]["daily_claim_award"]["gc_amount"] == 1000
    database.transactions.documents.clear()
    with pytest.raises(HTTPException) as duplicate_error:
        asyncio.run(sweepstakes_routes.claim_daily_coins({"id": "human-1"}))
    assert duplicate_error.value.status_code == 409
    assert database.transactions.documents[0]["id"].endswith(":gc")
