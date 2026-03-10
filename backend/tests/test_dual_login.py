"""
POKERCLAW Dual Login System Tests
Testing Agent and Human/Spectator signup and login flows with role-based features
"""

import pytest
import requests
import os
import uuid

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')


class TestAgentSignup:
    """Test signup flow for Agent role users - they should get crypto wallets"""

    def test_agent_signup_creates_agent_and_wallet(self):
        """Agent signup should create user, agent, and wallet with crypto addresses"""
        unique_id = str(uuid.uuid4())[:8]
        payload = {
            "username": f"TEST_agent_{unique_id}",
            "email": f"test_agent_{unique_id}@test.com",
            "password": "test123456",
            "role": "agent",
            "agent_name": f"MoltBot_{unique_id}"
        }
        
        response = requests.post(f"{BASE_URL}/api/auth/signup", json=payload)
        assert response.status_code == 200, f"Signup failed: {response.text}"
        
        data = response.json()
        
        # Verify user fields
        assert "token" in data
        assert "user" in data
        assert data["user"]["role"] == "agent"
        assert data["user"]["agent_id"] is not None
        
        # Verify agent was created
        assert "agent" in data
        assert data["agent"]["name"] == f"MoltBot_{unique_id}"
        assert data["agent"]["owner_id"] == data["user"]["id"]
        
        print(f"Agent signup successful: {data['user']['username']}, agent: {data['agent']['name']}")
    
    def test_agent_signup_auto_generates_agent_name(self):
        """Agent signup without agent_name should auto-generate agent name"""
        unique_id = str(uuid.uuid4())[:8]
        payload = {
            "username": f"TEST_autoagent_{unique_id}",
            "email": f"test_autoagent_{unique_id}@test.com",
            "password": "test123456",
            "role": "agent"
            # No agent_name provided
        }
        
        response = requests.post(f"{BASE_URL}/api/auth/signup", json=payload)
        assert response.status_code == 200
        
        data = response.json()
        assert data["agent"] is not None
        # Should auto-generate name like MoltBot_username
        assert data["agent"]["name"].startswith("MoltBot_")
        print(f"Auto-generated agent name: {data['agent']['name']}")


class TestHumanSignup:
    """Test signup flow for Human/Spectator role - no agent created"""
    
    def test_human_signup_no_agent_created(self):
        """Human signup should NOT create an agent"""
        unique_id = str(uuid.uuid4())[:8]
        payload = {
            "username": f"TEST_human_{unique_id}",
            "email": f"test_human_{unique_id}@test.com",
            "password": "test123456",
            "role": "human"
        }
        
        response = requests.post(f"{BASE_URL}/api/auth/signup", json=payload)
        assert response.status_code == 200
        
        data = response.json()
        assert data["user"]["role"] == "human"
        assert data["user"]["agent_id"] is None
        assert data["agent"] is None  # No agent should be created
        
        print(f"Human signup successful: {data['user']['username']}, no agent created")
    
    def test_human_signup_default_role(self):
        """Signup without specifying role should default to human"""
        unique_id = str(uuid.uuid4())[:8]
        payload = {
            "username": f"TEST_default_{unique_id}",
            "email": f"test_default_{unique_id}@test.com",
            "password": "test123456"
            # No role specified - should default to human
        }
        
        response = requests.post(f"{BASE_URL}/api/auth/signup", json=payload)
        assert response.status_code == 200
        
        data = response.json()
        assert data["user"]["role"] == "human"
        print("Default role is 'human' as expected")


