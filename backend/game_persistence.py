"""Concurrent-safe poker state transitions and replayable game completion."""
from datetime import datetime, timezone

from fastapi import HTTPException

from deps import db
from bet_settlement import record_agent_game_result, settle_parimutuel_bets
from wagering import close_event_betting


async def claim_table_seat(table: dict, agent_id: str) -> None:
    """Add one agent only if the roster and game pointer remain unchanged."""
    if agent_id in table.get("agent_ids", []):
        return
    if len(table.get("agent_ids", [])) >= 8:
        raise HTTPException(status_code=400, detail="Table is full (max 8 agents)")
    result = await db.tables.update_one(
        {
            "id": table["id"],
            "agent_ids": table.get("agent_ids", []),
            "current_game_id": table.get("current_game_id"),
        },
        {"$addToSet": {"agent_ids": agent_id}},
    )
    if result.modified_count != 1:
        raise HTTPException(status_code=409, detail="Table roster changed concurrently. Refresh and retry.")


async def attach_new_game_to_table(table: dict, game_id: str) -> None:
    """Claim the table's current-game slot once, even with competing starters."""
    result = await db.tables.update_one(
        {
            "id": table["id"],
            "current_game_id": table.get("current_game_id"),
            "agent_ids": table["agent_ids"],
        },
        {"$set": {"current_game_id": game_id, "status": "playing"}},
    )
    if result.modified_count != 1:
        # The freshly inserted game is unreachable if another caller won.
        await db.games.delete_one({"id": game_id})
        raise HTTPException(status_code=409, detail="Table changed concurrently. Refresh and retry.")


async def persist_game_transition(game: dict, expected_revision: int | None) -> None:
    """Advance a game exactly once without overwriting the wager close barrier.

    A wager transaction writes to the same game document. Updating selected
    fields instead of replacing the document preserves its bet_sequence and
    betting_closed fields even if a bet was committed during an agent turn.
    """
    revision_query = (
        {"$exists": False} if expected_revision is None else expected_revision
    )
    query = {"id": game["id"], "game_revision": revision_query}
    complete = game.get("phase") == "complete"
    if not complete:
        query["betting_closed"] = {"$ne": True}

    fields = {
        key: value for key, value in game.items()
        if key not in {"_id", "id", "bet_sequence", "betting_closed",
                       "betting_closed_at", "game_revision"}
    }
    if complete:
        # Close betting and publish the final result in a single atomic write.
        # A concurrent transactional wager will conflict on the game document.
        fields["betting_closed"] = True
        fields["betting_closed_at"] = datetime.now(timezone.utc).isoformat()
    result = await db.games.update_one(
        query,
        {"$set": fields, "$inc": {"game_revision": 1}},
    )
    if result.modified_count != 1:
        raise HTTPException(
            status_code=409,
            detail="Game state changed concurrently. Refresh and retry the turn.",
        )
    game["game_revision"] = (expected_revision or 0) + 1
    if complete:
        game["betting_closed"] = True


async def finalize_completed_game(game: dict) -> None:
    """Apply settlement effects safely again if an earlier request crashed."""
    if game.get("phase") != "complete":
        return
    await close_event_betting("games", game["id"])
    if game.get("winner_id"):
        await record_agent_game_result(game)
    await settle_parimutuel_bets(
        "bets", {"game_id": game["id"]}, game.get("winner_id"),
        "bet_won", "Won bet on game",
    )
    if game.get("table_id"):
        await db.tables.update_one(
            {"id": game["table_id"], "current_game_id": game["id"]},
            {"$set": {"status": "waiting"}},
        )
