"""
Poll Manager Service for CampPoll bot.
Handles poll publishing, reminders, and closing operations.
"""

import uuid
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any
import discord
import logging

from models import Event, EventType, PollMeta, PollOption
from storage import (
    get_events_by_date, save_poll, get_poll, 
    get_guild_settings, load_polls
)
from utils.time import tz_tomorrow, tz_now, tz_today
from services.csv_service import create_attendance_csv

logger = logging.getLogger(__name__)

def chunk_events(events: List[Event], max_size: int = 10) -> List[List[Event]]:
    """
    Split events into chunks for multiple polls if needed.
    
    Args:
        events: List of events to chunk
        max_size: Maximum events per poll
    
    Returns:
        List of event chunks
    """
    chunks = []
    for i in range(0, len(events), max_size):
        chunks.append(events[i:i + max_size])
    return chunks

async def publish_attendance_poll(
    bot: discord.Client, 
    guild: discord.Guild,
    guild_settings: Dict[str, Any]
) -> List[PollMeta]:
    """
    Publish daily attendance poll(s) for today's events.
    
    Args:
        bot: Discord bot instance
        guild: Discord guild
        guild_settings: Guild-specific settings
    
    Returns:
        List of created PollMeta objects
    """
    try:
        logger.info(f"Publishing attendance poll for guild {guild.id}")
        
        # Get today's date in guild timezone
        timezone = guild_settings.get("timezone", "Europe/Helsinki")
        today_date = tz_today(timezone)
        
        # Get today's events (only pollable ones)
        events_data = await get_events_by_date(today_date)
        events = [Event.from_dict(event) for event in events_data if Event.from_dict(event).is_pollable]
        
        if not events:
            logger.info(f"No pollable events for {today_date} in guild {guild.id}")
            return []
        
        # Get poll channel
        poll_channel_id = guild_settings.get("poll_channel_id")
        if not poll_channel_id:
            logger.error(f"No poll channel configured for guild {guild.id}")
            return []
        
        poll_channel = guild.get_channel(poll_channel_id)
        if not poll_channel:
            logger.error(f"Poll channel {poll_channel_id} not found in guild {guild.id}")
            return []
        
        # Chunk events if there are more than 10
        event_chunks = chunk_events(events, max_size=10)
        created_polls = []
        
        for chunk_index, event_chunk in enumerate(event_chunks):
            # Create poll question
            poll_question = f"🗳️ Choose your attendance for {today_date}"
            if len(event_chunks) > 1:
                poll_question += f" (Poll {chunk_index + 1}/{len(event_chunks)})"
            
            # Create poll with duration of 24 hours
            poll = discord.Poll(
                question=poll_question,
                duration=timedelta(hours=24),
                multiple=True
            )
            
            # Add options to poll
            poll_options = []
            for event in event_chunk:
                option_text = f"{event.event_type.value.title()}: {event.title}"
                poll.add_answer(text=option_text)
                poll_options.append(PollOption(
                    event_id=event.id,
                    title=option_text,
                    event_type=event.event_type
                ))
            
            # Send message with poll
            message = await poll_channel.send(poll=poll)
            
            # Create poll metadata
            poll_meta = PollMeta(
                id=str(message.id),  # Use message ID as poll ID
                guild_id=guild.id,
                channel_id=poll_channel.id,
                message_id=message.id,
                poll_date=today_date,
                options=poll_options
            )
            
            # Save poll metadata
            await save_poll(poll_meta.to_dict())
            created_polls.append(poll_meta)
            
            logger.info(f"Created poll {poll_meta.id} for {len(event_chunk)} events")
        
        logger.info(f"Published {len(created_polls)} poll(s) for {today_date}")
        return created_polls
        
    except Exception as e:
        logger.error(f"Error publishing attendance poll for guild {guild.id}: {e}")
        return []

