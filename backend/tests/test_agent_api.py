"""
Agent API Tests - OpenClaw Skill Integration Testing
Tests all new Agent API endpoints for external OpenClaw agents to play POKERCLAW autonomously.

Endpoints tested:
- POST /api/agent-api/register - Register new agent
- POST /api/agent-api/login - Login and get JWT token
- GET /api/agent-api/me - Get agent info and wallet
- POST /api/agent-api/tables/{id}/join - Seat agent at table
- POST /api/agent-api/tables/{id}/leave - Remove agent from table
- GET /api/agent-api/tables - List tables with game info
- POST /api/agent-api/game/{TABLE_ID}/start - Start a new game
- GET /api/agent-api/game/{GAME_ID}/state - Get game state with hole cards
- POST /api/agent-api/game/{GAME_ID}/action - Submit fold/call/raise
- POST /api/agent-api/game/{GAME_ID}/advance-others - Auto-advance house bots
- GET /api/agent-api/wallet - Get wallet balance

FULL GAME LOOP: Register -> Login -> Join table -> Start game -> Advance others -> Submit action -> Repeat
"""
import pytest
import requests
import os
import uuid

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')


class TestAgentAPIAuth:
    """Test Agent API authentication endpoints (register, login)"""
    
    def test_agent_register_success(self):
        """Register a new OpenClaw agent - should create user, agent, and wallet"""
        unique_id = str(uuid.uuid4())[:8]
        payload = {
            "username": f"TEST_openclaw_{unique_id}",
            "email": f"TEST_openclaw_{unique_id}@test.com",
            "password": "testpass123",
            "agent_name": f"TEST_MoltBot_{unique_id}"
        }
        response = requests.post(f"{BASE_URL}/api/agent-api/register", json=payload)
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        
        # Verify token returned
        assert "token" in data, "Token should be returned"
        assert isinstance(data["token"], str) and len(data["token"]) > 0
        
        # Verify agent created
        assert "agent" in data, "Agent should be returned"
        assert data["agent"]["name"] == payload["agent_name"]
        assert data["agent"]["is_external"] == True
        assert data["agent"]["is_house"] == False
        assert "id" in data["agent"]
        
        # Verify message
        assert "message" in data
        
    def test_agent_register_duplicate_email(self):
        """Register with existing email should fail"""
        # First registration
        unique_id = str(uuid.uuid4())[:8]
        payload = {
            "username": f"TEST_dup_{unique_id}",
            "email": f"TEST_dup_{unique_id}@test.com",
            "password": "testpass123"
        }
        requests.post(f"{BASE_URL}/api/agent-api/register", json=payload)
        
        # Duplicate attempt
        payload2 = {
            "username": f"TEST_dup2_{unique_id}",
            "email": f"TEST_dup_{unique_id}@test.com",  # Same email
            "password": "testpass123"
        }
        response = requests.post(f"{BASE_URL}/api/agent-api/register", json=payload2)
        
        assert response.status_code == 400
        assert "already registered" in response.json().get("detail", "").lower()
        
    def test_agent_login_success(self):
        """Login with valid credentials should return token and agent"""
        # Register first
        unique_id = str(uuid.uuid4())[:8]
        reg_payload = {
            "username": f"TEST_login_{unique_id}",
            "email": f"TEST_login_{unique_id}@test.com",
            "password": "testpass123",
            "agent_name": f"TEST_LoginBot_{unique_id}"
        }
        reg_response = requests.post(f"{BASE_URL}/api/agent-api/register", json=reg_payload)
        assert reg_response.status_code == 200
        
        # Now login
        login_payload = {
            "email": f"TEST_login_{unique_id}@test.com",
            "password": "testpass123"
        }
        response = requests.post(f"{BASE_URL}/api/agent-api/login", json=login_payload)
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        
        assert "token" in data
        assert "agent" in data
        assert "user_id" in data
        assert data["agent"]["name"] == reg_payload["agent_name"]
        
    def test_agent_login_invalid_credentials(self):
        """Login with wrong password should fail with 401"""
        payload = {
            "email": "nonexistent@test.com",
            "password": "wrongpassword"
        }
        response = requests.post(f"{BASE_URL}/api/agent-api/login", json=payload)
        
        assert response.status_code == 401
        assert "invalid" in response.json().get("detail", "").lower()


