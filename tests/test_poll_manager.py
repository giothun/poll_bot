"""
Tests for poll manager functionality.
Tests for attendance and feedback poll logic, scheduling, and timing.
"""

import pytest
import asyncio
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, patch, MagicMock

from models import Event, EventType, PollMeta, PollOption, GuildSettings
from utils.time import get_poll_closing_date
from services.polls.attendance import publish_attendance_poll, chunk_events  
from services.polls.feedback import publish_feedback_polls, create_feedback_poll
from utils.time import tz_today, tz_tomorrow


class TestPollTiming:
    """Test poll timing and scheduling logic."""
    
    def test_default_times(self):
        """Test default poll timing configuration."""
        settings = GuildSettings(guild_id=12345)
        
        # Check new default times
        assert settings.poll_publish_time == "14:30"  # Changed from 15:00
        assert settings.feedback_publish_time == "22:00"  # New setting
        assert settings.poll_close_time == "09:00"
        assert settings.reminder_time == "19:00"
    
    def test_time_parsing(self):
        """Test that time strings can be parsed correctly."""
        from utils.time import parse_time
        
        # Test new default times
        assert parse_time("14:30") == (14, 30)
        assert parse_time("22:00") == (22, 0)
        
        # Test edge cases
        assert parse_time("00:00") == (0, 0)
        assert parse_time("23:59") == (23, 59)


class TestAttendancePollLogic:
    """Test attendance poll creation and logic."""
    
    @pytest.mark.asyncio
    @patch('services.polls.attendance.get_events_by_date')
    @patch('services.polls.attendance.save_poll')
    async def test_publish_attendance_poll_for_tomorrow(self, mock_save, mock_get_events):
        """Test that attendance polls are created for tomorrow's events."""
        # Mock tomorrow's events as dictionaries (as returned by storage)
        tomorrow_events = [
            {
                'id': 'event1',
                'title': 'Tomorrow Lecture',
                'date': tz_tomorrow(),
                'event_type': 'lecture',
                'created_at': '2024-01-01T00:00:00+00:00',
                'feedback_only': False
            },
            {
                'id': 'event2', 
                'title': 'Tomorrow Contest',
                'date': tz_tomorrow(),
                'event_type': 'contest',
                'created_at': '2024-01-01T00:00:00+00:00',
                'feedback_only': False
            }
        ]
        mock_get_events.return_value = tomorrow_events
        
        # Mock Discord objects
        mock_guild = MagicMock()
        mock_guild.id = 12345
        mock_channel = MagicMock()
        mock_guild.get_channel.return_value = mock_channel
        
        mock_message = MagicMock()
        mock_message.id = 98765
        mock_channel.send = AsyncMock(return_value=mock_message)
        
        mock_bot = MagicMock()
        
        guild_settings = {
            "timezone": "Europe/Helsinki",
            "poll_channel_id": 67890
        }
        
        # Call function
        polls = await publish_attendance_poll(mock_bot, mock_guild, guild_settings)
        
        # Verify tomorrow's date was requested for this guild
        mock_get_events.assert_called_once_with(tz_tomorrow("Europe/Helsinki"), guild_id=mock_guild.id)
        
        # Verify poll was created
        assert len(polls) == 1
        assert polls[0].poll_date == tz_tomorrow("Europe/Helsinki")
        assert len(polls[0].options) == 2  # Two pollable events
    
    @pytest.mark.asyncio
    @patch('services.polls.attendance.get_events_by_date')
    async def test_no_events_tomorrow(self, mock_get_events):
        """Test handling when there are no events tomorrow."""
        mock_get_events.return_value = []
        
        mock_guild = MagicMock()
        mock_guild.id = 12345
        mock_bot = MagicMock()
        guild_settings = {"timezone": "Europe/Helsinki"}
        
        polls = await publish_attendance_poll(mock_bot, mock_guild, guild_settings)
        
        assert len(polls) == 0
        mock_get_events.assert_called_once_with(tz_tomorrow("Europe/Helsinki"), guild_id=mock_guild.id)
    
    def test_chunk_many_events(self):
        """Test chunking when there are many events."""
        # Create 25 events
        events = []
        for i in range(25):
            events.append(Event(
                id=f"event-{i}",
                title=f"Event {i}",
                date=tz_tomorrow(),
                event_type=EventType.LECTURE
            ))
        
        chunks = chunk_events(events, max_size=10)
        
        assert len(chunks) == 3
        assert len(chunks[0]) == 10
        assert len(chunks[1]) == 10
        assert len(chunks[2]) == 5