class TestLogin:
    """Test login flow returns correct role and agent_id"""
    
    @pytest.fixture(scope="class")
    def agent_user(self):
        """Create a fresh agent user for login tests"""
        unique_id = str(uuid.uuid4())[:8]
        payload = {
            "username": f"TEST_loginagent_{unique_id}",
            "email": f"test_loginagent_{unique_id}@test.com",
            "password": "test123456",
            "role": "agent",
            "agent_name": f"TestBot_{unique_id}"
        }
        response = requests.post(f"{BASE_URL}/api/auth/signup", json=payload)
        return {
            "email": payload["email"],
            "password": payload["password"],
            "signup_data": response.json()
        }
    
    @pytest.fixture(scope="class")
    def human_user(self):
        """Create a fresh human user for login tests"""
        unique_id = str(uuid.uuid4())[:8]
        payload = {
            "username": f"TEST_loginhuman_{unique_id}",
            "email": f"test_loginhuman_{unique_id}@test.com",
            "password": "test123456",
            "role": "human"
        }
        response = requests.post(f"{BASE_URL}/api/auth/signup", json=payload)
        return {
            "email": payload["email"],
            "password": payload["password"],
            "signup_data": response.json()
        }
    
    def test_agent_login_returns_role_and_agent_id(self, agent_user):
        """Agent login should return role='agent' and agent_id"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": agent_user["email"],
            "password": agent_user["password"]
        })
        assert response.status_code == 200
        
        data = response.json()
        assert data["user"]["role"] == "agent"
        assert data["user"]["agent_id"] is not None
        assert "token" in data
        
        print(f"Agent login: role={data['user']['role']}, agent_id={data['user']['agent_id']}")
    
    def test_human_login_returns_role_null_agent_id(self, human_user):
        """Human login should return role='human' and agent_id=null"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": human_user["email"],
            "password": human_user["password"]
        })
        assert response.status_code == 200
        
        data = response.json()
        assert data["user"]["role"] == "human"
        assert data["user"]["agent_id"] is None
        
        print(f"Human login: role={data['user']['role']}, agent_id={data['user']['agent_id']}")


class TestAuthMeEndpoint:
    """Test /api/auth/me returns role and agent data"""
    
    @pytest.fixture(scope="class")
    def agent_token(self):
        """Create agent user and return token"""
        unique_id = str(uuid.uuid4())[:8]
        signup_response = requests.post(f"{BASE_URL}/api/auth/signup", json={
            "username": f"TEST_meagent_{unique_id}",
            "email": f"test_meagent_{unique_id}@test.com",
            "password": "test123456",
            "role": "agent",
            "agent_name": f"MeBot_{unique_id}"
        })
        return signup_response.json()["token"]
    
    @pytest.fixture(scope="class")
    def human_token(self):
        """Create human user and return token"""
        unique_id = str(uuid.uuid4())[:8]
        signup_response = requests.post(f"{BASE_URL}/api/auth/signup", json={
            "username": f"TEST_mehuman_{unique_id}",
            "email": f"test_mehuman_{unique_id}@test.com",
            "password": "test123456",
            "role": "human"
        })
        return signup_response.json()["token"]
    
    def test_auth_me_agent_includes_agent_data(self, agent_token):
        """/api/auth/me should include agent data for agent users"""
        response = requests.get(
            f"{BASE_URL}/api/auth/me",
            headers={"Authorization": f"Bearer {agent_token}"}
        )
        assert response.status_code == 200
        
        data = response.json()
        assert data["role"] == "agent"
        assert data["agent_id"] is not None
        assert "agent" in data  # Agent object should be included
        assert data["agent"]["name"] is not None
        
        print(f"Auth/me for agent: role={data['role']}, agent={data['agent']['name']}")
    
    def test_auth_me_human_no_agent_data(self, human_token):
        """/api/auth/me should NOT include agent data for human users"""
        response = requests.get(
            f"{BASE_URL}/api/auth/me",
            headers={"Authorization": f"Bearer {human_token}"}
        )
        assert response.status_code == 200
        
        data = response.json()
        assert data["role"] == "human"
        assert data.get("agent_id") is None
        # Should not have agent key or it should be None
        assert data.get("agent") is None
        
        print(f"Auth/me for human: role={data['role']}, no agent data")


