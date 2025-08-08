"""
Discord utilities for CampPoll bot.
Common functions for creating embeds, formatting messages, and Discord-specific operations.
"""

import logging
from typing import Optional, Dict, List, Any, Union
from datetime import datetime, timezone

import discord

from models import PollMeta, Event, EventType
from utils.time import format_datetime, get_time_until

logger = logging.getLogger(__name__)


class EmbedColors:
    """Standard colors for different types of embeds."""
    SUCCESS = 0x00ff00
    ERROR = 0xff0000
    WARNING = 0xFFA500
    INFO = 0x007bff
    POLL = 0x9932cc
    FEEDBACK = 0xff9900


class EmbedBuilder:
    """Builder class for creating consistent Discord embeds."""
    
    def __init__(self, title: str = None, description: str = None, color: int = EmbedColors.INFO):
        self.embed = discord.Embed(title=title, description=description, color=color)
    
    def add_field(self, name: str, value: str, inline: bool = False) -> 'EmbedBuilder':
        """Add a field to the embed."""
        self.embed.add_field(name=name, value=value, inline=inline)
        return self
    
    def set_footer(self, text: str, icon_url: str = None) -> 'EmbedBuilder':
        """Set embed footer."""
        self.embed.set_footer(text=text, icon_url=icon_url)
        return self
    
    def set_thumbnail(self, url: str) -> 'EmbedBuilder':
        """Set embed thumbnail."""
        self.embed.set_thumbnail(url=url)
        return self
    
    def set_timestamp(self, timestamp: datetime = None) -> 'EmbedBuilder':
        """Set embed timestamp."""
        if timestamp is None:
            timestamp = datetime.now(timezone.utc)
        self.embed.timestamp = timestamp
        return self
    
    def build(self) -> discord.Embed:
        """Build and return the embed."""
        return self.embed


def create_success_embed(title: str, description: str = None, **kwargs) -> discord.Embed:
    """Create a success embed with standard formatting."""
    return EmbedBuilder(title=f"✅ {title}", description=description, color=EmbedColors.SUCCESS).build()


def create_error_embed(title: str, description: str = None, **kwargs) -> discord.Embed:
    """Create an error embed with standard formatting."""
    return EmbedBuilder(title=f"❌ {title}", description=description, color=EmbedColors.ERROR).build()


def create_warning_embed(title: str, description: str = None, **kwargs) -> discord.Embed:
    """Create a warning embed with standard formatting."""
    return EmbedBuilder(title=f"⚠️ {title}", description=description, color=EmbedColors.WARNING).build()


def create_info_embed(title: str, description: str = None, **kwargs) -> discord.Embed:
    """Create an info embed with standard formatting."""
    return EmbedBuilder(title=f"ℹ️ {title}", description=description, color=EmbedColors.INFO).build()


def create_poll_results_embed(poll_meta: PollMeta, poll_answers: List[Any] = None) -> discord.Embed:
    """
    Create an embed for poll results.
    
    Args:
        poll_meta: Poll metadata
        poll_answers: Optional Discord poll answers with vote counts
    """
    embed = EmbedBuilder(
        title=f"📊 Poll Results - {poll_meta.poll_date}",
        description="Attendance poll results" if not poll_meta.is_feedback else "Feedback poll results",
        color=EmbedColors.POLL
    )
    
    total_votes = poll_meta.total_votes
    if poll_answers:
        total_votes = sum(answer.vote_count for answer in poll_answers)
    
    embed.add_field("📈 Total Votes", str(total_votes), inline=True)
    embed.add_field("📝 Options", str(len(poll_meta.options)), inline=True)
    
    # Add results
    results_text = ""
    if poll_answers:
        sorted_answers = sorted(poll_answers, key=lambda a: a.vote_count, reverse=True)
        for i, answer in enumerate(sorted_answers):
            percentage = (answer.vote_count / total_votes * 100) if total_votes > 0 else 0
            emoji = "🥇" if i == 0 else "🥈" if i == 1 else "🥉" if i == 2 else "📝"
            results_text += f"{emoji} {answer.text}: **{answer.vote_count}** votes ({percentage:.1f}%)\n"
    else:
        # Fallback to poll_meta data
        sorted_options = sorted(poll_meta.options, key=lambda x: x.vote_count, reverse=True)
        for i, option in enumerate(sorted_options):
            percentage = (option.vote_count / total_votes * 100) if total_votes > 0 else 0
            emoji = "🥇" if i == 0 else "🥈" if i == 1 else "🥉" if i == 2 else "📝"
            results_text += f"{emoji} {option.title}: **{option.vote_count}** votes ({percentage:.1f}%)\n"
    
    if results_text:
        embed.add_field("🏆 Results", results_text, inline=False)
    
    if poll_meta.closed_at:
        embed.set_footer(f"Poll closed at {format_datetime(poll_meta.closed_at)}")
    
    return embed.build()


