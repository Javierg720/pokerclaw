import requests
import sys
import json
import websocket
import threading
import time
from datetime import datetime

class PokerClawAPITester:
    def __init__(self, base_url="https://agent-poker.preview.emergentagent.com"):
        self.base_url = base_url
        self.token = None
        self.tests_run = 0
        self.tests_passed = 0
        self.user_id = None
        self.username = None
        self.game_id = None
        self.table_id = None
        self.agent_ids = []
        self.tournament_id = None
        self.ws_messages = []

    def run_test(self, name, method, endpoint, expected_status, data=None, auth_required=True):
        """Run a single API test"""
        url = f"{self.base_url}/api/{endpoint}"
        headers = {'Content-Type': 'application/json'}
        if auth_required and self.token:
            headers['Authorization'] = f'Bearer {self.token}'

        self.tests_run += 1
        print(f"\n🔍 Testing {name}...")
        print(f"   URL: {method} {url}")
        
        try:
            if method == 'GET':
                response = requests.get(url, headers=headers, timeout=10)
            elif method == 'POST':
                response = requests.post(url, json=data, headers=headers, timeout=10)
            elif method == 'PUT':
                response = requests.put(url, json=data, headers=headers, timeout=10)
            elif method == 'DELETE':
                response = requests.delete(url, headers=headers, timeout=10)

            success = response.status_code == expected_status
            if success:
                self.tests_passed += 1
                print(f"✅ Passed - Status: {response.status_code}")
                try:
                    response_data = response.json()
                    return True, response_data
                except:
                    return True, {}
            else:
                print(f"❌ Failed - Expected {expected_status}, got {response.status_code}")
                try:
                    error_detail = response.json()
                    print(f"   Error: {error_detail}")
                except:
                    print(f"   Response: {response.text}")
                return False, {}

        except Exception as e:
            print(f"❌ Failed - Error: {str(e)}")
            return False, {}

    def test_signup(self):
        """Test user signup"""
        timestamp = datetime.now().strftime('%H%M%S')
        test_data = {
            "username": f"testuser_{timestamp}",
            "email": f"test_{timestamp}@pokerclaw.io", 
            "password": "testpass123"
        }
        
        success, response = self.run_test(
            "User Signup",
            "POST",
            "auth/signup",
            200,
            data=test_data,
            auth_required=False
        )
        
        if success and 'token' in response:
            self.token = response['token']
            self.user_id = response['user']['id']
            self.username = response['user']['username']
            print(f"   📝 Token obtained for user: {self.username}")
            return True
        return False

    def test_login(self):
        """Test login with demo user"""
        login_data = {
            "email": "demo@pokerclaw.io",
            "password": "demo123"
        }
        
        success, response = self.run_test(
            "Demo User Login",
            "POST", 
            "auth/login",
            200,
            data=login_data,
            auth_required=False
        )
        
        if success and 'token' in response:
            self.token = response['token']
            self.user_id = response['user']['id']
            self.username = response['user']['username']
            print(f"   📝 Login successful for: {self.username}")
            return True
        return False

    def test_auth_me(self):
        """Test /auth/me endpoint"""
        success, response = self.run_test(
            "Get Current User",
            "GET",
            "auth/me", 
            200
        )
        return success

    def test_get_agents(self):
        """Test getting all agents"""
        success, response = self.run_test(
            "Get Agents",
            "GET",
            "agents",
            200,
            auth_required=False
        )
        
        if success and isinstance(response, list):
            self.agent_ids = [agent['id'] for agent in response]
            print(f"   📊 Found {len(response)} agents")
            return True
        return False

    def test_get_tables(self):
        """Test getting all tables"""
        success, response = self.run_test(
            "Get Tables",
            "GET", 
            "tables",
            200,
            auth_required=False
        )
        
        if success and isinstance(response, list):
            print(f"   📊 Found {len(response)} tables")
            for table in response:
                print(f"      - {table.get('name', 'Unknown')} ({table.get('id', 'No ID')})")
            if response:
                self.table_id = response[0]['id']  # Use first table for testing
            return True
        return False

    def test_get_wallet(self):
        """Test wallet endpoint"""
        success, response = self.run_test(
            "Get Wallet",
            "GET",
            "wallet",
            200
        )
        
        if success:
            print(f"   💰 GC Balance: {response.get('gc_balance', 0)}")
            print(f"   ⚡ SC Balance: {response.get('sc_balance', 0)}")
        return success

    def test_wallet_transactions(self):
        """Test wallet transactions"""
        success, response = self.run_test(
            "Get Transactions",
            "GET",
            "wallet/transactions",
            200
        )
        
        if success and isinstance(response, list):
            print(f"   📋 Found {len(response)} transactions")
        return success

    def test_purchase_coins(self):
        """Test coin purchase"""
        purchase_data = {
            "amount": 1000,
            "currency": "gc"
        }
        
        success, response = self.run_test(
            "Purchase GC",
            "POST",
            "wallet/purchase",
            200,
            data=purchase_data
        )
        return success

    def test_start_game(self):
        """Test starting a new game or use existing game"""
        if not self.table_id:
            print("❌ No table ID available for game start test")
            return False
        
        # First try to get the table details to see if there's an existing game
        success, table_data = self.run_test(
            "Get Table Details",
            "GET",
            f"tables/{self.table_id}",
            200,
            auth_required=False
        )
        
        if success and table_data.get('current_game'):
            # Use existing game
            self.game_id = table_data['current_game']['id']
            print(f"   🎮 Using existing game ID: {self.game_id}")
            return True
        
        # Try to start a new game
        success, response = self.run_test(
            "Start New Game",
            "POST",
            f"tables/{self.table_id}/start-game",
            200
        )
        
        if success and 'id' in response:
            self.game_id = response['id']
            print(f"   🎮 Game started with ID: {self.game_id}")
            return True
        else:
            # Try with a different table that might not have an active game
            tables_response = requests.get(f"{self.base_url}/api/tables")
            if tables_response.status_code == 200:
                tables = tables_response.json()
                for table in tables:
                    if not table.get('current_game_id'):
                        print(f"   🔄 Trying different table: {table['name']}")
                        success, response = self.run_test(
                            f"Start New Game on {table['name']}",
                            "POST",
                            f"tables/{table['id']}/start-game",
                            200
                        )
                        if success and 'id' in response:
                            self.game_id = response['id']
                            self.table_id = table['id']
                            print(f"   🎮 Game started with ID: {self.game_id}")
                            return True
        return False

    def test_get_game(self):
        """Test getting game details"""
        if not self.game_id:
            print("❌ No game ID available")
            return False
            
        success, response = self.run_test(
            "Get Game Details",
            "GET",
            f"games/{self.game_id}",
            200,
            auth_required=False
        )
        
        if success:
            print(f"   🎯 Game Phase: {response.get('phase', 'Unknown')}")
            print(f"   💰 Pot: {response.get('pot', 0)}")
        return success

    def test_advance_game(self):
        """Test advancing game through phases"""
        if not self.game_id:
            print("❌ No game ID available")
            return False
            
        phases = ['waiting', 'preflop', 'flop', 'turn', 'river', 'showdown', 'complete']
        
        for expected_phase in phases[1:]:  # Skip 'waiting' as game starts there
            success, response = self.run_test(
                f"Advance Game to {expected_phase}",
                "POST",
                f"games/{self.game_id}/advance",
                200
            )
            
            if not success:
                return False
                
            actual_phase = response.get('phase', '')
            print(f"   📍 Current phase: {actual_phase}")
            
            if actual_phase == 'complete':
                print(f"   🏆 Winner: {response.get('winner_name', 'Unknown')}")
                print(f"   🃏 Winning hand: {response.get('winning_hand', 'Unknown')}")
                break
                
        return True

    def test_place_bet(self):
        """Test placing a bet"""
        if not self.game_id or not self.agent_ids:
            print("❌ No game ID or agent IDs available")
            return False
            
        bet_data = {
            "game_id": self.game_id,
            "agent_id": self.agent_ids[0],
            "amount": 50,
            "currency": "gc"
        }
        
        success, response = self.run_test(
            "Place Bet",
            "POST",
            "bets",
            200,
            data=bet_data
        )
        return success

    def test_get_my_bets(self):
        """Test getting user's bets"""
        success, response = self.run_test(
            "Get My Bets",
            "GET",
            "bets/my-bets",
            200
        )
        
        if success and isinstance(response, list):
            print(f"   🎲 Found {len(response)} bets")
        return success

    def test_leaderboard(self):
        """Test leaderboard endpoint"""
        success, response = self.run_test(
            "Get Leaderboard",
            "GET",
            "leaderboard",
            200,
            auth_required=False
        )
        
        if success:
            agents = response.get('top_agents', [])
            bettors = response.get('top_bettors', [])
            print(f"   🏆 Top agents: {len(agents)}")
            print(f"   🎯 Top bettors: {len(bettors)}")
        return success

    def test_tournaments(self):
        """Test tournament endpoints"""
        # Get existing tournaments
        success, response = self.run_test(
            "Get Tournaments",
            "GET",
            "tournaments",
            200,
            auth_required=False
        )
        
        if success and isinstance(response, list):
            print(f"   🏆 Found {len(response)} tournaments")
            if response:
                print(f"      - First tournament: {response[0].get('name', 'Unknown')} (Status: {response[0].get('status', 'Unknown')})")
        
        # Create new tournament 
        success, response = self.run_test(
            "Create Tournament",
            "POST",
            "tournaments",
            200
        )
        
        if success and 'id' in response:
            self.tournament_id = response['id']
            print(f"   🎮 Tournament created with ID: {self.tournament_id}")
            print(f"   📝 Tournament name: {response.get('name', 'Unknown')}")
            print(f"   ⚡ Status: {response.get('status', 'Unknown')}")
            return True
        return False

    def test_tournament_details(self):
        """Test getting tournament details"""
        if not self.tournament_id:
            print("❌ No tournament ID available")
            return False
            
        success, response = self.run_test(
            "Get Tournament Details",
            "GET",
            f"tournaments/{self.tournament_id}",
            200,
            auth_required=False
        )
        
        if success:
            print(f"   🎯 Tournament Status: {response.get('status', 'Unknown')}")
            bracket = response.get('bracket', {})
            print(f"   🥊 Semi 1 agents: {len(bracket.get('semi_1', {}).get('agent_ids', []))}")
            print(f"   🥊 Semi 2 agents: {len(bracket.get('semi_2', {}).get('agent_ids', []))}")
        return success

    def test_advance_tournament(self):
        """Test advancing tournament through phases"""
        if not self.tournament_id:
            print("❌ No tournament ID available") 
            return False
            
        # Advance from lobby to semis
        success, response = self.run_test(
            "Start Tournament (Lobby -> Semis)",
            "POST",
            f"tournaments/{self.tournament_id}/advance",
            200
        )
        
        if success:
            print(f"   📍 Tournament status: {response.get('status', 'Unknown')}")
            
            # Try advancing semi games a few times
            for i in range(3):
                success, response = self.run_test(
                    f"Advance Tournament Round {i+1}",
                    "POST", 
                    f"tournaments/{self.tournament_id}/advance",
                    200
                )
                
                if success:
                    status = response.get('status', 'Unknown')
                    print(f"   📍 Tournament status after round {i+1}: {status}")
                    
                    if status == 'complete':
                        champion = response.get('champion_name', 'Unknown')
                        print(f"   🏆 Tournament Champion: {champion}")
                        break
                else:
                    break
                    
        return success

    def test_tournament_bet(self):
        """Test placing tournament bets"""
        if not self.tournament_id or not self.agent_ids:
            print("❌ No tournament ID or agent IDs available")
            return False
            
        bet_data = {
            "tournament_id": self.tournament_id,
            "agent_id": self.agent_ids[0],
            "amount": 100,
            "currency": "gc"
        }
        
        success, response = self.run_test(
            "Place Tournament Bet", 
            "POST",
            "tournament-bets",
            200,
            data=bet_data
        )
        return success

    def test_websocket_connection(self):
        """Test WebSocket connection to table"""
        if not self.table_id:
            print("❌ No table ID available for WebSocket test")
            return False
            
        # Convert HTTPS URL to WSS
        ws_url = self.base_url.replace('https://', 'wss://').replace('http://', 'ws://')
        ws_endpoint = f"{ws_url}/api/ws/table/{self.table_id}"
        
        print(f"   🔌 Connecting to: {ws_endpoint}")
        
        self.ws_messages = []
        connection_success = False
        
        def on_message(ws, message):
            try:
                data = json.loads(message)
                self.ws_messages.append(data)
                print(f"   📨 WebSocket message: {data.get('type', 'unknown')}")
                if data.get('type') == 'spectators':
                    print(f"      - Spectator count: {data.get('count', 0)}")
                elif data.get('type') == 'game_state':
                    game = data.get('game', {})
                    print(f"      - Game phase: {game.get('phase', 'unknown')}")
            except Exception as e:
                print(f"   ⚠️ WebSocket message parse error: {e}")
        
        def on_open(ws):
            nonlocal connection_success
            connection_success = True
            print(f"   ✅ WebSocket connected successfully")
            # Send a test ping
            if self.token:
                auth_msg = json.dumps({"type": "auth", "token": self.token})
                ws.send(auth_msg)
        
        def on_error(ws, error):
            print(f"   ❌ WebSocket error: {error}")
        
        def on_close(ws, close_status_code, close_msg):
            print(f"   🔌 WebSocket closed")
        
        try:
            ws = websocket.WebSocketApp(
                ws_endpoint,
                on_message=on_message,
                on_open=on_open,
                on_error=on_error,
                on_close=on_close
            )
            
            # Run WebSocket in a separate thread for a few seconds
            def run_ws():
                ws.run_forever()
                
            ws_thread = threading.Thread(target=run_ws)
            ws_thread.daemon = True
            ws_thread.start()
            
            # Wait a bit for connection and messages
            time.sleep(3)
            ws.close()
            
            if connection_success and len(self.ws_messages) > 0:
                print(f"   📊 Received {len(self.ws_messages)} WebSocket messages")
                return True
            elif connection_success:
                print(f"   ✅ WebSocket connection successful (no messages received)")
                return True
            else:
                return False
                
        except Exception as e:
            print(f"   ❌ WebSocket connection failed: {e}")
            return False

