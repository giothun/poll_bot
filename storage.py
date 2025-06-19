"""
Storage utilities for CampPoll bot.
Handles async JSON file operations with thread safety.
"""

import json
import os
import asyncio
from typing import Any, Dict, List, Optional
from pathlib import Path
from datetime import datetime, timedelta, timezone

from config import get_config

# Global lock for file operations to prevent race conditions
_file_locks: Dict[str, asyncio.Lock] = {}

def _get_file_lock(filename: str) -> asyncio.Lock:
    """Get or create a lock for a specific file."""
    if filename not in _file_locks:
        _file_locks[filename] = asyncio.Lock()
    return _file_locks[filename]

async def load(filename: str, default: Any = None) -> Any:
    """
    Load data from a JSON file.
    
    Args:
        filename: Name of the file (without .json extension)
        default: Default value to return if file doesn't exist
    
    Returns:
        Loaded data or default value
    """
    config = get_config()
    file_path = Path(config.data_dir) / f"{filename}.json"
    
    # Ensure data directory exists
    file_path.parent.mkdir(exist_ok=True)
    
    # Use file-specific lock
    async with _get_file_lock(filename):
        try:
            if not file_path.exists():
                return default
            
            # Read file asynchronously
            loop = asyncio.get_event_loop()
            content = await loop.run_in_executor(None, file_path.read_text, 'utf-8')
            return json.loads(content)
            
        except (json.JSONDecodeError, OSError) as e:
            print(f"Error loading {file_path}: {e}")
            return default

async def save(filename: str, data: Any) -> bool:
    """
    Save data to a JSON file.
    
    Args:
        filename: Name of the file (without .json extension)
        data: Data to save
    
    Returns:
        True if successful, False otherwise
    """
    config = get_config()
    file_path = Path(config.data_dir) / f"{filename}.json"
    
    # Ensure data directory exists
    file_path.parent.mkdir(exist_ok=True)
    
    # Use file-specific lock
    async with _get_file_lock(filename):
        try:
            # Convert data to JSON string
            json_str = json.dumps(data, indent=2, ensure_ascii=False, default=str)

            # Write atomically: write to a temp file then move in place
            tmp_path = file_path.with_suffix(".tmp")

            def _atomic_write():
                tmp_path.write_text(json_str, encoding="utf-8")
                os.replace(tmp_path, file_path)

            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, _atomic_write)
            return True
            
        except (TypeError, OSError) as e:
            print(f"Error saving {file_path}: {e}")
            return False

# Event storage functions

async def load_events() -> List[Dict]:
    """Load all events from storage."""
    return await load("events", [])

async def save_events(events: List[Dict]) -> bool:
    """Save events to storage."""
    return await save("events", events)

async def add_event(event_dict: Dict) -> bool:
    """Add a new event to storage."""
    events = await load_events()
    events.append(event_dict)
    return await save_events(events)

async def update_event(event_id: str, updated_event: Dict) -> bool:
    """Update an existing event in storage."""
    events = await load_events()
    for i, event in enumerate(events):
        if event.get("id") == event_id:
            events[i] = updated_event
            return await save_events(events)
    return False

async def delete_event(event_id: str) -> bool:
    """Delete an event from storage."""
    events = await load_events()
    original_length = len(events)
    events = [event for event in events if event.get("id") != event_id]
    
    if len(events) < original_length:
        return await save_events(events)
    return False

async def get_events_by_date(date: str) -> List[Dict]:
    """Get all events for a specific date."""
    events = await load_events()
    return [event for event in events if event.get("date") == date]

async def get_events_by_type(event_type: str, date: Optional[str] = None) -> List[Dict]:
    """Get events by type, optionally filtered by date."""
    events = await load_events()
    filtered = [event for event in events if event.get("event_type") == event_type]
    
    if date:
        filtered = [event for event in filtered if event.get("date") == date]
    
    return filtered

# Poll storage functions

async def load_polls() -> Dict[str, Dict]:
    """Load all polls from storage. Returns dict with poll_id as key."""
    polls_list = await load("polls", [])
    # Convert list to dict for easier access
    return {poll["id"]: poll for poll in polls_list}

