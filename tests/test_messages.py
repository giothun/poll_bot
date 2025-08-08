"""
Tests for message utilities.
"""

import pytest
from unittest.mock import Mock
from datetime import datetime, timezone

from utils.messages import (
    MessageType, format_message, format_event_display, format_poll_summary,
    format_user_mention_list, format_poll_results_text, get_ranking_emoji,
    truncate_text, escape_markdown, format_duration, create_progress_bar
)
from models import Event, EventType, PollMeta, PollOption


class TestMessageFormatting:
    """Test message formatting functions."""
    
    def test_format_success_message(self):
        msg = format_message(MessageType.SUCCESS, 'event_added', 
                           event_type="lecture", title="Test Lecture", date="2024-12-25")
        assert "✅" in msg
        assert "lecture" in msg
        assert "Test Lecture" in msg
        assert "2024-12-25" in msg
    
    def test_format_error_message(self):
        msg = format_message(MessageType.ERROR, 'invalid_format', 
                           expected_format="YYYY-MM-DD")
        assert "❌" in msg
        assert "Invalid format" in msg
        assert "YYYY-MM-DD" in msg
    
    def test_format_warning_message(self):
        msg = format_message(MessageType.WARNING, 'no_events_found',
                           event_type="contests", date="2024-12-25")
        assert "⚠️" in msg
        assert "contests" in msg
        assert "2024-12-25" in msg
    
    def test_format_info_message(self):
        msg = format_message(MessageType.INFO, 'poll_published',
                           count=3, date="2024-12-25")
        assert "📊" in msg
        assert "3" in msg
        assert "2024-12-25" in msg
    
    def test_format_unknown_template(self):
        msg = format_message(MessageType.SUCCESS, 'unknown_template')
        assert "Unknown template" in msg


class TestEventDisplay:
    """Test event display formatting."""
    
    def test_format_lecture_display(self):
        event = Event(
            id="event_123",
            title="Introduction to Algorithms",
            date="2024-12-25",
            event_type=EventType.LECTURE,
            created_at=datetime.now(timezone.utc)
        )
        
        result = format_event_display(event, include_id=True, include_type_emoji=True)
        
        assert "📚" in result  # Lecture emoji
        assert "Lecture" in result
        assert "Introduction to Algorithms" in result
        assert "2024-12-25" in result
        assert "event_123" in result
    
    def test_format_contest_display(self):
        event = Event(
            id="contest_123",
            title="Programming Contest",
            date="2024-12-30",
            event_type=EventType.CONTEST,
            created_at=datetime.now(timezone.utc)
        )
        
        result = format_event_display(event, include_id=False, include_type_emoji=False)
        
        assert "🏆" not in result  # No emoji
        assert "Contest" in result
        assert "Programming Contest" in result
        assert "contest_123" not in result  # No ID
    
    def test_format_feedback_only_event(self):
        event = Event(
            id="event_123",
            title="Special Event",
            date="2024-12-25",
            event_type=EventType.LECTURE,
            created_at=datetime.now(timezone.utc),
            feedback_only=True
        )
        
        result = format_event_display(event)
        assert "[Feedback Only]" in result


class TestPollSummary:
    """Test poll summary formatting."""
    
    def test_format_attendance_poll_summary(self):
        poll_meta = PollMeta(
            id="123",
            guild_id=456,
            channel_id=789,
            message_id=123,
            poll_date="2024-12-25",
            options=[
                PollOption(
                    event_id="event1", 
                    title="Event 1", 
                    event_type=EventType.LECTURE,
                    votes=[1, 2, 3]
                )
            ]
        )
        
        result = format_poll_summary(poll_meta, include_votes=True)
        
        assert "Attendance Poll" in result
        assert "2024-12-25" in result
        assert "🔓 Active" in result
        assert "3 votes" in result
    
    def test_format_feedback_poll_summary(self):
        poll_meta = PollMeta(
            id="123",
            guild_id=456,
            channel_id=789,
            message_id=123,
            poll_date="event_123",
            options=[],
            is_feedback=True,
            closed_at=datetime.now(timezone.utc)
        )
        
        result = format_poll_summary(poll_meta, include_votes=False)
        
        assert "Feedback Poll" in result
        assert "🔒 Closed" in result
        assert "votes" not in result


class TestUserMentions:
    """Test user mention formatting."""
    
    def test_format_empty_user_list(self):
        result = format_user_mention_list([])
        assert result == "None"
    
    def test_format_small_user_list(self):
        user_ids = [123456789, 987654321, 555666777]
        result = format_user_mention_list(user_ids)
        
        assert "<@123456789>" in result
        assert "<@987654321>" in result
        assert "<@555666777>" in result
        assert "..." not in result
    
    def test_format_large_user_list(self):
        user_ids = list(range(100000000, 100000015))  # 15 users
        result = format_user_mention_list(user_ids, max_mentions=10)
        
        assert "<@100000000>" in result
        assert "<@100000009>" in result
        assert "... and 5 more" in result


