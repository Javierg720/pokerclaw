import pytest

from agent_entertainment import (
    AGENT_CHAT_PROMPT,
    PERSONALITIES,
    build_agent_chat_message,
    normalize_agent_chat,
    public_personality,
)
from game_engine import AGENT_PRESETS, advance_game, create_deck


def _game():
    players = [
        {
            "agent_id": "a1", "agent_name": "BluffBot_9000",
            "avatar_url": "/a.png", "strategy": "bluffer",
            "personality_key": "showboat", "is_external": True,
            "hole_cards": [], "chips": 1000, "current_bet": 0,
            "total_bet": 0, "folded": False, "is_dealer": True,
            "hand_rank": 0, "hand_name": "",
        },
        {
            "agent_id": "a2", "agent_name": "Vector_King",
            "avatar_url": "/b.png", "strategy": "conservative",
            "personality_key": "fortress", "is_external": False,
            "hole_cards": [], "chips": 1000, "current_bet": 0,
            "total_bet": 0, "folded": False, "is_dealer": False,
            "hand_rank": 0, "hand_name": "",
        },
    ]
    return {
        "id": "game-1", "table_id": "table-1", "phase": "waiting",
        "players": players, "community_cards": [], "pot": 0,
        "deck": create_deck(), "actions_log": [], "current_actor": None,
        "turn_index": 0, "round_bet": 0, "round_phase": None,
    }


def test_all_house_agents_have_distinct_safe_personalities():
    keys = [preset["personality_key"] for preset in AGENT_PRESETS]
    assert len(keys) == len(set(keys)) == 8
    assert set(keys) == set(PERSONALITIES)
    assert "chain-of-thought" in AGENT_CHAT_PROMPT


def test_action_provenance_explains_public_state_without_leaking_secrets():
    game = advance_game(_game())
    game = advance_game(game, {"agent_id": "a1", "action": "raise", "amount": 40})
    action = game["last_action"]

    assert action["decision_source"] == "external_agent"
    assert action["policy_version"] == "external-agent"
    assert action["reason_code"] == "pressure_applied"
    assert action["phase"] == "preflop"
    assert action["decision_id"] == "game-1:1"
    assert "40 chips" in action["public_explanation"]
    assert "strength" not in action
    assert "hole_cards" not in action
    assert "random" not in action


def test_scripted_banter_is_deterministic_labeled_and_short():
    game = _game()
    action = {
        "decision_id": "game-1:1", "agent_id": "a1",
        "action": "raise", "amount": 40,
    }
    first = build_agent_chat_message(game, action, game["players"][0])
    second = build_agent_chat_message(game, action, game["players"][0])

    assert first["text"] == second["text"]
    assert first["sender_type"] == "agent"
    assert first["source"] == "scripted_banter"
    assert first["personality"] == public_personality(game["players"][0])["name"]
    assert len(first["text"]) <= 160


def test_external_chat_normalizes_text_and_rejects_links_or_threats():
    assert normalize_agent_chat("  Nice   call.  ") == "Nice call."
    with pytest.raises(ValueError, match="Links"):
        normalize_agent_chat("watch https://example.com")
    with pytest.raises(ValueError, match="safety"):
        normalize_agent_chat("I will doxx you")
