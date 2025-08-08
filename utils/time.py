"""
Time utilities for CampPoll bot.
Provides timezone-aware date/time operations.
"""

import logging
from datetime import datetime, timedelta, time, timezone
from zoneinfo import ZoneInfo
from typing import Optional, Tuple

logger = logging.getLogger(__name__)

def tz_now(timezone: str = "Europe/Helsinki") -> datetime:
    """Get current time in specified timezone."""
    tz = ZoneInfo(timezone)
    return datetime.now(tz)

def tz_today(timezone: str = "Europe/Helsinki") -> str:
    """Get today's date in YYYY-MM-DD format for specified timezone."""
    return tz_now(timezone).strftime("%Y-%m-%d")

def tz_tomorrow(timezone: str = "Europe/Helsinki") -> str:
    """Get tomorrow's date in YYYY-MM-DD format for specified timezone."""
    tomorrow = tz_now(timezone) + timedelta(days=1)
    return tomorrow.strftime("%Y-%m-%d")

def parse_time(time_str: str) -> Optional[Tuple[int, int]]:
    """
    Parse time string in HH:MM format.
    
    Args:
        time_str: Time in HH:MM format (e.g., "15:30")
    
    Returns:
        Tuple of (hour, minute) or None if invalid
    """
    try:
        parts = time_str.split(":")
        if len(parts) != 2:
            return None
        
        hour = int(parts[0])
        minute = int(parts[1])
        
        if not (0 <= hour <= 23) or not (0 <= minute <= 59):
            return None
        
        return (hour, minute)
    except (ValueError, IndexError):
        return None

def create_scheduled_time(date_str: str, time_str: str, timezone: str) -> Optional[datetime]:
    """
    Create a timezone-aware datetime for a specific date and time.
    
    Args:
        date_str: Date in YYYY-MM-DD format
        time_str: Time in HH:MM format
        timezone: Timezone name (e.g., "Europe/Helsinki")
    
    Returns:
        Timezone-aware datetime or None if invalid
    """
    try:
        # Parse date
        date_obj = datetime.strptime(date_str, "%Y-%m-%d").date()
        
        # Parse time
        time_parts = parse_time(time_str)
        if not time_parts:
            return None
        
        hour, minute = time_parts
        time_obj = time(hour, minute)
        
        # Combine and localize
        tz = ZoneInfo(timezone)
        # Python 3.11+ supports tzinfo param for combine; fallback otherwise
        try:
            dt = datetime.combine(date_obj, time_obj, tzinfo=tz)  # type: ignore[arg-type]
        except TypeError:
            # Older interpreter – set tzinfo after combine (may shift wall time during DST transitions)
            dt = datetime.combine(date_obj, time_obj).replace(tzinfo=tz)
        return dt
        
    except (ValueError, Exception):
        return None

def next_occurrence(time_str: str, timezone: str = "Europe/Helsinki") -> Optional[datetime]:
    """
    Get the next occurrence of a specific time.
    
    Args:
        time_str: Time in HH:MM format
        timezone: Timezone name
    
    Returns:
        Next occurrence of the time, or None if invalid
    """
    now = tz_now(timezone)
    time_parts = parse_time(time_str)
    
    if not time_parts:
        return None
    
    hour, minute = time_parts
    
    # Create datetime for today at the specified time
    target_time = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    
    # If the time has already passed today, schedule for tomorrow
    if target_time <= now:
        target_time += timedelta(days=1)
    
    return target_time

def is_valid_timezone(tz_name: str) -> bool:
    """Check if a timezone name is valid."""
    try:
        ZoneInfo(tz_name)
        return True
    except Exception as e:
        logger.warning(f"Invalid timezone '{tz_name}': {e}")
        return False

def format_datetime(dt: datetime, include_timezone: bool = True) -> str:
    """
    Format datetime for display.
    
    Args:
        dt: Datetime to format
        include_timezone: Whether to include timezone info
    
    Returns:
        Formatted datetime string
    """
    if include_timezone:
        return dt.strftime("%Y-%m-%d %H:%M %Z")
    else:
        return dt.strftime("%Y-%m-%d %H:%M")

def get_time_until(target: datetime) -> str:
    """
    Get human-readable time until target datetime.
    
    Args:
        target: Target datetime
    
    Returns:
        Human-readable time difference (e.g., "2 hours 30 minutes")
    """
    now = datetime.now(target.tzinfo or timezone.utc)
    diff = target - now
    
    if diff.total_seconds() < 0:
        return "Time has passed"
    
    days = diff.days
    hours, remainder = divmod(diff.seconds, 3600)
    minutes, _ = divmod(remainder, 60)
    
    parts = []
    if days > 0:
        parts.append(f"{days} day{'s' if days != 1 else ''}")
    if hours > 0:
        parts.append(f"{hours} hour{'s' if hours != 1 else ''}")
    if minutes > 0:
        parts.append(f"{minutes} minute{'s' if minutes != 1 else ''}")
    
    if not parts:
        return "Less than a minute"
    
    return " ".join(parts)

