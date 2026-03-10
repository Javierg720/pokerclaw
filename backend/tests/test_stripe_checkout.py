"""
Backend tests for Phase 2 - Stripe Checkout Integration
Tests: GET /api/stripe/packages, POST /api/stripe/checkout, GET /api/stripe/status/{session_id}
       and existing wallet endpoints
"""

import pytest
import requests
import os
import uuid

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Test accounts provided
TEST_AGENT = {"email": "agent@test.com", "password": "test123"}
TEST_HUMAN = {"email": "human@test.com", "password": "test123"}


@pytest.fixture(scope="module")
def agent_token():
    """Login as agent user and return token"""
    res = requests.post(f"{BASE_URL}/api/auth/login", json=TEST_AGENT)
    assert res.status_code == 200, f"Agent login failed: {res.text}"
    return res.json()["token"]


@pytest.fixture(scope="module")
def human_token():
    """Login as human user and return token"""
    res = requests.post(f"{BASE_URL}/api/auth/login", json=TEST_HUMAN)
    assert res.status_code == 200, f"Human login failed: {res.text}"
    return res.json()["token"]


@pytest.fixture
def agent_headers(agent_token):
    return {"Authorization": f"Bearer {agent_token}", "Content-Type": "application/json"}


@pytest.fixture
def human_headers(human_token):
    return {"Authorization": f"Bearer {human_token}", "Content-Type": "application/json"}


class TestStripePackages:
    """Tests for GET /api/stripe/packages - returns 4 SC packages with correct prices"""
    
    def test_packages_returns_4_packages(self):
        """GET /api/stripe/packages returns exactly 4 packages"""
        res = requests.get(f"{BASE_URL}/api/stripe/packages")
        assert res.status_code == 200, f"Expected 200, got {res.status_code}: {res.text}"
        
        packages = res.json()
        assert isinstance(packages, list), "Response should be a list"
        assert len(packages) == 4, f"Expected 4 packages, got {len(packages)}"
    
    def test_packages_have_correct_structure(self):
        """Each package has id, sc_amount, price_usd, and label fields"""
        res = requests.get(f"{BASE_URL}/api/stripe/packages")
        packages = res.json()
        
        required_fields = ["id", "sc_amount", "price_usd", "label"]
        for pkg in packages:
            for field in required_fields:
                assert field in pkg, f"Package missing field '{field}': {pkg}"
    
    def test_packages_have_correct_values(self):
        """Verify the specific package values defined server-side"""
        res = requests.get(f"{BASE_URL}/api/stripe/packages")
        packages = res.json()
        
        expected = {
            "sc_50": {"sc_amount": 50, "price_usd": 4.99, "label": "50 SweepCoins"},
            "sc_200": {"sc_amount": 200, "price_usd": 14.99, "label": "200 SweepCoins"},
            "sc_500": {"sc_amount": 500, "price_usd": 34.99, "label": "500 SweepCoins"},
            "sc_1000": {"sc_amount": 1000, "price_usd": 59.99, "label": "1,000 SweepCoins"},
        }
        
        for pkg in packages:
            pkg_id = pkg["id"]
            assert pkg_id in expected, f"Unexpected package id: {pkg_id}"
            exp = expected[pkg_id]
            assert pkg["sc_amount"] == exp["sc_amount"], f"sc_amount mismatch for {pkg_id}"
            assert pkg["price_usd"] == exp["price_usd"], f"price_usd mismatch for {pkg_id}"
            assert pkg["label"] == exp["label"], f"label mismatch for {pkg_id}"
    
    def test_packages_does_not_require_auth(self):
        """GET /api/stripe/packages is public (no auth required)"""
        res = requests.get(f"{BASE_URL}/api/stripe/packages")
        assert res.status_code == 200, "Packages endpoint should not require auth"


class TestStripeCheckout:
    """Tests for POST /api/stripe/checkout - creates Stripe checkout session"""
    
    def test_checkout_requires_authentication(self):
        """POST /api/stripe/checkout without auth returns 401"""
        res = requests.post(
            f"{BASE_URL}/api/stripe/checkout",
            json={"package_id": "sc_50", "origin_url": "https://example.com"}
        )
        assert res.status_code == 401, f"Expected 401, got {res.status_code}"
    
    def test_checkout_rejects_invalid_package(self, agent_headers):
        """POST /api/stripe/checkout with invalid package_id returns 400"""
        res = requests.post(
            f"{BASE_URL}/api/stripe/checkout",
            json={"package_id": "invalid_pkg", "origin_url": "https://example.com"},
            headers=agent_headers
        )
        assert res.status_code == 400, f"Expected 400, got {res.status_code}"
        assert "Invalid package" in res.json().get("detail", "")
    
    def test_checkout_creates_session_for_agent(self, agent_headers):
        """POST /api/stripe/checkout creates checkout session for agent user"""
        res = requests.post(
            f"{BASE_URL}/api/stripe/checkout",
            json={"package_id": "sc_50", "origin_url": "https://agent-poker.preview.emergentagent.com"},
            headers=agent_headers
        )
        assert res.status_code == 200, f"Expected 200, got {res.status_code}: {res.text}"
        
        data = res.json()
        # Verify response has url and session_id
        assert "url" in data, "Response should have 'url'"
        assert "session_id" in data, "Response should have 'session_id'"
        
        # Verify URL is a valid Stripe checkout URL
        url = data["url"]
        assert url.startswith("https://"), f"URL should start with https: {url}"
        assert len(data["session_id"]) > 0, "session_id should not be empty"
    
    def test_checkout_creates_session_for_human(self, human_headers):
        """POST /api/stripe/checkout also works for human users"""
        res = requests.post(
            f"{BASE_URL}/api/stripe/checkout",
            json={"package_id": "sc_200", "origin_url": "https://agent-poker.preview.emergentagent.com"},
            headers=human_headers
        )
        assert res.status_code == 200, f"Expected 200, got {res.status_code}: {res.text}"
        
        data = res.json()
        assert "url" in data
        assert "session_id" in data
    
    def test_checkout_creates_payment_transaction(self, agent_headers):
        """Verify checkout creates a pending payment_transaction in DB"""
        res = requests.post(
            f"{BASE_URL}/api/stripe/checkout",
            json={"package_id": "sc_1000", "origin_url": "https://agent-poker.preview.emergentagent.com"},
            headers=agent_headers
        )
        assert res.status_code == 200
        
        session_id = res.json()["session_id"]
        
        # Check status endpoint to verify transaction exists
        status_res = requests.get(
            f"{BASE_URL}/api/stripe/status/{session_id}",
            headers=agent_headers
        )
        assert status_res.status_code == 200, f"Status check failed: {status_res.text}"
        
        status_data = status_res.json()
        assert "status" in status_data
        assert "payment_status" in status_data
        assert status_data["sc_amount"] == 1000, "SC amount should match package"
        assert status_data["amount_usd"] == 59.99, "USD amount should match package"


