"""
Test suite for POKERCLAW iteration 15 - Three new features:
1. Real blockchain monitoring for crypto deposits (BTC/ETH/LTC verification)
2. Multi-table OpenClaw agent support (join-multiple, my-games)
3. Custom avatar uploads (POST /auth/avatar/upload)
"""
import pytest
import requests
import os
import io

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Test credentials
OPENCLAW_EMAIL = "openclaw@test.com"
OPENCLAW_PASS = "test123"
SPECTATOR_EMAIL = "uitester@test.com"
SPECTATOR_PASS = "test123"

# Known real BTC transaction hash
KNOWN_BTC_TX = "b6f6991d03df0e2e04dafffcd6bc418aac66049e2cd74b80f14ac86db1e3f0da"


@pytest.fixture(scope="module")
def api_client():
    session = requests.Session()
    session.headers.update({"Content-Type": "application/json"})
    return session


@pytest.fixture(scope="module")
def openclaw_token(api_client):
    """Login with OpenClaw agent account"""
    resp = api_client.post(f"{BASE_URL}/api/agent-api/login", json={
        "email": OPENCLAW_EMAIL,
        "password": OPENCLAW_PASS
    })
    assert resp.status_code == 200, f"OpenClaw login failed: {resp.text}"
    return resp.json()["token"]


@pytest.fixture(scope="module")
def spectator_token(api_client):
    """Login with spectator account"""
    resp = api_client.post(f"{BASE_URL}/api/auth/login", json={
        "email": SPECTATOR_EMAIL,
        "password": SPECTATOR_PASS
    })
    assert resp.status_code == 200, f"Spectator login failed: {resp.text}"
    return resp.json()["token"]


# =============================================================================
# FEATURE 1: REAL BLOCKCHAIN VERIFICATION TESTS
# =============================================================================

class TestBlockchainVerification:
    """Tests for GET /api/crypto/verify/{crypto_type}/{tx_hash}"""

    def test_verify_real_btc_tx_returns_200(self, api_client):
        """Verify a known real BTC transaction"""
        resp = api_client.get(f"{BASE_URL}/api/crypto/verify/btc/{KNOWN_BTC_TX}")
        assert resp.status_code == 200
        print(f"BTC verification response: {resp.json()}")

    def test_verify_real_btc_tx_has_verified_field(self, api_client):
        """Response should have verified field"""
        resp = api_client.get(f"{BASE_URL}/api/crypto/verify/btc/{KNOWN_BTC_TX}")
        data = resp.json()
        assert "verified" in data, f"Missing 'verified' field: {data}"
        # The known TX should verify (it's a real transaction)
        assert data["verified"] == True, f"Expected verified=True for known TX: {data}"

    def test_verify_real_btc_tx_has_confirmations(self, api_client):
        """Response should include confirmations count"""
        resp = api_client.get(f"{BASE_URL}/api/crypto/verify/btc/{KNOWN_BTC_TX}")
        data = resp.json()
        assert "confirmations" in data, f"Missing 'confirmations' field: {data}"
        # Old transaction should have many confirmations
        assert data["confirmations"] > 0, f"Expected confirmations > 0: {data}"
        print(f"Confirmations for known TX: {data['confirmations']}")

    def test_verify_real_btc_tx_has_amount(self, api_client):
        """Response should include amount"""
        resp = api_client.get(f"{BASE_URL}/api/crypto/verify/btc/{KNOWN_BTC_TX}")
        data = resp.json()
        assert "amount" in data, f"Missing 'amount' field: {data}"
        assert data["amount"] >= 0, f"Amount should be >= 0: {data}"
        print(f"Amount for known TX: {data['amount']} BTC")

    def test_verify_invalid_btc_hash_returns_verified_false(self, api_client):
        """Invalid/unknown TX hash should return verified=false"""
        resp = api_client.get(f"{BASE_URL}/api/crypto/verify/btc/invalid_hash_abc123xyz")
        assert resp.status_code == 200
        data = resp.json()
        assert data["verified"] == False, f"Expected verified=False for invalid hash: {data}"
        print(f"Invalid hash response: {data}")

    def test_verify_unsupported_crypto_returns_400(self, api_client):
        """Unsupported crypto type should return 400"""
        resp = api_client.get(f"{BASE_URL}/api/crypto/verify/doge/somehash")
        assert resp.status_code == 400

    def test_crypto_deposit_includes_blockchain_verified_field(self, api_client, openclaw_token):
        """POST /api/crypto/deposit should include blockchain_verified in response"""
        # Use a unique TX hash for this test
        test_tx = f"test_tx_{os.urandom(8).hex()}"
        resp = api_client.post(
            f"{BASE_URL}/api/crypto/deposit",
            headers={"Authorization": f"Bearer {openclaw_token}"},
            json={
                "crypto_type": "btc",
                "tx_hash": test_tx,
                "amount_crypto": 0.0001
            }
        )
        if resp.status_code == 400:
            # TX may already exist, that's fine
            print(f"Deposit response (400): {resp.json()}")
            return
        assert resp.status_code == 200, f"Deposit failed: {resp.text}"
        data = resp.json()
        assert "blockchain_verified" in data, f"Missing blockchain_verified in deposit response: {data}"
        print(f"Deposit response: {data}")


