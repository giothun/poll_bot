"""
Tests for Discord utilities.
"""

import pytest
from unittest.mock import Mock, AsyncMock
from datetime import datetime, timezone

import discord

from utils.discord import (
    EmbedBuilder, EmbedColors, create_success_embed, create_error_embed,
    create_poll_results_embed, create_event_embed, format_user_list,
    check_bot_permissions, get_missing_permissions
)
from models import PollMeta, PollOption, Event, EventType


class TestEmbedBuilder:
    """Test EmbedBuilder class."""
    
    def test_basic_embed_creation(self):
        embed = EmbedBuilder("Test Title", "Test Description").build()
        
        assert embed.title == "Test Title"
        assert embed.description == "Test Description"
        assert embed.color.value == EmbedColors.INFO
    
    def test_embed_with_fields(self):
        embed = (EmbedBuilder("Test Title")
                .add_field("Field 1", "Value 1", inline=True)
                .add_field("Field 2", "Value 2", inline=False)
                .build())
        
        assert len(embed.fields) == 2
        assert embed.fields[0].name == "Field 1"
        assert embed.fields[0].value == "Value 1"
        assert embed.fields[0].inline is True
        assert embed.fields[1].inline is False
    
    def test_embed_with_footer_and_timestamp(self):
        test_time = datetime.now(timezone.utc)
        embed = (EmbedBuilder("Test")
                .set_footer("Test Footer")
                .set_timestamp(test_time)
                .build())
        
        assert embed.footer.text == "Test Footer"
        assert embed.timestamp == test_time
    
    def test_custom_color(self):
        embed = EmbedBuilder("Test", color=EmbedColors.SUCCESS).build()
        assert embed.color.value == EmbedColors.SUCCESS


class TestEmbedCreationFunctions:
    """Test predefined embed creation functions."""
    
    def test_success_embed(self):
        embed = create_success_embed("Operation Successful", "Details here")
        assert "✅" in embed.title
        assert "Operation Successful" in embed.title
        assert embed.description == "Details here"
        assert embed.color.value == EmbedColors.SUCCESS
    
    def test_error_embed(self):
        embed = create_error_embed("Error Occurred", "Error details")
        assert "❌" in embed.title
        assert "Error Occurred" in embed.title
        assert embed.color.value == EmbedColors.ERROR


class TestPollResultsEmbed:
    """Test poll results embed creation."""
    
    def test_poll_results_embed_basic(self):
        # Create test poll metadata
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
                ),
                PollOption(
                    event_id="event2", 
                    title="Event 2", 
                    event_type=EventType.CONTEST,
                    votes=[4, 5]
                )
            ]
        )
        
        embed = create_poll_results_embed(poll_meta)
        
        assert "📊 Poll Results" in embed.title
        assert "2024-12-25" in embed.title
        assert len(embed.fields) >= 2  # Should have total votes and options fields
        
        # Check that results are included
        results_field = next((f for f in embed.fields if "Results" in f.name), None)
        assert results_field is not None
        assert "Event 1" in results_field.value
        assert "Event 2" in results_field.value
    
    def test_feedback_poll_results_embed(self):
        poll_meta = PollMeta(
            id="123",
            guild_id=456,
            channel_id=789,
            message_id=123,
            poll_date="event_123",  # For feedback polls, this contains event ID
            options=[],
            is_feedback=True
        )
        
        embed = create_poll_results_embed(poll_meta)
        assert "Feedback poll results" in embed.description


class TestEventEmbed:
    """Test event embed creation."""
    
    def test_lecture_event_embed(self):
        event = Event(
            id="event_123",
            title="Introduction to Algorithms",
            date="2024-12-25",
            event_type=EventType.LECTURE,
            created_at=datetime.now(timezone.utc)
        )
        
        embed = create_event_embed(event, show_details=True)
        
        assert "📚" in embed.title  # Lecture emoji
        assert "Lecture" in embed.title
        assert any("Introduction to Algorithms" in field.value for field in embed.fields)
        assert any("2024-12-25" in field.value for field in embed.fields)
        assert "Event ID: event_123" in embed.footer.text
    
    def test_contest_event_embed(self):
        event = Event(
            id="contest_123",
            title="Programming Contest #1",
            date="2024-12-30",
            event_type=EventType.CONTEST,
            created_at=datetime.now(timezone.utc)
        )
        
        embed = create_event_embed(event, show_details=False)
        
        assert "🏆" in embed.title  # Contest emoji
        assert len([f for f in embed.fields if "Created" in f.name]) == 0  # No details
    
    def test_feedback_only_event(self):
        event = Event(
            id="event_123",
            title="Special Lecture",
            date="2024-12-25",
            event_type=EventType.LECTURE,
            created_at=datetime.now(timezone.utc),
            feedback_only=True
        )
        
        embed = create_event_embed(event, show_details=True)
        pollable_field = next((f for f in embed.fields if "Pollable" in f.name), None)
        assert pollable_field is not None
        assert "Feedback only" in pollable_field.value


