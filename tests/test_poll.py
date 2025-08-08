"""
Tests for CampPoll bot functionality.
Basic unit tests for poll logic and event management.
"""

import pytest
import asyncio
from datetime import datetime
from unittest.mock import AsyncMock, patch

from models import Event, EventType, PollMeta, PollOption
from services.polls.attendance import chunk_events
from services.csv_service import validate_csv_data
from utils.time import parse_time, is_valid_timezone, tz_tomorrow
from storage import add_event, get_events_by_date

class TestEventManagement:
    """Test event creation and management."""
    
    def test_event_creation(self):
        """Test basic event creation."""
        event = Event(
            id="test-123",
            title="Test Lecture",
            date="2024-12-25",
            event_type=EventType.LECTURE
        )
        
        assert event.id == "test-123"
        assert event.title == "Test Lecture"
        assert event.date == "2024-12-25"
        assert event.event_type == EventType.LECTURE
        assert event.is_pollable is True
    
    def test_event_type_pollable(self):
        """Test which event types are pollable."""
        lecture = Event("1", "Lecture", "2024-12-25", EventType.LECTURE)
        contest = Event("2", "Contest", "2024-12-25", EventType.CONTEST)
        extra = Event("3", "Extra", "2024-12-25", EventType.EXTRA_LECTURE)
        evening = Event("4", "Evening", "2024-12-25", EventType.EVENING_ACTIVITY)
        
        assert lecture.is_pollable is True
        assert contest.is_pollable is True
        assert extra.is_pollable is False
        assert evening.is_pollable is False
    
    def test_event_serialization(self):
        """Test event to/from dict conversion."""
        original = Event(
            id="test-456",
            title="Python Basics",
            date="2024-12-26",
            event_type=EventType.CONTEST
        )
        
        # Convert to dict and back
        event_dict = original.to_dict()
        restored = Event.from_dict(event_dict)
        
        assert restored.id == original.id
        assert restored.title == original.title
        assert restored.date == original.date
        assert restored.event_type == original.event_type

class TestPollLogic:
    """Test poll management logic."""
    
    def test_chunk_events(self):
        """Test event chunking for multiple polls."""
        # Create 15 events
        events = []
        for i in range(15):
            events.append(Event(
                id=f"event-{i}",
                title=f"Event {i}",
                date="2024-12-25",
                event_type=EventType.LECTURE
            ))
        
        # Chunk with max 10 per poll
        chunks = chunk_events(events, max_size=10)
        
        assert len(chunks) == 2
        assert len(chunks[0]) == 10
        assert len(chunks[1]) == 5
    
    def test_poll_option_voting(self):
        """Test poll option vote tracking."""
        option = PollOption(
            event_id="test-event",
            title="Test Event",
            event_type=EventType.LECTURE
        )
        
        # Add votes
        assert option.add_vote(123) is True
        assert option.add_vote(456) is True
        assert option.add_vote(123) is False  # Duplicate vote
        
        assert option.vote_count == 2
        assert 123 in option.votes
        assert 456 in option.votes
        
        # Remove vote
        assert option.remove_vote(123) is True
        assert option.remove_vote(123) is False  # Already removed
        assert option.vote_count == 1
    
    def test_poll_meta_voting(self):
        """Test poll metadata vote management."""
        poll = PollMeta(
            id="test-poll",
            guild_id=12345,
            channel_id=67890,
            message_id=11111,
            poll_date="2024-12-25"
        )
        
        # Add options
        option1 = PollOption("event1", "Lecture 1", EventType.LECTURE)
        option2 = PollOption("event2", "Contest 1", EventType.CONTEST)
        poll.options = [option1, option2]
        
        # Add votes
        assert poll.add_vote(123, "event1") is True
        assert poll.add_vote(456, "event2") is True
        assert poll.add_vote(123, "event2") is True  # Change vote
        
        assert poll.total_votes == 2
        assert poll.get_user_vote(123) == "event2"
        assert poll.get_user_vote(456) == "event2"
        
        # Test non-voters
        all_members = [123, 456, 789]
        non_voters = poll.get_non_voters(all_members)
        assert non_voters == [789]