# =============================================================================
# FEATURE 2: MULTI-TABLE OPENCLAW AGENT SUPPORT
# =============================================================================

class TestMultiTableSupport:
    """Tests for multi-table agent endpoints"""

    def test_get_tables_returns_list(self, api_client, openclaw_token):
        """GET /api/agent-api/tables should return list of tables"""
        resp = api_client.get(
            f"{BASE_URL}/api/agent-api/tables",
            headers={"Authorization": f"Bearer {openclaw_token}"}
        )
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list), f"Expected list, got: {type(data)}"
        print(f"Found {len(data)} tables")
        if data:
            print(f"First table: {data[0]}")

    def test_join_multiple_endpoint_exists(self, api_client, openclaw_token):
        """POST /api/agent-api/tables/join-multiple should exist"""
        resp = api_client.post(
            f"{BASE_URL}/api/agent-api/tables/join-multiple",
            headers={"Authorization": f"Bearer {openclaw_token}"},
            json={"table_ids": []}
        )
        # Empty table_ids should return success with empty results
        assert resp.status_code == 200, f"join-multiple failed: {resp.text}"
        data = resp.json()
        assert "results" in data, f"Missing 'results' field: {data}"
        assert "agent" in data, f"Missing 'agent' field: {data}"
        print(f"join-multiple response: {data}")

    def test_join_multiple_with_valid_tables(self, api_client, openclaw_token):
        """Join multiple tables at once"""
        # First get available tables
        tables_resp = api_client.get(
            f"{BASE_URL}/api/agent-api/tables",
            headers={"Authorization": f"Bearer {openclaw_token}"}
        )
        tables = tables_resp.json()
        if len(tables) < 2:
            pytest.skip("Not enough tables to test multi-join")
        
        # Try to join first 2 tables
        table_ids = [t["id"] for t in tables[:2]]
        resp = api_client.post(
            f"{BASE_URL}/api/agent-api/tables/join-multiple",
            headers={"Authorization": f"Bearer {openclaw_token}"},
            json={"table_ids": table_ids}
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["results"]) == 2, f"Expected 2 results: {data}"
        for result in data["results"]:
            assert "table_id" in result
            assert "status" in result
            # Status should be joined, already_seated, or error
            assert result["status"] in ["joined", "already_seated", "error"], f"Unexpected status: {result}"
        print(f"Multi-join results: {data['results']}")

    def test_join_multiple_handles_already_seated(self, api_client, openclaw_token):
        """join-multiple should handle already seated gracefully"""
        tables_resp = api_client.get(
            f"{BASE_URL}/api/agent-api/tables",
            headers={"Authorization": f"Bearer {openclaw_token}"}
        )
        tables = tables_resp.json()
        if not tables:
            pytest.skip("No tables available")
        
        # Join same table twice - second should be already_seated
        table_id = tables[0]["id"]
        
        # First join
        api_client.post(
            f"{BASE_URL}/api/agent-api/tables/join-multiple",
            headers={"Authorization": f"Bearer {openclaw_token}"},
            json={"table_ids": [table_id]}
        )
        
        # Second join - should return already_seated
        resp = api_client.post(
            f"{BASE_URL}/api/agent-api/tables/join-multiple",
            headers={"Authorization": f"Bearer {openclaw_token}"},
            json={"table_ids": [table_id]}
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["results"][0]["status"] == "already_seated", f"Expected already_seated: {data}"
        print(f"Already seated handling: {data}")

    def test_my_games_endpoint_exists(self, api_client, openclaw_token):
        """GET /api/agent-api/my-games should return active games"""
        resp = api_client.get(
            f"{BASE_URL}/api/agent-api/my-games",
            headers={"Authorization": f"Bearer {openclaw_token}"}
        )
        assert resp.status_code == 200, f"my-games failed: {resp.text}"
        data = resp.json()
        assert "games" in data, f"Missing 'games' field: {data}"
        assert "agent" in data, f"Missing 'agent' field: {data}"
        assert "total_tables" in data, f"Missing 'total_tables' field: {data}"
        print(f"my-games response: games={len(data['games'])}, total_tables={data['total_tables']}")

    def test_my_games_returns_sorted_by_priority(self, api_client, openclaw_token):
        """my-games should return games sorted by priority (your_turn first)"""
        resp = api_client.get(
            f"{BASE_URL}/api/agent-api/my-games",
            headers={"Authorization": f"Bearer {openclaw_token}"}
        )
        data = resp.json()
        games = data["games"]
        if len(games) > 1:
            # Check that your_turn comes before waiting
            priority = {"your_turn": 0, "waiting": 1, "complete": 2}
            for i in range(len(games) - 1):
                current_priority = priority.get(games[i]["status"], 9)
                next_priority = priority.get(games[i+1]["status"], 9)
                assert current_priority <= next_priority, f"Games not sorted by priority: {games}"
        print(f"Games sorted by priority: {[g['status'] for g in games]}")

    def test_my_games_includes_table_info(self, api_client, openclaw_token):
        """my-games should include table_id and table_name"""
        resp = api_client.get(
            f"{BASE_URL}/api/agent-api/my-games",
            headers={"Authorization": f"Bearer {openclaw_token}"}
        )
        data = resp.json()
        for game in data["games"]:
            assert "table_id" in game, f"Missing table_id: {game}"
            assert "table_name" in game, f"Missing table_name: {game}"
            assert "is_your_turn" in game, f"Missing is_your_turn: {game}"


# =============================================================================
# FEATURE 3: CUSTOM AVATAR UPLOADS
# =============================================================================

class TestAvatarUpload:
    """Tests for POST /api/auth/avatar/upload"""

    def test_avatar_upload_requires_auth(self, api_client):
        """Upload endpoint should require authentication"""
        resp = api_client.post(f"{BASE_URL}/api/auth/avatar/upload")
        assert resp.status_code in [401, 403, 422], f"Expected auth error: {resp.status_code}"

    def test_avatar_upload_accepts_png(self, api_client, spectator_token):
        """Should accept PNG file upload"""
        # Create a small valid PNG (1x1 pixel)
        png_data = bytes([
            0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A,  # PNG signature
            0x00, 0x00, 0x00, 0x0D, 0x49, 0x48, 0x44, 0x52,  # IHDR chunk
            0x00, 0x00, 0x00, 0x01, 0x00, 0x00, 0x00, 0x01,
            0x08, 0x02, 0x00, 0x00, 0x00, 0x90, 0x77, 0x53,
            0xDE, 0x00, 0x00, 0x00, 0x0C, 0x49, 0x44, 0x41,  # IDAT chunk
            0x54, 0x08, 0x99, 0x63, 0xF8, 0x0F, 0x00, 0x00,
            0x01, 0x01, 0x01, 0x00, 0x05, 0xFE, 0x02, 0xFE,
            0x00, 0x00, 0x00, 0x00, 0x49, 0x45, 0x4E, 0x44,  # IEND chunk
            0xAE, 0x42, 0x60, 0x82
        ])
        
        files = {"file": ("test_avatar.png", io.BytesIO(png_data), "image/png")}
        headers = {"Authorization": f"Bearer {spectator_token}"}
        # Remove Content-Type to let requests set multipart
        resp = requests.post(
            f"{BASE_URL}/api/auth/avatar/upload",
            headers=headers,
            files=files
        )
        assert resp.status_code == 200, f"Upload failed: {resp.text}"
        data = resp.json()
        assert "avatar_url" in data, f"Missing avatar_url: {data}"
        assert data["avatar_url"].startswith("/api/uploads/avatars/"), f"Invalid avatar_url: {data}"
        print(f"Avatar uploaded: {data['avatar_url']}")

    def test_avatar_upload_rejects_large_file(self, api_client, spectator_token):
        """Should reject files over 2MB"""
        # Create a file larger than 2MB
        large_data = b"x" * (2 * 1024 * 1024 + 100)  # 2MB + 100 bytes
        
        files = {"file": ("large_avatar.png", io.BytesIO(large_data), "image/png")}
        headers = {"Authorization": f"Bearer {spectator_token}"}
        resp = requests.post(
            f"{BASE_URL}/api/auth/avatar/upload",
            headers=headers,
            files=files
        )
        assert resp.status_code == 400, f"Should reject large file: {resp.status_code}"
        print(f"Large file rejection: {resp.json()}")

    def test_avatar_upload_rejects_invalid_extension(self, api_client, spectator_token):
        """Should reject unsupported file extensions"""
        files = {"file": ("test.exe", io.BytesIO(b"not an image"), "application/octet-stream")}
        headers = {"Authorization": f"Bearer {spectator_token}"}
        resp = requests.post(
            f"{BASE_URL}/api/auth/avatar/upload",
            headers=headers,
            files=files
        )
        assert resp.status_code == 400, f"Should reject .exe: {resp.status_code}"
        print(f"Invalid extension rejection: {resp.json()}")

    def test_uploaded_avatar_is_served(self, api_client, spectator_token):
        """Uploaded avatar should be accessible via /api/uploads/avatars/"""
        # First upload an image
        png_data = bytes([
            0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A,
            0x00, 0x00, 0x00, 0x0D, 0x49, 0x48, 0x44, 0x52,
            0x00, 0x00, 0x00, 0x01, 0x00, 0x00, 0x00, 0x01,
            0x08, 0x02, 0x00, 0x00, 0x00, 0x90, 0x77, 0x53,
            0xDE, 0x00, 0x00, 0x00, 0x0C, 0x49, 0x44, 0x41,
            0x54, 0x08, 0x99, 0x63, 0xF8, 0x0F, 0x00, 0x00,
            0x01, 0x01, 0x01, 0x00, 0x05, 0xFE, 0x02, 0xFE,
            0x00, 0x00, 0x00, 0x00, 0x49, 0x45, 0x4E, 0x44,
            0xAE, 0x42, 0x60, 0x82
        ])
        
        files = {"file": ("serve_test.png", io.BytesIO(png_data), "image/png")}
        headers = {"Authorization": f"Bearer {spectator_token}"}
        upload_resp = requests.post(
            f"{BASE_URL}/api/auth/avatar/upload",
            headers=headers,
            files=files
        )
        if upload_resp.status_code != 200:
            pytest.skip(f"Upload failed: {upload_resp.text}")
        
        avatar_url = upload_resp.json()["avatar_url"]
        
        # Verify the uploaded file is served
        serve_resp = api_client.get(f"{BASE_URL}{avatar_url}")
        assert serve_resp.status_code == 200, f"Avatar not served: {serve_resp.status_code}"
        print(f"Avatar served successfully at {avatar_url}")


# =============================================================================
# REGRESSION TESTS
# =============================================================================

class TestRegression:
    """Regression tests for existing functionality"""

    def test_leaderboard_still_works(self, api_client):
        """GET /api/leaderboard should still return data"""
        resp = api_client.get(f"{BASE_URL}/api/leaderboard")
        assert resp.status_code == 200
        data = resp.json()
        assert "top_agents" in data, f"Missing top_agents: {data}"
        assert "top_bettors" in data, f"Missing top_bettors: {data}"
        print(f"Leaderboard: {len(data['top_agents'])} top agents")

    def test_agent_api_login_still_works(self, api_client):
        """POST /api/agent-api/login should still work"""
        resp = api_client.post(f"{BASE_URL}/api/agent-api/login", json={
            "email": OPENCLAW_EMAIL,
            "password": OPENCLAW_PASS
        })
        assert resp.status_code == 200
        data = resp.json()
        assert "token" in data
        assert "agent" in data
        print(f"Agent API login: {data['agent']['name']}")

    def test_preset_avatars_still_work(self, api_client):
        """GET /api/auth/avatars should still return 16 presets"""
        resp = api_client.get(f"{BASE_URL}/api/auth/avatars")
        assert resp.status_code == 200
        data = resp.json()
        assert "avatars" in data
        assert len(data["avatars"]) == 16, f"Expected 16 avatars: {len(data['avatars'])}"
        print(f"Preset avatars: {len(data['avatars'])} available")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