class TestAgentAPIInfo:
    """Test Agent API info endpoints (me, wallet)"""
    
    @pytest.fixture
    def agent_token(self):
        """Create an agent and return its token"""
        unique_id = str(uuid.uuid4())[:8]
        payload = {
            "username": f"TEST_info_{unique_id}",
            "email": f"TEST_info_{unique_id}@test.com",
            "password": "testpass123",
            "agent_name": f"TEST_InfoBot_{unique_id}"
        }
        response = requests.post(f"{BASE_URL}/api/agent-api/register", json=payload)
        assert response.status_code == 200
        return response.json()["token"]
    
    def test_get_me(self, agent_token):
        """GET /api/agent-api/me should return agent info and wallet"""
        headers = {"Authorization": f"Bearer {agent_token}"}
        response = requests.get(f"{BASE_URL}/api/agent-api/me", headers=headers)
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        
        assert "agent" in data
        assert "wallet" in data
        assert "user_id" in data
        assert "sc_balance" in data["wallet"]
        
    def test_get_me_unauthorized(self):
        """GET /api/agent-api/me without token should fail"""
        response = requests.get(f"{BASE_URL}/api/agent-api/me")
        assert response.status_code == 401
        
    def test_get_wallet(self, agent_token):
        """GET /api/agent-api/wallet should return balance"""
        headers = {"Authorization": f"Bearer {agent_token}"}
        response = requests.get(f"{BASE_URL}/api/agent-api/wallet", headers=headers)
        
        assert response.status_code == 200
        data = response.json()
        
        assert "sc_balance" in data
        assert "gc_balance" in data
        assert isinstance(data["sc_balance"], int)


class TestAgentAPITables:
    """Test Agent API table endpoints (list, join, leave)"""
    
    @pytest.fixture
    def human_token_for_cleanup(self):
        """Create a human user for game cleanup"""
        unique_id = str(uuid.uuid4())[:8]
        payload = {
            "username": f"TEST_tblclean_{unique_id}",
            "email": f"TEST_tblclean_{unique_id}@test.com",
            "password": "testpass123",
            "role": "human"
        }
        response = requests.post(f"{BASE_URL}/api/auth/signup", json=payload)
        return response.json()["token"]
    
    @pytest.fixture
    def agent_token(self):
        """Create an agent and return its token"""
        unique_id = str(uuid.uuid4())[:8]
        payload = {
            "username": f"TEST_table_{unique_id}",
            "email": f"TEST_table_{unique_id}@test.com",
            "password": "testpass123",
            "agent_name": f"TEST_TableBot_{unique_id}"
        }
        response = requests.post(f"{BASE_URL}/api/agent-api/register", json=payload)
        assert response.status_code == 200
        return response.json()["token"]
    
    def test_list_tables(self, agent_token):
        """GET /api/agent-api/tables should return tables with your_agent_seated flag"""
        headers = {"Authorization": f"Bearer {agent_token}"}
        response = requests.get(f"{BASE_URL}/api/agent-api/tables", headers=headers)
        
        assert response.status_code == 200
        data = response.json()
        
        assert isinstance(data, list)
        assert len(data) > 0, "Should have at least one table"
        
        table = data[0]
        assert "id" in table
        assert "name" in table
        assert "min_bet" in table
        assert "max_bet" in table
        assert "your_agent_seated" in table
        assert isinstance(table["your_agent_seated"], bool)
        assert table["your_agent_seated"] == False  # Not seated yet
        
    def test_join_table(self, agent_token, human_token_for_cleanup):
        """POST /api/agent-api/tables/{id}/join should seat agent at table"""
        headers = {"Authorization": f"Bearer {agent_token}"}
        
        # Get tables (public endpoint)
        tables_response = requests.get(f"{BASE_URL}/api/tables")
        tables = tables_response.json()
        
        # Find a table and complete any existing game
        table_id = None
        for table in tables:
            complete_existing_game_if_needed(table, human_token_for_cleanup)
            
            # Refresh table
            table_refresh = requests.get(f"{BASE_URL}/api/tables/{table['id']}")
            table = table_refresh.json()
            
            # Try to join
            response = requests.post(f"{BASE_URL}/api/agent-api/tables/{table['id']}/join", headers=headers)
            if response.status_code == 200:
                table_id = table['id']
                break
                
        if not table_id:
            pytest.skip("All tables have active games - cannot test join")
            
        data = response.json()
        assert "message" in data
        assert "seated" in data["message"].lower() or "already" in data["message"].lower()
        
        # Verify your_agent_seated is now True
        tables_response2 = requests.get(f"{BASE_URL}/api/agent-api/tables", headers=headers)
        updated_table = next(t for t in tables_response2.json() if t["id"] == table_id)
        assert updated_table["your_agent_seated"] == True
        
    def test_leave_table(self, agent_token, human_token_for_cleanup):
        """POST /api/agent-api/tables/{id}/leave should remove agent from table"""
        headers = {"Authorization": f"Bearer {agent_token}"}
        
        # Get and join a table first
        tables_response = requests.get(f"{BASE_URL}/api/tables")
        tables = tables_response.json()
        
        # Find a table and join
        table_id = None
        for table in tables:
            complete_existing_game_if_needed(table, human_token_for_cleanup)
            
            # Refresh and try to join
            table_refresh = requests.get(f"{BASE_URL}/api/tables/{table['id']}")
            table = table_refresh.json()
            
            join_resp = requests.post(f"{BASE_URL}/api/agent-api/tables/{table['id']}/join", headers=headers)
            if join_resp.status_code == 200:
                table_id = table['id']
                break
                
        if not table_id:
            pytest.skip("All tables have active games")
        
        # Leave the table
        response = requests.post(f"{BASE_URL}/api/agent-api/tables/{table_id}/leave", headers=headers)
        
        assert response.status_code == 200
        data = response.json()
        assert "message" in data
        
        # Verify your_agent_seated is now False
        tables_response2 = requests.get(f"{BASE_URL}/api/agent-api/tables", headers=headers)
        updated_table = next(t for t in tables_response2.json() if t["id"] == table_id)
        assert updated_table["your_agent_seated"] == False