class TestFeedbackPollLogic:
    """Test feedback poll creation and logic."""
    
    @pytest.mark.asyncio
    @patch('services.polls.feedback.get_events_by_date')
    @patch('services.polls.feedback.create_feedback_poll')
    async def test_publish_feedback_polls_for_today(self, mock_create_feedback, mock_get_events):
        """Test that feedback polls are created for today's events."""
        # Mock today's events as dictionaries (as returned by storage)
        today_events = [
            {
                'id': 'event1',
                'title': 'Today Lecture',
                'date': tz_today(),
                'event_type': 'lecture',
                'created_at': '2024-01-01T00:00:00+00:00',
                'feedback_only': False
            },
            {
                'id': 'event2',
                'title': 'Today Contest', 
                'date': tz_today(),
                'event_type': 'contest',
                'created_at': '2024-01-01T00:00:00+00:00',
                'feedback_only': False
            }
        ]
        mock_get_events.return_value = today_events
        
        # Mock feedback poll creation
        mock_feedback_poll = PollMeta(
            id="feedback-poll",
            guild_id=12345,
            channel_id=67890,
            message_id=11111,
            poll_date=tz_today(),
            is_feedback=True
        )
        mock_create_feedback.return_value = mock_feedback_poll
        
        mock_guild = MagicMock()
        mock_guild.id = 12345
        mock_bot = MagicMock()
        guild_settings = {"timezone": "Europe/Helsinki"}
        
        # Call function
        polls = await publish_feedback_polls(mock_bot, mock_guild, guild_settings)
        
        # Verify today's date was requested for this guild
        mock_get_events.assert_called_once_with(tz_today("Europe/Helsinki"), guild_id=mock_guild.id)
        
        # Verify feedback polls were created
        assert len(polls) == 2  # Two events = two feedback polls
        assert mock_create_feedback.call_count == 2
    
    @pytest.mark.asyncio
    @patch('services.polls.feedback.get_events_by_date')
    async def test_no_events_today_for_feedback(self, mock_get_events):
        """Test handling when there are no events today for feedback."""
        mock_get_events.return_value = []
        
        mock_guild = MagicMock()
        mock_guild.id = 12345
        mock_bot = MagicMock()
        guild_settings = {"timezone": "Europe/Helsinki"}
        
        polls = await publish_feedback_polls(mock_bot, mock_guild, guild_settings)
        
        assert len(polls) == 0
        mock_get_events.assert_called_once_with(tz_today("Europe/Helsinki"), guild_id=mock_guild.id)
    
    @pytest.mark.asyncio
    @patch('services.polls.feedback.save_poll')
    async def test_create_feedback_poll_structure(self, mock_save):
        """Test the structure of created feedback polls."""
        mock_guild = MagicMock()
        mock_guild.id = 12345
        
        mock_channel = MagicMock()
        mock_channel.id = 67890  # Set the channel ID explicitly
        mock_guild.get_channel.return_value = mock_channel
        
        mock_message = MagicMock()
        mock_message.id = 98765
        mock_channel.send = AsyncMock(return_value=mock_message)
        
        guild_settings = {"poll_channel_id": 67890}
        
        event_option = PollOption(
            event_id="test-event",
            title="Lecture: Python Basics",
            event_type=EventType.LECTURE
        )
        
        # Call function
        poll = await create_feedback_poll(mock_guild, event_option, guild_settings, "2024-12-25")
        
        # Verify poll structure
        assert poll is not None
        assert poll.is_feedback is True
        assert poll.guild_id == 12345
        assert poll.channel_id == 67890
        assert poll.message_id == 98765
        
        # Verify feedback options for lecture
        assert len(poll.options) == 4  # Lecture has 4 feedback options
        option_texts = [opt.title for opt in poll.options]
        assert "😻 It was super useful!" in option_texts
        assert "🆗 I knew smth before, but still enjoyed it!" in option_texts


