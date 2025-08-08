"""
Validation utilities for CampPoll bot.
Provides validation functions for user inputs, settings, and data integrity.
"""

import re
import logging
from datetime import datetime, date
from typing import Optional, Tuple, List, Dict, Any, Union
from zoneinfo import ZoneInfo

from models import EventType
from utils.time import parse_time, is_valid_timezone

logger = logging.getLogger(__name__)


class ValidationError(Exception):
    """Custom exception for validation errors."""
    pass


class ValidationResult:
    """Result of a validation operation."""
    
    def __init__(self, is_valid: bool, error_message: str = None, cleaned_value: Any = None):
        self.is_valid = is_valid
        self.error_message = error_message
        self.cleaned_value = cleaned_value
    
    def __bool__(self) -> bool:
        return self.is_valid
    
    def __str__(self) -> str:
        if self.is_valid:
            return "Valid"
        return f"Invalid: {self.error_message}"


def validate_date_format(date_str: str) -> ValidationResult:
    """
    Validate date string in YYYY-MM-DD format.
    
    Args:
        date_str: Date string to validate
    
    Returns:
        ValidationResult with validation status and cleaned date
    """
    if not date_str or not isinstance(date_str, str):
        return ValidationResult(False, "Date string is required")
    
    date_str = date_str.strip()
    
    # Check basic format
    if not re.match(r'^\d{4}-\d{2}-\d{2}$', date_str):
        return ValidationResult(
            False, 
            "Invalid date format. Use YYYY-MM-DD (e.g., 2024-12-25)"
        )
    
    try:
        # Try to parse the date
        parsed_date = datetime.strptime(date_str, "%Y-%m-%d").date()
        return ValidationResult(True, cleaned_value=parsed_date)
    except ValueError as e:
        return ValidationResult(False, f"Invalid date: {str(e)}")


def validate_time_format(time_str: str) -> ValidationResult:
    """
    Validate time string in HH:MM format.
    
    Args:
        time_str: Time string to validate
    
    Returns:
        ValidationResult with validation status and parsed time tuple
    """
    if not time_str or not isinstance(time_str, str):
        return ValidationResult(False, "Time string is required")
    
    time_str = time_str.strip()
    
    # Check basic format
    if not re.match(r'^\d{1,2}:\d{2}$', time_str):
        return ValidationResult(
            False,
            "Invalid time format. Use HH:MM (e.g., 14:30, 09:00)"
        )
    
    parsed_time = parse_time(time_str)
    if not parsed_time:
        return ValidationResult(
            False,
            "Invalid time. Hours must be 0-23, minutes must be 0-59"
        )
    
    return ValidationResult(True, cleaned_value=parsed_time)


def validate_timezone(timezone_str: str) -> ValidationResult:
    """
    Validate timezone string.
    
    Args:
        timezone_str: Timezone string to validate
    
    Returns:
        ValidationResult with validation status
    """
    if not timezone_str or not isinstance(timezone_str, str):
        return ValidationResult(False, "Timezone string is required")
    
    timezone_str = timezone_str.strip()
    
    if not is_valid_timezone(timezone_str):
        return ValidationResult(
            False,
            f"Invalid timezone: '{timezone_str}'. Use IANA timezone names (e.g., Europe/Helsinki, America/New_York)"
        )
    
    return ValidationResult(True, cleaned_value=timezone_str)


def validate_event_title(title: str, max_length: int = 100) -> ValidationResult:
    """
    Validate event title.
    
    Args:
        title: Title to validate
        max_length: Maximum allowed length
    
    Returns:
        ValidationResult with validation status and cleaned title
    """
    if not title or not isinstance(title, str):
        return ValidationResult(False, "Event title is required")
    
    title = title.strip()
    
    if len(title) < 1:
        return ValidationResult(False, "Event title cannot be empty")
    
    if len(title) > max_length:
        return ValidationResult(
            False,
            f"Event title too long. Maximum {max_length} characters, got {len(title)}"
        )
    
    # Check for potentially problematic characters
    if any(char in title for char in ['\n', '\r', '\t']):
        return ValidationResult(False, "Event title cannot contain line breaks or tabs")
    
    return ValidationResult(True, cleaned_value=title)


def validate_event_type(event_type: Union[str, EventType]) -> ValidationResult:
    """
    Validate event type.
    
    Args:
        event_type: Event type to validate
    
    Returns:
        ValidationResult with validation status and EventType enum
    """
    if isinstance(event_type, EventType):
        return ValidationResult(True, cleaned_value=event_type)
    
    if not event_type or not isinstance(event_type, str):
        return ValidationResult(False, "Event type is required")
    
    try:
        parsed_type = EventType(event_type.lower().strip())
        return ValidationResult(True, cleaned_value=parsed_type)
    except ValueError:
        valid_types = [e.value for e in EventType]
        return ValidationResult(
            False,
            f"Invalid event type: '{event_type}'. Valid types: {', '.join(valid_types)}"
        )