async def save_polls(polls_dict: Dict[str, Dict]) -> bool:
    """Save polls to storage."""
    # Convert dict back to list for storage
    polls_list = list(polls_dict.values())
    return await save("polls", polls_list)

async def save_poll(poll_dict: Dict) -> bool:
    """Save or update a single poll."""
    polls = await load_polls()
    polls[poll_dict["id"]] = poll_dict
    return await save_polls(polls)

async def get_poll(poll_id: str) -> Optional[Dict]:
    """Get a specific poll by ID."""
    polls = await load_polls()
    return polls.get(poll_id)

async def get_active_polls() -> List[Dict]:
    """Get all active (non-closed) polls."""
    polls = await load_polls()
    return [poll for poll in polls.values() if poll.get("closed_at") is None]

async def get_polls_by_guild(guild_id: int) -> List[Dict]:
    """Get all polls for a specific guild."""
    polls = await load_polls()
    return [poll for poll in polls.values() if poll.get("guild_id") == guild_id]

async def delete_poll(poll_id: str) -> bool:
    """Delete a poll from storage."""
    polls = await load_polls()
    if poll_id in polls:
        del polls[poll_id]
        return await save_polls(polls)
    return False

# Guild settings storage functions

async def load_guild_settings() -> Dict[str, Dict]:
    """Load all guild settings. Returns dict with guild_id as key."""
    settings_list = await load("guild_settings", [])
    # Convert list to dict for easier access
    return {str(setting["guild_id"]): setting for setting in settings_list}

async def save_guild_settings(settings_dict: Dict[str, Dict]) -> bool:
    """Save guild settings to storage."""
    # Convert dict back to list for storage
    settings_list = list(settings_dict.values())
    return await save("guild_settings", settings_list)

async def get_guild_settings(guild_id: int) -> Optional[Dict]:
    """Get settings for a specific guild."""
    settings = await load_guild_settings()
    return settings.get(str(guild_id))

async def save_guild_setting(guild_setting: Dict) -> bool:
    """Save or update guild settings."""
    settings = await load_guild_settings()
    guild_id = str(guild_setting["guild_id"])
    settings[guild_id] = guild_setting
    return await save_guild_settings(settings)

# Utility functions

async def get_file_size(filename: str) -> int:
    """Get the size of a data file in bytes."""
    config = get_config()
    file_path = Path(config.data_dir) / f"{filename}.json"
    
    try:
        return file_path.stat().st_size if file_path.exists() else 0
    except OSError:
        return 0

async def cleanup_old_polls(days_old: int = 30) -> int:
    """Remove polls older than specified days. Returns number of removed polls."""
    polls = await load_polls()
    
    original_count = len(polls)
    cleaned_polls = {}
    
    cutoff_date = datetime.now(timezone.utc) - timedelta(days=days_old)
    
    for poll_id, poll in polls.items():
        try:
            published_at = datetime.fromisoformat(poll["published_at"])
            if published_at.tzinfo is None:
                published_at = published_at.replace(tzinfo=timezone.utc)
            if published_at >= cutoff_date:
                cleaned_polls[poll_id] = poll
        except (KeyError, ValueError):
            # Keep polls with invalid timestamps
            cleaned_polls[poll_id] = poll
    
    removed_count = original_count - len(cleaned_polls)
    if removed_count > 0:
        await save_polls(cleaned_polls)
    
    return removed_count

async def get_storage_stats() -> Dict[str, Any]:
    """Get statistics about storage usage."""
    events_size = await get_file_size("events")
    polls_size = await get_file_size("polls") 
    settings_size = await get_file_size("guild_settings")
    
    events_count = len(await load_events())
    polls_count = len(await load_polls())
    
    return {
        "events_count": events_count,
        "polls_count": polls_count,
        "events_size_bytes": events_size,
        "polls_size_bytes": polls_size,
        "settings_size_bytes": settings_size,
        "total_size_bytes": events_size + polls_size + settings_size,
        "total_size_kb": (events_size + polls_size + settings_size) / 1024
    } 