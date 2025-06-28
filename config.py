"""
Configuration management for CampPoll bot.
Handles environment variables and bot settings.
"""

import os
from dataclasses import dataclass
from typing import Optional
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

@dataclass
class BotConfig:
    """Bot configuration from environment variables."""
    token: str
    timezone: str = "Europe/Helsinki"
    poll_publish_time: str = "14:30"
    poll_close_time: str = "09:00"
    reminder_time: str = "19:00"
    feedback_publish_time: str = "22:00"
    
    # Channel names (can be overridden per guild)
    poll_channel_name: str = "daily-polls"
    organiser_channel_name: str = "organisers"
    alerts_channel_name: str = "bot-alerts"
    
    # Data paths
    data_dir: str = "data"
    events_file: str = "events.json"
    polls_file: str = "polls.json"
    
    @classmethod
    def from_env(cls) -> "BotConfig":
        """Create config from environment variables."""
        token = os.getenv("DISCORD_BOT_TOKEN")
        if not token:
            raise ValueError("DISCORD_BOT_TOKEN environment variable is required")
        
        return cls(
            token=token,
            timezone=os.getenv("TIMEZONE", "Europe/Helsinki"),
                    poll_publish_time=os.getenv("POLL_PUBLISH_TIME", "14:30"),
        poll_close_time=os.getenv("POLL_CLOSE_TIME", "09:00"),
        reminder_time=os.getenv("REMINDER_TIME", "19:00"),
        feedback_publish_time=os.getenv("FEEDBACK_PUBLISH_TIME", "22:00"),
            poll_channel_name=os.getenv("POLL_CHANNEL_NAME", "daily-polls"),
            organiser_channel_name=os.getenv("ORGANISER_CHANNEL_NAME", "organisers"),
            alerts_channel_name=os.getenv("ALERTS_CHANNEL_NAME", "bot-alerts"),
        )

# Global config instance
config: Optional[BotConfig] = None

def get_config() -> BotConfig:
    """Get the global configuration instance."""
    global config
    if config is None:
        config = BotConfig.from_env()
    return config 