import asyncio
import os

import pytest
from fastapi import HTTPException
from pydantic import ValidationError


os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "pokerclaw_test")
os.environ.setdefault("JWT_SECRET", "unit-test-secret-that-is-not-used-in-production")

from deps import require_agent, require_human  # noqa: E402
from routes.agent_api import router as agent_router  # noqa: E402
from routes.auth import router as auth_router  # noqa: E402
from routes.bets import BetRequest, router as bets_router  # noqa: E402
from routes.crypto import CryptoDepositRequest, submit_crypto_deposit  # noqa: E402
from routes.tournaments import TournamentBetRequest, router as tournaments_router  # noqa: E402
from routes.wallet import PurchaseRequest, purchase_coins  # noqa: E402


def _dependency_calls(route):
    return {dependency.call for dependency in route.dependant.dependencies}


def test_human_and_agent_guards_are_mutually_exclusive():
    human = {"id": "human-1", "role": "human"}
    agent = {"id": "agent-owner-1", "role": "agent", "agent_id": "agent-1"}

    assert asyncio.run(require_human(human)) == human
    assert asyncio.run(require_agent(agent)) == agent

    with pytest.raises(HTTPException) as human_error:
        asyncio.run(require_human(agent))
    assert human_error.value.status_code == 403

    with pytest.raises(HTTPException) as agent_error:
        asyncio.run(require_agent(human))
    assert agent_error.value.status_code == 403


def test_human_and_agent_auth_have_separate_routes():
    human_paths = {route.path for route in auth_router.routes}
    agent_paths = {route.path for route in agent_router.routes}

    assert "/api/human-auth/signup" in human_paths
    assert "/api/human-auth/login" in human_paths
    assert "/api/agent-api/register" in agent_paths
    assert "/api/agent-api/login" in agent_paths


def test_every_authenticated_agent_api_route_requires_agent_role():
    public_paths = {"/api/agent-api/register", "/api/agent-api/login"}

    for route in agent_router.routes:
        if route.path not in public_paths:
            assert require_agent in _dependency_calls(route), route.path


def test_side_bets_reject_non_positive_amounts_and_unknown_currencies():
    for model in (BetRequest, TournamentBetRequest):
        with pytest.raises(ValidationError):
            model(game_id="game-1", agent_id="agent-1", amount=0, currency="gc") \
                if model is BetRequest \
                else model(tournament_id="tournament-1", agent_id="agent-1", amount=0, currency="gc")

        with pytest.raises(ValidationError):
            model(game_id="game-1", agent_id="agent-1", amount=10, currency="usd") \
                if model is BetRequest \
                else model(tournament_id="tournament-1", agent_id="agent-1", amount=10, currency="usd")


def test_bet_writes_are_human_only():
    protected_paths = {"/api/bets", "/api/bets/my-bets", "/api/tournament-bets"}
    routes = [*bets_router.routes, *tournaments_router.routes]

    for route in routes:
        if route.path in protected_paths:
            assert require_human in _dependency_calls(route), route.path


def test_unverified_balance_credit_endpoints_are_fail_closed():
    with pytest.raises(HTTPException) as purchase_error:
        asyncio.run(purchase_coins(PurchaseRequest(amount=100, currency="sc"), {"id": "human-1"}))
    assert purchase_error.value.status_code == 410

    deposit = CryptoDepositRequest(crypto_type="btc", tx_hash="f" * 64, amount_crypto=1)
    with pytest.raises(HTTPException) as deposit_error:
        asyncio.run(submit_crypto_deposit(deposit, {"id": "agent-owner-1", "role": "agent"}))
    assert deposit_error.value.status_code == 503
