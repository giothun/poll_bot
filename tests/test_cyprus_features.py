"""
Tests for Cyprus camp features.
"""

import pytest
from unittest.mock import Mock, AsyncMock, patch
from datetime import datetime, timezone

from models import Event, EventType
from utils.feedback_templates import (
    get_cyprus_feedback_options, is_cyprus_supported_event, 
    get_cyprus_config, CYPRUS_FEEDBACK_TEMPLATES
)
from services.polls.cyprus_feedback import (
    publish_cyprus_feedback_polls, create_cyprus_feedback_poll,
    _get_event_type_display_name
)


class TestCyprusFeedbackTemplates:
    """Test Cyprus feedback templates."""
    
    def test_contest_feedback_options(self):
        """Test contest feedback options."""
        options = get_cyprus_feedback_options(EventType.CONTEST)
        
        assert len(options) == 3
        assert options[0].emoji == "🩷"
        assert "loved it" in options[0].text
        assert options[1].emoji == "😿"
        assert "too hard" in options[1].text
        assert options[2].emoji == "🥱"
        assert "too easy" in options[2].text
    
    def test_contest_editorial_feedback_options(self):
        """Test contest editorial feedback options."""
        options = get_cyprus_feedback_options(EventType.CONTEST_EDITORIAL)
        
        assert len(options) == 4
        assert options[0].emoji == "😻"
        assert "super useful" in options[0].text
        assert options[3].emoji == "🏃‍♀️‍➡️"
        assert "didn't attend" in options[3].text
    
    def test_extra_lecture_feedback_options(self):
        """Test extra lecture feedback options."""
        options = get_cyprus_feedback_options(EventType.EXTRA_LECTURE)
        
        assert len(options) == 4
        assert options[0].emoji == "🤩"
        assert "informative and useful" in options[0].text
        assert options[3].emoji == "🛑"
        assert "didn't participate" in options[3].text
    
    def test_evening_activity_feedback_options(self):
        """Test evening activity feedback options."""
        options = get_cyprus_feedback_options(EventType.EVENING_ACTIVITY)
        
        assert len(options) == 4
        assert options[0].emoji == "❤️‍🔥"
        assert "want more like it" in options[0].text
        assert options[3].emoji == "🙈"
        assert "didn't participate" in options[3].text
    
    def test_unsupported_event_type(self):
        """Test unsupported event type returns empty list."""
        options = get_cyprus_feedback_options(EventType.LECTURE)
        assert len(options) == 0
    
    def test_is_cyprus_supported_event(self):
        """Test Cyprus supported event check."""
        assert is_cyprus_supported_event(EventType.CONTEST)
        assert is_cyprus_supported_event(EventType.CONTEST_EDITORIAL)
        assert is_cyprus_supported_event(EventType.EXTRA_LECTURE)
        assert is_cyprus_supported_event(EventType.EVENING_ACTIVITY)
        assert not is_cyprus_supported_event(EventType.LECTURE)
    
    def test_feedback_option_formatting(self):
        """Test feedback option formatting."""
        options = get_cyprus_feedback_options(EventType.CONTEST)
        formatted = options[0].format()
        
        assert formatted.startswith("🩷")
        assert "Wow, I loved it!" in formatted
    
    def test_cyprus_config(self):
        """Test Cyprus configuration."""
        config = get_cyprus_config()
        
        assert config["timezone"] == "Europe/Nicosia"
        assert config["feedback_time"] == "23:00"
        assert config["attendance_polls_enabled"] is False
        assert config["reminders_enabled"] is False
        assert config["feedback_polls_enabled"] is True
        assert config["single_choice_polls"] is True