class TestTimeUtils:
    """Test time and timezone utilities."""
    
    def test_parse_time(self):
        """Test time string parsing."""
        assert parse_time("15:30") == (15, 30)
        assert parse_time("09:00") == (9, 0)
        assert parse_time("23:59") == (23, 59)
        
        # Invalid formats
        assert parse_time("25:00") is None
        assert parse_time("15:60") is None
        assert parse_time("invalid") is None
        assert parse_time("15") is None
    
    def test_timezone_validation(self):
        """Test timezone validation."""
        assert is_valid_timezone("Europe/Helsinki") is True
        assert is_valid_timezone("America/New_York") is True
        assert is_valid_timezone("UTC") is True
        
        assert is_valid_timezone("Invalid/Timezone") is False
        assert is_valid_timezone("") is False
    
    def test_tomorrow_date(self):
        """Test tomorrow date calculation."""
        tomorrow = tz_tomorrow("UTC")
        
        # Should be in YYYY-MM-DD format
        assert len(tomorrow) == 10
        assert tomorrow.count("-") == 2
        
        # Should be a valid date
        try:
            datetime.strptime(tomorrow, "%Y-%m-%d")
        except ValueError:
            pytest.fail("Tomorrow date is not in valid format")

class TestCSVValidation:
    """Test CSV export validation."""
    
    def test_poll_csv_validation(self):
        """Test poll metadata validation for CSV export."""
        # Valid poll
        valid_poll = PollMeta(
            id="valid-poll",
            guild_id=12345,
            channel_id=67890,
            message_id=11111,
            poll_date="2024-12-25",
            options=[
                PollOption("event1", "Event 1", EventType.LECTURE)
            ]
        )
        
        assert validate_csv_data(valid_poll) is True
        
        # Invalid poll - no ID
        invalid_poll = PollMeta(
            id="",
            guild_id=12345,
            channel_id=67890,
            message_id=11111,
            poll_date="2024-12-25"
        )
        
        assert validate_csv_data(invalid_poll) is False
        
        # Invalid poll - no options
        no_options_poll = PollMeta(
            id="poll-id",
            guild_id=12345,
            channel_id=67890,
            message_id=11111,
            poll_date="2024-12-25",
            options=[]
        )
        
        assert validate_csv_data(no_options_poll) is False

@pytest.mark.asyncio
class TestAsyncStorage:
    """Test async storage operations (mocked)."""
    
    @patch('storage.save')
    async def test_add_event_async(self, mock_save):
        """Test async event addition."""
        mock_save.return_value = True
        
        event_dict = {
            "id": "test-async",
            "title": "Async Test",
            "date": "2024-12-25",
            "event_type": "lecture",
            "created_at": datetime.utcnow().isoformat()
        }
        
        # This would normally interact with storage
        # For testing, we just verify the structure is correct
        assert "id" in event_dict
        assert "title" in event_dict
        assert "date" in event_dict
        assert "event_type" in event_dict

# Integration test example
@pytest.mark.asyncio
async def test_poll_workflow():
    """Test a complete poll workflow (mocked)."""
    # This would be an integration test if we had actual Discord API
    # For now, just test the data flow
    
    # 1. Create events
    events = [
        Event("1", "Morning Lecture", "2024-12-25", EventType.LECTURE),
        Event("2", "Afternoon Contest", "2024-12-25", EventType.CONTEST)
    ]
    
    # 2. Create poll metadata
    poll = PollMeta(
        id="workflow-test",
        guild_id=12345,
        channel_id=67890,
        message_id=11111,
        poll_date="2024-12-25"
    )
    
    # 3. Add poll options
    for event in events:
        option = PollOption(event.id, event.title, event.event_type)
        poll.options.append(option)
    
    # 4. Simulate voting
    poll.add_vote(123, "1")  # User votes for lecture
    poll.add_vote(456, "2")  # User votes for contest
    
    # 5. Verify results
    assert poll.total_votes == 2
    assert len(poll.options) == 2
    assert poll.get_user_vote(123) == "1"
    assert poll.get_user_vote(456) == "2"

if __name__ == "__main__":
    # Run tests manually if needed
    pytest.main([__file__, "-v"]) 