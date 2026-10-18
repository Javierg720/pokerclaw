"""Real-Mongo verification for idempotent crypto-to-SC crediting."""
import asyncio
import os
import uuid

import pytest
from motor.motor_asyncio import AsyncIOMotorClient
from pymongo.errors import DuplicateKeyError


# Require explicit opt-in: other unit tests set MONGO_URL to a dummy localhost.
# Never infer that a configured application database is safe for live test writes.
TEST_MONGO_URL = os.environ.get("POKERCLAW_TEST_MONGO_URL", "")


@pytest.mark.skipif(not TEST_MONGO_URL, reason="set POKERCLAW_TEST_MONGO_URL to a test replica set")
def test_concurrent_crypto_confirmation_credits_sc_exactly_once(monkeypatch):
    import deps
    from routes import crypto

    suffix = uuid.uuid4().hex
    user_id = f"crypto-release-{suffix}"
    address = f"release-address-{suffix}"
    tx_hash = suffix * 2

    monkeypatch.setenv("SWEEPSTAKES_PLAY_ENABLED", "1")
    monkeypatch.setenv("SWEEPSTAKES_NO_PURCHASE_ENTRY_ENABLED", "1")
    monkeypatch.setenv("SWEEPSTAKES_FUNDING_ENABLED", "1")
    monkeypatch.setenv("CRYPTO_FUNDING_ENABLED", "1")
    monkeypatch.setenv("SC_PER_USD", "100")
    monkeypatch.setenv("CRYPTO_BTC_CONFIRMATIONS", "2")

    # Exercise the dormant ledger without enabling customer-facing SC funding.
    monkeypatch.setattr(crypto, "crypto_funding_enabled", lambda: True)

    async def test_only_sc_eligibility(_user):
        return None

    monkeypatch.setattr(crypto, "ensure_sc_play_eligible", test_only_sc_eligibility)

    async def verified(*_args):
        await asyncio.sleep(0)
        return {"verified": True, "confirmations": 3, "amount": "0.001", "error": None}

    async def quoted_prices():
        return {"btc": {"usd": 1000, "change_24h": 0}}

    monkeypatch.setattr(crypto, "verify_tx_on_blockchain", verified)
    monkeypatch.setattr(crypto, "get_crypto_prices", quoted_prices)

    async def exercise():
        test_client = AsyncIOMotorClient(TEST_MONGO_URL)
        test_db = test_client[f"pokerclaw_crypto_deposit_{suffix}"]
        monkeypatch.setattr(deps, "client", test_client)
        monkeypatch.setattr(deps, "db", test_db)
        monkeypatch.setattr(crypto, "client", test_client)
        monkeypatch.setattr(crypto, "db", test_db)
        await deps.ensure_database_indexes()
        await deps.db.users.insert_one({"id": user_id, "role": "human"})
        await deps.db.wallets.insert_one({
            "id": f"wallet-{suffix}",
            "user_id": user_id,
            "sc_balance": 0,
            "gc_balance": 0,
            "crypto_addresses": {"btc": address},
        })
        await deps.db.sweepstakes_profiles.insert_one({
            "user_id": user_id,
            "age_verified": True,
            "jurisdiction_allowed": True,
        })

        request = crypto.CryptoDepositRequest(crypto_type="btc", tx_hash=tx_hash)
        user = {"id": user_id, "role": "human"}
        results = await asyncio.gather(*(
            crypto.submit_crypto_deposit(request, user) for _ in range(8)
        ))

        wallet = await deps.db.wallets.find_one({"user_id": user_id}, {"_id": 0})
        assert wallet["sc_balance"] == 100
        assert await deps.db.crypto_deposits.count_documents({"user_id": user_id}) == 1
        assert await deps.db.transactions.count_documents({"id": {"$regex": "^crypto:"}}) == 1
        assert sum(result.get("sc_credited", 0) for result in results) == 100

        with pytest.raises(DuplicateKeyError):
            await deps.db.wallets.insert_one({
                "id": f"wallet-duplicate-{suffix}",
                "user_id": f"duplicate-{suffix}",
                "crypto_addresses": {"btc": address},
            })

        await deps.db.users.delete_one({"id": user_id})
        await deps.db.wallets.delete_many({"user_id": {"$in": [user_id, f"duplicate-{suffix}"]}})
        await deps.db.sweepstakes_profiles.delete_one({"user_id": user_id})
        await deps.db.crypto_deposits.delete_many({"user_id": user_id})
        await deps.db.transactions.delete_many({"user_id": user_id})
        await test_client.drop_database(test_db.name)
        test_client.close()

    asyncio.run(exercise())


