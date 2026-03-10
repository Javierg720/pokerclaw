"""
Phase 4: Enhanced Spectator Betting - Backend API Tests
Tests for:
- GET /api/bets/game/{game_id}/odds - live odds with multipliers
- POST /api/bets - bet placement
- GET /api/bets/my-bets - user bet history
- Odds multiplier calculation logic
"""

import pytest
import requests
import os
import uuid

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Test credentials
HUMAN_EMAIL = "human@test.com"
HUMAN_PASSWORD = "test123"
AGENT_EMAIL = "agent@test.com"
AGENT_PASSWORD = "test123"


class TestOddsEndpoint:
    """Tests for GET /api/bets/game/{game_id}/odds endpoint"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        self.session = requests.Session()
        # Login as human user
        login_res = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": HUMAN_EMAIL,
            "password": HUMAN_PASSWORD
        })
        if login_res.status_code == 200:
            self.token = login_res.json().get("token")
            self.session.headers.update({"Authorization": f"Bearer {self.token}"})
        yield
        self.session.close()
    
    def test_odds_returns_404_for_nonexistent_game(self):
        """GET /api/bets/game/{game_id}/odds returns 404 for non-existent game"""
        fake_game_id = str(uuid.uuid4())
        res = self.session.get(f"{BASE_URL}/api/bets/game/{fake_game_id}/odds")
        assert res.status_code == 404
        assert "not found" in res.json().get("detail", "").lower()
        print("PASSED: Odds returns 404 for non-existent game")
    
    def test_odds_returns_live_odds_structure(self):
        """GET /api/bets/game/{game_id}/odds returns proper structure"""
        # Get a table with active game
        tables_res = self.session.get(f"{BASE_URL}/api/tables")
        assert tables_res.status_code == 200
        tables = tables_res.json()
        
        # Find a table with a current game
        game_id = None
        for t in tables:
            if t.get("current_game_id"):
                game_id = t["current_game_id"]
                break
        
        if not game_id:
            pytest.skip("No active game to test odds")
        
        res = self.session.get(f"{BASE_URL}/api/bets/game/{game_id}/odds")
        assert res.status_code == 200
        data = res.json()
        
        # Check response structure
        assert "total_pool" in data
        assert "total_bets" in data
        assert "odds" in data
        assert isinstance(data["odds"], list)
        
        print(f"PASSED: Odds structure valid - total_pool={data['total_pool']}, total_bets={data['total_bets']}, agents={len(data['odds'])}")
    
    def test_odds_agents_have_required_fields(self):
        """Each agent in odds has multiplier, pool, bets_count, etc."""
        tables_res = self.session.get(f"{BASE_URL}/api/tables")
        tables = tables_res.json()
        
        game_id = None
        for t in tables:
            if t.get("current_game_id"):
                game_id = t["current_game_id"]
                break
        
        if not game_id:
            pytest.skip("No active game")
        
        res = self.session.get(f"{BASE_URL}/api/bets/game/{game_id}/odds")
        assert res.status_code == 200
        data = res.json()
        
        for agent_odds in data["odds"]:
            assert "agent_id" in agent_odds
            assert "agent_name" in agent_odds
            assert "multiplier" in agent_odds
            assert "pool" in agent_odds
            assert "bets_count" in agent_odds
            assert "pct" in agent_odds
            assert "folded" in agent_odds
            assert isinstance(agent_odds["multiplier"], (int, float))
            assert agent_odds["multiplier"] >= 0
        
        print(f"PASSED: All {len(data['odds'])} agents have required fields with multipliers")
    
    def test_odds_multiplier_calculation_with_bets(self):
        """Odds multiplier = (total_pool * 0.8) / agent_pool for agents with bets"""
        # This test validates the formula when there are existing bets
        tables_res = self.session.get(f"{BASE_URL}/api/tables")
        tables = tables_res.json()
        
        game_id = None
        for t in tables:
            if t.get("current_game_id"):
                game_id = t["current_game_id"]
                break
        
        if not game_id:
            pytest.skip("No active game")
        
        res = self.session.get(f"{BASE_URL}/api/bets/game/{game_id}/odds")
        data = res.json()
        
        total_pool = data["total_pool"]
        
        for agent_odds in data["odds"]:
            pool = agent_odds["pool"]
            mult = agent_odds["multiplier"]
            
            if total_pool > 0 and pool > 0:
                # Formula: (total_pool * 0.8) / pool
                expected = round((total_pool * 0.8) / pool, 2)
                assert abs(mult - expected) < 0.01, f"Multiplier mismatch: got {mult}, expected {expected}"
                print(f"  Agent {agent_odds['agent_name']}: pool={pool}, multiplier={mult} (expected {expected})")
        
        print("PASSED: Odds multiplier formula validated")
    
    def test_odds_default_multiplier_for_no_bets(self):
        """Agents with no bets get default multiplier based on active player count"""
        # When no bets exist, multiplier = active_players * 0.8
        tables_res = self.session.get(f"{BASE_URL}/api/tables")
        tables = tables_res.json()
        
        game_id = None
        for t in tables:
            if t.get("current_game_id"):
                game_id = t["current_game_id"]
                break
        
        if not game_id:
            pytest.skip("No active game")
        
        res = self.session.get(f"{BASE_URL}/api/bets/game/{game_id}/odds")
        data = res.json()
        
        # Count non-folded agents
        active_count = len([o for o in data["odds"] if not o["folded"]])
        
        for agent_odds in data["odds"]:
            if agent_odds["pool"] == 0:
                # Default multiplier = active_count * 0.8
                expected_default = round(active_count * 0.8, 2) if active_count > 0 else 1.0
                assert abs(agent_odds["multiplier"] - expected_default) < 0.01, \
                    f"Default multiplier mismatch for {agent_odds['agent_name']}: got {agent_odds['multiplier']}, expected {expected_default}"
        
        print(f"PASSED: Default multiplier logic verified (active_count={active_count})")


class TestBetPlacement:
    """Tests for POST /api/bets bet placement"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        self.session = requests.Session()
        # Login as human user
        login_res = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": HUMAN_EMAIL,
            "password": HUMAN_PASSWORD
        })
        if login_res.status_code == 200:
            self.token = login_res.json().get("token")
            self.session.headers.update({"Authorization": f"Bearer {self.token}"})
        yield
        self.session.close()
    
    def test_bet_requires_authentication(self):
        """POST /api/bets requires auth"""
        no_auth_session = requests.Session()
        res = no_auth_session.post(f"{BASE_URL}/api/bets", json={
            "game_id": "fake",
            "agent_id": "fake",
            "amount": 50,
            "currency": "sc"
        })
        assert res.status_code == 401
        print("PASSED: Bet placement requires authentication")
    
    def test_bet_rejects_nonexistent_game(self):
        """POST /api/bets rejects bets for non-existent games"""
        fake_game_id = str(uuid.uuid4())
        res = self.session.post(f"{BASE_URL}/api/bets", json={
            "game_id": fake_game_id,
            "agent_id": "fake_agent",
            "amount": 50,
            "currency": "sc"
        })
        assert res.status_code == 404
        assert "game not found" in res.json().get("detail", "").lower()
        print("PASSED: Bet rejected for non-existent game")
    
    def test_bet_rejects_invalid_agent(self):
        """POST /api/bets rejects bets on agents not in the game"""
        # Get an active game
        tables_res = self.session.get(f"{BASE_URL}/api/tables")
        tables = tables_res.json()
        
        game_id = None
        for t in tables:
            cg = t.get("current_game")
            if cg and cg.get("phase") not in ["showdown", "complete"]:
                game_id = t["current_game_id"]
                break
        
        if not game_id:
            pytest.skip("No active game in betting phase")
        
        res = self.session.post(f"{BASE_URL}/api/bets", json={
            "game_id": game_id,
            "agent_id": str(uuid.uuid4()),  # Fake agent ID
            "amount": 50,
            "currency": "sc"
        })
        assert res.status_code == 400
        assert "not in this game" in res.json().get("detail", "").lower()
        print("PASSED: Bet rejected for agent not in game")
    
    def test_bet_creates_pending_bet(self):
        """POST /api/bets creates a pending bet for authenticated users"""
        # First, ensure user has balance
        wallet_res = self.session.get(f"{BASE_URL}/api/wallet")
        if wallet_res.status_code != 200:
            pytest.skip("Wallet not found")
        
        wallet = wallet_res.json()
        if wallet.get("sc_balance", 0) < 50:
            # Add some balance
            self.session.post(f"{BASE_URL}/api/wallet/purchase", json={
                "amount": 1000,
                "currency": "sc"
            })
        
        # Get active game
        tables_res = self.session.get(f"{BASE_URL}/api/tables")
        tables = tables_res.json()
        
        game_id = None
        agent_id = None
        for t in tables:
            cg = t.get("current_game")
            if cg and cg.get("phase") not in ["showdown", "complete"]:
                game_id = t["current_game_id"]
                # Get the table details for agent IDs
                table_detail = self.session.get(f"{BASE_URL}/api/tables/{t['id']}").json()
                if table_detail.get("current_game"):
                    players = table_detail["current_game"].get("players", [])
                    if players:
                        agent_id = players[0]["agent_id"]
                break
        
        if not game_id or not agent_id:
            pytest.skip("No active game or agent to bet on")
        
        res = self.session.post(f"{BASE_URL}/api/bets", json={
            "game_id": game_id,
            "agent_id": agent_id,
            "amount": 50,
            "currency": "sc"
        })
        
        assert res.status_code == 200
        data = res.json()
        assert "id" in data
        assert data["status"] == "pending"
        assert data["amount"] == 50
        
        print(f"PASSED: Bet created with id={data['id']}, status=pending, amount=50")
    
    def test_bet_rejects_completed_game(self):
        """POST /api/bets rejects bets on showdown/complete games"""
        # Find a completed game
        tables_res = self.session.get(f"{BASE_URL}/api/tables")
        tables = tables_res.json()
        
        game_id = None
        agent_id = None
        for t in tables:
            cg = t.get("current_game")
            if cg and cg.get("phase") in ["showdown", "complete"]:
                game_id = t["current_game_id"]
                # Get agents from table
                if t.get("agent_ids"):
                    agent_id = t["agent_ids"][0]
                break
        
        if not game_id:
            pytest.skip("No completed/showdown game found")
        
        res = self.session.post(f"{BASE_URL}/api/bets", json={
            "game_id": game_id,
            "agent_id": agent_id,
            "amount": 50,
            "currency": "sc"
        })
        assert res.status_code == 400
        assert "cannot bet on completed game" in res.json().get("detail", "").lower()
        print("PASSED: Bet rejected for completed game")


