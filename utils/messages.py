"""
Message formatting utilities for CampPoll bot.
Provides consistent message formatting, templates, and text processing functions.
"""

import logging
from typing import Dict, List, Any, Optional, Union
from datetime import datetime, timezone
from enum import Enum

from models import Event, EventType, PollMeta, GuildSettings
from utils.time import format_datetime, get_time_until, get_discord_timestamp

logger = logging.getLogger(__name__)


class MessageType(Enum):
    """Types of messages for consistent formatting."""
    SUCCESS = "success"
    ERROR = "error" 
    WARNING = "warning"
    INFO = "info"
    REMINDER = "reminder"


class MessageTemplates:
    """Pre-defined message templates."""
    
    # Success messages
    SUCCESS_TEMPLATES = {
        'event_added': "✅ {event_type} '{title}' added for {date}",
        'event_updated': "✅ {event_type} '{title}' updated for {date}",
        'event_deleted': "✅ {event_type} '{title}' deleted",
        'settings_updated': "✅ {setting_name} updated successfully",
        'poll_closed': "✅ Poll closed successfully",
        'export_ready': "✅ Export completed successfully",
    }
    
    # Error messages
    ERROR_TEMPLATES = {
        'invalid_format': "❌ Invalid format. Expected: {expected_format}",
        'event_not_found': "❌ Event '{event_id}' not found",
        'poll_not_found': "❌ Poll with message ID '{message_id}' not found",
        'permission_denied': "❌ You don't have permission to use this command",
        'channel_not_found': "❌ Channel not found or bot doesn't have access",
        'invalid_timezone': "❌ Invalid timezone: '{timezone}'",
        'invalid_time': "❌ Invalid time format: '{time}'. Use HH:MM format",
        'duplicate_event': "❌ {event_type} '{title}' on {date} already exists",
        'missing_permissions': "❌ Bot needs '{permissions}' permissions in {channel}",
    }
    
    # Warning messages
    WARNING_TEMPLATES = {
        'no_events_found': "⚠️ No {event_type}s found for {date}",
        'no_active_polls': "⚠️ No active polls found",
        'backup_failed': "⚠️ Could not create backup: {reason}",
        'dm_failed': "⚠️ Could not send DM to user: {reason}",
    }
    
    # Info messages
    INFO_TEMPLATES = {
        'poll_published': "📊 Published {count} poll(s) for {date}",
        'reminders_sent': "📝 Sent {count} reminder(s) to users",
        'polls_closed': "🔒 Closed {count} poll(s)",
        'scheduler_started': "⏰ Scheduler started with {job_count} jobs",
    }


def format_message(template_type: MessageType, template_key: str, **kwargs) -> str:
    """
    Format a message using predefined templates.
    
    Args:
        template_type: Type of message (success, error, etc.)
        template_key: Key for specific template
        **kwargs: Variables to substitute in template
    
    Returns:
        Formatted message string
    """
    templates = {
        MessageType.SUCCESS: MessageTemplates.SUCCESS_TEMPLATES,
        MessageType.ERROR: MessageTemplates.ERROR_TEMPLATES,
        MessageType.WARNING: MessageTemplates.WARNING_TEMPLATES,
        MessageType.INFO: MessageTemplates.INFO_TEMPLATES,
    }
    
    template_dict = templates.get(template_type, {})
    template = template_dict.get(template_key, f"Unknown template: {template_key}")
    
    try:
        return template.format(**kwargs)
    except KeyError as e:
        logger.warning(f"Missing template variable {e} for template {template_key}")
        return template
    except Exception as e:
        logger.error(f"Error formatting template {template_key}: {e}")
        return template


def format_event_display(event: Event, include_id: bool = False, include_type_emoji: bool = True) -> str:
    """
    Format an event for display in messages.
    
    Args:
        event: Event to format
        include_id: Whether to include event ID
        include_type_emoji: Whether to include emoji for event type
    
    Returns:
        Formatted event string
    """
    event_type_emojis = {
        EventType.LECTURE: "📚",
        EventType.CONTEST: "🏆", 
        EventType.EXTRA_LECTURE: "📖",
        EventType.EVENING_ACTIVITY: "🌙"
    }
    
    emoji = event_type_emojis.get(event.event_type, "📅") if include_type_emoji else ""
    type_name = event.event_type.value.replace('_', ' ').title()
    
    result = f"{emoji} {type_name}: {event.title} ({event.date})"
    
    if event.feedback_only:
        result += " [Feedback Only]"
    
    if include_id:
        result += f" [ID: {event.id}]"
    
    return result


