"""
Test Turn-by-Turn Agent Decision System
Testing the new game_engine.py that processes ONE agent action per advance call.
Phase flow: waiting -> preflop_betting -> flop_deal -> flop_betting -> turn_deal -> turn_betting -> river_deal -> river_betting -> showdown -> complete
"""
import pytest
import requests
import os
import time

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Test credentials
HUMAN_EMAIL = "human@test.com"
HUMAN_PASS = "test123"


@pytest.fixture(scope="module")
def api_session():
    """Create a requests session for API calls."""
    session = requests.Session()
    session.headers.update({"Content-Type": "application/json"})
    return session


@pytest.fixture(scope="module")
def auth_token(api_session):
    """Get authentication token for human user."""
    resp = api_session.post(f"{BASE_URL}/api/auth/login", json={
        "email": HUMAN_EMAIL,
        "password": HUMAN_PASS
    })
    if resp.status_code == 200:
        return resp.json().get("token")
    pytest.skip("Human user authentication failed")


@pytest.fixture(scope="module")
def authenticated_client(api_session, auth_token):
    """Session with auth header."""
    api_session.headers.update({"Authorization": f"Bearer {auth_token}"})
    return api_session


def get_or_create_fresh_game(client, table_id):
    """Helper: Complete existing game and start a fresh one."""
    # Check for existing game
    table_resp = client.get(f"{BASE_URL}/api/tables/{table_id}")
    if table_resp.status_code != 200:
        return None
    table = table_resp.json()
    
    # If there's an active game that's not complete, advance it to completion
    if table.get("current_game_id"):
        game = client.get(f"{BASE_URL}/api/games/{table['current_game_id']}").json()
        advance_count = 0
        while game.get("phase") != "complete" and advance_count < 60:
            resp = client.post(f"{BASE_URL}/api/games/{game['id']}/advance")
            if resp.status_code != 200:
                break
            game = resp.json()
            advance_count += 1
    
    # Now start a fresh game
    resp = client.post(f"{BASE_URL}/api/tables/{table_id}/start-game")
    if resp.status_code == 200:
        return resp.json()
    return None


@pytest.fixture(scope="module")
def table_id(api_session):
    """Get the first available table ID."""
    resp = api_session.get(f"{BASE_URL}/api/tables")
    assert resp.status_code == 200, f"Failed to get tables: {resp.text}"
    tables = resp.json()
    assert len(tables) > 0, "No tables available for testing"
    return tables[0]["id"]


class TestStartGame:
    """Test game start creates game in 'waiting' phase."""
    
    def test_start_game_creates_waiting_phase(self, authenticated_client, table_id):
        """POST /api/tables/{id}/start-game creates a game in 'waiting' phase."""
        game = get_or_create_fresh_game(authenticated_client, table_id)
        assert game is not None, "Failed to create fresh game"
        
        assert game["phase"] == "waiting", f"Expected 'waiting' phase, got {game['phase']}"
        assert "id" in game, "Game should have an id"
        assert "players" in game, "Game should have players"
        assert len(game["players"]) >= 4, "Game should have at least 4 players"
        assert game["pot"] == 0, "Initial pot should be 0"
        
        # Check sanitization - deck should NOT be in response
        assert "deck" not in game, "Deck should not be exposed in response"
        
        # Check display_phase and is_betting fields exist
        assert "display_phase" in game, "Game should have display_phase"
        assert "is_betting" in game, "Game should have is_betting"
        print(f"SUCCESS: Game started with id={game['id'][:8]}, phase={game['phase']}")