def create_event_embed(event: Event, show_details: bool = True) -> discord.Embed:
    """Create an embed for displaying event information."""
    event_type_emojis = {
        EventType.LECTURE: "📚",
        EventType.CONTEST: "🏆",
        EventType.EXTRA_LECTURE: "📖",
        EventType.EVENING_ACTIVITY: "🌙"
    }
    
    emoji = event_type_emojis.get(event.event_type, "📅")
    title = f"{emoji} {event.event_type.value.replace('_', ' ').title()}"
    
    embed = EmbedBuilder(title=title, color=EmbedColors.INFO)
    embed.add_field("📝 Title", event.title, inline=False)
    embed.add_field("📅 Date", event.date, inline=True)
    
    if show_details:
        embed.add_field("🏷️ Type", event.event_type.value.replace("_", " ").title(), inline=True)
        
        if event.is_pollable:
            embed.add_field("🗳️ Pollable", "Yes" if not event.feedback_only else "Feedback only", inline=True)
        else:
            embed.add_field("🗳️ Pollable", "No", inline=True)
        
        embed.add_field("🕒 Created", format_datetime(event.created_at), inline=False)
        embed.set_footer(f"Event ID: {event.id}")
    
    return embed.build()


def create_reminder_embed(poll_channel_id: int, deadline_text: str, timezone: str) -> discord.Embed:
    """Create an embed for poll reminders."""
    embed = EmbedBuilder(
        title="📝 Attendance Poll Reminder",
        description=(
            "You still have not voted in the attendance poll for tomorrow's events. "
            f"Please cast your vote before the deadline!"
        ),
        color=EmbedColors.WARNING
    )
    
    embed.add_field("🗳️ Poll Channel", f"<#{poll_channel_id}>", inline=False)
    embed.add_field("⏰ Deadline", deadline_text, inline=False)
    embed.set_footer("This is an automated reminder from CampPoll")
    
    return embed.build()


def create_guild_settings_embed(settings: Dict[str, Any]) -> discord.Embed:
    """Create an embed showing guild settings."""
    embed = EmbedBuilder(
        title="⚙️ Server Settings",
        description="Current bot configuration for this server",
        color=EmbedColors.INFO
    )
    
    # Timing settings
    embed.add_field("🕐 Poll Publish Time", settings.get("poll_publish_time", "14:30"), inline=True)
    embed.add_field("⏰ Reminder Time", settings.get("reminder_time", "19:00"), inline=True)
    embed.add_field("🔒 Poll Close Time", settings.get("poll_close_time", "09:00"), inline=True)
    embed.add_field("📝 Feedback Time", settings.get("feedback_publish_time", "22:00"), inline=True)
    embed.add_field("🌍 Timezone", settings.get("timezone", "Europe/Helsinki"), inline=True)
    
    # Channel settings
    poll_channel_id = settings.get("poll_channel_id")
    organiser_channel_id = settings.get("organiser_channel_id")
    alerts_channel_id = settings.get("alerts_channel_id")
    
    embed.add_field(
        "📢 Channels",
        f"Polls: {f'<#{poll_channel_id}>' if poll_channel_id else 'Not set'}\n"
        f"Results: {f'<#{organiser_channel_id}>' if organiser_channel_id else 'Not set'}\n"
        f"Alerts: {f'<#{alerts_channel_id}>' if alerts_channel_id else 'Not set'}",
        inline=False
    )
    
    # Role settings
    student_role_id = settings.get("student_role_id")
    organiser_role_id = settings.get("organiser_role_id")
    
    embed.add_field(
        "👥 Roles",
        f"Students: {f'<@&{student_role_id}>' if student_role_id else 'Not set'}\n"
        f"Organisers: {f'<@&{organiser_role_id}>' if organiser_role_id else 'Not set'}",
        inline=False
    )
    
    embed.set_footer(f"Guild ID: {settings.get('guild_id', 'Unknown')}")
    
    return embed.build()


def create_welcome_embed() -> discord.Embed:
    """Create a welcome embed for new servers."""
    embed = EmbedBuilder(
        title="👋 CampPoll Bot Added!",
        description="Thanks for adding me to your server!",
        color=EmbedColors.SUCCESS
    )
    
    embed.add_field(
        "🚀 Getting Started",
        "Use `/settimezone` to configure your timezone\nUse `/setpolltimes` to set poll schedule",
        inline=False
    )
    embed.add_field(
        "📋 Add Events",
        "Use `/addlecture` and `/addcontest` to add events",
        inline=False
    )
    embed.add_field(
        "⚙️ Admin Only",
        "All commands require Administrator permissions",
        inline=False
    )
    
    return embed.build()


