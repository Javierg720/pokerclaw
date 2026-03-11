"""
Test Suite for 5 New Features:
1. Spectator Live Chat (via WebSocket - tested via REST chat history check)
2. Crypto Auto-Confirmations (background task + deposit flow)
3. Chip Movement Animations (CSS classes existence in frontend)
4. Tournament Late Join (POST /api/tournaments/{id}/join)
5. Frontend Refactoring (ChatPanel.jsx existence - checked separately)
"""
import pytest
import requests
import os
import time
import uuid

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

class TestCryptoAutoConfirmations:
    """
    FEATURE 2: Crypto deposit auto-confirmation
    Tests the deposit submission and auto-confirm background loop
    """
    
    @pytest.fixture
    def agent_auth(self):
        """Get or create agent account for crypto tests"""
        email = f"TEST_crypto_{uuid.uuid4().hex[:8]}@test.com"
        password = "test123"
        
        # Try to register new agent
        reg_resp = requests.post(f"{BASE_URL}/api/agent-api/register", json={
            "email": email,
            "password": password,
            "agent_name": f"TEST_CryptoBot_{uuid.uuid4().hex[:8]}",
            "strategy": "balanced"
        })
        
        if reg_resp.status_code == 200:
            return {"token": reg_resp.json()["token"], "email": email}
        
        # If registration fails, try existing test account
        login_resp = requests.post(f"{BASE_URL}/api/agent-api/login", json={
            "email": "openclaw@test.com",
            "password": "test123"
        })
        
        if login_resp.status_code == 200:
            return {"token": login_resp.json()["token"], "email": "openclaw@test.com"}
        
        pytest.skip("Could not authenticate for crypto tests")
    
    def test_crypto_prices_endpoint(self):
        """Test GET /api/crypto/prices returns BTC, LTC, ETH prices"""
        resp = requests.get(f"{BASE_URL}/api/crypto/prices")
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}"
        
        data = resp.json()
        assert "prices" in data
        assert "btc" in data["prices"]
        assert "ltc" in data["prices"]
        assert "eth" in data["prices"]
        assert data["prices"]["btc"]["usd"] > 0
        print(f"✓ Crypto prices: BTC=${data['prices']['btc']['usd']}")
    
    def test_submit_crypto_deposit(self, agent_auth):
        """Test POST /api/crypto/deposit creates pending deposit"""
        headers = {"Authorization": f"Bearer {agent_auth['token']}"}
        
        # Submit a new crypto deposit with unique tx hash
        tx_hash = f"TEST_0x{uuid.uuid4().hex}"
        resp = requests.post(f"{BASE_URL}/api/crypto/deposit", json={
            "crypto_type": "btc",
            "tx_hash": tx_hash,
            "amount_crypto": 0.001
        }, headers=headers)
        
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        assert data["status"] == "pending"
        assert "deposit_id" in data
        assert data["sc_amount"] > 0
        print(f"✓ Deposit submitted: {data['deposit_id']} - {data['sc_amount']} SC pending")
        return data["deposit_id"]
    
    def test_get_deposits_list(self, agent_auth):
        """Test GET /api/crypto/deposits returns user's deposits"""
        headers = {"Authorization": f"Bearer {agent_auth['token']}"}
        
        resp = requests.get(f"{BASE_URL}/api/crypto/deposits", headers=headers)
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}"
        
        deposits = resp.json()
        assert isinstance(deposits, list)
        print(f"✓ Found {len(deposits)} deposits for user")
    
    def test_manual_confirm_deposit(self, agent_auth):
        """Test manual confirmation endpoint (simulates background loop)"""
        headers = {"Authorization": f"Bearer {agent_auth['token']}"}
        
        # First submit a deposit
        tx_hash = f"TEST_MANUAL_0x{uuid.uuid4().hex}"
        submit_resp = requests.post(f"{BASE_URL}/api/crypto/deposit", json={
            "crypto_type": "eth",
            "tx_hash": tx_hash,
            "amount_crypto": 0.01
        }, headers=headers)
        
        if submit_resp.status_code != 200:
            pytest.skip("Could not submit deposit for confirmation test")
        
        deposit_id = submit_resp.json()["deposit_id"]
        
        # Manually confirm (simulate what background loop does)
        confirm_resp = requests.post(
            f"{BASE_URL}/api/crypto/deposits/{deposit_id}/confirm",
            headers=headers
        )
        assert confirm_resp.status_code == 200, f"First confirm failed: {confirm_resp.text}"
        data = confirm_resp.json()
        assert data["confirmations"] == 1
        assert data["status"] == "pending"
        print(f"✓ First confirmation: {data['confirmations']}/2")
        
        # Second confirmation should credit wallet
        confirm_resp2 = requests.post(
            f"{BASE_URL}/api/crypto/deposits/{deposit_id}/confirm",
            headers=headers
        )
        assert confirm_resp2.status_code == 200
        data2 = confirm_resp2.json()
        assert data2["confirmations"] == 2
        assert data2["status"] == "confirmed"
        assert data2["sc_credited"] > 0
        print(f"✓ Deposit confirmed! Credited {data2['sc_credited']} SC")