class TestPollResults:
    """Test poll results formatting."""
    
    def test_format_poll_results_with_metadata(self):
        poll_meta = PollMeta(
            id="123",
            guild_id=456,
            channel_id=789,
            message_id=123,
            poll_date="2024-12-25",
            options=[
                PollOption(
                    event_id="event1", 
                    title="Event 1", 
                    event_type=EventType.LECTURE,
                    votes=[1, 2, 3, 4, 5]  # 5 votes
                ),
                PollOption(
                    event_id="event2", 
                    title="Event 2", 
                    event_type=EventType.CONTEST,
                    votes=[6, 7]  # 2 votes
                )
            ]
        )
        
        result = format_poll_results_text(poll_meta)
        
        assert "🥇" in result  # First place emoji
        assert "🥈" in result  # Second place emoji
        assert "Event 1" in result
        assert "Event 2" in result
        assert "5" in result  # Vote count
        assert "2" in result  # Vote count
        assert "71.4%" in result or "28.6%" in result  # Percentages
    
    def test_format_empty_poll_results(self):
        poll_meta = PollMeta(
            id="123",
            guild_id=456,
            channel_id=789,
            message_id=123,
            poll_date="2024-12-25",
            options=[]
        )
        
        result = format_poll_results_text(poll_meta)
        assert result == "No votes recorded"


class TestRankingEmojis:
    """Test ranking emoji function."""
    
    def test_ranking_emojis(self):
        assert get_ranking_emoji(0) == "🥇"  # First place
        assert get_ranking_emoji(1) == "🥈"  # Second place
        assert get_ranking_emoji(2) == "🥉"  # Third place
        assert get_ranking_emoji(3) == "📝"  # Default
        assert get_ranking_emoji(10) == "📝"  # Default


class TestTextUtilities:
    """Test text manipulation utilities."""
    
    def test_truncate_text_short(self):
        text = "Short text"
        result = truncate_text(text, max_length=100)
        assert result == text
    
    def test_truncate_text_long(self):
        text = "This is a very long text that should be truncated"
        result = truncate_text(text, max_length=20, suffix="...")
        assert len(result) == 20
        assert result.endswith("...")
        assert result.startswith("This is a very")
    
    def test_truncate_text_suffix_too_long(self):
        result = truncate_text("test", max_length=2, suffix="...")
        assert result == ".."
    
    def test_escape_markdown(self):
        text = "Text with *bold* and _italic_ and `code`"
        result = escape_markdown(text)
        assert "\\\\*bold\\\\*" in result
        assert "\\\\_italic\\\\_" in result
        assert "\\\\`code\\\\`" in result
    
    def test_escape_markdown_no_special_chars(self):
        text = "Normal text without markdown"
        result = escape_markdown(text)
        assert result == text


class TestDurationFormatting:
    """Test duration formatting."""
    
    def test_format_seconds(self):
        assert format_duration(30) == "30s"
        assert format_duration(59) == "59s"
    
    def test_format_minutes(self):
        assert format_duration(60) == "1m"
        assert format_duration(90) == "1m"
        assert format_duration(3599) == "59m"
    
    def test_format_hours(self):
        assert format_duration(3600) == "1h"
        assert format_duration(3660) == "1h 1m"
        assert format_duration(7200) == "2h"
    
    def test_format_days(self):
        assert format_duration(86400) == "1d"
        assert format_duration(90000) == "1d 1h"
        assert format_duration(172800) == "2d"


class TestProgressBar:
    """Test progress bar creation."""
    
    def test_progress_bar_empty(self):
        result = create_progress_bar(0, 100)
        assert result.startswith("▱" * 20)
        assert "0/100 (0.0%)" in result
    
    def test_progress_bar_half(self):
        result = create_progress_bar(50, 100)
        assert "▰" * 10 in result
        assert "▱" * 10 in result
        assert "50/100 (50.0%)" in result
    
    def test_progress_bar_full(self):
        result = create_progress_bar(100, 100)
        assert result.startswith("▰" * 20)
        assert "100/100 (100.0%)" in result
    
    def test_progress_bar_zero_total(self):
        result = create_progress_bar(0, 0)
        assert result.startswith("▱" * 20)
    
    def test_progress_bar_custom_length(self):
        result = create_progress_bar(25, 100, length=10)
        assert "▰" * 2 in result  # 25% of 10
        assert "▱" * 8 in result
        assert len(result.split()[0]) == 10  # Bar length should be 10
