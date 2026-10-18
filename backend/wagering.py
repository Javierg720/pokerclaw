"""Atomic wager placement and event closure helpers."""
import uuid
from collections.abc import Callable
from datetime import datetime, timezone

from fastapi import HTTPException
from pymongo.errors import DuplicateKeyError, OperationFailure

from deps import client, db, logger


async def place_wager(
    *,
    collection_name: str,
    event_collection_name: str,
    event_id: str,
    event_open_query: dict,
    validate_event: Callable[[dict], None],
    user_id: str,
    agent_id: str,
    amount: int,
    currency: str,
    transaction_type: str,
    idempotency_key: str | None,
) -> dict:
    """Create a wager and its debit/ledger entry in one database transaction."""
    if idempotency_key and len(idempotency_key) > 128:
        raise HTTPException(status_code=400, detail="Idempotency-Key must be 128 characters or fewer")

    bet_id = (
        str(uuid.uuid5(uuid.NAMESPACE_URL, f"{collection_name}:{event_id}:{user_id}:{idempotency_key}"))
        if idempotency_key
        else str(uuid.uuid4())
    )
    bets = db[collection_name]

    async def commit_wager(session):
        existing = await bets.find_one({"id": bet_id}, {"_id": 0}, session=session)
        if existing:
            if (
                existing.get("user_id") != user_id
                or existing.get("agent_id") != agent_id
                or existing.get("amount") != amount
                or existing.get("currency") != currency
            ):
                raise HTTPException(status_code=409, detail="Idempotency-Key was reused with different wager details")
            return existing

        event_query = {"id": event_id, "betting_closed": {"$ne": True}, **event_open_query}
        event = await db[event_collection_name].find_one(event_query, {"_id": 0}, session=session)
        if not event:
            raise HTTPException(status_code=409, detail="Betting is closed for this event")
        validate_event(event)

        # This write conflicts with the close barrier below.
        event_result = await db[event_collection_name].update_one(
            event_query,
            {"$inc": {"bet_sequence": 1}},
            session=session,
        )
        if event_result.modified_count != 1:
            raise HTTPException(status_code=409, detail="Betting is closed for this event")

        balance_field = f"{currency}_balance"
        wallet_result = await db.wallets.update_one(
            {"user_id": user_id, balance_field: {"$gte": amount}},
            {"$inc": {balance_field: -amount}},
            session=session,
        )
        if wallet_result.modified_count != 1:
            raise HTTPException(status_code=400, detail="Insufficient balance")

        now = datetime.now(timezone.utc).isoformat()
        bet = {
            "id": bet_id,
            "user_id": user_id,
            "agent_id": agent_id,
            "amount": amount,
            "currency": currency,
            "status": "pending",
            "payout": 0,
            "created_at": now,
        }
        bet["game_id" if collection_name == "bets" else "tournament_id"] = event_id
        await bets.insert_one(bet, session=session)
        await db.transactions.insert_one(
            {
                "id": f"bet:{bet_id}",
                "user_id": user_id,
                "type": transaction_type,
                "amount": -amount,
                "currency": currency,
                "description": "Bet on game" if collection_name == "bets" else "Tournament bet placed",
                "created_at": now,
            },
            session=session,
        )
        return bet

    try:
        async with await client.start_session() as session:
            # Motor retries transient transaction and uncertain-commit errors.
            return await session.with_transaction(commit_wager)
    except DuplicateKeyError:
        existing = await bets.find_one({"id": bet_id}, {"_id": 0})
        if existing:
            if (
                existing.get("user_id") != user_id
                or existing.get("agent_id") != agent_id
                or existing.get("amount") != amount
                or existing.get("currency") != currency
            ):
                raise HTTPException(
                    status_code=409,
                    detail="Idempotency-Key was reused with different wager details",
                )
            return existing
        raise
    except OperationFailure as error:
        logger.warning("Wager transaction failed safely: %s", error)
        raise HTTPException(
            status_code=503,
            detail="Wager could not be committed atomically. Retry with the same Idempotency-Key.",
        ) from error


async def close_event_betting(event_collection_name: str, event_id: str) -> None:
    """Prevent new wagers before settlement reads the event pool."""
    result = await db[event_collection_name].update_one(
        {"id": event_id, "betting_closed": {"$ne": True}},
        {"$set": {"betting_closed": True, "betting_closed_at": datetime.now(timezone.utc).isoformat()}},
    )
    if result.modified_count == 1:
        return
    event = await db[event_collection_name].find_one({"id": event_id}, {"_id": 0})
    if not event or not event.get("betting_closed"):
        raise RuntimeError(f"Could not close betting for {event_collection_name}/{event_id}")