class TestUserListFormatting:
    """Test user list formatting utilities."""
    
    def test_format_empty_user_list(self):
        result = format_user_list([])
        assert result == "None"
    
    def test_format_small_user_list(self):
        # Create mock users
        users = []
        for i in range(3):
            user = Mock()
            user.display_name = f"User{i+1}"
            users.append(user)
        
        result = format_user_list(users)
        assert "• User1" in result
        assert "• User2" in result
        assert "• User3" in result
        assert "... and" not in result  # Should not truncate
    
    def test_format_large_user_list(self):
        # Create mock users
        users = []
        for i in range(15):
            user = Mock()
            user.display_name = f"User{i+1}"
            users.append(user)
        
        result = format_user_list(users, max_display=10)
        assert "• User1" in result
        assert "• User10" in result
        assert "... and 5 more" in result


class TestPermissionChecking:
    """Test permission checking utilities."""
    
    def test_check_bot_permissions_all_present(self):
        # Mock channel and permissions
        channel = Mock()
        bot_member = Mock()
        permissions = Mock()
        
        # Set all required permissions to True
        permissions.send_messages = True
        permissions.embed_links = True
        permissions.manage_messages = True
        
        channel.permissions_for.return_value = permissions
        channel.guild.me = bot_member
        
        required_perms = ['send_messages', 'embed_links', 'manage_messages']
        result = check_bot_permissions(channel, required_perms)
        
        assert result['send_messages'] is True
        assert result['embed_links'] is True
        assert result['manage_messages'] is True
    
    def test_check_bot_permissions_some_missing(self):
        # Mock channel and permissions
        channel = Mock()
        bot_member = Mock()
        permissions = Mock()
        
        # Set some permissions to False
        permissions.send_messages = True
        permissions.embed_links = False
        permissions.manage_messages = True
        
        channel.permissions_for.return_value = permissions
        channel.guild.me = bot_member
        
        required_perms = ['send_messages', 'embed_links', 'manage_messages']
        result = check_bot_permissions(channel, required_perms)
        
        assert result['send_messages'] is True
        assert result['embed_links'] is False
        assert result['manage_messages'] is True
    
    def test_get_missing_permissions(self):
        # Mock channel and permissions
        channel = Mock()
        bot_member = Mock()
        permissions = Mock()
        
        # Set some permissions to False
        permissions.send_messages = True
        permissions.embed_links = False
        permissions.manage_messages = False
        
        channel.permissions_for.return_value = permissions
        channel.guild.me = bot_member
        
        required_perms = ['send_messages', 'embed_links', 'manage_messages']
        missing = get_missing_permissions(channel, required_perms)
        
        assert 'send_messages' not in missing
        assert 'embed_links' in missing
        assert 'manage_messages' in missing
        assert len(missing) == 2
    
    def test_get_missing_permissions_none_missing(self):
        # Mock channel and permissions
        channel = Mock()
        bot_member = Mock()
        permissions = Mock()
        
        # Set all permissions to True
        permissions.send_messages = True
        permissions.embed_links = True
        
        channel.permissions_for.return_value = permissions
        channel.guild.me = bot_member
        
        required_perms = ['send_messages', 'embed_links']
        missing = get_missing_permissions(channel, required_perms)
        
        assert len(missing) == 0


class TestEmbedColors:
    """Test that embed colors are properly defined."""
    
    def test_color_definitions(self):
        # Test that all color constants are properly defined
        assert isinstance(EmbedColors.SUCCESS, int)
        assert isinstance(EmbedColors.ERROR, int)
        assert isinstance(EmbedColors.WARNING, int)
        assert isinstance(EmbedColors.INFO, int)
        assert isinstance(EmbedColors.POLL, int)
        assert isinstance(EmbedColors.FEEDBACK, int)
        
        # Test that colors are different
        colors = [
            EmbedColors.SUCCESS, EmbedColors.ERROR, EmbedColors.WARNING,
            EmbedColors.INFO, EmbedColors.POLL, EmbedColors.FEEDBACK
        ]
        assert len(set(colors)) == len(colors)  # All colors should be unique