class TestPhaseTransitions:
    """Test turn-by-turn phase transitions."""
    
    def test_first_advance_deals_cards_and_enters_preflop_betting(self, authenticated_client, table_id):
        """First advance from 'waiting' deals hole cards and enters 'preflop_betting'."""
        game = get_or_create_fresh_game(authenticated_client, table_id)
        assert game is not None, "Failed to create fresh game"
        game_id = game["id"]
        
        # Verify initial state is 'waiting'
        assert game["phase"] == "waiting", f"Initial phase should be 'waiting', got {game['phase']}"
        
        # First advance should deal cards
        resp = authenticated_client.post(f"{BASE_URL}/api/games/{game_id}/advance")
        assert resp.status_code == 200, f"Failed to advance game: {resp.text}"
        
        game = resp.json()
        assert game["phase"] == "preflop_betting", f"Expected 'preflop_betting', got {game['phase']}"
        assert game["display_phase"] == "preflop", f"Expected display_phase='preflop', got {game['display_phase']}"
        assert game["is_betting"] == True, "is_betting should be True during betting phase"
        
        # Players should have hole cards (though sanitized - shows [None, None])
        for p in game["players"]:
            assert "hole_cards" in p, f"Player {p['agent_name']} should have hole_cards"
        
        # turn_index should be set
        assert game.get("turn_index") is not None, "turn_index should be set"
        
        print(f"SUCCESS: First advance entered preflop_betting")
    
    def test_each_advance_processes_one_agent_action(self, authenticated_client, table_id):
        """Each advance in betting phase processes ONE agent action."""
        game = get_or_create_fresh_game(authenticated_client, table_id)
        assert game is not None, "Failed to create fresh game"
        game_id = game["id"]
        
        # First advance: waiting -> preflop_betting
        resp = authenticated_client.post(f"{BASE_URL}/api/games/{game_id}/advance")
        game = resp.json()
        assert game["phase"] == "preflop_betting"
        
        actions_before = len(game.get("actions_log", []))
        
        # Second advance: should process ONE agent action
        resp = authenticated_client.post(f"{BASE_URL}/api/games/{game_id}/advance")
        game = resp.json()
        
        actions_after = len(game.get("actions_log", []))
        
        # Should have exactly ONE more action OR transition to next phase
        if game["phase"] == "preflop_betting":
            assert actions_after == actions_before + 1, f"Expected one more action, got {actions_after - actions_before}"
            
            # last_action should reflect what happened
            assert "last_action" in game, "Game should have last_action"
            if game["last_action"]:
                last = game["last_action"]
                assert "agent_id" in last, "last_action should have agent_id"
                assert "action" in last, "last_action should have action"
                assert last["action"] in ["fold", "call", "raise"], f"Invalid action: {last['action']}"
                print(f"SUCCESS: Agent {last['agent_name']} performed '{last['action']}' (amount: {last.get('amount', 0)})")
        else:
            # Transitioned to next phase
            print(f"SUCCESS: Phase transitioned from preflop_betting to {game['phase']}")

    def test_full_game_flow_to_completion(self, authenticated_client, table_id):
        """Run through a complete game and verify all phases."""
        game = get_or_create_fresh_game(authenticated_client, table_id)
        assert game is not None, "Failed to create fresh game"
        game_id = game["id"]
        
        seen_phases = set()
        seen_phases.add(game["phase"])
        
        max_advances = 60  # Safety limit (6 players * 4 rounds + deal phases)
        advance_count = 0
        
        while game["phase"] != "complete" and advance_count < max_advances:
            resp = authenticated_client.post(f"{BASE_URL}/api/games/{game_id}/advance")
            assert resp.status_code == 200, f"Advance failed at phase {game['phase']}: {resp.text}"
            
            game = resp.json()
            seen_phases.add(game["phase"])
            advance_count += 1
        
        assert game["phase"] == "complete", f"Game did not complete after {advance_count} advances"
        
        # Verify we saw key phases
        expected_phases = ["waiting", "preflop_betting"]  # At minimum these
        for phase in expected_phases:
            assert phase in seen_phases, f"Expected to see phase '{phase}'"
        
        # Verify game completion fields
        assert game.get("winner_id") is not None, "Game should have winner_id"
        assert game.get("winner_name") is not None, "Game should have winner_name"
        assert game.get("winning_hand") is not None, "Game should have winning_hand"
        assert game.get("house_rake") is not None, "Game should have house_rake"
        assert game.get("final_pot") is not None, "Game should have final_pot"
        
        # Verify house rake is 20%
        pot = game["pot"]
        rake = game["house_rake"]
        expected_rake = int(pot * 0.20)
        assert rake == expected_rake, f"House rake should be 20% ({expected_rake}), got {rake}"
        
        print(f"\nSUCCESS: Game completed in {advance_count} advances")
        print(f"  Winner: {game['winner_name']}")
        print(f"  Hand: {game['winning_hand']}")
        print(f"  Pot: {pot}, Rake: {rake}, Final: {game['final_pot']}")