def complete_existing_game_if_needed(table, human_token):
    """Helper to complete an existing game on a table using regular user advance"""
    headers = {"Authorization": f"Bearer {human_token}"}
    
    if table.get("current_game") and table["current_game"].get("phase") not in ("complete", None):
        game_id = table["current_game"]["id"]
        # Advance game to completion
        max_advances = 100
        for _ in range(max_advances):
            adv = requests.post(f"{BASE_URL}/api/games/{game_id}/advance", headers=headers)
            if adv.status_code != 200:
                break
            game = adv.json()
            if game.get("phase") == "complete":
                break
        # Give a moment for table status to update
        import time
        time.sleep(0.5)


class TestAgentAPIGameLoop:
    """Test full game loop: Start -> Advance -> State -> Action -> Complete"""
    
    @pytest.fixture
    def human_token_for_cleanup(self):
        """Create a human user for game cleanup"""
        unique_id = str(uuid.uuid4())[:8]
        payload = {
            "username": f"TEST_cleanup_{unique_id}",
            "email": f"TEST_cleanup_{unique_id}@test.com",
            "password": "testpass123",
            "role": "human"
        }
        response = requests.post(f"{BASE_URL}/api/auth/signup", json=payload)
        return response.json()["token"]
    
    @pytest.fixture
    def agent_with_table(self, human_token_for_cleanup):
        """Create an agent, join a table, return token and table_id"""
        unique_id = str(uuid.uuid4())[:8]
        payload = {
            "username": f"TEST_game_{unique_id}",
            "email": f"TEST_game_{unique_id}@test.com",
            "password": "testpass123",
            "agent_name": f"TEST_GameBot_{unique_id}"
        }
        response = requests.post(f"{BASE_URL}/api/agent-api/register", json=payload)
        assert response.status_code == 200
        token = response.json()["token"]
        agent_id = response.json()["agent"]["id"]
        
        headers = {"Authorization": f"Bearer {token}"}
        
        # Get tables
        tables_response = requests.get(f"{BASE_URL}/api/tables")
        tables = tables_response.json()
        
        # Find a table to join - complete existing game if needed
        table_id = None
        for table in tables:
            # Try to complete any existing game
            complete_existing_game_if_needed(table, human_token_for_cleanup)
            
            # Refresh table info
            table_refresh = requests.get(f"{BASE_URL}/api/tables/{table['id']}")
            table = table_refresh.json()
            
            # Try to join
            join_response = requests.post(f"{BASE_URL}/api/agent-api/tables/{table['id']}/join", headers=headers)
            if join_response.status_code == 200:
                table_id = table['id']
                break
                
        if not table_id:
            pytest.skip("Could not join any table - all have active games")
        
        return {"token": token, "table_id": table_id, "agent_id": agent_id}
    
    def test_start_game(self, agent_with_table):
        """POST /api/agent-api/game/{TABLE_ID}/start should create and start game"""
        token = agent_with_table["token"]
        table_id = agent_with_table["table_id"]
        agent_id = agent_with_table["agent_id"]
        headers = {"Authorization": f"Bearer {token}"}
        
        response = requests.post(f"{BASE_URL}/api/agent-api/game/{table_id}/start", headers=headers)
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        
        assert "game_id" in data
        assert "table" in data
        assert "game" in data
        
        game = data["game"]
        assert "players" in game
        assert "phase" in game
        assert "pot" in game
        assert "community_cards" in game
        
        # Verify our agent's hole cards are visible
        our_player = next((p for p in game["players"] if p["agent_id"] == agent_id), None)
        assert our_player is not None, "Our agent should be in the game"
        assert our_player["hole_cards"] != [None, None], "Our hole cards should be visible"
        
    def test_game_state(self, agent_with_table):
        """GET /api/agent-api/game/{GAME_ID}/state should show our cards, hide others"""
        token = agent_with_table["token"]
        table_id = agent_with_table["table_id"]
        agent_id = agent_with_table["agent_id"]
        headers = {"Authorization": f"Bearer {token}"}
        
        # Start a game
        start_response = requests.post(f"{BASE_URL}/api/agent-api/game/{table_id}/start", headers=headers)
        game_id = start_response.json()["game_id"]
        
        # Get state
        response = requests.get(f"{BASE_URL}/api/agent-api/game/{game_id}/state", headers=headers)
        
        assert response.status_code == 200
        data = response.json()
        
        # Should have hand strength hints
        assert "your_hand_strength" in data
        assert "your_hole_cards" in data
        assert "is_your_turn" in data
        assert "round_bet" in data
        assert "your_chips" in data
        
        # Our hole cards should be visible in your_hole_cards
        if data["your_hole_cards"]:
            assert data["your_hole_cards"][0] is not None
            
        # Others' cards should be hidden (unless showdown/complete)
        if data.get("phase") not in ("showdown", "complete"):
            for player in data["players"]:
                if player["agent_id"] != agent_id:
                    assert player["hole_cards"] == [None, None], "Other players' cards should be hidden"
                    
    def test_advance_others(self, agent_with_table):
        """POST /api/agent-api/game/{GAME_ID}/advance-others should auto-play house bots"""
        token = agent_with_table["token"]
        table_id = agent_with_table["table_id"]
        headers = {"Authorization": f"Bearer {token}"}
        
        # Start a game
        start_response = requests.post(f"{BASE_URL}/api/agent-api/game/{table_id}/start", headers=headers)
        game_id = start_response.json()["game_id"]
        
        # Advance others
        response = requests.post(f"{BASE_URL}/api/agent-api/game/{game_id}/advance-others", headers=headers)
        
        assert response.status_code == 200
        data = response.json()
        
        assert "advances" in data
        assert "game" in data
        assert isinstance(data["advances"], int)
        
        # After advancing, it should either be our turn or game complete
        game = data["game"]
        assert game.get("is_your_turn") == True or game.get("phase") == "complete"
        
    def test_submit_action_call(self, agent_with_table):
        """POST /api/agent-api/game/{GAME_ID}/action with 'call' should work"""
        token = agent_with_table["token"]
        table_id = agent_with_table["table_id"]
        agent_id = agent_with_table["agent_id"]
        headers = {"Authorization": f"Bearer {token}"}
        
        # Start a game
        start_response = requests.post(f"{BASE_URL}/api/agent-api/game/{table_id}/start", headers=headers)
        game_id = start_response.json()["game_id"]
        
        # Advance until our turn
        adv_response = requests.post(f"{BASE_URL}/api/agent-api/game/{game_id}/advance-others", headers=headers)
        game_state = adv_response.json()["game"]
        
        if game_state.get("phase") == "complete":
            pytest.skip("Game completed before our turn")
            
        if not game_state.get("is_your_turn"):
            pytest.skip("Not our turn after advancing")
            
        # Submit call action
        action_payload = {"action": "call", "amount": 0}
        response = requests.post(f"{BASE_URL}/api/agent-api/game/{game_id}/action", 
                                json=action_payload, headers=headers)
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        
        assert data["action_applied"] == "call"
        assert "game" in data
        
    def test_submit_action_raise(self, agent_with_table):
        """POST /api/agent-api/game/{GAME_ID}/action with 'raise' should work"""
        token = agent_with_table["token"]
        table_id = agent_with_table["table_id"]
        headers = {"Authorization": f"Bearer {token}"}
        
        # Start a game
        start_response = requests.post(f"{BASE_URL}/api/agent-api/game/{table_id}/start", headers=headers)
        game_id = start_response.json()["game_id"]
        
        # Advance until our turn
        adv_response = requests.post(f"{BASE_URL}/api/agent-api/game/{game_id}/advance-others", headers=headers)
        game_state = adv_response.json()["game"]
        
        if game_state.get("phase") == "complete":
            pytest.skip("Game completed before our turn")
            
        if not game_state.get("is_your_turn"):
            pytest.skip("Not our turn after advancing")
            
        # Submit raise action
        action_payload = {"action": "raise", "amount": 50}
        response = requests.post(f"{BASE_URL}/api/agent-api/game/{game_id}/action", 
                                json=action_payload, headers=headers)
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        
        assert data["action_applied"] == "raise"
        
    def test_submit_action_fold(self, agent_with_table):
        """POST /api/agent-api/game/{GAME_ID}/action with 'fold' should work"""
        token = agent_with_table["token"]
        table_id = agent_with_table["table_id"]
        headers = {"Authorization": f"Bearer {token}"}
        
        # Start a game
        start_response = requests.post(f"{BASE_URL}/api/agent-api/game/{table_id}/start", headers=headers)
        game_id = start_response.json()["game_id"]
        
        # Advance until our turn
        adv_response = requests.post(f"{BASE_URL}/api/agent-api/game/{game_id}/advance-others", headers=headers)
        game_state = adv_response.json()["game"]
        
        if game_state.get("phase") == "complete":
            pytest.skip("Game completed before our turn")
            
        if not game_state.get("is_your_turn"):
            pytest.skip("Not our turn after advancing")
            
        # Submit fold action
        action_payload = {"action": "fold", "amount": 0}
        response = requests.post(f"{BASE_URL}/api/agent-api/game/{game_id}/action", 
                                json=action_payload, headers=headers)
        
        assert response.status_code == 200
        data = response.json()
        
        assert data["action_applied"] == "fold"
        
    def test_action_not_your_turn(self, agent_with_table):
        """Submitting action when not your turn should return 400"""
        token = agent_with_table["token"]
        table_id = agent_with_table["table_id"]
        headers = {"Authorization": f"Bearer {token}"}
        
        # Start a game (don't advance to make it someone else's turn initially)
        start_response = requests.post(f"{BASE_URL}/api/agent-api/game/{table_id}/start", headers=headers)
        game_id = start_response.json()["game_id"]
        game_state = start_response.json()["game"]
        
        # If it happens to be our turn, advance once so it's not
        if game_state.get("is_your_turn"):
            # Submit one action then try again
            requests.post(f"{BASE_URL}/api/agent-api/game/{game_id}/action", 
                         json={"action": "call"}, headers=headers)
            
        # Get current state
        state_response = requests.get(f"{BASE_URL}/api/agent-api/game/{game_id}/state", headers=headers)
        if state_response.json().get("phase") == "complete":
            pytest.skip("Game already complete")
            
        if state_response.json().get("is_your_turn"):
            pytest.skip("Still our turn, can't test not-your-turn scenario")
            
        # Try to submit action when not our turn
        action_payload = {"action": "call"}
        response = requests.post(f"{BASE_URL}/api/agent-api/game/{game_id}/action", 
                                json=action_payload, headers=headers)
        
        assert response.status_code == 400
        assert "not your" in response.json().get("detail", "").lower()


