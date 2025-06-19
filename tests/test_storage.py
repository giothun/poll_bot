"""Unit tests for storage helper functions that operate on poll data.

These tests patch internal async helpers so that no real filesystem access
occurs. Only the in-memory logic is validated.
"""

# pylint: disable=import-error

from datetime import datetime, timedelta
from typing import Dict
from types import SimpleNamespace

import pytest

import storage

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class DummyConfig(SimpleNamespace):
    """Minimal replacement for BotConfig used by storage."""

    data_dir: str = "/tmp"


@pytest.fixture(autouse=True)
def patch_config(monkeypatch):
    """Provide a dummy config so storage.get_config does not access env vars."""

    monkeypatch.setattr("config.get_config", lambda: DummyConfig())
    monkeypatch.setattr(storage, "get_config", lambda: DummyConfig())
    yield


# ---------------------------------------------------------------------------
# cleanup_old_polls
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_cleanup_old_polls(monkeypatch):
    """Verify that polls older than *days_old* are removed."""

    recent_poll = {
        "id": "recent",
        "published_at": (datetime.utcnow() - timedelta(days=5)).isoformat(),
    }
    old_poll = {
        "id": "old",
        "published_at": (datetime.utcnow() - timedelta(days=40)).isoformat(),
    }
    polls: Dict[str, Dict] = {"recent": recent_poll, "old": old_poll}

    async def fake_load_polls():  # noqa: D401
        return polls

    saved_polls: Dict[str, Dict] = {}

    async def fake_save_polls(arg):
        nonlocal saved_polls
        saved_polls = arg
        return True

    monkeypatch.setattr(storage, "load_polls", fake_load_polls)
    monkeypatch.setattr(storage, "save_polls", fake_save_polls)

    removed = await storage.cleanup_old_polls(days_old=30)
    assert removed == 1
    assert "old" not in saved_polls and "recent" in saved_polls


# ---------------------------------------------------------------------------
# get_storage_stats
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_storage_stats(monkeypatch):
    """Ensure returned statistics aggregate values from helpers correctly."""

    async def fake_get_file_size(name):  # noqa: D401
        return {"events": 1024, "polls": 2048, "guild_settings": 512}[name]

    async def fake_load_events():
        return [1, 2, 3]

    async def fake_load_polls():
        return {"a": {}, "b": {}}

    monkeypatch.setattr(storage, "get_file_size", fake_get_file_size)
    monkeypatch.setattr(storage, "load_events", fake_load_events)
    monkeypatch.setattr(storage, "load_polls", fake_load_polls)

    stats = await storage.get_storage_stats()

    assert stats["events_count"] == 3
    assert stats["polls_count"] == 2
    # Total size should be sum of individual sizes
    assert stats["total_size_bytes"] == 1024 + 2048 + 512
    # Derived KB value (float) should match bytes / 1024
    assert abs(stats["total_size_kb"] - ((1024 + 2048 + 512) / 1024)) < 0.01 