async def send_reminders(
    bot: discord.Client,
    guild: discord.Guild,
    guild_settings: Dict[str, Any]
) -> Dict[str, int]:
    """
    Send reminder DMs to users who haven't voted and have the student role.
    
    Args:
        bot: Discord bot instance
        guild: Discord guild
        guild_settings: Guild-specific settings
    
    Returns:
        Dictionary with reminder statistics
    """
    try:
        logger.info(f"Sending poll reminders for guild {guild.id}")
        
        # Get active polls for this guild
        all_polls = await load_polls()
        active_polls = [
            PollMeta.from_dict(poll) for poll in all_polls.values()
            if poll["guild_id"] == guild.id and poll["closed_at"] is None
        ]
        
        if not active_polls:
            logger.info(f"No active polls for guild {guild.id}")
            return {"sent": 0, "failed": 0, "already_reminded": 0}
        
        # Get student role
        student_role = discord.utils.get(guild.roles, name="student")
        if not student_role:
            logger.warning(f"Student role not found in guild {guild.id}")
            return {"sent": 0, "failed": 0, "already_reminded": 0}
            
        # Get all non-bot members with student role
        members = [member for member in guild.members 
                  if not member.bot and student_role in member.roles]
        total_members = len(members)
        
        sent_count = 0
        failed_count = 0
        already_reminded_count = 0
        
        for poll_meta in active_polls:
            # Get non-voters for this poll
            member_ids = [member.id for member in members]
            non_voter_ids = poll_meta.get_non_voters(member_ids)
            
            # Filter out already reminded users
            not_reminded = [
                uid for uid in non_voter_ids 
                if uid not in poll_meta.reminded_users
            ]
            
            already_reminded_count += len(non_voter_ids) - len(not_reminded)
            
            # Send reminders
            for user_id in not_reminded:
                try:
                    user = guild.get_member(user_id)
                    if not user:
                        continue
                    
                    # Create reminder embed
                    embed = discord.Embed(
                        title="📝 Poll Reminder",
                        description=f"Don't forget to vote for your attendance on **{poll_meta.poll_date}**!",
                        color=0xffa500
                    )
                    
                    embed.add_field(
                        name="🗳️ Poll Location",
                        value=f"#{guild.get_channel(poll_meta.channel_id).name}",
                        inline=False
                    )
                    
                    close_time = guild_settings.get("poll_close_time", "09:00")
                    embed.add_field(
                        name="⏰ Deadline",
                        value=f"Tomorrow at {close_time}",
                        inline=False
                    )
                    
                    embed.set_footer(text="This is an automated reminder from CampPoll")
                    
                    await user.send(embed=embed)
                    
                    # Mark as reminded
                    poll_meta.reminded_users.append(user_id)
                    sent_count += 1
                    
                except discord.Forbidden:
                    logger.warning(f"Cannot send DM to user {user_id} - DMs disabled")
                    failed_count += 1
                except Exception as e:
                    logger.error(f"Failed to send reminder to user {user_id}: {e}")
                    failed_count += 1
            
            # Save updated poll metadata
            await save_poll(poll_meta.to_dict())
        
        stats = {
            "sent": sent_count,
            "failed": failed_count,
            "already_reminded": already_reminded_count,
            "total_members": total_members
        }
        
        logger.info(f"Reminder stats for guild {guild.id}: {stats}")
        
        # Send summary to alerts channel if there were failures
        if failed_count > 0:
            alerts_channel_id = guild_settings.get("alerts_channel_id")
            if alerts_channel_id:
                alerts_channel = guild.get_channel(alerts_channel_id)
                if alerts_channel:
                    embed = discord.Embed(
                        title="⚠️ Reminder Summary",
                        description=f"Poll reminder summary for today",
                        color=0xffa500
                    )
                    embed.add_field(name="✅ Sent", value=str(sent_count), inline=True)
                    embed.add_field(name="❌ Failed", value=str(failed_count), inline=True)
                    embed.add_field(name="📝 Note", value="Failed reminders likely due to disabled DMs", inline=False)
                    
                    await alerts_channel.send(embed=embed)
        
        return stats
        
    except Exception as e:
        logger.error(f"Error sending reminders for guild {guild.id}: {e}")
        return {"sent": 0, "failed": 0, "already_reminded": 0}