class TestAgentAPIFullGameLoop:
    """Test complete game loop: Register -> Join -> Start -> Play to completion"""
    
    @pytest.fixture
    def human_token_for_cleanup(self):
        """Create a human user for game cleanup"""
        unique_id = str(uuid.uuid4())[:8]
        payload = {
            "username": f"TEST_fullclean_{unique_id}",
            "email": f"TEST_fullclean_{unique_id}@test.com",
            "password": "testpass123",
            "role": "human"
        }
        response = requests.post(f"{BASE_URL}/api/auth/signup", json=payload)
        return response.json()["token"]
    
    def test_full_game_loop(self, human_token_for_cleanup):
        """Play a complete game through the Agent API"""
        unique_id = str(uuid.uuid4())[:8]
        
        # 1. Register
        reg_payload = {
            "username": f"TEST_fullgame_{unique_id}",
            "email": f"TEST_fullgame_{unique_id}@test.com",
            "password": "testpass123",
            "agent_name": f"TEST_FullGameBot_{unique_id}"
        }
        reg_response = requests.post(f"{BASE_URL}/api/agent-api/register", json=reg_payload)
        assert reg_response.status_code == 200, f"Register failed: {reg_response.text}"
        token = reg_response.json()["token"]
        agent_id = reg_response.json()["agent"]["id"]
        headers = {"Authorization": f"Bearer {token}"}
        print(f"1. Registered agent: {reg_payload['agent_name']}")
        
        # 2. List tables
        tables_response = requests.get(f"{BASE_URL}/api/tables")
        assert tables_response.status_code == 200
        tables = tables_response.json()
        assert len(tables) > 0
        print(f"2. Found {len(tables)} tables")
        
        # 3. Find a table to join - complete existing game if needed
        table_id = None
        for table in tables:
            # Complete any existing game first
            complete_existing_game_if_needed(table, human_token_for_cleanup)
            
            # Refresh table
            table_refresh = requests.get(f"{BASE_URL}/api/tables/{table['id']}")
            table = table_refresh.json()
            
            # Try to join
            join_response = requests.post(f"{BASE_URL}/api/agent-api/tables/{table['id']}/join", headers=headers)
            if join_response.status_code == 200:
                table_id = table['id']
                print(f"3. Joined table: {table['name']}")
                break
                
        if not table_id:
            pytest.skip("Could not join any table - all have active games")
        
        # 4. Start game
        start_response = requests.post(f"{BASE_URL}/api/agent-api/game/{table_id}/start", headers=headers)
        assert start_response.status_code == 200, f"Start failed: {start_response.text}"
        game_id = start_response.json()["game_id"]
        game = start_response.json()["game"]
        print(f"4. Started game: {game_id}, phase: {game['phase']}")
        
        # 5. Play the game loop
        max_iterations = 50
        action_count = 0
        for i in range(max_iterations):
            # Advance others until our turn
            adv_response = requests.post(f"{BASE_URL}/api/agent-api/game/{game_id}/advance-others", headers=headers)
            assert adv_response.status_code == 200
            game = adv_response.json()["game"]
            advances = adv_response.json()["advances"]
            
            if game.get("phase") == "complete":
                print(f"5. Game complete after {action_count} of our actions!")
                break
                
            if game.get("is_your_turn"):
                # Get state
                state_response = requests.get(f"{BASE_URL}/api/agent-api/game/{game_id}/state", headers=headers)
                state = state_response.json()
                
                # Decide action based on hand strength
                strength = state.get("your_hand_strength", 0.5)
                round_bet = state.get("round_bet", 0)
                
                if strength > 0.6:
                    action = "raise"
                    amount = max(50, round_bet * 2)
                elif strength > 0.3 or round_bet == 0:
                    action = "call"
                    amount = 0
                else:
                    action = "fold"
                    amount = 0
                    
                # Submit action
                action_response = requests.post(
                    f"{BASE_URL}/api/agent-api/game/{game_id}/action",
                    json={"action": action, "amount": amount},
                    headers=headers
                )
                assert action_response.status_code == 200, f"Action failed: {action_response.text}"
                action_count += 1
                print(f"   Iteration {i+1}: Submitted {action}, advances: {advances}")
                
                game = action_response.json()["game"]
                if game.get("phase") == "complete":
                    print(f"5. Game complete after {action_count} of our actions!")
                    break
        else:
            print(f"5. Game didn't complete within {max_iterations} iterations")
            
        # 6. Verify final state
        final_state = requests.get(f"{BASE_URL}/api/agent-api/game/{game_id}/state", headers=headers)
        final_game = final_state.json()
        
        print(f"6. Final state: phase={final_game.get('phase')}, winner={final_game.get('winner_name')}")
        
        if final_game.get("phase") == "complete":
            assert final_game.get("winner_id") is not None
            assert final_game.get("winner_name") is not None
            assert final_game.get("final_pot") is not None
            print(f"   Winner: {final_game.get('winner_name')}, Pot: {final_game.get('final_pot')}")


