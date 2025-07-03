# pylint: disable=import-error

import pytest
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from utils.time import (
    create_scheduled_time,
    next_occurrence,
    get_time_until,
    chunk_by_days,
    to_unix_timestamp,
    get_discord_timestamp,
)

# Freeze current time for deterministic tests
class FixedDateTime(datetime):
    """Subclass of datetime to control now()."""

    @classmethod
    def now(cls, tz=None):  # type: ignore[override]
        return datetime(2024, 1, 1, 12, 0, 0, tzinfo=tz or timezone.utc)


def test_create_scheduled_time_valid(monkeypatch):
    monkeypatch.setattr("utils.time.datetime", FixedDateTime)

    scheduled = create_scheduled_time("2024-01-02", "15:30", "Europe/Helsinki")
    assert scheduled is not None
    assert scheduled.hour == 15 and scheduled.minute == 30
    assert scheduled.tzinfo == ZoneInfo("Europe/Helsinki")


def test_create_scheduled_time_invalid():
    # Invalid time string should return None
    assert create_scheduled_time("2024-01-02", "25:00", "UTC") is None


def test_next_occurrence_same_day(monkeypatch):
    # Freeze time at 12:00 UTC, expect next_occurrence at 13:00 same day
    monkeypatch.setattr("utils.time.datetime", FixedDateTime)
    next_time = next_occurrence("13:00", "UTC")
    assert next_time is not None
    assert next_time.date() == datetime(2024, 1, 1, tzinfo=timezone.utc).date()
    assert next_time.hour == 13 and next_time.minute == 0


def test_next_occurrence_next_day(monkeypatch):
    # Asking for 11:00 when now is 12:00 should schedule for next day
    monkeypatch.setattr("utils.time.datetime", FixedDateTime)
    next_time = next_occurrence("11:00", "UTC")
    assert next_time is not None
    assert next_time > FixedDateTime.now(timezone.utc)
    assert (next_time - FixedDateTime.now(timezone.utc)) >= timedelta(hours=23)


def test_get_time_until(monkeypatch):
    monkeypatch.setattr("utils.time.datetime", FixedDateTime)

    target = FixedDateTime.now(timezone.utc) + timedelta(hours=2, minutes=30)
    result = get_time_until(target)
    assert "2 hour" in result and "30 minute" in result

    past_target = FixedDateTime.now(timezone.utc) - timedelta(minutes=5)
    assert get_time_until(past_target) == "Time has passed"


def test_chunk_by_days():
    dates = chunk_by_days("2024-12-25", "2024-12-28")
    assert dates == [
        "2024-12-25",
        "2024-12-26",
        "2024-12-27",
        "2024-12-28",
    ] 


def test_to_unix_timestamp():
    """Test conversion of datetime to Unix timestamp."""
    # Test with a fixed datetime
    dt = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    timestamp = to_unix_timestamp(dt)
    
    # 2024-01-01 12:00:00 UTC = 1704110400
    assert timestamp == 1704110400
    
    # Test with a different timezone
    dt_helsinki = datetime(2024, 1, 1, 12, 0, 0, tzinfo=ZoneInfo("Europe/Helsinki"))
    timestamp_helsinki = to_unix_timestamp(dt_helsinki)
    
    # Should be 2 hours earlier than UTC (10:00 UTC)
    assert timestamp_helsinki == 1704110400 - 7200


def test_get_discord_timestamp():
    """Test creation of Discord-formatted timestamps."""
    # Test with default style
    timestamp_str = get_discord_timestamp("2024-01-01", "12:00", "UTC", "f")
    assert timestamp_str.startswith("<t:")
    assert timestamp_str.endswith(":f>")
    
    # Extract the timestamp part and verify it's correct
    timestamp_part = int(timestamp_str.split(":")[1])
    assert timestamp_part == 1704110400
    
    # Test with different style
    timestamp_str_relative = get_discord_timestamp("2024-01-01", "12:00", "UTC", "R")
    assert timestamp_str_relative.endswith(":R>")
    
    # Test with invalid date/time
    timestamp_str_invalid = get_discord_timestamp("invalid", "12:00", "UTC")
    assert timestamp_str_invalid == "invalid 12:00"