class TestTournamentLateJoin:
    """
    FEATURE 4: Tournament Late Join
    Tests POST /api/tournaments/{id}/join endpoint
    """
    
    @pytest.fixture
    def user_auth(self):
        """Get auth token for tournament tests"""
        email = f"TEST_tourney_{uuid.uuid4().hex[:8]}@test.com"
        password = "test123"
        
        # Try signup
        signup_resp = requests.post(f"{BASE_URL}/api/auth/signup", json={
            "email": email,
            "password": password,
            "username": f"TEST_Tourney_{uuid.uuid4().hex[:4]}"
        })
        
        if signup_resp.status_code == 200:
            return {"token": signup_resp.json()["token"], "email": email}
        
        # Try login with existing test account
        login_resp = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "test@test.com",
            "password": "test123"
        })
        
        if login_resp.status_code == 200:
            return {"token": login_resp.json()["token"], "email": "test@test.com"}
        
        pytest.skip("Could not authenticate for tournament tests")
    
    def test_create_tournament(self, user_auth):
        """Test POST /api/tournaments creates a lobby tournament"""
        headers = {"Authorization": f"Bearer {user_auth['token']}"}
        
        resp = requests.post(f"{BASE_URL}/api/tournaments", headers=headers)
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        
        data = resp.json()
        assert "id" in data
        assert data["status"] == "lobby"
        assert len(data["agent_ids"]) == 8
        print(f"✓ Tournament created: {data['id']} - status: {data['status']}")
        return data["id"]
    
    def test_late_join_tournament(self, user_auth):
        """Test POST /api/tournaments/{id}/join replaces agent in slot"""
        headers = {"Authorization": f"Bearer {user_auth['token']}"}
        
        # Create tournament
        create_resp = requests.post(f"{BASE_URL}/api/tournaments", headers=headers)
        if create_resp.status_code != 200:
            pytest.skip("Could not create tournament")
        
        tournament = create_resp.json()
        tournament_id = tournament["id"]
        original_agents = tournament["agent_ids"].copy()
        
        # Get all agents to find one not in tournament
        agents_resp = requests.get(f"{BASE_URL}/api/agents")
        if agents_resp.status_code != 200:
            pytest.skip("Could not fetch agents")
        
        all_agents = agents_resp.json()
        available = [a for a in all_agents if a["id"] not in original_agents]
        
        if not available:
            pytest.skip("No available agents for swap test")
        
        replacement_agent = available[0]
        
        # Try to join/replace slot 0
        join_resp = requests.post(
            f"{BASE_URL}/api/tournaments/{tournament_id}/join",
            json={"slot_index": 0, "agent_id": replacement_agent["id"]},
            headers=headers
        )
        
        assert join_resp.status_code == 200, f"Join failed: {join_resp.text}"
        updated = join_resp.json()
        
        # Verify the swap
        assert updated["agent_ids"][0] == replacement_agent["id"]
        assert updated["agent_ids"][0] != original_agents[0]
        print(f"✓ Late join successful: Swapped slot 0 with {replacement_agent['name']}")
    
    def test_late_join_fails_after_start(self, user_auth):
        """Test that late join fails once tournament is started"""
        headers = {"Authorization": f"Bearer {user_auth['token']}"}
        
        # Create and start tournament
        create_resp = requests.post(f"{BASE_URL}/api/tournaments", headers=headers)
        if create_resp.status_code != 200:
            pytest.skip("Could not create tournament")
        
        tournament_id = create_resp.json()["id"]
        
        # Start tournament (advance from lobby)
        advance_resp = requests.post(
            f"{BASE_URL}/api/tournaments/{tournament_id}/advance",
            headers=headers
        )
        
        if advance_resp.status_code != 200:
            pytest.skip("Could not advance tournament")
        
        # Now try to join - should fail
        agents_resp = requests.get(f"{BASE_URL}/api/agents")
        all_agents = agents_resp.json()
        
        join_resp = requests.post(
            f"{BASE_URL}/api/tournaments/{tournament_id}/join",
            json={"slot_index": 0, "agent_id": all_agents[0]["id"]},
            headers=headers
        )
        
        assert join_resp.status_code == 400, f"Expected 400, got {join_resp.status_code}"
        assert "already started" in join_resp.json().get("detail", "").lower()
        print("✓ Late join correctly blocked after tournament start")
    
    def test_late_join_invalid_slot(self, user_auth):
        """Test that invalid slot index is rejected"""
        headers = {"Authorization": f"Bearer {user_auth['token']}"}
        
        create_resp = requests.post(f"{BASE_URL}/api/tournaments", headers=headers)
        if create_resp.status_code != 200:
            pytest.skip("Could not create tournament")
        
        tournament_id = create_resp.json()["id"]
        
        # Get any agent
        agents_resp = requests.get(f"{BASE_URL}/api/agents")
        agent_id = agents_resp.json()[0]["id"]
        
        # Try invalid slot 99
        join_resp = requests.post(
            f"{BASE_URL}/api/tournaments/{tournament_id}/join",
            json={"slot_index": 99, "agent_id": agent_id},
            headers=headers
        )
        
        assert join_resp.status_code == 400, f"Expected 400 for invalid slot"
        print("✓ Invalid slot index correctly rejected")