def format_poll_summary(poll_meta: PollMeta, include_votes: bool = True) -> str:
    """
    Format a poll summary for display.
    
    Args:
        poll_meta: Poll metadata to format
        include_votes: Whether to include vote counts
    
    Returns:
        Formatted poll summary
    """
    poll_type = "Feedback Poll" if poll_meta.is_feedback else "Attendance Poll"
    status = "🔒 Closed" if poll_meta.is_closed else "🔓 Active"
    
    result = f"{poll_type} for {poll_meta.poll_date} - {status}"
    
    if include_votes:
        result += f" ({poll_meta.total_votes} votes)"
    
    return result


def format_user_mention_list(user_ids: List[int], max_mentions: int = 10) -> str:
    """
    Format a list of user IDs as mentions.
    
    Args:
        user_ids: List of user IDs to mention
        max_mentions: Maximum number of mentions before truncating
    
    Returns:
        Formatted mention string
    """
    if not user_ids:
        return "None"
    
    mentions = [f"<@{user_id}>" for user_id in user_ids[:max_mentions]]
    
    if len(user_ids) > max_mentions:
        remaining = len(user_ids) - max_mentions
        mentions.append(f"... and {remaining} more")
    
    return ", ".join(mentions)


def format_time_remaining(target_time: datetime, timezone_name: str = "UTC") -> str:
    """
    Format time remaining until a target time.
    
    Args:
        target_time: Target datetime
        timezone_name: Timezone name for display
    
    Returns:
        Human-readable time remaining string
    """
    time_until = get_time_until(target_time)
    
    if time_until == "Time has passed":
        return "⏰ Time has passed"
    elif time_until == "Less than a minute":
        return "⏰ Less than a minute remaining"
    else:
        return f"⏰ {time_until} remaining"


def format_poll_results_text(poll_meta: PollMeta, poll_answers: List[Any] = None) -> str:
    """
    Format poll results as text.
    
    Args:
        poll_meta: Poll metadata
        poll_answers: Optional Discord poll answers with vote counts
    
    Returns:
        Formatted results text
    """
    results = []
    total_votes = poll_meta.total_votes
    
    if poll_answers:
        # Use Discord poll data
        sorted_answers = sorted(poll_answers, key=lambda a: a.vote_count, reverse=True)
        total_votes = sum(answer.vote_count for answer in sorted_answers)
        
        for i, answer in enumerate(sorted_answers):
            percentage = (answer.vote_count / total_votes * 100) if total_votes > 0 else 0
            emoji = get_ranking_emoji(i)
            results.append(f"{emoji} {answer.text}: **{answer.vote_count}** votes ({percentage:.1f}%)")
    else:
        # Use poll metadata
        sorted_options = sorted(poll_meta.options, key=lambda x: x.vote_count, reverse=True)
        
        for i, option in enumerate(sorted_options):
            percentage = (option.vote_count / total_votes * 100) if total_votes > 0 else 0
            emoji = get_ranking_emoji(i)
            results.append(f"{emoji} {option.title}: **{option.vote_count}** votes ({percentage:.1f}%)")
    
    return "\n".join(results) if results else "No votes recorded"


def get_ranking_emoji(rank: int) -> str:
    """
    Get emoji for ranking position.
    
    Args:
        rank: Zero-based ranking position
    
    Returns:
        Appropriate emoji for the rank
    """
    emojis = {
        0: "🥇",  # First place
        1: "🥈",  # Second place
        2: "🥉",  # Third place
    }
    return emojis.get(rank, "📝")  # Default for other positions


def format_guild_info(guild_settings: Dict[str, Any]) -> str:
    """
    Format guild settings information for display.
    
    Args:
        guild_settings: Guild settings dictionary
    
    Returns:
        Formatted guild info string
    """
    lines = []
    
    # Basic info
    lines.append(f"**Guild ID:** {guild_settings.get('guild_id', 'Unknown')}")
    lines.append(f"**Timezone:** {guild_settings.get('timezone', 'Europe/Helsinki')}")
    
    # Timing
    lines.append("**Poll Schedule:**")
    lines.append(f"  • Publish: {guild_settings.get('poll_publish_time', '14:30')}")
    lines.append(f"  • Reminder: {guild_settings.get('reminder_time', '19:00')}")
    lines.append(f"  • Close: {guild_settings.get('poll_close_time', '09:00')}")
    lines.append(f"  • Feedback: {guild_settings.get('feedback_publish_time', '22:00')}")
    
    # Channels
    poll_channel = guild_settings.get('poll_channel_id')
    organiser_channel = guild_settings.get('organiser_channel_id')
    alerts_channel = guild_settings.get('alerts_channel_id')
    
    lines.append("**Channels:**")
    lines.append(f"  • Polls: {f'<#{poll_channel}>' if poll_channel else 'Not set'}")
    lines.append(f"  • Results: {f'<#{organiser_channel}>' if organiser_channel else 'Not set'}")
    lines.append(f"  • Alerts: {f'<#{alerts_channel}>' if alerts_channel else 'Not set'}")
    
    return "\n".join(lines)


