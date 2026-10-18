import asyncio
import os
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "pokerclaw_test")
os.environ.setdefault("JWT_SECRET", "unit-test-secret-that-is-not-used-in-production")

from routes import tournaments as tournament_routes  # noqa: E402


class _Cursor:
    def __init__(self, documents):
        self.documents = documents

    async def to_list(self, _limit):
        return [document.copy() for document in self.documents]


class _TournamentCollection:
    def __init__(self):
        self.documents = [
            {"id": "t-1", "name": "First flight", "status": "lobby"},
            {"id": "t-2", "name": "Final table", "status": "semis"},
        ]

    def find(self, query, _projection):
        ids = set(query.get("id", {}).get("$in", []))
        return _Cursor([document for document in self.documents if document["id"] in ids])


class _WorkspaceCollection:
    def __init__(self):
        self.documents = {}

    async def find_one(self, query, _projection):
        document = self.documents.get(query["user_id"])
        return document.copy() if document else None

    async def update_one(self, query, update, upsert=False):
        user_id = query["user_id"]
        document = self.documents.get(user_id)
        if document is None and upsert:
            document = update.get("$setOnInsert", {}).copy()
            document["tournament_ids"] = []
            self.documents[user_id] = document
        if document is None:
            return SimpleNamespace(modified_count=0)
        document.update(update.get("$set", {}))
        for tournament_id in update.get("$addToSet", {}).get("tournament_ids", {}).get("$each", []):
            if tournament_id not in document["tournament_ids"]:
                document["tournament_ids"].append(tournament_id)
        if "$pull" in update:
            removed = update["$pull"]["tournament_ids"]
            document["tournament_ids"] = [item for item in document["tournament_ids"] if item != removed]
        return SimpleNamespace(modified_count=1)


@pytest.fixture
def table_pilot_db(monkeypatch):
    database = SimpleNamespace(
        tournaments=_TournamentCollection(),
        table_pilot_workspaces=_WorkspaceCollection(),
    )
    monkeypatch.setattr(tournament_routes, "db", database)
    return database


def test_table_pilot_links_are_ordered_deduplicated_and_private(table_pilot_db):
    async def scenario():
        linked = await tournament_routes.link_table_pilot_tournaments(
            tournament_routes.TablePilotLinkRequest(tournament_ids=["t-2", "t-1", "t-2"]),
            {"id": "club-a"},
        )

        assert linked["tournament_ids"] == ["t-2", "t-1"]
        assert [item["id"] for item in linked["tournaments"]] == ["t-2", "t-1"]
        assert (await tournament_routes.get_table_pilot_workspace({"id": "club-b"}))["tournaments"] == []

    asyncio.run(scenario())


def test_table_pilot_rejects_unknown_tournament(table_pilot_db):
    async def scenario():
        with pytest.raises(HTTPException) as exc:
            await tournament_routes.link_table_pilot_tournaments(
                tournament_routes.TablePilotLinkRequest(tournament_ids=["missing"]),
                {"id": "club-a"},
            )

        assert exc.value.status_code == 404

    asyncio.run(scenario())


def test_table_pilot_unlinks_only_requested_tournament(table_pilot_db):
    async def scenario():
        await tournament_routes.link_table_pilot_tournaments(
            tournament_routes.TablePilotLinkRequest(tournament_ids=["t-1", "t-2"]),
            {"id": "club-a"},
        )

        result = await tournament_routes.unlink_table_pilot_tournament("t-1", {"id": "club-a"})

        assert result["tournament_ids"] == ["t-2"]
        assert [item["id"] for item in result["tournaments"]] == ["t-2"]

    asyncio.run(scenario())