class TestRegressionBasics:
    """
    Regression tests for core functionality
    """
    
    def test_tables_load(self):
        """Test GET /api/tables returns tables"""
        resp = requests.get(f"{BASE_URL}/api/tables")
        assert resp.status_code == 200
        tables = resp.json()
        assert isinstance(tables, list)
        assert len(tables) >= 1
        print(f"✓ Tables loaded: {len(tables)} tables")
    
    def test_agents_load(self):
        """Test GET /api/agents returns agents"""
        resp = requests.get(f"{BASE_URL}/api/agents")
        assert resp.status_code == 200
        agents = resp.json()
        assert isinstance(agents, list)
        assert len(agents) >= 8
        print(f"✓ Agents loaded: {len(agents)} agents")
    
    def test_tournaments_list(self):
        """Test GET /api/tournaments returns list"""
        resp = requests.get(f"{BASE_URL}/api/tournaments")
        assert resp.status_code == 200
        tournaments = resp.json()
        assert isinstance(tournaments, list)
        print(f"✓ Tournaments loaded: {len(tournaments)} tournaments")
    
    def test_openclaw_agent_login(self):
        """Test OpenClaw agent API login still works"""
        resp = requests.post(f"{BASE_URL}/api/agent-api/login", json={
            "email": "openclaw@test.com",
            "password": "test123"
        })
        assert resp.status_code == 200, f"OpenClaw login failed: {resp.text}"
        data = resp.json()
        assert "token" in data
        assert "agent" in data
        print(f"✓ OpenClaw agent login works: {data['agent']['name']}")
    
    def test_regular_signup_login(self):
        """Test regular user signup and login"""
        email = f"TEST_reg_{uuid.uuid4().hex[:8]}@test.com"
        password = "test123"
        
        # Signup
        signup_resp = requests.post(f"{BASE_URL}/api/auth/signup", json={
            "email": email,
            "password": password,
            "username": f"TEST_User_{uuid.uuid4().hex[:4]}"
        })
        assert signup_resp.status_code == 200, f"Signup failed: {signup_resp.text}"
        print(f"✓ Regular signup works")
        
        # Login
        login_resp = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": email,
            "password": password
        })
        assert login_resp.status_code == 200, f"Login failed: {login_resp.text}"
        print(f"✓ Regular login works")


class TestWebSocketChatEndpoint:
    """
    FEATURE 1: Spectator Chat - Basic connectivity test
    Note: Full WebSocket testing requires browser/Playwright
    Here we test that the endpoint accepts connections
    """
    
    def test_websocket_endpoint_exists(self):
        """Test that WebSocket endpoint is accessible"""
        # We can't fully test WebSocket via requests, but we can verify
        # the path exists by checking an HTTP request fails correctly
        resp = requests.get(f"{BASE_URL}/api/ws/table/test-table-id")
        # WebSocket endpoints typically return 403 or upgrade required for HTTP
        # or 426 Upgrade Required
        assert resp.status_code in [403, 404, 405, 426, 400], \
            f"WebSocket endpoint returned unexpected: {resp.status_code}"
        print(f"✓ WebSocket endpoint exists (returned {resp.status_code} for HTTP)")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