def format_permission_error(missing_permissions: List[str], channel_name: str) -> str:
    """
    Format a permission error message.
    
    Args:
        missing_permissions: List of missing permission names
        channel_name: Name of the channel
    
    Returns:
        Formatted error message
    """
    permissions_text = ", ".join(f"'{perm}'" for perm in missing_permissions)
    return format_message(
        MessageType.ERROR,
        'missing_permissions',
        permissions=permissions_text,
        channel=channel_name
    )


def format_export_info(poll_meta: PollMeta, export_type: str) -> str:
    """
    Format export information text.
    
    Args:
        poll_meta: Poll metadata
        export_type: Type of export ('attendance' or 'user_votes')
    
    Returns:
        Formatted export info
    """
    lines = []
    
    if export_type == "attendance":
        lines.append("📄 **Attendance Export**")
        lines.append(f"Poll for {poll_meta.poll_date}")
    else:
        lines.append("👥 **User Votes Export**") 
        lines.append(f"Individual votes for {poll_meta.poll_date}")
        lines.append("⚠️ Contains user IDs - handle securely")
    
    lines.append(f"Total votes: {poll_meta.total_votes}")
    lines.append(f"Options: {len(poll_meta.options)}")
    lines.append(f"Status: {'Closed' if poll_meta.is_closed else 'Active'}")
    lines.append(f"Exported: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")
    
    return "\n".join(lines)


def format_command_help(command_name: str, description: str, usage: str, examples: List[str] = None) -> str:
    """
    Format help text for a command.
    
    Args:
        command_name: Name of the command
        description: Command description
        usage: Usage syntax
        examples: List of example usages
    
    Returns:
        Formatted help text
    """
    lines = []
    lines.append(f"**{command_name}**")
    lines.append(f"{description}")
    lines.append(f"**Usage:** `{usage}`")
    
    if examples:
        lines.append("**Examples:**")
        for example in examples:
            lines.append(f"  • `{example}`")
    
    return "\n".join(lines)


def format_stats_text(stats: Dict[str, Any]) -> str:
    """
    Format statistics for display.
    
    Args:
        stats: Dictionary of statistics
    
    Returns:
        Formatted stats text
    """
    lines = []
    
    for key, value in stats.items():
        # Format key from snake_case to Title Case
        display_key = key.replace('_', ' ').title()
        
        # Format value based on type
        if isinstance(value, float):
            display_value = f"{value:.1f}"
        elif isinstance(value, list):
            display_value = f"{len(value)} items"
        else:
            display_value = str(value)
        
        lines.append(f"**{display_key}:** {display_value}")
    
    return "\n".join(lines)


def truncate_text(text: str, max_length: int = 100, suffix: str = "...") -> str:
    """
    Truncate text to a maximum length.
    
    Args:
        text: Text to truncate
        max_length: Maximum length including suffix
        suffix: Suffix to add when truncating
    
    Returns:
        Truncated text
    """
    if len(text) <= max_length:
        return text
    
    # Account for suffix length
    available_length = max_length - len(suffix)
    if available_length <= 0:
        return suffix[:max_length]
    
    return text[:available_length] + suffix


def escape_markdown(text: str) -> str:
    """
    Escape Discord markdown characters in text.
    
    Args:
        text: Text to escape
    
    Returns:
        Escaped text
    """
    markdown_chars = ['*', '_', '`', '~', '|', '\\']
    escaped_text = text
    
    for char in markdown_chars:
        escaped_text = escaped_text.replace(char, f'\\{char}')
    
    return escaped_text


def format_duration(seconds: int) -> str:
    """
    Format duration in seconds to human-readable format.
    
    Args:
        seconds: Duration in seconds
    
    Returns:
        Formatted duration string
    """
    if seconds < 60:
        return f"{seconds}s"
    elif seconds < 3600:
        minutes = seconds // 60
        return f"{minutes}m"
    elif seconds < 86400:
        hours = seconds // 3600
        minutes = (seconds % 3600) // 60
        return f"{hours}h {minutes}m" if minutes > 0 else f"{hours}h"
    else:
        days = seconds // 86400
        hours = (seconds % 86400) // 3600
        return f"{days}d {hours}h" if hours > 0 else f"{days}d"


def create_progress_bar(current: int, total: int, length: int = 20) -> str:
    """
    Create a text-based progress bar.
    
    Args:
        current: Current progress value
        total: Total/maximum value
        length: Length of the progress bar in characters
    
    Returns:
        Progress bar string
    """
    if total <= 0:
        return "▱" * length
    
    filled_length = int(length * current / total)
    bar = "▰" * filled_length + "▱" * (length - filled_length)
    percentage = (current / total) * 100
    
    return f"{bar} {current}/{total} ({percentage:.1f}%)"