class TestCyprusFeedbackService:
    """Test Cyprus feedback service."""
    
    def test_event_type_display_names(self):
        """Test event type display name mapping."""
        assert _get_event_type_display_name(EventType.CONTEST) == "Contest"
        assert _get_event_type_display_name(EventType.CONTEST_EDITORIAL) == "Contest Editorial"
        assert _get_event_type_display_name(EventType.EXTRA_LECTURE) == "Extra Lecture"
        assert _get_event_type_display_name(EventType.EVENING_ACTIVITY) == "Evening Activity"
    
    @pytest.mark.asyncio
    async def test_publish_cyprus_feedback_polls_no_events(self):
        """Test publishing Cyprus feedback polls with no events."""
        mock_bot = Mock()
        mock_guild = Mock()
        mock_guild.id = 12345
        guild_settings = {"timezone": "Europe/Nicosia"}
        
        with patch('services.polls.cyprus_feedback.get_events_by_date') as mock_get_events:
            mock_get_events.return_value = []
            
            result = await publish_cyprus_feedback_polls(mock_bot, mock_guild, guild_settings)
            
            assert result == []
    
    @pytest.mark.asyncio
    async def test_publish_cyprus_feedback_polls_no_channel(self):
        """Test publishing Cyprus feedback polls with no poll channel."""
        mock_bot = Mock()
        mock_guild = Mock()
        mock_guild.id = 12345
        guild_settings = {"timezone": "Europe/Nicosia"}  # No poll_channel_id
        
        # Mock events
        event_data = {
            'id': 'contest_123',
            'title': 'Test Contest',
            'date': '2024-06-12',
            'event_type': 'contest',
            'created_at': '2024-01-01T00:00:00+00:00',
            'feedback_only': False
        }
        
        with patch('services.polls.cyprus_feedback.get_events_by_date') as mock_get_events:
            mock_get_events.return_value = [event_data]
            
            result = await publish_cyprus_feedback_polls(mock_bot, mock_guild, guild_settings)
            
            assert result == []
    
    @pytest.mark.asyncio 
    async def test_publish_cyprus_feedback_polls_success(self):
        """Test successful Cyprus feedback polls publishing."""
        mock_bot = Mock()
        mock_guild = Mock()
        mock_guild.id = 12345
        
        mock_channel = Mock()
        mock_guild.get_channel.return_value = mock_channel
        
        guild_settings = {
            "timezone": "Europe/Nicosia",
            "poll_channel_id": 67890
        }
        
        # Mock events
        event_data = {
            'id': 'contest_123',
            'title': 'Test Contest',
            'date': '2024-06-12',
            'event_type': 'contest',
            'created_at': '2024-01-01T00:00:00+00:00',
            'feedback_only': False
        }
        
        with patch('services.polls.cyprus_feedback.get_events_by_date') as mock_get_events, \
             patch('services.polls.cyprus_feedback.create_cyprus_feedback_poll') as mock_create_poll, \
             patch('services.polls.cyprus_feedback.save_poll') as mock_save_poll:
            
            mock_get_events.return_value = [event_data]
            
            # Mock poll creation
            mock_poll_meta = Mock()
            mock_poll_meta.id = "cyprus_feedback_contest_123"
            mock_poll_meta.to_dict.return_value = {"id": "cyprus_feedback_contest_123"}
            mock_create_poll.return_value = mock_poll_meta
            
            result = await publish_cyprus_feedback_polls(mock_bot, mock_guild, guild_settings)
            
            assert len(result) == 1
            assert result[0] == mock_poll_meta
            mock_create_poll.assert_called_once()
            mock_save_poll.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_create_cyprus_feedback_poll_success(self):
        """Test creating a single Cyprus feedback poll."""
        mock_guild = Mock()
        mock_guild.id = 12345
        
        mock_channel = Mock()
        mock_message = Mock()
        mock_message.id = 98765
        mock_channel.send = AsyncMock(return_value=mock_message)
        
        guild_settings = {"timezone": "Europe/Nicosia"}
        
        # Create test event
        event = Event(
            id="contest_123",
            title="Test Contest",
            date="2024-06-12", 
            event_type=EventType.CONTEST,
            created_at=datetime.now(timezone.utc)
        )
        
        result = await create_cyprus_feedback_poll(mock_guild, event, guild_settings, mock_channel)
        
        assert result is not None
        assert result.guild_id == 12345
        assert result.channel_id == mock_channel.id
        assert result.message_id == 98765
        assert result.is_feedback is True
        assert "cyprus_feedback" in result.id
        
        # Verify poll was sent
        mock_channel.send.assert_called_once()
        call_args = mock_channel.send.call_args
        assert 'poll' in call_args.kwargs
        
        # Verify poll question
        sent_poll = call_args.kwargs['poll']
        assert "Contest - Test Contest" in sent_poll.question
        assert sent_poll.multiple is False  # Single choice
    
    @pytest.mark.asyncio
    async def test_create_cyprus_feedback_poll_no_template(self):
        """Test creating Cyprus feedback poll for unsupported event type."""
        mock_guild = Mock()
        mock_channel = Mock()
        guild_settings = {}
        
        # Unsupported event type
        event = Event(
            id="lecture_123",
            title="Test Lecture",
            date="2024-06-12",
            event_type=EventType.LECTURE,  # Not supported in Cyprus
            created_at=datetime.now(timezone.utc)
        )
        
        result = await create_cyprus_feedback_poll(mock_guild, event, guild_settings, mock_channel)
        
        assert result is None


