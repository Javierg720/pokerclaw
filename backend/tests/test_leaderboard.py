"""
Test Leaderboard API - Spectator Leaderboard Feature (iteration 13)
Tests the combined agent and bettor leaderboard endpoint.
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')


class TestLeaderboardAPI:
    """Tests for GET /api/leaderboard endpoint - combined agent/bettor rankings"""

    def test_leaderboard_returns_correct_structure(self):
        """Verify leaderboard returns both top_agents and top_bettors arrays"""
        response = requests.get(f"{BASE_URL}/api/leaderboard")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        data = response.json()
        assert "top_agents" in data, "Response missing 'top_agents' key"
        assert "top_bettors" in data, "Response missing 'top_bettors' key"
        assert isinstance(data["top_agents"], list), "top_agents should be a list"
        assert isinstance(data["top_bettors"], list), "top_bettors should be a list"
        print(f"✓ Leaderboard structure correct: {len(data['top_agents'])} agents, {len(data['top_bettors'])} bettors")

    def test_top_agents_has_required_fields(self):
        """Verify top_agents entries have all required fields"""
        response = requests.get(f"{BASE_URL}/api/leaderboard")
        assert response.status_code == 200
        
        data = response.json()
        required_fields = ['id', 'rank', 'name', 'avatar_url', 'tagline', 'wins', 'losses', 'total_games', 'total_chips_won', 'win_rate']
        
        if len(data['top_agents']) > 0:
            agent = data['top_agents'][0]
            for field in required_fields:
                assert field in agent, f"Agent missing required field: {field}"
            print(f"✓ Top agent has all required fields: {list(agent.keys())}")
            
            # Verify data types
            assert isinstance(agent['rank'], int), "rank should be int"
            assert isinstance(agent['wins'], int), "wins should be int"
            assert isinstance(agent['losses'], int), "losses should be int"
            assert isinstance(agent['total_games'], int), "total_games should be int"
            assert isinstance(agent['win_rate'], (int, float)), "win_rate should be numeric"
            print(f"✓ Agent data types validated")
        else:
            pytest.skip("No agents in leaderboard to test")

    def test_top_bettors_has_required_fields(self):
        """Verify top_bettors entries have all required fields"""
        response = requests.get(f"{BASE_URL}/api/leaderboard")
        assert response.status_code == 200
        
        data = response.json()
        required_fields = ['user_id', 'username', 'rank', 'total_bets', 'bets_won', 'bets_lost', 'total_wagered', 'total_won', 'net_profit', 'win_rate']
        
        if len(data['top_bettors']) > 0:
            bettor = data['top_bettors'][0]
            for field in required_fields:
                assert field in bettor, f"Bettor missing required field: {field}"
            print(f"✓ Top bettor has all required fields: {list(bettor.keys())}")
            
            # Verify data types
            assert isinstance(bettor['rank'], int), "rank should be int"
            assert isinstance(bettor['total_bets'], int), "total_bets should be int"
            assert isinstance(bettor['bets_won'], int), "bets_won should be int"
            assert isinstance(bettor['bets_lost'], int), "bets_lost should be int"
            assert isinstance(bettor['total_wagered'], (int, float)), "total_wagered should be numeric"
            assert isinstance(bettor['total_won'], (int, float)), "total_won should be numeric"
            assert isinstance(bettor['net_profit'], (int, float)), "net_profit should be numeric"
            assert isinstance(bettor['win_rate'], (int, float)), "win_rate should be numeric"
            print(f"✓ Bettor data types validated")
        else:
            pytest.skip("No bettors in leaderboard to test")

    def test_top_agents_sorted_by_wins_desc(self):
        """Verify top_agents are sorted by wins in descending order"""
        response = requests.get(f"{BASE_URL}/api/leaderboard")
        assert response.status_code == 200
        
        data = response.json()
        agents = data['top_agents']
        
        if len(agents) >= 2:
            for i in range(len(agents) - 1):
                current_wins = agents[i].get('wins', 0)
                next_wins = agents[i + 1].get('wins', 0)
                # Primary sort by wins DESC, secondary by total_chips_won DESC
                if current_wins < next_wins:
                    assert False, f"Agents not sorted by wins DESC: position {i} has {current_wins} wins, position {i+1} has {next_wins}"
            print(f"✓ Agents correctly sorted by wins DESC (top: {agents[0]['wins']}W, last: {agents[-1]['wins']}W)")
        else:
            print("✓ Not enough agents to verify sorting (need >= 2)")

    def test_top_bettors_sorted_by_total_won_desc(self):
        """Verify top_bettors are sorted by total_won in descending order"""
        response = requests.get(f"{BASE_URL}/api/leaderboard")
        assert response.status_code == 200
        
        data = response.json()
        bettors = data['top_bettors']
        
        if len(bettors) >= 2:
            for i in range(len(bettors) - 1):
                current_won = bettors[i].get('total_won', 0)
                next_won = bettors[i + 1].get('total_won', 0)
                # Primary sort by total_won DESC
                if current_won < next_won:
                    assert False, f"Bettors not sorted by total_won DESC: position {i} has {current_won} SC, position {i+1} has {next_won}"
            print(f"✓ Bettors correctly sorted by total_won DESC (top: {bettors[0]['total_won']} SC, last: {bettors[-1]['total_won']} SC)")
        else:
            print("✓ Not enough bettors to verify sorting (need >= 2)")

    def test_agent_ranks_are_sequential(self):
        """Verify agent ranks are sequential starting from 1"""
        response = requests.get(f"{BASE_URL}/api/leaderboard")
        assert response.status_code == 200
        
        data = response.json()
        agents = data['top_agents']
        
        for i, agent in enumerate(agents):
            expected_rank = i + 1
            actual_rank = agent.get('rank', 0)
            assert actual_rank == expected_rank, f"Agent rank mismatch: expected {expected_rank}, got {actual_rank}"
        
        print(f"✓ All {len(agents)} agent ranks are sequential (1 to {len(agents)})")

    def test_bettor_ranks_are_sequential(self):
        """Verify bettor ranks are sequential starting from 1"""
        response = requests.get(f"{BASE_URL}/api/leaderboard")
        assert response.status_code == 200
        
        data = response.json()
        bettors = data['top_bettors']
        
        for i, bettor in enumerate(bettors):
            expected_rank = i + 1
            actual_rank = bettor.get('rank', 0)
            assert actual_rank == expected_rank, f"Bettor rank mismatch: expected {expected_rank}, got {actual_rank}"
        
        print(f"✓ All {len(bettors)} bettor ranks are sequential (1 to {len(bettors)})")

    def test_win_rate_calculation_agents(self):
        """Verify agent win_rate is calculated correctly (wins/total_games * 100)"""
        response = requests.get(f"{BASE_URL}/api/leaderboard")
        assert response.status_code == 200
        
        data = response.json()
        agents = data['top_agents']
        
        for agent in agents[:5]:  # Check first 5 agents
            wins = agent.get('wins', 0)
            total_games = agent.get('total_games', 0)
            reported_win_rate = agent.get('win_rate', 0)
            
            if total_games > 0:
                expected_win_rate = round(wins / total_games * 100, 1)
                assert abs(reported_win_rate - expected_win_rate) < 0.2, f"Agent win_rate mismatch: expected {expected_win_rate}, got {reported_win_rate}"
            else:
                assert reported_win_rate == 0, f"Agent with 0 games should have 0 win_rate, got {reported_win_rate}"
        
        print(f"✓ Agent win_rate calculations verified")

    def test_win_rate_calculation_bettors(self):
        """Verify bettor win_rate is calculated correctly (bets_won/total_bets * 100)"""
        response = requests.get(f"{BASE_URL}/api/leaderboard")
        assert response.status_code == 200
        
        data = response.json()
        bettors = data['top_bettors']
        
        for bettor in bettors[:5]:  # Check first 5 bettors
            bets_won = bettor.get('bets_won', 0)
            total_bets = bettor.get('total_bets', 0)
            reported_win_rate = bettor.get('win_rate', 0)
            
            if total_bets > 0:
                expected_win_rate = round(bets_won / total_bets * 100, 1)
                assert abs(reported_win_rate - expected_win_rate) < 0.2, f"Bettor win_rate mismatch: expected {expected_win_rate}, got {reported_win_rate}"
            else:
                assert reported_win_rate == 0, f"Bettor with 0 bets should have 0 win_rate, got {reported_win_rate}"
        
        print(f"✓ Bettor win_rate calculations verified")

    def test_max_20_results_per_category(self):
        """Verify max 20 entries returned per category"""
        response = requests.get(f"{BASE_URL}/api/leaderboard")
        assert response.status_code == 200
        
        data = response.json()
        assert len(data['top_agents']) <= 20, f"top_agents exceeds 20: {len(data['top_agents'])}"
        assert len(data['top_bettors']) <= 20, f"top_bettors exceeds 20: {len(data['top_bettors'])}"
        print(f"✓ Leaderboard respects max 20 limit (agents: {len(data['top_agents'])}, bettors: {len(data['top_bettors'])})")


class TestLeaderboardRegressionBasics:
    """Quick regression checks for existing endpoints"""

    def test_agents_endpoint_still_works(self):
        """Ensure /api/agents still returns agent list"""
        response = requests.get(f"{BASE_URL}/api/agents")
        assert response.status_code == 200, f"Agents endpoint failed: {response.status_code}"
        data = response.json()
        assert isinstance(data, list), "Agents should return list"
        print(f"✓ /api/agents returns {len(data)} agents")

    def test_tables_endpoint_still_works(self):
        """Ensure /api/tables still returns table list"""
        response = requests.get(f"{BASE_URL}/api/tables")
        assert response.status_code == 200, f"Tables endpoint failed: {response.status_code}"
        data = response.json()
        assert isinstance(data, list), "Tables should return list"
        print(f"✓ /api/tables returns {len(data)} tables")

    def test_tournaments_endpoint_still_works(self):
        """Ensure /api/tournaments still returns tournament list"""
        response = requests.get(f"{BASE_URL}/api/tournaments")
        assert response.status_code == 200, f"Tournaments endpoint failed: {response.status_code}"
        data = response.json()
        assert isinstance(data, list), "Tournaments should return list"
        print(f"✓ /api/tournaments returns {len(data)} tournaments")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