def main():
    print("🃏 PokerClaw API Testing Suite")
    print("=" * 50)
    
    tester = PokerClawAPITester()
    
    # Test auth flow
    print("\n📋 AUTHENTICATION TESTS")
    signup_success = tester.test_signup()
    if not signup_success:
        # Try login with demo user if signup fails
        login_success = tester.test_login()
        if not login_success:
            print("❌ Both signup and login failed, stopping tests")
            return 1
    
    tester.test_auth_me()
    
    # Test core endpoints
    print("\n📋 CORE FUNCTIONALITY TESTS")
    tester.test_get_agents()
    tester.test_get_tables()
    
    # Test wallet functionality
    print("\n📋 WALLET TESTS")
    tester.test_get_wallet()
    tester.test_wallet_transactions()
    tester.test_purchase_coins()
    
    # Test game functionality
    print("\n📋 GAME TESTS")
    if tester.test_start_game():
        tester.test_get_game()
        tester.test_place_bet()  # Place bet before advancing
        tester.test_advance_game()
    
    # Test betting and leaderboard
    print("\n📋 BETTING & LEADERBOARD TESTS")
    tester.test_get_my_bets()
    tester.test_leaderboard()
    
    # Test NEW FEATURES - Tournaments and WebSocket
    print("\n📋 NEW FEATURES TESTS")
    if tester.test_tournaments():
        tester.test_tournament_details()
        tester.test_tournament_bet() 
        tester.test_advance_tournament()
    
    # Test WebSocket connection
    tester.test_websocket_connection()
    
    # Print results
    print("\n" + "=" * 50)
    print(f"📊 RESULTS: {tester.tests_passed}/{tester.tests_run} tests passed")
    success_rate = (tester.tests_passed / tester.tests_run) * 100 if tester.tests_run > 0 else 0
    print(f"📈 Success Rate: {success_rate:.1f}%")
    
    if success_rate >= 80:
        print("🎉 Backend API tests mostly successful!")
        return 0
    else:
        print("⚠️  Backend API has significant issues")
        return 1

if __name__ == "__main__":
    sys.exit(main())