def chunk_by_days(start_date: str, end_date: str) -> list[str]:
    """
    Generate list of dates between start and end (inclusive).
    
    Args:
        start_date: Start date in YYYY-MM-DD format
        end_date: End date in YYYY-MM-DD format
    
    Returns:
        List of date strings in YYYY-MM-DD format
    """
    try:
        start = datetime.strptime(start_date, "%Y-%m-%d").date()
        end = datetime.strptime(end_date, "%Y-%m-%d").date()
        
        dates = []
        current = start
        while current <= end:
            dates.append(current.strftime("%Y-%m-%d"))
            current += timedelta(days=1)
        
        return dates
    except ValueError:
        return [] 

def to_unix_timestamp(dt: datetime) -> int:
    """
    Convert a datetime object to Unix timestamp (seconds since epoch).
    
    Args:
        dt: Datetime object (timezone-aware)
    
    Returns:
        Unix timestamp as an integer
    """
    return int(dt.timestamp())

def get_discord_timestamp(date_str: str, time_str: str, timezone: str, style: str = "f") -> str:
    """
    Get a Discord-formatted timestamp for a specific date and time.
    
    Args:
        date_str: Date in YYYY-MM-DD format
        time_str: Time in HH:MM format
        timezone: Timezone name (e.g., "Europe/Helsinki")
        style: Discord timestamp style (t=short time, T=long time, d=short date, 
               D=long date, f=short date/time, F=long date/time, R=relative)
    
    Returns:
        Discord-formatted timestamp string (<t:timestamp:style>)
    """
    dt = create_scheduled_time(date_str, time_str, timezone)
    if not dt:
        return f"{date_str} {time_str}"
    
    timestamp = to_unix_timestamp(dt)
    return f"<t:{timestamp}:{style}>"


def get_poll_closing_date(
    poll_date: str, publish_time: str, close_time: str, timezone: str = "Europe/Helsinki"
) -> str:
    """
    Determine closing date based on publish and close times.
    
    Args:
        poll_date: Date when poll was published (YYYY-MM-DD)
        publish_time: Time when polls are published (HH:MM)
        close_time: Time when polls close (HH:MM)
        timezone: Timezone name
    
    Returns:
        Date when poll should close (YYYY-MM-DD)
    """
    try:
        publish_parts = parse_time(publish_time)
        close_parts = parse_time(close_time)
        if not publish_parts or not close_parts:
            return poll_date
        
        publish_minutes = publish_parts[0] * 60 + publish_parts[1]
        close_minutes = close_parts[0] * 60 + close_parts[1]
        
        # If close time is earlier than publish time, poll closes next day
        if close_minutes < publish_minutes:
            from datetime import datetime, timedelta
            poll_date_obj = datetime.strptime(poll_date, "%Y-%m-%d").date()
            return (poll_date_obj + timedelta(days=1)).strftime("%Y-%m-%d")
        
        return poll_date
    except Exception as e:
        logger.warning(f"Error calculating poll closing date: {e}")
        return poll_date


def parse_flexible_date(date_input: str) -> Optional[str]:
    """
    Parse flexible date input and return the next matching date in YYYY-MM-DD format.
    
    Supports:
    - YYYY-MM-DD: exact date
    - MM-DD: next occurrence of this month/day
    - DD: next occurrence of this day of month
    
    Args:
        date_input: Date string in one of the supported formats
        
    Returns:
        Date string in YYYY-MM-DD format, or None if invalid
    """
    from datetime import datetime, timedelta
    import re
    
    if not date_input or not isinstance(date_input, str):
        return None
    
    date_input = date_input.strip()
    today = datetime.now().date()
    
    # YYYY-MM-DD format (exact date)
    if re.match(r'^\d{4}-\d{2}-\d{2}$', date_input):
        try:
            parsed_date = datetime.strptime(date_input, "%Y-%m-%d").date()
            return parsed_date.strftime("%Y-%m-%d")
        except ValueError:
            return None
    
    # MM-DD format (next occurrence of this month/day)
    elif re.match(r'^\d{1,2}-\d{1,2}$', date_input):
        try:
            month, day = map(int, date_input.split('-'))
            if month < 1 or month > 12 or day < 1 or day > 31:
                return None
            
            # Try current year first
            try:
                target_date = datetime(today.year, month, day).date()
                if target_date > today:
                    return target_date.strftime("%Y-%m-%d")
            except ValueError:
                # Invalid date (e.g., Feb 30)
                pass
            
            # Try next year
            try:
                target_date = datetime(today.year + 1, month, day).date()
                return target_date.strftime("%Y-%m-%d")
            except ValueError:
                return None
                
        except (ValueError, IndexError):
            return None
    
    # DD format (next occurrence of this day)
    elif re.match(r'^\d{1,2}$', date_input):
        try:
            day = int(date_input)
            if day < 1 or day > 31:
                return None
            
            # Try current month first
            try:
                target_date = datetime(today.year, today.month, day).date()
                if target_date > today:
                    return target_date.strftime("%Y-%m-%d")
            except ValueError:
                # Day doesn't exist in current month
                pass
            
            # Try next months until we find a valid date
            current = today.replace(day=1)  # First day of current month
            for _ in range(12):  # Search up to 12 months ahead
                # Move to next month
                if current.month == 12:
                    current = current.replace(year=current.year + 1, month=1)
                else:
                    current = current.replace(month=current.month + 1)
                
                try:
                    target_date = current.replace(day=day)
                    if target_date > today:
                        return target_date.strftime("%Y-%m-%d")
                except ValueError:
                    # Day doesn't exist in this month (e.g., Feb 30)
                    continue
            
            return None
            
        except ValueError:
            return None
    
    return None