def validate_date_title_format(date_title: str) -> ValidationResult:
    """
    Validate date;title format used in admin commands.
    
    Args:
        date_title: String in format "YYYY-MM-DD;Title"
    
    Returns:
        ValidationResult with validation status and tuple of (date, title)
    """
    if not date_title or not isinstance(date_title, str):
        return ValidationResult(False, "Date and title string is required")
    
    if ";" not in date_title:
        return ValidationResult(
            False,
            "Invalid format. Use: YYYY-MM-DD;Title (e.g., 2024-12-25;Search Algorithms)"
        )
    
    parts = date_title.split(";", 1)
    if len(parts) != 2:
        return ValidationResult(
            False,
            "Invalid format. Use: YYYY-MM-DD;Title"
        )
    
    date_str, title = parts[0].strip(), parts[1].strip()
    
    # Validate date part
    date_result = validate_date_format(date_str)
    if not date_result:
        return ValidationResult(False, f"Date validation failed: {date_result.error_message}")
    
    # Validate title part
    title_result = validate_event_title(title)
    if not title_result:
        return ValidationResult(False, f"Title validation failed: {title_result.error_message}")
    
    return ValidationResult(
        True,
        cleaned_value=(date_result.cleaned_value, title_result.cleaned_value)
    )


def validate_poll_times_format(times_str: str) -> ValidationResult:
    """
    Validate poll times format (publish;close;reminder).
    
    Args:
        times_str: String in format "HH:MM;HH:MM;HH:MM"
    
    Returns:
        ValidationResult with validation status and tuple of time tuples
    """
    if not times_str or not isinstance(times_str, str):
        return ValidationResult(False, "Poll times string is required")
    
    parts = times_str.split(";")
    if len(parts) != 3:
        return ValidationResult(
            False,
            "Invalid format. Use: HH:MM;HH:MM;HH:MM (publish;close;reminder)\nExample: 15:00;09:00;19:00"
        )
    
    publish_time, close_time, reminder_time = [p.strip() for p in parts]
    time_names = ["publish", "close", "reminder"]
    
    validated_times = []
    for time_str, name in zip([publish_time, close_time, reminder_time], time_names):
        time_result = validate_time_format(time_str)
        if not time_result:
            return ValidationResult(
                False,
                f"Invalid {name} time: {time_result.error_message}"
            )
        validated_times.append(time_result.cleaned_value)
    
    return ValidationResult(True, cleaned_value=tuple(validated_times))


def validate_role_id(role_id_str: str) -> ValidationResult:
    """
    Validate Discord role ID.
    
    Args:
        role_id_str: Role ID string to validate
    
    Returns:
        ValidationResult with validation status and integer role ID
    """
    if not role_id_str or not isinstance(role_id_str, str):
        return ValidationResult(False, "Role ID is required")
    
    role_id_str = role_id_str.strip()
    
    try:
        role_id = int(role_id_str)
        if role_id <= 0:
            return ValidationResult(False, "Role ID must be a positive number")
        
        # Discord snowflake IDs are typically 17-19 digits
        if len(str(role_id)) < 10 or len(str(role_id)) > 20:
            return ValidationResult(
                False,
                "Role ID seems invalid. Discord IDs are typically 17-19 digits long"
            )
        
        return ValidationResult(True, cleaned_value=role_id)
    except ValueError:
        return ValidationResult(False, "Role ID must be a valid number")


def validate_channel_permissions(
    channel,
    required_permissions: List[str]
) -> ValidationResult:
    """
    Validate that bot has required permissions in a channel.
    
    Args:
        channel: Discord channel object
        required_permissions: List of permission names to check
    
    Returns:
        ValidationResult with validation status and missing permissions
    """
    if not hasattr(channel, 'permissions_for') or not hasattr(channel, 'guild'):
        return ValidationResult(False, "Invalid channel object")
    
    bot_permissions = channel.permissions_for(channel.guild.me)
    missing_permissions = []
    
    for perm_name in required_permissions:
        if not getattr(bot_permissions, perm_name, False):
            missing_permissions.append(perm_name)
    
    if missing_permissions:
        return ValidationResult(
            False,
            f"Bot missing permissions in {channel.mention}: {', '.join(missing_permissions)}",
            cleaned_value=missing_permissions
        )
    
    return ValidationResult(True)


