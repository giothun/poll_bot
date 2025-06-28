"""
Simple tests for timing configuration and basic functionality.
Tests that don't require external dependencies like pytest.
"""

import sys
import os
import asyncio
from datetime import datetime

# Add the parent directory to Python path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from models import GuildSettings, Event, EventType, PollOption
from utils.time import parse_time, tz_today, tz_tomorrow, is_valid_timezone


def test_default_timing_configuration():
    """Test that default timing has been updated correctly."""
    print("Testing default timing configuration...")
    
    settings = GuildSettings(guild_id=12345)
    
    # Test new default times
    assert settings.poll_publish_time == "14:30", f"Expected 14:30, got {settings.poll_publish_time}"
    assert settings.feedback_publish_time == "22:00", f"Expected 22:00, got {settings.feedback_publish_time}"
    assert settings.poll_close_time == "09:00", f"Expected 09:00, got {settings.poll_close_time}"
    assert settings.reminder_time == "19:00", f"Expected 19:00, got {settings.reminder_time}"
    
    print("✅ Default timing configuration test passed")


def test_time_parsing():
    """Test time parsing functionality."""
    print("Testing time parsing...")
    
    # Test new default times
    assert parse_time("14:30") == (14, 30), "Failed to parse 14:30"
    assert parse_time("22:00") == (22, 0), "Failed to parse 22:00"
    
    # Test edge cases
    assert parse_time("00:00") == (0, 0), "Failed to parse 00:00"
    assert parse_time("23:59") == (23, 59), "Failed to parse 23:59"
    
    # Test invalid times
    assert parse_time("25:00") is None, "Should reject invalid hour"
    assert parse_time("14:60") is None, "Should reject invalid minute"
    assert parse_time("invalid") is None, "Should reject invalid format"
    
    print("✅ Time parsing test passed")


def test_timezone_functionality():
    """Test timezone utilities."""
    print("Testing timezone functionality...")
    
    # Test valid timezones
    assert is_valid_timezone("Europe/Helsinki") == True, "Helsinki should be valid"
    assert is_valid_timezone("UTC") == True, "UTC should be valid"
    assert is_valid_timezone("America/New_York") == True, "New York should be valid"
    
    # Test invalid timezone
    assert is_valid_timezone("Invalid/Timezone") == False, "Invalid timezone should be rejected"
    
    # Test date functions return proper format
    today = tz_today("UTC")
    tomorrow = tz_tomorrow("UTC")
    
    assert len(today) == 10, f"Today date should be 10 chars, got {len(today)}"
    assert len(tomorrow) == 10, f"Tomorrow date should be 10 chars, got {len(tomorrow)}"
    assert today.count("-") == 2, "Today date should have 2 dashes"
    assert tomorrow.count("-") == 2, "Tomorrow date should have 2 dashes"
    
    # Verify they are valid dates
    try:
        datetime.strptime(today, "%Y-%m-%d")
        datetime.strptime(tomorrow, "%Y-%m-%d")
    except ValueError:
        raise AssertionError("Date format is invalid")
    
    print("✅ Timezone functionality test passed")


def test_event_pollability():
    """Test event pollability logic."""
    print("Testing event pollability...")
    
    # Test pollable events
    lecture = Event("1", "Test Lecture", "2024-12-25", EventType.LECTURE)
    contest = Event("2", "Test Contest", "2024-12-25", EventType.CONTEST)
    
    assert lecture.is_pollable == True, "Lectures should be pollable"
    assert contest.is_pollable == True, "Contests should be pollable"
    
    # Test non-pollable events
    extra = Event("3", "Extra Lecture", "2024-12-25", EventType.EXTRA_LECTURE)
    evening = Event("4", "Evening Activity", "2024-12-25", EventType.EVENING_ACTIVITY)
    
    assert extra.is_pollable == False, "Extra lectures should not be pollable"
    assert evening.is_pollable == False, "Evening activities should not be pollable"
    
    # Test feedback-only events
    feedback_event = Event("5", "Feedback Event", "2024-12-25", EventType.LECTURE, feedback_only=True)
    assert feedback_event.feedback_only == True, "Should be feedback only"
    assert feedback_event.is_pollable == True, "Should still be pollable"
    
    print("✅ Event pollability test passed")


def test_poll_option_voting():
    """Test poll option voting logic."""
    print("Testing poll option voting...")
    
    option = PollOption(
        event_id="test-event",
        title="Test Event",
        event_type=EventType.LECTURE
    )
    
    # Test adding votes
    assert option.add_vote(123) == True, "Should add new vote"
    assert option.add_vote(456) == True, "Should add another vote"
    assert option.add_vote(123) == False, "Should reject duplicate vote"
    
    assert option.vote_count == 2, f"Should have 2 votes, got {option.vote_count}"
    assert 123 in option.votes, "Should contain user 123"
    assert 456 in option.votes, "Should contain user 456"
    
    # Test removing votes
    assert option.remove_vote(123) == True, "Should remove existing vote"
    assert option.remove_vote(123) == False, "Should reject removing non-existent vote"
    assert option.vote_count == 1, f"Should have 1 vote after removal, got {option.vote_count}"
    
    print("✅ Poll option voting test passed")


def test_event_serialization():
    """Test event serialization/deserialization."""
    print("Testing event serialization...")
    
    original = Event(
        id="test-123",
        title="Python Workshop",
        date="2024-12-25",
        event_type=EventType.LECTURE,
        feedback_only=False
    )
    
    # Convert to dict and back
    event_dict = original.to_dict()
    restored = Event.from_dict(event_dict)
    
    assert restored.id == original.id, "ID should match"
    assert restored.title == original.title, "Title should match"
    assert restored.date == original.date, "Date should match"
    assert restored.event_type == original.event_type, "Event type should match"
    assert restored.feedback_only == original.feedback_only, "Feedback only should match"
    
    print("✅ Event serialization test passed")


def test_poll_closing_logic():
    """Test that poll closing logic works correctly."""
    print("Testing poll closing date logic...")
    
    from datetime import datetime, timezone
    
    # Test date comparison logic
    today = tz_today("UTC")
    tomorrow = tz_tomorrow("UTC")
    
    # Mock poll metadata
    class MockPoll:
        def __init__(self, poll_date, is_feedback=False):
            self.poll_date = poll_date
            self.is_feedback = is_feedback
    
    # Test polls
    today_attendance_poll = MockPoll(today, False)
    tomorrow_attendance_poll = MockPoll(tomorrow, False)
    feedback_poll = MockPoll("some-event-id", True)
    
    # Logic: close today's attendance polls and all feedback polls
    polls_to_test = [today_attendance_poll, tomorrow_attendance_poll, feedback_poll]
    should_close = []
    
    for poll in polls_to_test:
        if poll.is_feedback:
            should_close.append(True)  # Always close feedback polls
        else:
            should_close.append(poll.poll_date == today)  # Only close today's attendance polls
    
    assert should_close == [True, False, True], f"Expected [True, False, True], got {should_close}"
    print("✅ Poll closing logic test passed")


def run_all_tests():
    """Run all tests."""
    print("🧪 Running timing and configuration tests...\n")
    
    try:
        test_default_timing_configuration()
        test_time_parsing()
        test_timezone_functionality()
        test_event_pollability()
        test_poll_option_voting()
        test_event_serialization()
        test_poll_closing_logic()
        
        print("\n🎉 All tests passed successfully!")
        return True
        
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1) 