@pytest.mark.skipif(not TEST_MONGO_URL, reason="set POKERCLAW_TEST_MONGO_URL to a test replica set")
def test_crypto_redemption_reserves_and_refunds_sc_exactly_once(monkeypatch):
    import deps
    from routes import admin, wallet

    suffix = uuid.uuid4().hex
    user_id = f"redemption-release-{suffix}"
    admin_secret = f"admin-{suffix}"

    monkeypatch.setenv("ADMIN_SECRET", admin_secret)
    monkeypatch.setenv("CRYPTO_REDEMPTION_MIN_SC", "2500")
    monkeypatch.setenv("SC_PER_USD", "100")

    async def eligible(_user):
        return None

    async def quoted_prices():
        return {"btc": {"usd": 50000, "change_24h": 0}}

    monkeypatch.setattr(wallet, "ensure_redemption_eligible", eligible)
    monkeypatch.setattr(wallet, "get_crypto_prices", quoted_prices)

    async def exercise():
        test_client = AsyncIOMotorClient(TEST_MONGO_URL)
        test_db = test_client[f"pokerclaw_crypto_redemption_{suffix}"]
        monkeypatch.setattr(deps, "client", test_client)
        monkeypatch.setattr(deps, "db", test_db)
        monkeypatch.setattr(wallet, "client", test_client)
        monkeypatch.setattr(wallet, "db", test_db)
        monkeypatch.setattr(admin, "client", test_client)
        monkeypatch.setattr(admin, "db", test_db)
        await deps.ensure_database_indexes()
        await deps.db.users.insert_one({"id": user_id, "role": "human"})
        await deps.db.wallets.insert_one({
            "id": f"wallet-{suffix}",
            "user_id": user_id,
            "sc_balance": 5000,
            "gc_balance": 0,
        })

        request = wallet.CashoutRequest(
            amount=2500,
            crypto_type="btc",
            payout_address="bc1q234567890123456789012345678901234567890",
        )
        user = {"id": user_id, "role": "human"}
        results = await asyncio.gather(*(
            wallet.cashout(request, "one-redemption", user) for _ in range(8)
        ))

        assert len({result["id"] for result in results}) == 1
        redemption_id = results[0]["id"]
        stored_wallet = await deps.db.wallets.find_one({"user_id": user_id}, {"_id": 0})
        assert stored_wallet["sc_balance"] == 2500
        assert await deps.db.crypto_redemptions.count_documents({"user_id": user_id}) == 1
        assert await deps.db.transactions.count_documents({"id": f"redemption-hold:{redemption_id}"}) == 1

        rejections = await asyncio.gather(*(
            admin.reject_redemption(
                redemption_id,
                admin.RedemptionRejection(reason="Operator review rejected"),
                admin_secret,
            )
            for _ in range(8)
        ))
        assert {result["status"] for result in rejections} == {"rejected"}
        stored_wallet = await deps.db.wallets.find_one({"user_id": user_id}, {"_id": 0})
        assert stored_wallet["sc_balance"] == 5000
        assert await deps.db.transactions.count_documents({"id": f"redemption-refund:{redemption_id}"}) == 1

        second, third = await asyncio.gather(
            wallet.cashout(request, "second-redemption", user),
            wallet.cashout(request, "third-redemption", user),
        )
        assert second["id"] != third["id"]
        assert await deps.db.crypto_redemptions.count_documents({"status": "review_pending"}) == 2

        async def verified_payout(*_args):
            return {
                "verified": True,
                "confirmations": 3,
                "amount": second["payout_crypto_amount"],
                "error": None,
            }

        monkeypatch.setattr(admin, "verify_tx_on_blockchain", verified_payout)
        paid = await admin.complete_redemption(
            second["id"], admin.RedemptionCompletion(payout_tx_hash="a" * 64), admin_secret,
        )
        assert paid["status"] == "paid"
        await admin.reject_redemption(
            third["id"], admin.RedemptionRejection(reason="Release cleanup refund"), admin_secret,
        )
        stored_wallet = await deps.db.wallets.find_one({"user_id": user_id}, {"_id": 0})
        assert stored_wallet["sc_balance"] == 2500

        await deps.db.users.delete_one({"id": user_id})
        await deps.db.wallets.delete_one({"user_id": user_id})
        await deps.db.crypto_redemptions.delete_many({"user_id": user_id})
        await deps.db.transactions.delete_many({"user_id": user_id})
        await test_client.drop_database(test_db.name)
        test_client.close()

    asyncio.run(exercise())