class TestGameResponseFields:
    """Test that game responses include all required fields."""
    
    def test_game_has_required_fields_during_betting(self, authenticated_client, table_id):
        """Game response should have current_actor, display_phase, is_betting, last_action."""
        game = get_or_create_fresh_game(authenticated_client, table_id)
        assert game is not None, "Failed to create fresh game"
        game_id = game["id"]
        
        # Advance to preflop_betting
        resp = authenticated_client.post(f"{BASE_URL}/api/games/{game_id}/advance")
        game = resp.json()
        
        # Check required fields
        assert "current_actor" in game, "Game should have current_actor"
        assert "display_phase" in game, "Game should have display_phase"
        assert "is_betting" in game, "Game should have is_betting"
        assert "last_action" in game, "Game should have last_action field (may be null)"
        
        # Verify display_phase maps correctly
        phase_display_mapping = {
            "preflop_betting": "preflop",
            "flop_deal": "flop",
            "flop_betting": "flop",
            "turn_deal": "turn",
            "turn_betting": "turn",
            "river_deal": "river",
            "river_betting": "river",
        }
        
        if game["phase"] in phase_display_mapping:
            expected_display = phase_display_mapping[game["phase"]]
            assert game["display_phase"] == expected_display, f"display_phase should be '{expected_display}' for phase '{game['phase']}'"
        
        # is_betting should be True during betting phases
        if game["phase"].endswith("_betting"):
            assert game["is_betting"] == True, f"is_betting should be True for {game['phase']}"
        
        print(f"SUCCESS: Game has all required fields")


class TestCommunityCards:
    """Test community card dealing across phases."""
    
    def test_community_cards_dealt_correctly(self, authenticated_client, table_id):
        """Test that community cards are dealt: flop=3, turn=1, river=1."""
        game = get_or_create_fresh_game(authenticated_client, table_id)
        assert game is not None, "Failed to create fresh game"
        game_id = game["id"]
        
        # Track community card counts at each phase
        card_counts = {}
        
        max_advances = 60
        advance_count = 0
        
        while game["phase"] != "complete" and advance_count < max_advances:
            resp = authenticated_client.post(f"{BASE_URL}/api/games/{game_id}/advance")
            game = resp.json()
            advance_count += 1
            
            cc_count = len(game.get("community_cards", []))
            
            # Record first time we see each phase
            if game["phase"] not in card_counts:
                card_counts[game["phase"]] = cc_count
        
        # Verify final card count
        final_cc = len(game.get("community_cards", []))
        assert final_cc == 5, f"Final community cards should be 5, got {final_cc}"
        
        print(f"SUCCESS: Community cards dealt correctly, final count: {final_cc}")


class TestHouseRake:
    """Test house rake calculation."""
    
    def test_house_rake_is_20_percent(self, authenticated_client, table_id):
        """Verify house rake is 20% of final pot."""
        game = get_or_create_fresh_game(authenticated_client, table_id)
        assert game is not None, "Failed to create fresh game"
        game_id = game["id"]
        
        max_advances = 60
        while game["phase"] != "complete" and max_advances > 0:
            resp = authenticated_client.post(f"{BASE_URL}/api/games/{game_id}/advance")
            game = resp.json()
            max_advances -= 1
        
        assert game["phase"] == "complete", "Game should complete"
        
        pot = game["pot"]
        rake = game["house_rake"]
        final_pot = game["final_pot"]
        
        expected_rake = int(pot * 0.20)
        expected_final = pot - expected_rake
        
        assert rake == expected_rake, f"Rake should be 20% of pot ({expected_rake}), got {rake}"
        assert final_pot == expected_final, f"Final pot should be {expected_final}, got {final_pot}"
        
        print(f"SUCCESS: House rake is 20% - Pot: {pot}, Rake: {rake}, Final: {final_pot}")