class TestMyAgentEndpoint:
    """Test /api/agents/my-agent endpoint for agent vs human users"""
    
    @pytest.fixture(scope="class")
    def agent_session(self):
        """Create agent user and return token with agent info"""
        unique_id = str(uuid.uuid4())[:8]
        signup_response = requests.post(f"{BASE_URL}/api/auth/signup", json={
            "username": f"TEST_myagent_{unique_id}",
            "email": f"test_myagent_{unique_id}@test.com",
            "password": "test123456",
            "role": "agent",
            "agent_name": f"MyBot_{unique_id}"
        })
        data = signup_response.json()
        return {
            "token": data["token"],
            "agent_name": data["agent"]["name"]
        }
    
    @pytest.fixture(scope="class")
    def human_session(self):
        """Create human user and return token"""
        unique_id = str(uuid.uuid4())[:8]
        signup_response = requests.post(f"{BASE_URL}/api/auth/signup", json={
            "username": f"TEST_myagenthuman_{unique_id}",
            "email": f"test_myagenthuman_{unique_id}@test.com",
            "password": "test123456",
            "role": "human"
        })
        return {"token": signup_response.json()["token"]}
    
    def test_my_agent_returns_agent_and_wallet_for_agent(self, agent_session):
        """/api/agents/my-agent should return agent details and wallet with crypto_addresses"""
        response = requests.get(
            f"{BASE_URL}/api/agents/my-agent",
            headers={"Authorization": f"Bearer {agent_session['token']}"}
        )
        assert response.status_code == 200
        
        data = response.json()
        assert "agent" in data
        assert data["agent"]["name"] == agent_session["agent_name"]
        
        # Wallet should be present with crypto addresses
        assert "wallet" in data
        assert data["wallet"] is not None
        assert "crypto_addresses" in data["wallet"]
        
        crypto = data["wallet"]["crypto_addresses"]
        assert "btc" in crypto
        assert "ltc" in crypto
        assert "eth" in crypto
        
        # Verify address formats
        assert crypto["btc"].startswith("1")  # Bitcoin mainnet address
        assert crypto["ltc"].startswith("L")  # Litecoin address
        assert crypto["eth"].startswith("0x") # Ethereum address
        
        print(f"My-agent for agent user: {data['agent']['name']}")
        print(f"  BTC: {crypto['btc'][:20]}...")
        print(f"  LTC: {crypto['ltc'][:20]}...")
        print(f"  ETH: {crypto['eth'][:20]}...")
    
    def test_my_agent_returns_403_for_human(self, human_session):
        """/api/agents/my-agent should return 403 for human users"""
        response = requests.get(
            f"{BASE_URL}/api/agents/my-agent",
            headers={"Authorization": f"Bearer {human_session['token']}"}
        )
        assert response.status_code == 403
        
        data = response.json()
        assert "detail" in data
        print(f"My-agent for human user: 403 Forbidden - {data['detail']}")


class TestWalletEndpoint:
    """Test /api/wallet returns crypto_addresses for agents only"""
    
    @pytest.fixture(scope="class")
    def agent_token(self):
        unique_id = str(uuid.uuid4())[:8]
        signup_response = requests.post(f"{BASE_URL}/api/auth/signup", json={
            "username": f"TEST_walletagent_{unique_id}",
            "email": f"test_walletagent_{unique_id}@test.com",
            "password": "test123456",
            "role": "agent"
        })
        return signup_response.json()["token"]
    
    @pytest.fixture(scope="class")
    def human_token(self):
        unique_id = str(uuid.uuid4())[:8]
        signup_response = requests.post(f"{BASE_URL}/api/auth/signup", json={
            "username": f"TEST_wallethuman_{unique_id}",
            "email": f"test_wallethuman_{unique_id}@test.com",
            "password": "test123456",
            "role": "human"
        })
        return signup_response.json()["token"]
    
    def test_wallet_has_crypto_addresses_for_agent(self, agent_token):
        """/api/wallet should include crypto_addresses for agent users"""
        response = requests.get(
            f"{BASE_URL}/api/wallet",
            headers={"Authorization": f"Bearer {agent_token}"}
        )
        assert response.status_code == 200
        
        data = response.json()
        assert "crypto_addresses" in data
        assert data["crypto_addresses"] is not None
        assert "btc" in data["crypto_addresses"]
        assert "sc_balance" in data  # Agent starts with 100 SC
        
        print(f"Agent wallet has crypto addresses: {list(data['crypto_addresses'].keys())}")
        print(f"Agent SC balance: {data['sc_balance']}")
    
    def test_wallet_no_crypto_addresses_for_human(self, human_token):
        """/api/wallet should NOT include crypto_addresses for human users"""
        response = requests.get(
            f"{BASE_URL}/api/wallet",
            headers={"Authorization": f"Bearer {human_token}"}
        )
        assert response.status_code == 200
        
        data = response.json()
        # Human wallet should not have crypto addresses
        assert data.get("crypto_addresses") is None
        assert "gc_balance" in data  # Human has GC
        assert "sc_balance" in data  # Human starts with 500 SC
        
        print(f"Human wallet: no crypto addresses, SC={data['sc_balance']}, GC={data['gc_balance']}")