def validate_guild_settings(settings: Dict[str, Any]) -> ValidationResult:
    """
    Validate a complete guild settings dictionary.
    
    Args:
        settings: Guild settings dictionary to validate
    
    Returns:
        ValidationResult with validation status and list of errors
    """
    errors = []
    
    # Validate required fields
    required_fields = ['guild_id']
    for field in required_fields:
        if field not in settings:
            errors.append(f"Missing required field: {field}")
    
    # Validate guild_id
    if 'guild_id' in settings:
        try:
            guild_id = int(settings['guild_id'])
            if guild_id <= 0:
                errors.append("Guild ID must be positive")
        except (ValueError, TypeError):
            errors.append("Guild ID must be a valid integer")
    
    # Validate timezone
    if 'timezone' in settings:
        tz_result = validate_timezone(settings['timezone'])
        if not tz_result:
            errors.append(f"Timezone validation failed: {tz_result.error_message}")
    
    # Validate time settings
    time_fields = [
        'poll_publish_time', 'poll_close_time', 
        'reminder_time', 'feedback_publish_time'
    ]
    for field in time_fields:
        if field in settings:
            time_result = validate_time_format(settings[field])
            if not time_result:
                errors.append(f"{field} validation failed: {time_result.error_message}")
    
    # Validate channel IDs
    channel_fields = [
        'poll_channel_id', 'organiser_channel_id', 
        'alerts_channel_id'
    ]
    for field in channel_fields:
        if field in settings and settings[field] is not None:
            try:
                channel_id = int(settings[field])
                if channel_id <= 0:
                    errors.append(f"{field} must be positive")
            except (ValueError, TypeError):
                errors.append(f"{field} must be a valid integer")
    
    # Validate role IDs
    role_fields = ['student_role_id', 'organiser_role_id']
    for field in role_fields:
        if field in settings and settings[field] is not None:
            role_result = validate_role_id(str(settings[field]))
            if not role_result:
                errors.append(f"{field} validation failed: {role_result.error_message}")
    
    if errors:
        return ValidationResult(False, "; ".join(errors))
    
    return ValidationResult(True)


def sanitize_filename(filename: str, max_length: int = 100) -> str:
    """
    Sanitize a filename for safe file system usage.
    
    Args:
        filename: Original filename
        max_length: Maximum allowed length
    
    Returns:
        Sanitized filename
    """
    if not filename:
        return "untitled"
    
    # Remove potentially dangerous characters
    sanitized = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', filename)
    
    # Remove multiple consecutive underscores
    sanitized = re.sub(r'_+', '_', sanitized)
    
    # Trim whitespace and dots (Windows doesn't like trailing dots)
    sanitized = sanitized.strip(' .')
    
    # Truncate if too long
    if len(sanitized) > max_length:
        name, ext = sanitized.rsplit('.', 1) if '.' in sanitized else (sanitized, '')
        if ext:
            max_name_length = max_length - len(ext) - 1
            sanitized = f"{name[:max_name_length]}.{ext}"
        else:
            sanitized = sanitized[:max_length]
    
    # Ensure it's not empty after sanitization
    if not sanitized:
        sanitized = "untitled"
    
    return sanitized


def validate_message_content(content: str, max_length: int = 2000) -> ValidationResult:
    """
    Validate Discord message content.
    
    Args:
        content: Message content to validate
        max_length: Maximum allowed length (Discord limit is 2000)
    
    Returns:
        ValidationResult with validation status
    """
    if not content:
        return ValidationResult(False, "Message content cannot be empty")
    
    if len(content) > max_length:
        return ValidationResult(
            False,
            f"Message too long. Maximum {max_length} characters, got {len(content)}"
        )
    
    return ValidationResult(True, cleaned_value=content)


def is_safe_user_input(user_input: str, allow_newlines: bool = False) -> bool:
    """
    Check if user input is safe (doesn't contain potential injection patterns).
    
    Args:
        user_input: User input to check
        allow_newlines: Whether to allow newline characters
    
    Returns:
        True if input appears safe
    """
    if not user_input:
        return True
    
    # Check for SQL injection patterns (basic)
    dangerous_patterns = [
        r"(?i)(union\s+select)",
        r"(?i)(drop\s+table)",
        r"(?i)(delete\s+from)",
        r"(?i)(insert\s+into)",
        r"(?i)(update\s+\w+\s+set)",
    ]
    
    for pattern in dangerous_patterns:
        if re.search(pattern, user_input):
            return False
    
    # Check for script injection
    if re.search(r"<script[^>]*>", user_input, re.IGNORECASE):
        return False
    
    # Check for excessive control characters
    if not allow_newlines and any(ord(char) < 32 and char not in ['\t'] for char in user_input):
        return False
    
    return True