class TestMyBets:
    """Tests for GET /api/bets/my-bets endpoint"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        self.session = requests.Session()
        login_res = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": HUMAN_EMAIL,
            "password": HUMAN_PASSWORD
        })
        if login_res.status_code == 200:
            self.token = login_res.json().get("token")
            self.session.headers.update({"Authorization": f"Bearer {self.token}"})
        yield
        self.session.close()
    
    def test_my_bets_requires_auth(self):
        """GET /api/bets/my-bets requires authentication"""
        no_auth_session = requests.Session()
        res = no_auth_session.get(f"{BASE_URL}/api/bets/my-bets")
        assert res.status_code == 401
        print("PASSED: My bets requires authentication")
    
    def test_my_bets_returns_list(self):
        """GET /api/bets/my-bets returns user's bet history"""
        res = self.session.get(f"{BASE_URL}/api/bets/my-bets")
        assert res.status_code == 200
        bets = res.json()
        assert isinstance(bets, list)
        
        if len(bets) > 0:
            # Verify bet structure
            bet = bets[0]
            assert "id" in bet
            assert "game_id" in bet
            assert "agent_id" in bet
            assert "amount" in bet
            assert "status" in bet
            print(f"PASSED: My bets returns {len(bets)} bets with proper structure")
        else:
            print("PASSED: My bets returns empty list (no bets yet)")