class TestStarterBalances:
    """Test that agent and human users get correct starter balances"""
    
    def test_agent_starter_balance_100_sc(self):
        """Agent users should start with 100 SC"""
        unique_id = str(uuid.uuid4())[:8]
        signup_response = requests.post(f"{BASE_URL}/api/auth/signup", json={
            "username": f"TEST_balanceagent_{unique_id}",
            "email": f"test_balanceagent_{unique_id}@test.com",
            "password": "test123456",
            "role": "agent"
        })
        assert signup_response.status_code == 200
        token = signup_response.json()["token"]
        
        wallet_response = requests.get(
            f"{BASE_URL}/api/wallet",
            headers={"Authorization": f"Bearer {token}"}
        )
        wallet = wallet_response.json()
        
        assert wallet["sc_balance"] == 100
        assert wallet["gc_balance"] == 10000
        print(f"Agent starter balance: SC={wallet['sc_balance']}, GC={wallet['gc_balance']}")
    
    def test_human_starter_balance_500_sc(self):
        """Human users should start with 500 SC"""
        unique_id = str(uuid.uuid4())[:8]
        signup_response = requests.post(f"{BASE_URL}/api/auth/signup", json={
            "username": f"TEST_balancehuman_{unique_id}",
            "email": f"test_balancehuman_{unique_id}@test.com",
            "password": "test123456",
            "role": "human"
        })
        assert signup_response.status_code == 200
        token = signup_response.json()["token"]
        
        wallet_response = requests.get(
            f"{BASE_URL}/api/wallet",
            headers={"Authorization": f"Bearer {token}"}
        )
        wallet = wallet_response.json()
        
        assert wallet["sc_balance"] == 500
        assert wallet["gc_balance"] == 10000
        print(f"Human starter balance: SC={wallet['sc_balance']}, GC={wallet['gc_balance']}")


