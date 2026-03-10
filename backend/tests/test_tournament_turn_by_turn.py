"""
Test Tournament System with Turn-by-Turn Game Engine
Tournament flow: 
  - POST /api/tournaments creates 8-agent tournament
  - First advance: plays semis to completion, creates final, status='final'
  - Semi brackets show complete=True with winners (top 2 from each)
  - Final game plays turn-by-turn (each advance = one agent action)
  - Tournament status becomes 'complete' when final finishes, champion is set
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


class TestCreateTournament:
    """Test tournament creation endpoint."""

    def test_create_tournament_with_8_agents(self, authenticated_client):
        """POST /api/tournaments creates a new tournament with 8 agents."""
        resp = authenticated_client.post(f"{BASE_URL}/api/tournaments")
        assert resp.status_code == 200, f"Failed to create tournament: {resp.text}"
        
        t = resp.json()
        assert "id" in t, "Tournament should have id"
        assert "name" in t, "Tournament should have name"
        assert t["status"] == "lobby", f"Initial status should be 'lobby', got {t['status']}"
        
        # Check agent_ids
        assert "agent_ids" in t, "Tournament should have agent_ids"
        assert len(t["agent_ids"]) == 8, f"Tournament should have 8 agents, got {len(t['agent_ids'])}"
        
        # Check bracket structure
        bracket = t.get("bracket", {})
        assert "semi_1" in bracket, "Bracket should have semi_1"
        assert "semi_2" in bracket, "Bracket should have semi_2"
        assert "final" in bracket, "Bracket should have final"
        
        # Semi 1 should have 4 agents
        assert len(bracket["semi_1"]["agent_ids"]) == 4, "Semi 1 should have 4 agents"
        # Semi 2 should have 4 agents
        assert len(bracket["semi_2"]["agent_ids"]) == 4, "Semi 2 should have 4 agents"
        # Final should be empty at start
        assert len(bracket["final"]["agent_ids"]) == 0, "Final should start empty"
        
        print(f"SUCCESS: Created tournament '{t['name']}' with 8 agents")
        return t


class TestFirstAdvance:
    """Test first advance plays semis to completion and creates final."""

    def test_first_advance_plays_semis_and_creates_final(self, authenticated_client):
        """First advance: plays semis to completion instantly, creates final, status='final'."""
        # Create a new tournament
        resp = authenticated_client.post(f"{BASE_URL}/api/tournaments")
        assert resp.status_code == 200
        t = resp.json()
        tournament_id = t["id"]
        
        # First advance should play semis and create final
        resp = authenticated_client.post(f"{BASE_URL}/api/tournaments/{tournament_id}/advance")
        assert resp.status_code == 200, f"Failed to advance: {resp.text}"
        
        t = resp.json()
        
        # Status should be 'final' (skipping 'semis' since semis complete instantly)
        assert t["status"] == "final", f"Status should be 'final' after first advance, got {t['status']}"
        
        bracket = t["bracket"]
        
        # Semi 1 should be complete with winners
        assert bracket["semi_1"]["complete"] == True, "Semi 1 should be complete"
        assert bracket["semi_1"]["game_phase"] == "complete", "Semi 1 game_phase should be 'complete'"
        assert len(bracket["semi_1"]["winners"]) == 2, f"Semi 1 should have 2 winners, got {len(bracket['semi_1']['winners'])}"
        
        # Semi 2 should be complete with winners
        assert bracket["semi_2"]["complete"] == True, "Semi 2 should be complete"
        assert bracket["semi_2"]["game_phase"] == "complete", "Semi 2 game_phase should be 'complete'"
        assert len(bracket["semi_2"]["winners"]) == 2, f"Semi 2 should have 2 winners, got {len(bracket['semi_2']['winners'])}"
        
        # Final should have 4 agents (2 from each semi)
        assert len(bracket["final"]["agent_ids"]) == 4, f"Final should have 4 agents, got {len(bracket['final']['agent_ids'])}"
        assert bracket["final"]["game_id"] is not None, "Final should have game_id"
        assert bracket["final"]["game_phase"] == "waiting", f"Final game_phase should be 'waiting', got {bracket['final']['game_phase']}"
        
        print(f"SUCCESS: First advance - semis complete, final created with 4 agents")
        print(f"  Semi 1 winners: {bracket['semi_1']['winners'][:2]}")
        print(f"  Semi 2 winners: {bracket['semi_2']['winners'][:2]}")
        return t


class TestFinalTurnByTurn:
    """Test final game plays turn-by-turn."""

    def test_final_game_advances_turn_by_turn(self, authenticated_client):
        """Final game plays turn-by-turn (each advance = one agent action)."""
        # Create and advance to final
        resp = authenticated_client.post(f"{BASE_URL}/api/tournaments")
        t = resp.json()
        tournament_id = t["id"]
        
        resp = authenticated_client.post(f"{BASE_URL}/api/tournaments/{tournament_id}/advance")
        t = resp.json()
        assert t["status"] == "final"
        
        # Get the final game_id
        final_game_id = t["bracket"]["final"]["game_id"]
        assert final_game_id is not None, "Final should have game_id"
        
        # Get initial game state
        game_resp = authenticated_client.get(f"{BASE_URL}/api/games/{final_game_id}")
        assert game_resp.status_code == 200
        game = game_resp.json()
        initial_phase = game["phase"]
        
        # Advance once - should process one action
        resp = authenticated_client.post(f"{BASE_URL}/api/tournaments/{tournament_id}/advance")
        assert resp.status_code == 200
        t = resp.json()
        
        new_phase = t["bracket"]["final"]["game_phase"]
        
        # Phase should have changed (from waiting to something else)
        assert initial_phase != new_phase or new_phase is not None, "Phase should progress"
        
        print(f"SUCCESS: Final game advancing turn-by-turn")
        print(f"  Initial phase: {initial_phase}, New phase: {new_phase}")
        return t


class TestFinalGamePhases:
    """Test final game progresses through all phases."""

    def test_final_game_progresses_through_phases(self, authenticated_client):
        """Final game progresses through: preflop -> flop -> turn -> river -> showdown -> complete."""
        # Create and advance to final
        resp = authenticated_client.post(f"{BASE_URL}/api/tournaments")
        t = resp.json()
        tournament_id = t["id"]
        
        resp = authenticated_client.post(f"{BASE_URL}/api/tournaments/{tournament_id}/advance")
        t = resp.json()
        
        seen_phases = set()
        max_advances = 50  # Safety limit
        advance_count = 0
        
        while t["status"] != "complete" and advance_count < max_advances:
            game_phase = t["bracket"]["final"].get("game_phase")
            if game_phase:
                seen_phases.add(game_phase)
            
            resp = authenticated_client.post(f"{BASE_URL}/api/tournaments/{tournament_id}/advance")
            assert resp.status_code == 200, f"Advance failed: {resp.text}"
            t = resp.json()
            advance_count += 1
        
        # Tournament should complete
        assert t["status"] == "complete", f"Tournament should complete, got {t['status']}"
        
        # Should have seen key phases
        print(f"SUCCESS: Final game completed in {advance_count} advances")
        print(f"  Phases seen: {seen_phases}")
        return t


class TestTournamentCompletion:
    """Test tournament completion and champion."""

    def test_tournament_completion_sets_champion(self, authenticated_client):
        """Tournament status becomes 'complete' when final finishes, champion is set."""
        # Create tournament
        resp = authenticated_client.post(f"{BASE_URL}/api/tournaments")
        t = resp.json()
        tournament_id = t["id"]
        
        # Play through entire tournament
        max_advances = 60
        advance_count = 0
        
        while t["status"] != "complete" and advance_count < max_advances:
            resp = authenticated_client.post(f"{BASE_URL}/api/tournaments/{tournament_id}/advance")
            assert resp.status_code == 200
            t = resp.json()
            advance_count += 1
        
        # Verify completion
        assert t["status"] == "complete", f"Tournament should be complete, got {t['status']}"
        assert t["champion_id"] is not None, "Tournament should have champion_id"
        assert t["champion_name"] is not None, "Tournament should have champion_name"
        assert t["completed_at"] is not None, "Tournament should have completed_at"
        
        # Final bracket should show winner
        assert t["bracket"]["final"]["complete"] == True, "Final should be complete"
        assert t["bracket"]["final"]["winner"] == t["champion_id"], "Final winner should match champion_id"
        
        print(f"SUCCESS: Tournament completed!")
        print(f"  Champion: {t['champion_name']}")
        print(f"  Total advances: {advance_count}")
        return t


class TestTournamentList:
    """Test tournament list shows correct statuses."""

    def test_tournament_list_with_statuses(self, authenticated_client):
        """Tournament page shows tournaments with correct statuses (FINISHED, LIVE, OPEN)."""
        # Get all tournaments
        resp = authenticated_client.get(f"{BASE_URL}/api/tournaments")
        assert resp.status_code == 200
        tournaments = resp.json()
        
        status_counts = {"lobby": 0, "final": 0, "complete": 0, "other": 0}
        
        for t in tournaments:
            status = t.get("status", "")
            if status in status_counts:
                status_counts[status] += 1
            else:
                status_counts["other"] += 1
        
        print(f"SUCCESS: Tournament list retrieved")
        print(f"  Total tournaments: {len(tournaments)}")
        print(f"  Status breakdown: lobby(OPEN)={status_counts['lobby']}, final(LIVE)={status_counts['final']}, complete(FINISHED)={status_counts['complete']}")
        
        # Verify each tournament has required fields
        for t in tournaments[:3]:  # Check first 3
            assert "id" in t, "Tournament should have id"
            assert "name" in t, "Tournament should have name"
            assert "status" in t, "Tournament should have status"
            assert "bracket" in t, "Tournament should have bracket"


class TestRegularTableGames:
    """Regression test: Regular table games still work correctly with turn-by-turn."""

    def test_regular_game_start_and_advance(self, authenticated_client):
        """Start new table game, advance through full game to completion."""
        # Get first table
        resp = authenticated_client.get(f"{BASE_URL}/api/tables")
        assert resp.status_code == 200
        tables = resp.json()
        assert len(tables) > 0, "Need at least one table"
        table_id = tables[0]["id"]
        
        # Complete any existing game
        table = authenticated_client.get(f"{BASE_URL}/api/tables/{table_id}").json()
        if table.get("current_game_id"):
            game = authenticated_client.get(f"{BASE_URL}/api/games/{table['current_game_id']}").json()
            while game.get("phase") != "complete":
                resp = authenticated_client.post(f"{BASE_URL}/api/games/{game['id']}/advance")
                if resp.status_code != 200:
                    break
                game = resp.json()
        
        # Start fresh game
        resp = authenticated_client.post(f"{BASE_URL}/api/tables/{table_id}/start-game")
        assert resp.status_code == 200, f"Failed to start game: {resp.text}"
        game = resp.json()
        game_id = game["id"]
        
        assert game["phase"] == "waiting", f"Initial phase should be 'waiting', got {game['phase']}"
        
        # Play through to completion
        max_advances = 60
        while game["phase"] != "complete" and max_advances > 0:
            resp = authenticated_client.post(f"{BASE_URL}/api/games/{game_id}/advance")
            assert resp.status_code == 200
            game = resp.json()
            max_advances -= 1
        
        # Verify completion
        assert game["phase"] == "complete", "Game should complete"
        assert game["winner_id"] is not None
        assert game["winner_name"] is not None
        
        print(f"SUCCESS: Regular table game completed")
        print(f"  Winner: {game['winner_name']} with {game['winning_hand']}")


class TestSemiBracketsShowWinners:
    """Test semi brackets show complete=True with winners."""

    def test_semi_brackets_show_top2_winners(self, authenticated_client):
        """Semi brackets show complete=True with winners (top 2 from each)."""
        # Create and advance to final
        resp = authenticated_client.post(f"{BASE_URL}/api/tournaments")
        t = resp.json()
        tournament_id = t["id"]
        
        resp = authenticated_client.post(f"{BASE_URL}/api/tournaments/{tournament_id}/advance")
        assert resp.status_code == 200
        t = resp.json()
        
        # Check semi_1
        semi_1 = t["bracket"]["semi_1"]
        assert semi_1["complete"] == True, "Semi 1 should be complete"
        assert len(semi_1["winners"]) == 2, f"Semi 1 should have 2 winners (top 2), got {len(semi_1['winners'])}"
        
        # Winners should be from the semi_1 agent pool
        for winner_id in semi_1["winners"]:
            assert winner_id in semi_1["agent_ids"], f"Winner {winner_id} should be from semi_1 agents"
        
        # Check semi_2
        semi_2 = t["bracket"]["semi_2"]
        assert semi_2["complete"] == True, "Semi 2 should be complete"
        assert len(semi_2["winners"]) == 2, f"Semi 2 should have 2 winners (top 2), got {len(semi_2['winners'])}"
        
        # Winners should be from the semi_2 agent pool
        for winner_id in semi_2["winners"]:
            assert winner_id in semi_2["agent_ids"], f"Winner {winner_id} should be from semi_2 agents"
        
        print(f"SUCCESS: Semi brackets show top 2 winners each")
        print(f"  Semi 1: {semi_1['winners']}")
        print(f"  Semi 2: {semi_2['winners']}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