class TestAgentSideBets:
    """Tests for agent users placing side bets"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        self.session = requests.Session()
        login_res = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": AGENT_EMAIL,
            "password": AGENT_PASSWORD
        })
        if login_res.status_code == 200:
            self.token = login_res.json().get("token")
            self.user = login_res.json().get("user")
            self.session.headers.update({"Authorization": f"Bearer {self.token}"})
        yield
        self.session.close()
    
    def test_agent_can_place_side_bet(self):
        """Agent users can also place side bets"""
        # Ensure agent has balance
        wallet_res = self.session.get(f"{BASE_URL}/api/wallet")
        if wallet_res.status_code == 200:
            wallet = wallet_res.json()
            if wallet.get("sc_balance", 0) < 50:
                self.session.post(f"{BASE_URL}/api/wallet/purchase", json={
                    "amount": 1000,
                    "currency": "sc"
                })
        
        # Get active game
        tables_res = self.session.get(f"{BASE_URL}/api/tables")
        tables = tables_res.json()
        
        game_id = None
        agent_id = None
        for t in tables:
            cg = t.get("current_game")
            if cg and cg.get("phase") not in ["showdown", "complete"]:
                game_id = t["current_game_id"]
                table_detail = self.session.get(f"{BASE_URL}/api/tables/{t['id']}").json()
                if table_detail.get("current_game"):
                    players = table_detail["current_game"].get("players", [])
                    if players:
                        agent_id = players[0]["agent_id"]
                break
        
        if not game_id or not agent_id:
            pytest.skip("No active game")
        
        res = self.session.post(f"{BASE_URL}/api/bets", json={
            "game_id": game_id,
            "agent_id": agent_id,
            "amount": 50,
            "currency": "sc"
        })
        
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "pending"
        print(f"PASSED: Agent user can place side bet (id={data['id']})")


class TestGameFlow:
    """Tests for gameplay flow that was existing before"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        self.session = requests.Session()
        login_res = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": HUMAN_EMAIL,
            "password": HUMAN_PASSWORD
        })
        if login_res.status_code == 200:
            self.token = login_res.json().get("token")
            self.session.headers.update({"Authorization": f"Bearer {self.token}"})
        yield
        self.session.close()
    
    def test_start_game_flow(self):
        """Start game, advance through phases to completion"""
        # Get a table
        tables_res = self.session.get(f"{BASE_URL}/api/tables")
        tables = tables_res.json()
        
        # Find a table where we can start a new game
        table_id = None
        for t in tables:
            cg = t.get("current_game")
            if not cg or cg.get("phase") in ["complete", "showdown"]:
                table_id = t["id"]
                break
        
        if not table_id:
            # Use first table and try
            table_id = tables[0]["id"]
        
        # Start a new game
        start_res = self.session.post(f"{BASE_URL}/api/tables/{table_id}/start-game")
        if start_res.status_code == 400:
            # Game already in progress, just advance existing
            table_detail = self.session.get(f"{BASE_URL}/api/tables/{table_id}").json()
            game = table_detail.get("current_game")
            if game:
                game_id = game["id"]
            else:
                pytest.skip("Cannot start or find game")
        else:
            assert start_res.status_code == 200
            game = start_res.json()
            game_id = game["id"]
            assert game["phase"] == "waiting"
        
        # Advance through phases until complete
        phases_seen = []
        for _ in range(20):  # Max iterations
            adv_res = self.session.post(f"{BASE_URL}/api/games/{game_id}/advance")
            if adv_res.status_code != 200:
                break
            game = adv_res.json()
            phases_seen.append(game["phase"])
            
            if game["phase"] == "complete":
                break
        
        print(f"PASSED: Game flow complete - phases: {phases_seen}")
        assert "complete" in phases_seen or "showdown" in phases_seen, "Game should reach completion"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