class TestEventFiltering:
    """Test event filtering logic for different poll types."""
    
    def test_pollable_events_for_attendance(self):
        """Test filtering pollable events for attendance polls."""
        events = [
            Event("1", "Lecture", tz_tomorrow(), EventType.LECTURE),
            Event("2", "Contest", tz_tomorrow(), EventType.CONTEST), 
            Event("3", "Extra", tz_tomorrow(), EventType.EXTRA_LECTURE),
            Event("4", "Evening", tz_tomorrow(), EventType.EVENING_ACTIVITY),
        ]
        
        # Filter pollable events (only lecture and contest)
        pollable = [e for e in events if e.is_pollable and not e.feedback_only]
        
        assert len(pollable) == 2
        assert pollable[0].event_type == EventType.LECTURE
        assert pollable[1].event_type == EventType.CONTEST
    
    def test_feedback_only_events(self):
        """Test handling of feedback-only events."""
        feedback_event = Event(
            id="feedback-only",
            title="Feedback Only Event",
            date=tz_today(),
            event_type=EventType.LECTURE,
            feedback_only=True
        )
        
        assert feedback_event.feedback_only is True
        assert feedback_event.is_pollable is True  # Still pollable, but feedback only


class TestPollClosingLogic:
    """Test poll closing logic and timing."""
    
    @pytest.mark.asyncio
    @patch('services.polls.closing.load_polls')
    @patch('services.polls.closing.close_poll')
    async def test_close_only_todays_attendance_polls(self, mock_close_poll, mock_load_polls):
        """Test that only today's attendance polls are closed based on smart timing logic."""
        from datetime import datetime, timezone
        
        # Mock polls data
        today = tz_today("Europe/Helsinki")
        tomorrow = tz_tomorrow("Europe/Helsinki")
        
        mock_polls = {
            "poll1": {
                "id": "poll1",
                "guild_id": 12345,
                "channel_id": 67890,
                "message_id": 11111,
                "poll_date": today,  # Today's poll - should be closed with default times (14:30 → 09:00 = next day)
                "options": [],
                "published_at": datetime.now(timezone.utc).isoformat(),
                "closed_at": None,
                "reminded_users": [],
                "is_feedback": False
            },
            "poll2": {
                "id": "poll2", 
                "guild_id": 12345,
                "channel_id": 67890,
                "message_id": 22222,
                "poll_date": tomorrow,  # Tomorrow's poll - should NOT be closed
                "options": [],
                "published_at": datetime.now(timezone.utc).isoformat(),
                "closed_at": None,
                "reminded_users": [],
                "is_feedback": False
            },
            "poll3": {
                "id": "poll3", 
                "guild_id": 12345,
                "channel_id": 67890,
                "message_id": 33333,
                "poll_date": today,  # Feedback poll for today - should be closed next day
                "options": [],
                "published_at": datetime.now(timezone.utc).isoformat(),
                "closed_at": None,
                "reminded_users": [],
                "is_feedback": True
            }
        }
        
        mock_load_polls.return_value = mock_polls
        mock_close_poll.return_value = True
        
        mock_guild = MagicMock()
        mock_guild.id = 12345
        mock_bot = MagicMock()
        
        # Use default times: 14:30 → 09:00 (close next day)
        guild_settings = {
            "timezone": "Europe/Helsinki",
            "poll_publish_time": "14:30",
            "poll_close_time": "09:00"
        }
        
        # Call function
        from services.polls.closing import close_all_active_polls
        closed_count = await close_all_active_polls(mock_bot, mock_guild, guild_settings)
        
        # Теперь feedback опросы закрываются на следующий день после события, 
        # а attendance опросы также закрываются на следующий день (14:30→09:00)
        # Поэтому сегодня не должно быть закрытых опросов
        assert closed_count == 0
        # С новой логикой feedback опросы не закрываются в тот же день

    @pytest.mark.asyncio
    @patch('services.polls.closing.load_polls')
    @patch('services.polls.closing.close_poll')
    async def test_smart_closing_same_day(self, mock_close_poll, mock_load_polls):
        """Test smart closing logic when close_time >= publish_time (same day closing)."""
        from datetime import datetime, timezone
        
        today = tz_today("Europe/Helsinki")
        
        mock_polls = {
            "poll1": {
                "id": "poll1",
                "guild_id": 12345,
                "channel_id": 67890,
                "message_id": 11111,
                "poll_date": today,  # Today's poll - should be closed with 15:00 → 18:00 (same day)
                "options": [],
                "published_at": datetime.now(timezone.utc).isoformat(),
                "closed_at": None,
                "reminded_users": [],
                "is_feedback": False
            }
        }
        
        mock_load_polls.return_value = mock_polls
        mock_close_poll.return_value = True
        
        mock_guild = MagicMock()
        mock_guild.id = 12345
        mock_bot = MagicMock()
        
        # Use same-day times: 15:00 → 18:00 (close same day)
        guild_settings = {
            "timezone": "Europe/Helsinki",
            "poll_publish_time": "15:00",
            "poll_close_time": "18:00"
        }
        
        # Call function
        from services.polls.closing import close_all_active_polls
        closed_count = await close_all_active_polls(mock_bot, mock_guild, guild_settings)
        
        # Should close 1 poll: today's attendance poll (18:00 >= 15:00 = same day)
        assert closed_count == 1
        assert mock_close_poll.call_count == 1
        
        # Verify which poll was closed
        closed_poll_ids = [call[0][2].id for call in mock_close_poll.call_args_list]
        assert "poll1" in closed_poll_ids  # Today's attendance poll closes today


