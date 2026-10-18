"""Currency-isolated and retry-safe spectator bet settlement."""
from datetime import datetime, timezone

from pymongo.errors import DuplicateKeyError

from deps import db, logger
from sweepstakes import public_config


async def record_agent_game_result(game: dict) -> None:
    """Record agent stats and owner rewards once per completed game."""
    winner_id = game.get("winner_id")
    game_id = game["id"]
    if not winner_id:
        return

    for player in game.get("players", []):
        agent_id = player["agent_id"]
        increments = (
            {
                "wins": 1,
                "total_games": 1,
                "total_chips_won": game.get("final_pot", 0),
            }
            if agent_id == winner_id
            else {"losses": 1, "total_games": 1}
        )
        await db.agents.update_one(
            {"id": agent_id, "completed_game_ids": {"$ne": game_id}},
            {
                "$inc": increments,
                "$addToSet": {"completed_game_ids": game_id},
            },
        )

    if not public_config()["sc_play_enabled"]:
        return

    winner = await db.agents.find_one({"id": winner_id}, {"_id": 0})
    if not winner or not winner.get("owner_id"):
        return

    winnings = game.get("final_pot", 0)
    sc_credit = max(1, winnings // 10)
    await db.wallets.update_one(
        {
            "user_id": winner["owner_id"],
            "credited_game_ids": {"$ne": game_id},
        },
        {
            "$inc": {"sc_balance": sc_credit},
            "$addToSet": {"credited_game_ids": game_id},
        },
    )

    transaction = {
        "id": f"game-win:{game_id}",
        "user_id": winner["owner_id"],
        "type": "game_winnings",
        "amount": sc_credit,
        "currency": "sc",
        "description": f"{winner['name']} won {winnings} chips (pot after 20% rake)",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    try:
        await db.transactions.update_one(
            {"id": transaction["id"]},
            {"$setOnInsert": transaction},
            upsert=True,
        )
    except DuplicateKeyError:
        existing = await db.transactions.find_one({"id": transaction["id"]}, {"_id": 0})
        if not existing or any(
            existing.get(key) != transaction[key]
            for key in ("user_id", "type", "amount", "currency", "description")
        ):
            raise


async def settle_parimutuel_bets(
    collection_name: str,
    event_filter: dict,
    winner_id: str | None,
    transaction_type: str,
    description: str,
) -> None:
    collection = db[collection_name]
    bets = await collection.find(event_filter, {"_id": 0}).to_list(None)

    for currency in ("gc", "sc"):
        currency_bets = [bet for bet in bets if bet.get("currency") == currency]
        unresolved_bets = [
            bet for bet in currency_bets
            if bet.get("status") in {"pending", "settling"}
        ]
        total_pool = sum(bet["amount"] for bet in currency_bets)
        winning_bets = [bet for bet in currency_bets if bet["agent_id"] == winner_id]
        total_winning = sum(bet["amount"] for bet in winning_bets)

        for bet in unresolved_bets:
            if bet["agent_id"] != winner_id or total_winning <= 0:
                await collection.update_one(
                    {"id": bet["id"], "status": {"$in": ["pending", "settling"]}},
                    {"$set": {"status": "lost", "payout": 0}},
                )
                continue

            # Exact integer arithmetic avoids floating-point payout drift,
            # including large pools and amounts above 2**53.
            payout = (bet["amount"] * total_pool * 4) // (total_winning * 5)
            await collection.update_one(
                {"id": bet["id"], "status": "pending"},
                {"$set": {"status": "settling", "payout": payout}},
            )

            wallet_result = await db.wallets.update_one(
                {
                    "user_id": bet["user_id"],
                    "settled_bet_ids": {"$ne": bet["id"]},
                },
                {
                    "$inc": {f"{currency}_balance": payout},
                    "$addToSet": {"settled_bet_ids": bet["id"]},
                },
            )
            if wallet_result.modified_count != 1:
                wallet = await db.wallets.find_one({"user_id": bet["user_id"]}, {"_id": 0})
                settled_bet_ids = (wallet or {}).get("settled_bet_ids") or []
                if not wallet or bet["id"] not in settled_bet_ids:
                    logger.error(
                        "Settlement wallet credit failed for bet %s and user %s",
                        bet["id"], bet["user_id"],
                    )
                    raise RuntimeError(f"Settlement wallet credit failed for bet {bet['id']}")
            transaction = {
                "id": f"settlement:{bet['id']}",
                "user_id": bet["user_id"],
                "type": transaction_type,
                "amount": payout,
                "currency": currency,
                "description": description,
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
            # A retry after the wallet update must still write this ledger record.
            try:
                await db.transactions.update_one(
                    {"id": transaction["id"]}, {"$setOnInsert": transaction}, upsert=True,
                )
            except DuplicateKeyError:
                existing = await db.transactions.find_one({"id": transaction["id"]}, {"_id": 0})
                if not existing or any(
                    existing.get(key) != transaction[key]
                    for key in ("user_id", "type", "amount", "currency", "description")
                ):
                    raise

            await collection.update_one(
                {"id": bet["id"], "status": "settling"},
                {"$set": {"status": "won", "payout": payout}},
            )
