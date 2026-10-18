"""Production-path smoke test for the fail-closed GC-only release."""
import os
import uuid
from concurrent.futures import ThreadPoolExecutor

import pytest
import requests


BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
TEST_CORS_ORIGIN = os.environ.get("POKERCLAW_TEST_CORS_ORIGIN", "http://localhost:3000")


def _expect(response, status):
    assert response.status_code == status, response.text
    return response


@pytest.mark.skipif(not BASE_URL, reason="requires a running PokerClaw backend")
def test_release_flow_against_transactional_mongodb():
    base = f"{BASE_URL}/api"
    suffix = uuid.uuid4().hex[:10]
    password = "ReleaseTest!234"
    human_email = f"release-human-{suffix}@example.test"
    agent_email = f"release-agent-{suffix}@example.test"

    config = _expect(requests.get(f"{base}/sweepstakes/config"), 200).json()
    assert config["sc_play_enabled"] is False
    assert config["funding_enabled"] is False
    assert config["redemption_enabled"] is False

    human = _expect(requests.post(f"{base}/human-auth/signup", json={
        "username": f"ReleaseHuman{suffix}",
        "email": human_email,
        "password": password,
    }), 200).json()
    human_headers = {"Authorization": f"Bearer {human['token']}"}
    assert human["user"]["role"] == "human"
    assert human["user"]["agent_id"] is None

    prices = _expect(requests.get(f"{base}/crypto/prices", headers=human_headers), 200).json()
    assert prices["funding_enabled"] is False
    assert prices["rate"] is None

    agent = _expect(requests.post(f"{base}/agent-api/register", json={
        "username": f"ReleaseAgent{suffix}",
        "email": agent_email,
        "password": password,
        "agent_name": f"ReleaseBot{suffix}",
    }), 200).json()
    agent_headers = {"Authorization": f"Bearer {agent['token']}"}
    assert agent["user"]["role"] == "agent"
    assert agent["agent"]["is_external"] is True

    _expect(requests.post(f"{base}/human-auth/login", json={
        "email": agent_email, "password": password,
    }), 403)
    _expect(requests.post(f"{base}/agent-api/login", json={
        "email": human_email, "password": password,
    }), 403)
    _expect(requests.get(f"{base}/agent-api/tables", headers=human_headers), 403)
    _expect(requests.get(f"{base}/bets/my-bets", headers=agent_headers), 403)

    wallet = _expect(requests.get(f"{base}/wallet", headers=human_headers), 200).json()
    assert wallet["gc_balance"] == 5000
    assert wallet["sc_balance"] == 0

    claim = _expect(
        requests.post(f"{base}/sweepstakes/daily-claim", headers=human_headers), 200,
    ).json()
    assert claim["gc_credited"] == 1000
    assert claim["sc_credited"] == 0
    _expect(requests.post(f"{base}/sweepstakes/daily-claim", headers=human_headers), 409)

    _expect(requests.post(
        f"{base}/wallet/purchase", headers=human_headers,
        json={"amount": 100, "currency": "gc"},
    ), 410)
    _expect(requests.post(
        f"{base}/wallet/cashout", headers=human_headers, json={"amount": 100},
    ), 410)
    _expect(requests.post(
        f"{base}/crypto/deposit", headers=human_headers,
        json={"crypto_type": "btc", "tx_hash": "f" * 64, "amount_crypto": 0.01},
    ), 503)
    _expect(requests.post(f"{base}/stripe/checkout", headers=human_headers), 410)

    tables = _expect(
        requests.get(f"{base}/agent-api/tables", headers=agent_headers), 200,
    ).json()
    table_id = tables[0]["id"]
    _expect(requests.post(
        f"{base}/agent-api/tables/{table_id}/join", headers=agent_headers,
    ), 200)
    started = _expect(requests.post(
        f"{base}/agent-api/game/{table_id}/start", headers=agent_headers,
    ), 200).json()
    game_id = started["game_id"]
    game = started["game"]
    assert all(
        player["agent_id"] == agent["agent"]["id"]
        or player["hole_cards"] == [None, None]
        for player in game["players"]
    )

    target_agent = next(
        player["agent_id"] for player in game["players"]
        if player["agent_id"] != agent["agent"]["id"]
    )
    bet = {
        "game_id": game_id,
        "agent_id": target_agent,
        "amount": 100,
        "currency": "gc",
    }
    bet_headers = {
        **human_headers,
        "Idempotency-Key": f"release-bet-{suffix}",
    }
    def place_same_wager():
        return requests.post(f"{base}/bets", headers=bet_headers, json=bet)

    with ThreadPoolExecutor(max_workers=8) as pool:
        concurrent_wagers = list(pool.map(lambda _: place_same_wager(), range(8)))

    assert {response.status_code for response in concurrent_wagers} == {200}, [
        (response.status_code, response.text) for response in concurrent_wagers
    ]
    wager_ids = {response.json()["id"] for response in concurrent_wagers}
    assert len(wager_ids) == 1
    first = concurrent_wagers[0].json()

    replay = _expect(place_same_wager(), 200).json()
    assert replay["id"] == first["id"]
    _expect(requests.post(
        f"{base}/bets", headers=bet_headers, json={**bet, "amount": 101},
    ), 409)
    _expect(requests.post(
        f"{base}/bets",
        headers={**human_headers, "Idempotency-Key": f"sc-{suffix}"},
        json={**bet, "currency": "sc"},
    ), 403)
    wallet = _expect(requests.get(f"{base}/wallet", headers=human_headers), 200).json()
    assert wallet["gc_balance"] == 5900

    for _ in range(120):
        state = _expect(requests.get(
            f"{base}/agent-api/game/{game_id}/state", headers=agent_headers,
        ), 200).json()
        if state["phase"] == "complete":
            break
        if state.get("is_your_turn"):
            _expect(requests.post(
                f"{base}/agent-api/game/{game_id}/action",
                headers=agent_headers,
                json={"action": "call", "amount": 0},
            ), 200)
        else:
            next_turn = _expect(requests.post(
                f"{base}/agent-api/game/{game_id}/advance-others",
                headers=agent_headers,
            ), 200).json()
            if (next_turn["advances"] == 0
                    and next_turn.get("waiting_for_agent_id") != agent["agent"]["id"]):
                pytest.fail("Test table contains another external agent; use a fresh disposable HTTP database")
    else:
        pytest.fail("game did not complete within 120 action cycles")

    completed = _expect(requests.get(f"{base}/games/{game_id}"), 200).json()
    assert completed["phase"] == "complete"
    assert completed["betting_closed"] is True
    _expect(requests.post(
        f"{base}/bets",
        headers={**human_headers, "Idempotency-Key": f"late-{suffix}"},
        json=bet,
    ), 409)

    bets = _expect(requests.get(
        f"{base}/bets/my-bets", headers=human_headers,
    ), 200).json()
    placed = next(item for item in bets if item["id"] == first["id"])
    assert placed["status"] in {"won", "lost"}

    transactions = _expect(requests.get(
        f"{base}/wallet/transactions", headers=human_headers,
    ), 200).json()
    assert len([
        transaction for transaction in transactions
        if transaction["id"] == f"bet:{first['id']}"
    ]) == 1

    cors = _expect(requests.options(f"{base}/tables", headers={
        "Origin": TEST_CORS_ORIGIN,
        "Access-Control-Request-Method": "GET",
    }), 200)
    assert cors.headers["access-control-allow-origin"] == TEST_CORS_ORIGIN