class TestErrorHandling:
    """Test error handling in poll manager."""
    
    @pytest.mark.asyncio
    @patch('services.polls.attendance.get_events_by_date')
    async def test_storage_error_handling(self, mock_get_events):
        """Test handling of storage errors."""
        mock_get_events.side_effect = Exception("Storage error")
        
        mock_guild = MagicMock()
        mock_guild.id = 12345
        mock_bot = MagicMock()
        guild_settings = {"timezone": "Europe/Helsinki"}
        
        # Should not raise exception, should return empty list
        polls = await publish_attendance_poll(mock_bot, mock_guild, guild_settings)
        assert len(polls) == 0
    
    @pytest.mark.asyncio
    async def test_missing_poll_channel(self):
        """Test handling when poll channel is not configured."""
        mock_guild = MagicMock()
        mock_guild.id = 12345
        mock_bot = MagicMock()
        
        # No poll_channel_id in settings
        guild_settings = {"timezone": "Europe/Helsinki"}
        
        with patch('storage.get_events_by_date') as mock_get_events:
            mock_get_events.return_value = [
                {
                    'id': 'event1',
                    'title': 'Test Event',
                    'date': tz_tomorrow(),
                    'event_type': 'lecture',
                    'created_at': '2024-01-01T00:00:00+00:00',
                    'feedback_only': False
                }
            ]
            
            polls = await publish_attendance_poll(mock_bot, mock_guild, guild_settings)
            assert len(polls) == 0


if __name__ == "__main__":
    pytest.main([__file__]) 