"""
Test Avatar Profile Customization API - iteration 14
Tests for spectator avatar customization feature:
- GET /api/auth/avatars - Returns list of 16 avatar URLs
- PUT /api/auth/profile - Update avatar_url, returns updated user
- PUT /api/auth/profile - Update username, rejects if taken
- GET /api/auth/me - Returns avatar_url field after update
- POST /api/auth/login - Returns avatar_url in user object
- REGRESSION: Leaderboard and OpenClaw Agent API
"""
import pytest
import requests
import os
import uuid

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Test credentials from review_request
TEST_USER_EMAIL = "uitester@test.com"
TEST_USER_PASSWORD = "test123"
TEST_AGENT_EMAIL = "openclaw@test.com"
TEST_AGENT_PASSWORD = "test123"


class TestAvatarOptionsEndpoint:
    """Tests for GET /api/auth/avatars endpoint - returns list of 16 avatar URLs"""

    def test_avatars_endpoint_returns_200(self):
        """GET /api/auth/avatars returns 200 OK"""
        response = requests.get(f"{BASE_URL}/api/auth/avatars")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        print("✓ GET /api/auth/avatars returns 200")

    def test_avatars_returns_correct_structure(self):
        """Response contains 'avatars' array"""
        response = requests.get(f"{BASE_URL}/api/auth/avatars")
        assert response.status_code == 200
        data = response.json()
        assert "avatars" in data, "Response missing 'avatars' key"
        assert isinstance(data["avatars"], list), "'avatars' should be a list"
        print(f"✓ Response has 'avatars' list with {len(data['avatars'])} items")

    def test_avatars_returns_16_options(self):
        """Avatars list contains exactly 16 DiceBear avatar URLs"""
        response = requests.get(f"{BASE_URL}/api/auth/avatars")
        assert response.status_code == 200
        data = response.json()
        assert len(data["avatars"]) == 16, f"Expected 16 avatars, got {len(data['avatars'])}"
        print("✓ Exactly 16 avatar options returned")

    def test_avatars_are_dicebear_urls(self):
        """All avatar URLs are valid DiceBear API URLs"""
        response = requests.get(f"{BASE_URL}/api/auth/avatars")
        assert response.status_code == 200
        data = response.json()
        
        for idx, url in enumerate(data["avatars"]):
            assert isinstance(url, str), f"Avatar {idx} is not a string"
            assert url.startswith("https://api.dicebear.com/"), f"Avatar {idx} is not a DiceBear URL: {url[:50]}"
        print("✓ All 16 avatars are valid DiceBear URLs")