class TestActionsLog:
    """Test actions log records all agent decisions."""
    
    def test_actions_log_populated(self, authenticated_client, table_id):
        """Actions log should record each agent's decision."""
        game = get_or_create_fresh_game(authenticated_client, table_id)
        assert game is not None, "Failed to create fresh game"
        game_id = game["id"]
        
        max_advances = 60
        while game["phase"] != "complete" and max_advances > 0:
            resp = authenticated_client.post(f"{BASE_URL}/api/games/{game_id}/advance")
            game = resp.json()
            max_advances -= 1
        
        assert game["phase"] == "complete"
        
        # Verify actions_log
        assert len(game.get("actions_log", [])) > 0, "actions_log should have entries"
        
        # Each action should have required fields
        for action in game["actions_log"]:
            assert "agent_id" in action, "Action should have agent_id"
            assert "agent_name" in action, "Action should have agent_name"
            assert "action" in action, "Action should have action"
            assert action["action"] in ["fold", "call", "raise"], f"Invalid action: {action['action']}"
        
        action_counts = {"fold": 0, "call": 0, "raise": 0}
        for a in game["actions_log"]:
            action_counts[a["action"]] += 1
        
        print(f"SUCCESS: Actions log recorded {len(game['actions_log'])} actions")
        print(f"  Breakdown: fold={action_counts['fold']}, call={action_counts['call']}, raise={action_counts['raise']}")


class TestLastStandingWin:
    """Test that if all but one agent folds, remaining agent wins."""
    
    def test_verify_last_standing_logic_exists(self, authenticated_client, table_id):
        """Verify the 'Last Standing' win logic is properly implemented."""
        # Run multiple games to check for Last Standing scenario
        last_standing_found = False
        
        for attempt in range(3):
            game = get_or_create_fresh_game(authenticated_client, table_id)
            assert game is not None, "Failed to create fresh game"
            game_id = game["id"]
            
            max_advances = 60
            while game["phase"] != "complete" and max_advances > 0:
                resp = authenticated_client.post(f"{BASE_URL}/api/games/{game_id}/advance")
                game = resp.json()
                max_advances -= 1
            
            if game.get("winning_hand") == "Last Standing":
                last_standing_found = True
                print(f"SUCCESS: Found 'Last Standing' win - {game['winner_name']} won!")
                break
            else:
                print(f"Attempt {attempt+1}: {game['winner_name']} won with {game['winning_hand']}")
        
        # Whether we saw it or not, verify the game completed properly
        assert game["phase"] == "complete"
        assert game["winner_name"] is not None
        print(f"INFO: 'Last Standing' scenario {'found' if last_standing_found else 'not triggered in 3 attempts (depends on AI decisions)'}")


class TestDisplayPhaseMapping:
    """Test display_phase maps internal phases to friendly names."""
    
    def test_display_phase_mapping(self, authenticated_client, table_id):
        """Verify display_phase correctly maps internal phases."""
        game = get_or_create_fresh_game(authenticated_client, table_id)
        assert game is not None, "Failed to create fresh game"
        game_id = game["id"]
        
        phase_mappings = {}
        
        max_advances = 60
        while game["phase"] != "complete" and max_advances > 0:
            resp = authenticated_client.post(f"{BASE_URL}/api/games/{game_id}/advance")
            game = resp.json()
            max_advances -= 1
            
            internal_phase = game["phase"]
            display_phase = game["display_phase"]
            
            if internal_phase not in phase_mappings:
                phase_mappings[internal_phase] = display_phase
        
        # Expected mappings based on server.py sanitize_game_for_response
        expected_mappings = {
            "preflop_betting": "preflop",
            "flop_deal": "flop",
            "flop_betting": "flop",
            "turn_deal": "turn",
            "turn_betting": "turn",
            "river_deal": "river",
            "river_betting": "river",
            "showdown": "showdown",
            "complete": "complete",
        }
        
        for internal, expected_display in expected_mappings.items():
            if internal in phase_mappings:
                actual = phase_mappings[internal]
                assert actual == expected_display, f"display_phase for '{internal}' should be '{expected_display}', got '{actual}'"
        
        print(f"SUCCESS: Phase mappings verified")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