async def close_poll(
    bot: discord.Client,
    guild: discord.Guild,
    poll_meta: PollMeta,
    guild_settings: Dict[str, Any]
) -> bool:
    """
    Close a specific poll and publish results.
    
    Args:
        bot: Discord bot instance
        guild: Discord guild
        poll_meta: Poll to close
        guild_settings: Guild-specific settings
    
    Returns:
        True if successful, False otherwise
    """
    try:
        logger.info(f"Closing poll {poll_meta.id} for guild {guild.id}")
        
        # Get poll channel and message
        poll_channel = guild.get_channel(poll_meta.channel_id)
        if not poll_channel:
            logger.error(f"Poll channel {poll_meta.channel_id} not found")
            return False
        
        try:
            poll_message = await poll_channel.fetch_message(poll_meta.message_id)
            if not poll_message or not poll_message.poll:
                logger.error(f"Poll message {poll_meta.message_id} not found or not a poll")
                return False
        except discord.NotFound:
            logger.error(f"Poll message {poll_meta.message_id} not found")
            return False
        
        # End the poll
        try:
            ended_poll = await poll_message.poll.end()
            logger.info(f"Successfully ended poll {poll_meta.id}")
        except Exception as e:
            logger.error(f"Failed to end poll {poll_meta.id}: {e}")
            return False
        
        # Mark poll as closed
        poll_meta.closed_at = datetime.utcnow()
        
        # Get organiser channel
        organiser_channel_id = guild_settings.get("organiser_channel_id")
        if not organiser_channel_id:
            logger.error(f"No organiser channel configured for guild {guild.id}")
            return False
        
        organiser_channel = guild.get_channel(organiser_channel_id)
        if not organiser_channel:
            logger.error(f"Organiser channel {organiser_channel_id} not found")
            return False
        
        # Create results embed
        embed = discord.Embed(
            title=f"📊 Poll Results - {poll_meta.poll_date}",
            description=f"Attendance poll results",
            color=0x00ff00
        )
        
        embed.add_field(
            name="📈 Total Votes",
            value=str(ended_poll.total_votes),
            inline=True
        )
        
        embed.add_field(
            name="📝 Options",
            value=str(len(ended_poll.answers)),
            inline=True
        )
        
        # Add voting results
        results_text = ""
        for i, answer in enumerate(ended_poll.answers):
            percentage = (answer.vote_count / ended_poll.total_votes * 100) if ended_poll.total_votes > 0 else 0
            emoji = "🥇" if answer.victor else "🥈" if i == 1 else "🥉" if i == 2 else "📝"
            results_text += f"{emoji} {answer.text}: **{answer.vote_count}** votes ({percentage:.1f}%)\n"
            
            # Update vote counts in metadata
            for option in poll_meta.options:
                if option.title == answer.text:
                    # Get actual voters
                    voters = [voter.id async for voter in answer.voters()]
                    option.votes = voters
                    break
        
        if results_text:
            embed.add_field(name="🏆 Results", value=results_text, inline=False)
        else:
            embed.add_field(name="🏆 Results", value="No votes received", inline=False)
        
        embed.set_footer(text=f"Poll closed at {poll_meta.closed_at.strftime('%Y-%m-%d %H:%M UTC')}")
        
        # Send results
        await organiser_channel.send(embed=embed)
        
        # Create and send CSV
        csv_content = await create_attendance_csv(poll_meta)
        if csv_content:
            csv_file = discord.File(
                csv_content,
                filename=f"attendance_{poll_meta.poll_date}_{poll_meta.id[:8]}.csv"
            )
            await organiser_channel.send(
                content="📄 Detailed attendance data:",
                file=csv_file
            )
        
        # Save updated poll
        await save_poll(poll_meta.to_dict())
        
        logger.info(f"Successfully closed poll {poll_meta.id}")
        return True
        
    except Exception as e:
        logger.error(f"Error closing poll {poll_meta.id}: {e}")
        return False

async def close_all_active_polls(
    bot: discord.Client,
    guild: discord.Guild,
    guild_settings: Dict[str, Any]
) -> int:
    """
    Close all active polls for a guild.
    
    Args:
        bot: Discord bot instance
        guild: Discord guild
        guild_settings: Guild-specific settings
    
    Returns:
        Number of polls closed
    """
    try:
        # Get active polls
        all_polls = await load_polls()
        active_polls = [
            PollMeta.from_dict(poll) for poll in all_polls.values()
            if poll["guild_id"] == guild.id and poll["closed_at"] is None
        ]
        
        closed_count = 0
        for poll_meta in active_polls:
            if await close_poll(bot, guild, poll_meta, guild_settings):
                closed_count += 1
        
        return closed_count
        
    except Exception as e:
        logger.error(f"Error closing active polls for guild {guild.id}: {e}")
        return 0