class TestRegressionRegularAuth:
    """Regression tests: Ensure regular auth still works"""
    
    def test_regular_signup(self):
        """POST /api/auth/signup should still work for human users"""
        unique_id = str(uuid.uuid4())[:8]
        payload = {
            "username": f"TEST_human_{unique_id}",
            "email": f"TEST_human_{unique_id}@test.com",
            "password": "testpass123",
            "role": "human"
        }
        response = requests.post(f"{BASE_URL}/api/auth/signup", json=payload)
        
        assert response.status_code == 200
        data = response.json()
        assert "token" in data
        assert data["user"]["role"] == "human"
        
    def test_regular_agent_signup(self):
        """POST /api/auth/signup should still work for agent role"""
        unique_id = str(uuid.uuid4())[:8]
        payload = {
            "username": f"TEST_regtag_{unique_id}",
            "email": f"TEST_regagt_{unique_id}@test.com",
            "password": "testpass123",
            "role": "agent",
            "agent_name": f"TEST_RegAgent_{unique_id}"
        }
        response = requests.post(f"{BASE_URL}/api/auth/signup", json=payload)
        
        assert response.status_code == 200
        data = response.json()
        assert "token" in data
        assert data["user"]["role"] == "agent"
        assert data["agent"] is not None
        
    def test_regular_login(self):
        """POST /api/auth/login should still work"""
        # Sign up first
        unique_id = str(uuid.uuid4())[:8]
        signup_payload = {
            "username": f"TEST_reglog_{unique_id}",
            "email": f"TEST_reglog_{unique_id}@test.com",
            "password": "testpass123"
        }
        requests.post(f"{BASE_URL}/api/auth/signup", json=signup_payload)
        
        # Login
        login_payload = {
            "email": f"TEST_reglog_{unique_id}@test.com",
            "password": "testpass123"
        }
        response = requests.post(f"{BASE_URL}/api/auth/login", json=login_payload)
        
        assert response.status_code == 200
        assert "token" in response.json()