@pytest.mark.skipif(not BASE_URL, reason="requires a running PokerClaw backend")
def test_tournament_gc_wager_closes_and_settles():
    base = f"{BASE_URL}/api"
    suffix = uuid.uuid4().hex[:10]
    password = "ReleaseTest!234"
    human = _expect(requests.post(f"{base}/human-auth/signup", json={
        "username": f"TourneyHuman{suffix}",
        "email": f"tourney-human-{suffix}@example.test",
        "password": password,
    }), 200).json()
    agent = _expect(requests.post(f"{base}/agent-api/register", json={
        "username": f"TourneyAgent{suffix}",
        "email": f"tourney-agent-{suffix}@example.test",
        "password": password,
        "agent_name": f"TourneyBot{suffix}",
    }), 200).json()
    human_headers = {"Authorization": f"Bearer {human['token']}"}
    agent_headers = {"Authorization": f"Bearer {agent['token']}"}

    tournament = _expect(requests.post(
        f"{base}/tournaments", headers=agent_headers,
    ), 200).json()
    tournament_id = tournament["id"]
    selected = tournament["agent_ids"][0]
    request = {"tournament_id": tournament_id, "agent_id": selected,
               "amount": 100, "currency": "gc"}
    bet_headers = {**human_headers, "Idempotency-Key": f"tournament-{suffix}"}
    first = _expect(requests.post(
        f"{base}/tournament-bets", headers=bet_headers, json=request,
    ), 200).json()
    assert _expect(requests.post(
        f"{base}/tournament-bets", headers=bet_headers, json=request,
    ), 200).json()["id"] == first["id"]

    for _ in range(180):
        if tournament["status"] == "complete":
            break
        tournament = _expect(requests.post(
            f"{base}/tournaments/{tournament_id}/advance", headers=agent_headers,
        ), 200).json()
    else:
        pytest.fail("tournament did not finish in 180 steps")

    assert tournament["betting_closed"] is True
    assert tournament["champion_id"] is not None
    assert tournament["bracket"]["final"]["complete"] is True
    _expect(requests.post(
        f"{base}/tournament-bets",
        headers={**human_headers, "Idempotency-Key": f"late-tournament-{suffix}"},
        json=request,
    ), 409)

    wallet = _expect(requests.get(f"{base}/wallet", headers=human_headers), 200).json()
    # Only one wager in the pool: a win returns 80 GC after the 20% rake.
    expected_balance = 4980 if tournament["champion_id"] == selected else 4900
    assert wallet["gc_balance"] == expected_balance
    transactions = _expect(requests.get(
        f"{base}/wallet/transactions", headers=human_headers,
    ), 200).json()
    assert len([item for item in transactions if item["id"] == f"bet:{first['id']}"]) == 1
    assert len([item for item in transactions if item["id"] == f"settlement:{first['id']}"]) == (
        1 if tournament["champion_id"] == selected else 0
    )

    # Replaying completion must not duplicate a credit or ledger entry.
    repeated = _expect(requests.post(
        f"{base}/tournaments/{tournament_id}/advance", headers=agent_headers,
    ), 200).json()
    assert repeated["status"] == "complete"
    assert repeated["champion_id"] == tournament["champion_id"]
    assert _expect(requests.get(
        f"{base}/wallet", headers=human_headers,
    ), 200).json()["gc_balance"] == expected_balance
    assert _expect(requests.get(
        f"{base}/wallet/transactions", headers=human_headers,
    ), 200).json() == transactions