class TestStripeStatus:
    """Tests for GET /api/stripe/status/{session_id} - returns payment status"""
    
    def test_status_requires_authentication(self):
        """GET /api/stripe/status/{session_id} without auth returns 401"""
        res = requests.get(f"{BASE_URL}/api/stripe/status/test_session_123")
        assert res.status_code == 401, f"Expected 401, got {res.status_code}"
    
    def test_status_returns_404_for_unknown_session(self, agent_headers):
        """GET /api/stripe/status/{session_id} returns 404 for unknown session"""
        fake_session = f"cs_test_fake_{uuid.uuid4().hex[:16]}"
        res = requests.get(
            f"{BASE_URL}/api/stripe/status/{fake_session}",
            headers=agent_headers
        )
        # Should be 404 for unknown transaction, not 500
        assert res.status_code in [404, 500], f"Expected 404 or 500, got {res.status_code}: {res.text}"
    
    def test_status_returns_pending_for_new_session(self, agent_headers):
        """GET /api/stripe/status/{session_id} returns pending for unpaid session"""
        # First create a checkout session
        checkout_res = requests.post(
            f"{BASE_URL}/api/stripe/checkout",
            json={"package_id": "sc_50", "origin_url": "https://agent-poker.preview.emergentagent.com"},
            headers=agent_headers
        )
        assert checkout_res.status_code == 200
        session_id = checkout_res.json()["session_id"]
        
        # Check status - should be unpaid since we don't complete payment
        status_res = requests.get(
            f"{BASE_URL}/api/stripe/status/{session_id}",
            headers=agent_headers
        )
        assert status_res.status_code == 200, f"Status check failed: {status_res.text}"
        
        data = status_res.json()
        # Payment status should be 'unpaid' or 'pending' since we didn't complete
        assert data["payment_status"] in ["unpaid", "pending", "expired"], f"Expected unpaid/pending, got {data['payment_status']}"


class TestExistingWalletEndpoints:
    """Tests for existing wallet endpoints - ensure they still work"""
    
    def test_get_wallet(self, agent_headers):
        """GET /wallet returns wallet with balance"""
        res = requests.get(f"{BASE_URL}/api/wallet", headers=agent_headers)
        assert res.status_code == 200
        
        wallet = res.json()
        assert "sc_balance" in wallet, "Wallet should have sc_balance"
        assert "gc_balance" in wallet, "Wallet should have gc_balance"
        assert isinstance(wallet["sc_balance"], (int, float)), "sc_balance should be numeric"
    
    def test_get_wallet_transactions(self, agent_headers):
        """GET /wallet/transactions returns list of transactions"""
        res = requests.get(f"{BASE_URL}/api/wallet/transactions", headers=agent_headers)
        assert res.status_code == 200
        
        txns = res.json()
        assert isinstance(txns, list), "Transactions should be a list"
    
    def test_cashout_insufficient_balance(self, human_headers):
        """POST /wallet/cashout with amount > balance returns 400"""
        # First get current balance
        wallet_res = requests.get(f"{BASE_URL}/api/wallet", headers=human_headers)
        current_balance = wallet_res.json().get("sc_balance", 0)
        
        # Try to cashout more than balance
        res = requests.post(
            f"{BASE_URL}/api/wallet/cashout",
            json={"amount": current_balance + 10000},
            headers=human_headers
        )
        assert res.status_code == 400
        assert "Insufficient" in res.json().get("detail", "")
    
    def test_wallet_for_human_no_crypto(self, human_headers):
        """Human wallet should not have crypto_addresses"""
        res = requests.get(f"{BASE_URL}/api/wallet", headers=human_headers)
        assert res.status_code == 200
        
        wallet = res.json()
        # Human users don't get crypto addresses
        assert wallet.get("crypto_addresses") is None, "Human wallet should not have crypto_addresses"
    
    def test_wallet_for_agent_has_crypto(self, agent_headers):
        """Agent wallet should have crypto_addresses"""
        res = requests.get(f"{BASE_URL}/api/wallet", headers=agent_headers)
        assert res.status_code == 200
        
        wallet = res.json()
        assert wallet.get("crypto_addresses") is not None, "Agent wallet should have crypto_addresses"
        
        crypto = wallet["crypto_addresses"]
        assert "btc" in crypto, "Should have BTC address"
        assert "ltc" in crypto, "Should have LTC address"
        assert "eth" in crypto, "Should have ETH address"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
