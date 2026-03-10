"""
Phase 3: Crypto Deposit Monitoring System Tests
Tests for CoinGecko price integration and crypto deposit flow
"""
import pytest
import requests
import os
import uuid
import time

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL').rstrip('/')

# Test credentials
AGENT_EMAIL = "agent@test.com"
AGENT_PASSWORD = "test123"
HUMAN_EMAIL = "human@test.com"
HUMAN_PASSWORD = "test123"


class TestCryptoPrices:
    """Tests for GET /api/crypto/prices - CoinGecko integration"""
    
    def test_crypto_prices_returns_btc_ltc_eth(self):
        """Verify endpoint returns prices for all 3 supported cryptos"""
        response = requests.get(f"{BASE_URL}/api/crypto/prices")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        data = response.json()
        assert "prices" in data, "Response should contain 'prices' key"
        assert "rate" in data, "Response should contain 'rate' key"
        
        prices = data["prices"]
        assert "btc" in prices, "Should have BTC price"
        assert "ltc" in prices, "Should have LTC price"
        assert "eth" in prices, "Should have ETH price"
        
    def test_crypto_prices_structure(self):
        """Verify each crypto has usd price and 24h change"""
        response = requests.get(f"{BASE_URL}/api/crypto/prices")
        assert response.status_code == 200
        
        data = response.json()
        prices = data["prices"]
        
        for crypto in ["btc", "ltc", "eth"]:
            assert "usd" in prices[crypto], f"{crypto} should have 'usd' field"
            assert "change_24h" in prices[crypto], f"{crypto} should have 'change_24h' field"
            assert isinstance(prices[crypto]["usd"], (int, float)), f"{crypto} usd should be numeric"
            assert prices[crypto]["usd"] > 0, f"{crypto} price should be positive"
    
    def test_crypto_prices_rate_info(self):
        """Verify rate info is included"""
        response = requests.get(f"{BASE_URL}/api/crypto/prices")
        assert response.status_code == 200
        
        data = response.json()
        assert data["rate"] == "100 SC per $1 USD", "Rate should be 100 SC per $1"
    
    def test_crypto_prices_no_auth_required(self):
        """Verify endpoint is public"""
        response = requests.get(f"{BASE_URL}/api/crypto/prices")
        assert response.status_code == 200, "Endpoint should be public"


