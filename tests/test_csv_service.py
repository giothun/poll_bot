# pylint: disable=import-error

"""Unit tests for services.csv_service functions."""

import pytest
import pandas as pd
from io import BytesIO
from datetime import datetime

from models import PollMeta, PollOption, EventType
from services.csv_service import (
    create_attendance_csv,
    create_summary_csv,
    export_user_votes,
)


@pytest.fixture()
def sample_poll_meta():
    """Return a PollMeta with two options and user votes."""
    option1 = PollOption("evt1", "Lecture: Intro", EventType.LECTURE, votes=[1001, 1002])
    option2 = PollOption("evt2", "Contest: Challenge", EventType.CONTEST, votes=[1002, 1003])

    return PollMeta(
        id="poll-xyz",
        guild_id=123,
        channel_id=456,
        message_id=789,
        poll_date="2024-12-25",
        options=[option1, option2],
        published_at=datetime(2024, 12, 24, 15, 0),
        closed_at=datetime(2024, 12, 25, 9, 0),
    )


@pytest.mark.asyncio
async def test_create_attendance_csv(sample_poll_meta):
    guild_members = {1001: "Alice", 1002: "Bob", 1003: "Carol"}
    csv_bytes: BytesIO | None = await create_attendance_csv(sample_poll_meta, guild_members)
    assert csv_bytes is not None

    # Read back into DataFrame to verify contents
    df = pd.read_csv(csv_bytes)
    assert set(df.columns) == {"user_id", "username", "choice"}
    # After de-duplication we expect one row per voter
    assert len(df) == 3
    assert {"Alice", "Bob", "Carol"}.issubset(set(df["username"]))


@pytest.mark.asyncio
async def test_export_user_votes(sample_poll_meta):
    csv_bytes = await export_user_votes(sample_poll_meta)
    assert csv_bytes is not None

    df = pd.read_csv(csv_bytes)
    # There should be one row per (user, vote)
    expected_rows = len(sample_poll_meta.options[0].votes) + len(sample_poll_meta.options[1].votes)
    assert len(df) == expected_rows
    assert set(df["Poll ID"].unique()) == {sample_poll_meta.id}


@pytest.mark.asyncio
async def test_create_summary_csv(sample_poll_meta):
    # Create a second poll with no votes to exercise edge cases
    empty_option = PollOption("evt3", "Lecture: Empty", EventType.LECTURE, votes=[])
    empty_poll = PollMeta(
        id="poll-empty",
        guild_id=123,
        channel_id=456,
        message_id=999,
        poll_date="2024-12-26",
        options=[empty_option],
        published_at=datetime(2024, 12, 25, 15, 0),
    )

    csv_bytes = await create_summary_csv([sample_poll_meta, empty_poll], date_range="2024-12-25 – 2024-12-26")
    assert csv_bytes is not None

    df = pd.read_csv(csv_bytes)
    # There should be at least one header row and some data rows
    assert not df.empty
    # Ensure the summary header row exists
    assert (df["Status"] == "HEADER").any() 