class TestProfileUpdateEndpoint:
    """Tests for PUT /api/auth/profile endpoint - update avatar and username"""

    @pytest.fixture(scope="class")
    def auth_token(self):
        """Get auth token for test user"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": TEST_USER_EMAIL,
            "password": TEST_USER_PASSWORD
        })
        assert response.status_code == 200, f"Login failed: {response.text}"
        return response.json()["token"]

    @pytest.fixture(scope="class")
    def user_data(self):
        """Get current user data"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": TEST_USER_EMAIL,
            "password": TEST_USER_PASSWORD
        })
        return response.json()["user"]

    def test_update_avatar_requires_auth(self):
        """PUT /api/auth/profile returns 401 without token"""
        response = requests.put(f"{BASE_URL}/api/auth/profile", json={
            "avatar_url": "https://api.dicebear.com/7.x/bottts-neutral/svg?seed=test"
        })
        assert response.status_code in [401, 403], f"Expected 401/403 without auth, got {response.status_code}"
        print("✓ Profile update requires authentication")

    def test_update_avatar_success(self, auth_token):
        """PUT /api/auth/profile updates avatar_url successfully"""
        # Get available avatars first
        avatars_response = requests.get(f"{BASE_URL}/api/auth/avatars")
        avatars = avatars_response.json()["avatars"]
        test_avatar = avatars[5]  # Pick a specific avatar
        
        response = requests.put(
            f"{BASE_URL}/api/auth/profile",
            headers={"Authorization": f"Bearer {auth_token}"},
            json={"avatar_url": test_avatar}
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "avatar_url" in data, "Response missing 'avatar_url' field"
        assert data["avatar_url"] == test_avatar, f"Avatar not updated: expected {test_avatar[:50]}, got {data.get('avatar_url', 'None')[:50]}"
        print(f"✓ Avatar updated successfully to: {test_avatar[:60]}...")

    def test_update_avatar_returns_updated_user(self, auth_token):
        """PUT /api/auth/profile returns complete user object with updated avatar"""
        avatars_response = requests.get(f"{BASE_URL}/api/auth/avatars")
        avatars = avatars_response.json()["avatars"]
        test_avatar = avatars[10]
        
        response = requests.put(
            f"{BASE_URL}/api/auth/profile",
            headers={"Authorization": f"Bearer {auth_token}"},
            json={"avatar_url": test_avatar}
        )
        assert response.status_code == 200
        
        data = response.json()
        required_fields = ["id", "username", "email", "role", "avatar_url"]
        for field in required_fields:
            assert field in data, f"Response missing required field: {field}"
        print(f"✓ Response contains all required user fields: {list(data.keys())}")

    def test_update_empty_payload_fails(self, auth_token):
        """PUT /api/auth/profile with empty payload returns 400"""
        response = requests.put(
            f"{BASE_URL}/api/auth/profile",
            headers={"Authorization": f"Bearer {auth_token}"},
            json={}
        )
        assert response.status_code == 400, f"Expected 400 for empty payload, got {response.status_code}"
        print("✓ Empty update payload correctly rejected with 400")

    def test_update_username_rejects_if_taken(self, auth_token):
        """PUT /api/auth/profile rejects username update if already taken"""
        # Try to update to a username we know exists (openclaw agent's actual username)
        response = requests.put(
            f"{BASE_URL}/api/auth/profile",
            headers={"Authorization": f"Bearer {auth_token}"},
            json={"username": "openclaw_test"}  # This is the agent account username
        )
        # Should fail because username is taken
        assert response.status_code == 400, f"Expected 400 for taken username, got {response.status_code}: {response.text}"
        data = response.json()
        assert "taken" in data.get("detail", "").lower() or "username" in data.get("detail", "").lower(), \
            f"Error message should mention username taken: {data}"
        print("✓ Username update correctly rejected when taken")


class TestAuthMeReturnsAvatarUrl:
    """Tests for GET /api/auth/me - returns avatar_url field"""

    @pytest.fixture(scope="class")
    def auth_token(self):
        """Get auth token for test user"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": TEST_USER_EMAIL,
            "password": TEST_USER_PASSWORD
        })
        assert response.status_code == 200, f"Login failed: {response.text}"
        return response.json()["token"]

    def test_auth_me_returns_avatar_url(self, auth_token):
        """GET /api/auth/me includes avatar_url in response"""
        response = requests.get(
            f"{BASE_URL}/api/auth/me",
            headers={"Authorization": f"Bearer {auth_token}"}
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        data = response.json()
        assert "avatar_url" in data, "GET /api/auth/me missing 'avatar_url' field"
        print(f"✓ GET /api/auth/me includes avatar_url: {data.get('avatar_url', 'None')[:50] if data.get('avatar_url') else 'None'}")

    def test_auth_me_avatar_persists_after_update(self, auth_token):
        """Avatar URL persists in /api/auth/me after update"""
        # Update avatar
        avatars_response = requests.get(f"{BASE_URL}/api/auth/avatars")
        test_avatar = avatars_response.json()["avatars"][0]
        
        update_response = requests.put(
            f"{BASE_URL}/api/auth/profile",
            headers={"Authorization": f"Bearer {auth_token}"},
            json={"avatar_url": test_avatar}
        )
        assert update_response.status_code == 200
        
        # Verify with GET /api/auth/me
        me_response = requests.get(
            f"{BASE_URL}/api/auth/me",
            headers={"Authorization": f"Bearer {auth_token}"}
        )
        assert me_response.status_code == 200
        
        me_data = me_response.json()
        assert me_data.get("avatar_url") == test_avatar, \
            f"Avatar not persisted: expected {test_avatar[:50]}, got {me_data.get('avatar_url', 'None')[:50] if me_data.get('avatar_url') else 'None'}"
        print("✓ Avatar URL correctly persists after update")


class TestLoginReturnsAvatarUrl:
    """Tests for POST /api/auth/login - returns avatar_url in user object"""

    def test_login_returns_avatar_url_in_user(self):
        """POST /api/auth/login includes avatar_url in user object"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": TEST_USER_EMAIL,
            "password": TEST_USER_PASSWORD
        })
        assert response.status_code == 200, f"Login failed: {response.text}"
        
        data = response.json()
        assert "user" in data, "Login response missing 'user' object"
        assert "avatar_url" in data["user"], "User object missing 'avatar_url' field"
        print(f"✓ Login returns avatar_url in user: {data['user'].get('avatar_url', 'None')[:50] if data['user'].get('avatar_url') else 'None'}")


class TestRegressionLeaderboard:
    """Regression tests: Leaderboard API still works after avatar changes"""

    def test_leaderboard_returns_top_agents_and_bettors(self):
        """GET /api/leaderboard still returns top_agents and top_bettors"""
        response = requests.get(f"{BASE_URL}/api/leaderboard")
        assert response.status_code == 200, f"Leaderboard failed: {response.status_code}"
        
        data = response.json()
        assert "top_agents" in data, "Leaderboard missing 'top_agents'"
        assert "top_bettors" in data, "Leaderboard missing 'top_bettors'"
        assert isinstance(data["top_agents"], list), "top_agents should be list"
        assert isinstance(data["top_bettors"], list), "top_bettors should be list"
        print(f"✓ REGRESSION: Leaderboard returns {len(data['top_agents'])} agents, {len(data['top_bettors'])} bettors")


class TestRegressionOpenClawAgentAPI:
    """Regression tests: OpenClaw Agent API still works"""

    def test_agent_api_login_works(self):
        """POST /api/agent-api/login still works for agent authentication"""
        response = requests.post(f"{BASE_URL}/api/agent-api/login", json={
            "email": TEST_AGENT_EMAIL,
            "password": TEST_AGENT_PASSWORD
        })
        assert response.status_code == 200, f"Agent API login failed: {response.status_code}: {response.text}"
        
        data = response.json()
        assert "token" in data, "Agent API login missing 'token'"
        assert "agent" in data, "Agent API login missing 'agent'"
        print(f"✓ REGRESSION: OpenClaw Agent API login works, agent: {data['agent'].get('name', 'unknown')}")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