def create_export_embed(poll_meta: PollMeta, export_type: str = "attendance") -> discord.Embed:
    """Create an embed for data exports."""
    if export_type == "attendance":
        title = "📄 Attendance Export"
        description = f"Detailed attendance data for poll on **{poll_meta.poll_date}**"
        color = EmbedColors.INFO
    else:
        title = "👥 User Votes Export"
        description = f"Individual vote data for poll on **{poll_meta.poll_date}**"
        color = EmbedColors.POLL
    
    embed = EmbedBuilder(title=title, description=description, color=color)
    
    embed.add_field(
        "📊 Poll Stats",
        f"**{poll_meta.total_votes}** total votes\n**{len(poll_meta.options)}** options",
        inline=True
    )
    
    status = "🔒 Closed" if poll_meta.is_closed else "🔓 Active"
    embed.add_field("📈 Status", status, inline=True)
    
    if export_type == "user_votes":
        embed.add_field(
            "🔒 Privacy Notice", 
            "Contains user IDs - handle securely",
            inline=True
        )
    
    embed.add_field(
        "📅 Export Details",
        f"Poll Date: {poll_meta.poll_date}\nExported: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}",
        inline=False
    )
    
    embed.set_footer(f"Poll ID: {poll_meta.id}")
    
    return embed.build()


async def safe_send_message(
    channel: discord.abc.Messageable,
    content: str = None,
    embed: discord.Embed = None,
    file: discord.File = None,
    **kwargs
) -> Optional[discord.Message]:
    """
    Safely send a message with error handling.
    
    Returns:
        The sent message or None if failed
    """
    try:
        return await channel.send(content=content, embed=embed, file=file, **kwargs)
    except discord.Forbidden:
        logger.error(f"Permission denied when sending message to {channel}")
    except discord.HTTPException as e:
        logger.error(f"HTTP error when sending message to {channel}: {e}")
    except Exception as e:
        logger.error(f"Unexpected error when sending message to {channel}: {e}")
    return None


async def safe_send_dm(
    user: discord.User,
    content: str = None,
    embed: discord.Embed = None,
    **kwargs
) -> Optional[discord.Message]:
    """
    Safely send a DM with error handling.
    
    Args:
        user: User to send DM to
        content: Message content (optional)
        embed: Embed to send (optional)
        **kwargs: Additional parameters for send()
    
    Returns:
        The sent message or None if failed
    """
    try:
        return await user.send(content=content, embed=embed, **kwargs)
    except discord.Forbidden:
        logger.warning(f"Cannot send DM to user {user.id} - DMs disabled")
    except discord.HTTPException as e:
        logger.error(f"HTTP error when sending DM to user {user.id}: {e}")
    except Exception as e:
        logger.error(f"Unexpected error when sending DM to user {user.id}: {e}")
    return None


def format_user_list(users: List[Union[discord.User, discord.Member]], max_display: int = 10) -> str:
    """
    Format a list of users for display in embeds.
    
    Args:
        users: List of users to format
        max_display: Maximum number of users to show before truncating
    
    Returns:
        Formatted string of users
    """
    if not users:
        return "None"
    
    if len(users) <= max_display:
        return "\n".join(f"• {user.display_name}" for user in users)
    else:
        shown_users = users[:max_display]
        remaining = len(users) - max_display
        result = "\n".join(f"• {user.display_name}" for user in shown_users)
        result += f"\n... and {remaining} more"
        return result


def check_bot_permissions(
    channel: discord.TextChannel,
    required_permissions: List[str]
) -> Dict[str, bool]:
    """
    Check if bot has required permissions in a channel.
    
    Args:
        channel: Channel to check permissions in
        required_permissions: List of permission names to check
    
    Returns:
        Dict mapping permission names to boolean values
    """
    bot_permissions = channel.permissions_for(channel.guild.me)
    results = {}
    
    for perm_name in required_permissions:
        results[perm_name] = getattr(bot_permissions, perm_name, False)
    
    return results


def get_missing_permissions(
    channel: discord.TextChannel,
    required_permissions: List[str]
) -> List[str]:
    """
    Get list of missing permissions for the bot in a channel.
    
    Args:
        channel: Channel to check
        required_permissions: List of permission names required
    
    Returns:
        List of missing permission names
    """
    permission_results = check_bot_permissions(channel, required_permissions)
    return [perm for perm, has_perm in permission_results.items() if not has_perm]