class TestEventTypeExtension:
    """Test new CONTEST_EDITORIAL event type."""
    
    def test_contest_editorial_enum_value(self):
        """Test CONTEST_EDITORIAL enum value."""
        assert EventType.CONTEST_EDITORIAL.value == "contest_editorial"
    
    def test_contest_editorial_in_all_event_types(self):
        """Test CONTEST_EDITORIAL is included in all event types."""
        all_types = list(EventType)
        assert EventType.CONTEST_EDITORIAL in all_types
    
    def test_event_creation_with_contest_editorial(self):
        """Test creating event with CONTEST_EDITORIAL type."""
        event = Event(
            id="editorial_123",
            title="Contest A Editorial",
            date="2024-06-12",
            event_type=EventType.CONTEST_EDITORIAL,
            created_at=datetime.now(timezone.utc)
        )
        
        assert event.event_type == EventType.CONTEST_EDITORIAL
        assert event.title == "Contest A Editorial"
    
    def test_contest_editorial_serialization(self):
        """Test CONTEST_EDITORIAL event serialization."""
        event = Event(
            id="editorial_123",
            title="Contest A Editorial", 
            date="2024-06-12",
            event_type=EventType.CONTEST_EDITORIAL,
            created_at=datetime.now(timezone.utc)
        )
        
        event_dict = event.to_dict()
        assert event_dict["event_type"] == "contest_editorial"
        
        # Test deserialization
        restored_event = Event.from_dict(event_dict)
        assert restored_event.event_type == EventType.CONTEST_EDITORIAL


class TestCyprusSchedulerIntegration:
    """Test Cyprus scheduler integration."""
    
    def test_cyprus_scheduler_config_parsing(self):
        """Test Cyprus scheduler configuration parsing."""
        from services.scheduler_service import SchedulerService
        
        mock_bot = Mock()
        service = SchedulerService(mock_bot)
        
        # Cyprus mode settings
        cyprus_settings = {
            "camp_mode": "cyprus",
            "feedback_publish_time": "23:00",
            "timezone": "Europe/Nicosia"
        }
        
        job_configs = service._build_job_configs(12345, cyprus_settings, "Europe/Nicosia")
        
        # Should only have Cyprus feedback job
        assert len(job_configs) == 1
        assert job_configs[0]['id'] == "cyprus_feedback_12345"
        assert job_configs[0]['func'] == service._run_cyprus_feedback_publish
    
    def test_standard_scheduler_config_parsing(self):
        """Test standard scheduler configuration parsing."""
        from services.scheduler_service import SchedulerService
        
        mock_bot = Mock()
        service = SchedulerService(mock_bot)
        
        # Standard mode settings
        standard_settings = {
            "camp_mode": "standard",
            "poll_publish_time": "14:30",
            "reminder_time": "19:00",
            "poll_close_time": "09:00",
            "feedback_publish_time": "22:00"
        }
        
        job_configs = service._build_job_configs(12345, standard_settings, "Europe/Helsinki")
        
        # Should have all standard jobs
        assert len(job_configs) >= 4  # At least 4 jobs (can have more like close)
        job_ids = [config['id'] for config in job_configs]
        assert "poll_publish_12345" in job_ids
        assert "poll_reminder_12345" in job_ids
        assert "feedback_publish_12345" in job_ids