class TestCryptoDepositEndpoint:
    """Tests for POST /api/crypto/deposit"""
    
    @pytest.fixture
    def agent_token(self):
        """Get auth token for agent user"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": AGENT_EMAIL,
            "password": AGENT_PASSWORD
        })
        if response.status_code != 200:
            pytest.skip(f"Agent login failed: {response.text}")
        return response.json()["token"]
    
    @pytest.fixture
    def human_token(self):
        """Get auth token for human user"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": HUMAN_EMAIL,
            "password": HUMAN_PASSWORD
        })
        if response.status_code != 200:
            pytest.skip(f"Human login failed: {response.text}")
        return response.json()["token"]
    
    def test_deposit_requires_auth(self):
        """Verify deposit requires authentication"""
        response = requests.post(f"{BASE_URL}/api/crypto/deposit", json={
            "crypto_type": "btc",
            "tx_hash": "test_hash_no_auth",
            "amount_crypto": 0.01
        })
        assert response.status_code == 401, "Should reject unauthenticated request"
    
    def test_deposit_rejects_human_users(self, human_token):
        """Verify only agent accounts can deposit crypto"""
        response = requests.post(
            f"{BASE_URL}/api/crypto/deposit",
            json={
                "crypto_type": "btc",
                "tx_hash": f"TEST_human_hash_{uuid.uuid4().hex[:8]}",
                "amount_crypto": 0.01
            },
            headers={"Authorization": f"Bearer {human_token}"}
        )
        assert response.status_code == 403, f"Expected 403, got {response.status_code}"
        assert "agent" in response.json().get("detail", "").lower(), "Should mention agent requirement"
    
    def test_deposit_rejects_invalid_crypto_type(self, agent_token):
        """Verify invalid crypto type is rejected"""
        response = requests.post(
            f"{BASE_URL}/api/crypto/deposit",
            json={
                "crypto_type": "doge",
                "tx_hash": f"TEST_invalid_crypto_{uuid.uuid4().hex[:8]}",
                "amount_crypto": 100
            },
            headers={"Authorization": f"Bearer {agent_token}"}
        )
        assert response.status_code == 400, f"Expected 400, got {response.status_code}"
        assert "unsupported" in response.json().get("detail", "").lower() or "btc" in response.json().get("detail", "").lower()
    
    def test_deposit_rejects_negative_amount(self, agent_token):
        """Verify negative amount is rejected"""
        response = requests.post(
            f"{BASE_URL}/api/crypto/deposit",
            json={
                "crypto_type": "btc",
                "tx_hash": f"TEST_neg_amount_{uuid.uuid4().hex[:8]}",
                "amount_crypto": -0.01
            },
            headers={"Authorization": f"Bearer {agent_token}"}
        )
        assert response.status_code == 400, f"Expected 400, got {response.status_code}"
        assert "positive" in response.json().get("detail", "").lower()
    
    def test_deposit_rejects_zero_amount(self, agent_token):
        """Verify zero amount is rejected"""
        response = requests.post(
            f"{BASE_URL}/api/crypto/deposit",
            json={
                "crypto_type": "btc",
                "tx_hash": f"TEST_zero_amount_{uuid.uuid4().hex[:8]}",
                "amount_crypto": 0
            },
            headers={"Authorization": f"Bearer {agent_token}"}
        )
        assert response.status_code == 400, f"Expected 400, got {response.status_code}"
    
    def test_deposit_rejects_duplicate_tx_hash(self, agent_token):
        """Verify duplicate tx_hash is rejected"""
        # The context says 'abc123def456' is already used
        response = requests.post(
            f"{BASE_URL}/api/crypto/deposit",
            json={
                "crypto_type": "btc",
                "tx_hash": "abc123def456",
                "amount_crypto": 0.01
            },
            headers={"Authorization": f"Bearer {agent_token}"}
        )
        assert response.status_code == 400, f"Expected 400 for duplicate hash, got {response.status_code}"
        assert "already" in response.json().get("detail", "").lower()
    
    def test_deposit_creates_pending_deposit_btc(self, agent_token):
        """Test successful BTC deposit creates pending record"""
        unique_hash = f"TEST_btc_{uuid.uuid4().hex}"
        response = requests.post(
            f"{BASE_URL}/api/crypto/deposit",
            json={
                "crypto_type": "btc",
                "tx_hash": unique_hash,
                "amount_crypto": 0.001
            },
            headers={"Authorization": f"Bearer {agent_token}"}
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "deposit_id" in data, "Should return deposit_id"
        assert data["crypto_type"] == "btc"
        assert data["amount_crypto"] == 0.001
        assert data["status"] == "pending"
        assert "sc_amount" in data, "Should calculate SC amount"
        assert "price_usd" in data, "Should include price used"
        assert "usd_value" in data, "Should include USD value"
        
        # Verify SC calculation: 100 SC per $1 USD
        expected_sc = int(data["usd_value"] * 100)
        assert data["sc_amount"] == expected_sc, f"SC should be {expected_sc}, got {data['sc_amount']}"
        
        return data["deposit_id"]
    
    def test_deposit_creates_pending_deposit_eth(self, agent_token):
        """Test successful ETH deposit creates pending record"""
        unique_hash = f"TEST_eth_{uuid.uuid4().hex}"
        response = requests.post(
            f"{BASE_URL}/api/crypto/deposit",
            json={
                "crypto_type": "eth",
                "tx_hash": unique_hash,
                "amount_crypto": 0.1
            },
            headers={"Authorization": f"Bearer {agent_token}"}
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert data["crypto_type"] == "eth"
        assert data["status"] == "pending"
    
    def test_deposit_creates_pending_deposit_ltc(self, agent_token):
        """Test successful LTC deposit creates pending record"""
        unique_hash = f"TEST_ltc_{uuid.uuid4().hex}"
        response = requests.post(
            f"{BASE_URL}/api/crypto/deposit",
            json={
                "crypto_type": "ltc",
                "tx_hash": unique_hash,
                "amount_crypto": 1.0
            },
            headers={"Authorization": f"Bearer {agent_token}"}
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert data["crypto_type"] == "ltc"
        assert data["status"] == "pending"


class TestGetCryptoDeposits:
    """Tests for GET /api/crypto/deposits"""
    
    @pytest.fixture
    def agent_token(self):
        """Get auth token for agent user"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": AGENT_EMAIL,
            "password": AGENT_PASSWORD
        })
        if response.status_code != 200:
            pytest.skip(f"Agent login failed: {response.text}")
        return response.json()["token"]
    
    def test_get_deposits_requires_auth(self):
        """Verify getting deposits requires auth"""
        response = requests.get(f"{BASE_URL}/api/crypto/deposits")
        assert response.status_code == 401
    
    def test_get_deposits_returns_user_deposits(self, agent_token):
        """Verify user can get their deposits"""
        response = requests.get(
            f"{BASE_URL}/api/crypto/deposits",
            headers={"Authorization": f"Bearer {agent_token}"}
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        data = response.json()
        assert isinstance(data, list), "Should return list of deposits"
        
        if len(data) > 0:
            deposit = data[0]
            assert "id" in deposit, "Deposit should have id"
            assert "crypto_type" in deposit, "Deposit should have crypto_type"
            assert "tx_hash" in deposit, "Deposit should have tx_hash"
            assert "amount_crypto" in deposit, "Deposit should have amount_crypto"
            assert "sc_amount" in deposit, "Deposit should have sc_amount"
            assert "confirmations" in deposit, "Deposit should have confirmations"
            assert "status" in deposit, "Deposit should have status"


class TestConfirmDeposit:
    """Tests for POST /api/crypto/deposits/{id}/confirm"""
    
    @pytest.fixture
    def agent_token(self):
        """Get auth token for agent user"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": AGENT_EMAIL,
            "password": AGENT_PASSWORD
        })
        if response.status_code != 200:
            pytest.skip(f"Agent login failed: {response.text}")
        return response.json()["token"]
    
    def test_confirm_requires_auth(self):
        """Verify confirm requires authentication"""
        response = requests.post(f"{BASE_URL}/api/crypto/deposits/fake-id/confirm")
        assert response.status_code == 401
    
    def test_confirm_returns_404_for_invalid_id(self, agent_token):
        """Verify 404 for non-existent deposit"""
        response = requests.post(
            f"{BASE_URL}/api/crypto/deposits/nonexistent-id-12345/confirm",
            headers={"Authorization": f"Bearer {agent_token}"}
        )
        assert response.status_code == 404
    
    def test_full_deposit_confirm_flow(self, agent_token):
        """Test full flow: create deposit -> confirm twice -> SC credited"""
        # Get initial wallet balance
        wallet_before = requests.get(
            f"{BASE_URL}/api/wallet",
            headers={"Authorization": f"Bearer {agent_token}"}
        ).json()
        initial_sc = wallet_before.get("sc_balance", 0)
        
        # Create new deposit
        unique_hash = f"TEST_confirm_flow_{uuid.uuid4().hex}"
        create_resp = requests.post(
            f"{BASE_URL}/api/crypto/deposit",
            json={
                "crypto_type": "btc",
                "tx_hash": unique_hash,
                "amount_crypto": 0.0001
            },
            headers={"Authorization": f"Bearer {agent_token}"}
        )
        assert create_resp.status_code == 200, f"Create failed: {create_resp.text}"
        deposit_data = create_resp.json()
        deposit_id = deposit_data["deposit_id"]
        expected_sc = deposit_data["sc_amount"]
        
        # First confirmation
        confirm1 = requests.post(
            f"{BASE_URL}/api/crypto/deposits/{deposit_id}/confirm",
            headers={"Authorization": f"Bearer {agent_token}"}
        )
        assert confirm1.status_code == 200, f"First confirm failed: {confirm1.text}"
        confirm1_data = confirm1.json()
        assert confirm1_data["confirmations"] == 1, "Should have 1 confirmation"
        assert confirm1_data["status"] == "pending", "Should still be pending after 1 confirm"
        assert confirm1_data["sc_credited"] == 0, "Should not credit SC yet"
        
        # Second confirmation
        confirm2 = requests.post(
            f"{BASE_URL}/api/crypto/deposits/{deposit_id}/confirm",
            headers={"Authorization": f"Bearer {agent_token}"}
        )
        assert confirm2.status_code == 200, f"Second confirm failed: {confirm2.text}"
        confirm2_data = confirm2.json()
        assert confirm2_data["confirmations"] == 2, "Should have 2 confirmations"
        assert confirm2_data["status"] == "confirmed", "Should be confirmed after 2 confirms"
        assert confirm2_data["sc_credited"] == expected_sc, f"Should credit {expected_sc} SC"
        
        # Verify wallet balance increased
        wallet_after = requests.get(
            f"{BASE_URL}/api/wallet",
            headers={"Authorization": f"Bearer {agent_token}"}
        ).json()
        final_sc = wallet_after.get("sc_balance", 0)
        assert final_sc == initial_sc + expected_sc, f"Wallet should increase by {expected_sc} SC"
        
        # Verify deposit status in list
        deposits = requests.get(
            f"{BASE_URL}/api/crypto/deposits",
            headers={"Authorization": f"Bearer {agent_token}"}
        ).json()
        
        target_deposit = next((d for d in deposits if d["id"] == deposit_id), None)
        assert target_deposit is not None, "Deposit should be in list"
        assert target_deposit["status"] == "confirmed", "Deposit status should be confirmed"
        assert target_deposit["confirmations"] == 2, "Should have 2 confirmations"
    
    def test_confirm_already_confirmed_deposit(self, agent_token):
        """Verify confirming already confirmed deposit returns error"""
        # First create and fully confirm a deposit
        unique_hash = f"TEST_double_confirm_{uuid.uuid4().hex}"
        create_resp = requests.post(
            f"{BASE_URL}/api/crypto/deposit",
            json={
                "crypto_type": "eth",
                "tx_hash": unique_hash,
                "amount_crypto": 0.001
            },
            headers={"Authorization": f"Bearer {agent_token}"}
        )
        assert create_resp.status_code == 200
        deposit_id = create_resp.json()["deposit_id"]
        
        # Confirm twice
        requests.post(
            f"{BASE_URL}/api/crypto/deposits/{deposit_id}/confirm",
            headers={"Authorization": f"Bearer {agent_token}"}
        )
        requests.post(
            f"{BASE_URL}/api/crypto/deposits/{deposit_id}/confirm",
            headers={"Authorization": f"Bearer {agent_token}"}
        )
        
        # Try third confirmation
        third_confirm = requests.post(
            f"{BASE_URL}/api/crypto/deposits/{deposit_id}/confirm",
            headers={"Authorization": f"Bearer {agent_token}"}
        )
        assert third_confirm.status_code == 400, "Should reject confirming already confirmed deposit"
        assert "already confirmed" in third_confirm.json().get("detail", "").lower()


class TestSCCalculation:
    """Tests for SC calculation: 100 SC per $1 USD"""
    
    @pytest.fixture
    def agent_token(self):
        """Get auth token for agent user"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": AGENT_EMAIL,
            "password": AGENT_PASSWORD
        })
        if response.status_code != 200:
            pytest.skip(f"Agent login failed: {response.text}")
        return response.json()["token"]
    
    def test_sc_calculation_accuracy(self, agent_token):
        """Verify SC = amount_crypto * price_usd * 100"""
        # Get current prices
        prices_resp = requests.get(f"{BASE_URL}/api/crypto/prices")
        prices = prices_resp.json()["prices"]
        
        for crypto_type in ["btc", "eth", "ltc"]:
            price_usd = prices[crypto_type]["usd"]
            amount = 0.01 if crypto_type == "btc" else (0.1 if crypto_type == "eth" else 1.0)
            
            unique_hash = f"TEST_sc_calc_{crypto_type}_{uuid.uuid4().hex}"
            response = requests.post(
                f"{BASE_URL}/api/crypto/deposit",
                json={
                    "crypto_type": crypto_type,
                    "tx_hash": unique_hash,
                    "amount_crypto": amount
                },
                headers={"Authorization": f"Bearer {agent_token}"}
            )
            
            if response.status_code == 200:
                data = response.json()
                expected_usd = amount * price_usd
                expected_sc = int(expected_usd * 100)
                
                # Allow small variance due to price changes between calls
                assert abs(data["sc_amount"] - expected_sc) < expected_sc * 0.05, \
                    f"{crypto_type}: SC {data['sc_amount']} should be ~{expected_sc}"


class TestStripeIntegrationStillWorks:
    """Verify Stripe packages still work alongside crypto"""
    
    def test_stripe_packages_available(self):
        """Verify Stripe packages endpoint still works"""
        response = requests.get(f"{BASE_URL}/api/stripe/packages")
        assert response.status_code == 200
        
        packages = response.json()
        assert len(packages) >= 4, "Should have at least 4 packages"
        
        for pkg in packages:
            assert "id" in pkg
            assert "sc_amount" in pkg
            assert "price_usd" in pkg


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