class TestRegressionTables:
    """Regression tests: Ensure regular table endpoints still work"""
    
    @pytest.fixture
    def human_token(self):
        """Create a human user and return token"""
        unique_id = str(uuid.uuid4())[:8]
        payload = {
            "username": f"TEST_humtbl_{unique_id}",
            "email": f"TEST_humtbl_{unique_id}@test.com",
            "password": "testpass123",
            "role": "human"
        }
        response = requests.post(f"{BASE_URL}/api/auth/signup", json=payload)
        return response.json()["token"]
    
    def test_get_tables(self):
        """GET /api/tables should return tables"""
        response = requests.get(f"{BASE_URL}/api/tables")
        
        assert response.status_code == 200
        tables = response.json()
        assert isinstance(tables, list)
        assert len(tables) > 0
        
    def test_start_game_regular(self, human_token):
        """POST /api/tables/{id}/start-game should still work for regular users"""
        headers = {"Authorization": f"Bearer {human_token}"}
        
        # Get a table
        tables_response = requests.get(f"{BASE_URL}/api/tables")
        tables = tables_response.json()
        table_id = tables[0]["id"]
        
        response = requests.post(f"{BASE_URL}/api/tables/{table_id}/start-game", headers=headers)
        
        # Should succeed (200) or fail due to game in progress (400)
        assert response.status_code in [200, 400], f"Unexpected: {response.status_code}: {response.text}"
        
    def test_advance_game_regular(self, human_token):
        """POST /api/games/{id}/advance should still work for regular users"""
        headers = {"Authorization": f"Bearer {human_token}"}
        
        # Get a table and try to start/advance a game
        tables_response = requests.get(f"{BASE_URL}/api/tables")
        tables = tables_response.json()
        table = tables[0]
        
        # Start a new game or use existing
        if table.get("current_game") and table["current_game"].get("id"):
            game_id = table["current_game"]["id"]
        else:
            start_response = requests.post(f"{BASE_URL}/api/tables/{table['id']}/start-game", headers=headers)
            if start_response.status_code == 200:
                game_id = start_response.json()["id"]
            else:
                pytest.skip("Could not start game for advance test")
                return
                
        # Try to advance
        response = requests.post(f"{BASE_URL}/api/games/{game_id}/advance", headers=headers)
        
        assert response.status_code == 200


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
