import asyncio
import os
import sys
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
import pytest
from fastapi import HTTPException


os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "pokerclaw_test")
os.environ.setdefault("JWT_SECRET", "unit-test-secret-that-is-not-used-in-production")

import sweepstakes  # noqa: E402
import bet_settlement  # noqa: E402
import deps  # noqa: E402
from routes import agent_api  # noqa: E402
from routes import sweepstakes as sweepstakes_routes  # noqa: E402
from routes.bets import BetRequest  # noqa: E402
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
            if "$in" in expected and actual not in expected["$in"]:
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


class _Collection:
    def __init__(self, documents=()):
        self.documents = [document.copy() for document in documents]
        self.indexes = []

    def find(self, query, _projection=None):
        return _Cursor([document for document in self.documents if _matches(document, query)])

    async def find_one(self, query, _projection=None):
        document = next((item for item in self.documents if _matches(item, query)), None)
        return document.copy() if document else None

    async def update_one(self, query, update, upsert=False):
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

    async def replace_one(self, query, document):
        existing = next((item for item in self.documents if _matches(item, query)), None)
        if existing is None:
            return _UpdateResult(0)
        self.documents[self.documents.index(existing)] = document.copy()
        return _UpdateResult(1)

    async def create_index(self, field, unique, name):
        self.indexes.append((field, unique, name))


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
    ):
        monkeypatch.delenv(name, raising=False)

    config = sweepstakes.public_config()
    assert config["model"] == "purchased_gc_with_promotional_sc"
    assert config["no_purchase_necessary"] is True
    assert config["gc_redeemable"] is False
    assert config["sc_play_enabled"] is False
    assert config["funding_enabled"] is False
    assert config["redemption_enabled"] is False
    assert BetRequest(game_id="game", agent_id="agent", amount=10).currency == "gc"


def test_sc_launch_requires_a_valid_free_entry_path(monkeypatch):
    monkeypatch.setenv("SWEEPSTAKES_PLAY_ENABLED", "true")
    monkeypatch.setenv("DAILY_FREE_SC", "not-a-number")
    assert sweepstakes.public_config()["sc_play_enabled"] is False
    monkeypatch.setenv("DAILY_FREE_SC", "0")
    assert sweepstakes.public_config()["sc_play_enabled"] is False
    monkeypatch.setenv("DAILY_FREE_SC", "1")
    monkeypatch.setenv("SWEEPSTAKES_NO_PURCHASE_ENTRY_ENABLED", "false")
    assert sweepstakes.public_config()["sc_play_enabled"] is False


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


def test_sc_play_checks_verified_profile(monkeypatch):
    # With SWEEPSTAKES_PLAY_ENABLED=true and a valid free-entry path, a fully
    # verified user should be able to pass ensure_sc_play_eligible.
    # An unverified user must still be rejected.
    monkeypatch.setenv("SWEEPSTAKES_PLAY_ENABLED", "true")
    monkeypatch.setenv("DAILY_FREE_SC", "1")
    monkeypatch.setenv("SWEEPSTAKES_NO_PURCHASE_ENTRY_ENABLED", "true")

    verified_db = _Database(sweepstakes_profiles=[{
        "user_id": "human-1",
        "age_verified": True,
        "jurisdiction_allowed": True,
    }])
    monkeypatch.setattr(sweepstakes, "db", verified_db)
    # A fully verified user must NOT raise when sc_play_enabled=True
    asyncio.run(sweepstakes.ensure_sc_play_eligible({"id": "human-1"}))

    # An unverified user (no profile) must still get 403
    empty_db = _Database(sweepstakes_profiles=[])
    monkeypatch.setattr(sweepstakes, "db", empty_db)
    with pytest.raises(HTTPException) as error:
        asyncio.run(sweepstakes.ensure_sc_play_eligible({"id": "human-1"}))
    assert error.value.status_code == 403


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
    monkeypatch.setattr(
        agent_api,
        "advance_game",
        lambda game: {**game, "phase": "complete", "winner_id": "winner", "final_pot": 100},
    )
    monkeypatch.setattr(agent_api, "settle_parimutuel_bets", record_settlement)
    monkeypatch.setitem(sys.modules, "server", SimpleNamespace(table_manager=None))

    asyncio.run(agent_api.advance_other_agents(
        "game", {"id": "owner", "agent_id": "external"},
    ))

    assert settlements == [("bets", {"game_id": "game"}, "winner", "bet_won", "Won bet on game")]


def test_database_indexes_cover_idempotent_wallet_and_ledger_keys(monkeypatch):
    database = _Database(
        # Core idempotency collections (assertions below target these)
        wallets=[], bets=[], tournament_bets=[], transactions=[], sweepstakes_profiles=[],
        # Additional collections indexed by ensure_database_indexes for lookup performance
        users=[], agents=[], games=[],
    )
    monkeypatch.setattr(deps, "db", database)

    asyncio.run(deps.ensure_database_indexes())

    # Verify the idempotency-critical collections have the right indexes
    assert ("id", True, "wallet_id_unique") in database.wallets.indexes
    assert ("user_id", True, "wallet_user_id_unique") in database.wallets.indexes
    assert database.bets.indexes == [("id", True, "bet_id_unique")]
    assert database.tournament_bets.indexes == [("id", True, "tournament_bet_id_unique")]
    assert database.transactions.indexes == [("id", True, "transaction_id_unique")]
    assert database.sweepstakes_profiles.indexes == [
        ("user_id", True, "sweepstakes_profile_user_id_unique")
    ]


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