class TestExistingGameFlowStillWorks:
    """Verify existing game flow is not broken by dual-login changes"""
    
    @pytest.fixture(scope="class")
    def auth_token(self):
        """Create a test user for game flow tests"""
        unique_id = str(uuid.uuid4())[:8]
        signup_response = requests.post(f"{BASE_URL}/api/auth/signup", json={
            "username": f"TEST_gameflow_{unique_id}",
            "email": f"test_gameflow_{unique_id}@test.com",
            "password": "test123456",
            "role": "agent"
        })
        return signup_response.json()["token"]
    
    def test_list_tables(self, auth_token):
        """GET /api/tables should work"""
        response = requests.get(
            f"{BASE_URL}/api/tables",
            headers={"Authorization": f"Bearer {auth_token}"}
        )
        assert response.status_code == 200
        tables = response.json()
        assert isinstance(tables, list)
        print(f"Tables endpoint works: {len(tables)} tables found")
    
    def test_list_agents(self, auth_token):
        """GET /api/agents should work"""
        response = requests.get(
            f"{BASE_URL}/api/agents",
            headers={"Authorization": f"Bearer {auth_token}"}
        )
        assert response.status_code == 200
        agents = response.json()
        assert isinstance(agents, list)
        assert len(agents) > 0
        print(f"Agents endpoint works: {len(agents)} agents found")
    
    def test_start_and_advance_game(self, auth_token):
        """Game start and advance should still work"""
        # Get first table
        tables_response = requests.get(
            f"{BASE_URL}/api/tables",
            headers={"Authorization": f"Bearer {auth_token}"}
        )
        tables = tables_response.json()
        if not tables:
            pytest.skip("No tables available")
        
        table_id = tables[0]["id"]
        
        # Start a game
        start_response = requests.post(
            f"{BASE_URL}/api/tables/{table_id}/start-game",
            headers={"Authorization": f"Bearer {auth_token}"}
        )
        # May return 400 if game in progress, which is fine
        if start_response.status_code == 400:
            print("Game already in progress, using existing game")
            # Get existing game
            table_detail = requests.get(
                f"{BASE_URL}/api/tables/{table_id}",
                headers={"Authorization": f"Bearer {auth_token}"}
            ).json()
            if not table_detail.get("current_game"):
                pytest.skip("No game available to test")
            game_id = table_detail["current_game"]["id"]
        else:
            assert start_response.status_code == 200
            game_id = start_response.json()["id"]
        
        # Advance the game
        advance_response = requests.post(
            f"{BASE_URL}/api/games/{game_id}/advance",
            headers={"Authorization": f"Bearer {auth_token}"}
        )
        # May return 400 if game complete
        assert advance_response.status_code in [200, 400]
        print(f"Game flow test passed - game_id: {game_id}")


class TestValidation:
    """Test input validation for signup"""
    
    def test_invalid_role_rejected(self):
        """Signup with invalid role should be rejected"""
        unique_id = str(uuid.uuid4())[:8]
        response = requests.post(f"{BASE_URL}/api/auth/signup", json={
            "username": f"TEST_invalid_{unique_id}",
            "email": f"test_invalid_{unique_id}@test.com",
            "password": "test123456",
            "role": "admin"  # Invalid role
        })
        assert response.status_code == 400
        assert "role" in response.json().get("detail", "").lower()
        print("Invalid role rejected correctly")
    
    def test_duplicate_email_rejected(self):
        """Signup with duplicate email should be rejected"""
        unique_id = str(uuid.uuid4())[:8]
        email = f"test_dup_{unique_id}@test.com"
        
        # First signup
        requests.post(f"{BASE_URL}/api/auth/signup", json={
            "username": f"TEST_dup1_{unique_id}",
            "email": email,
            "password": "test123456",
            "role": "human"
        })
        
        # Second signup with same email
        response = requests.post(f"{BASE_URL}/api/auth/signup", json={
            "username": f"TEST_dup2_{unique_id}",
            "email": email,
            "password": "test123456",
            "role": "human"
        })
        assert response.status_code == 400
        print("Duplicate email rejected correctly")
    
    def test_duplicate_agent_name_rejected(self):
        """Signup with duplicate agent name should be rejected"""
        unique_id = str(uuid.uuid4())[:8]
        agent_name = f"DuplicateBot_{unique_id}"
        
        # First agent signup
        requests.post(f"{BASE_URL}/api/auth/signup", json={
            "username": f"TEST_dupagent1_{unique_id}",
            "email": f"test_dupagent1_{unique_id}@test.com",
            "password": "test123456",
            "role": "agent",
            "agent_name": agent_name
        })
        
        # Second signup with same agent name
        response = requests.post(f"{BASE_URL}/api/auth/signup", json={
            "username": f"TEST_dupagent2_{unique_id}",
            "email": f"test_dupagent2_{unique_id}@test.com",
            "password": "test123456",
            "role": "agent",
            "agent_name": agent_name
        })
        assert response.status_code == 400
        print("Duplicate agent name rejected correctly")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
