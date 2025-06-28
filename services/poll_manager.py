"""
Poll Manager Service for CampPoll bot.
Handles poll publishing, reminders, and closing operations.
"""

# pylint: disable=import-error

import uuid
from datetime import datetime, timedelta, timezone
from typing import List, Optional, Dict, Any
import discord  # type: ignore
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
    Publish daily attendance poll(s) for tomorrow's events.
    
    Args:
        bot: Discord bot instance
        guild: Discord guild
        guild_settings: Guild-specific settings
    
    Returns:
        List of created PollMeta objects
    """
    try:
        logger.info(f"Publishing attendance poll for guild {guild.id}")
        
        # Get tomorrow's date in guild timezone
        timezone = guild_settings.get("timezone", "Europe/Helsinki")
        tomorrow_date = tz_tomorrow(timezone)
        
        # Get tomorrow's events (only pollable ones)
        events_data = await get_events_by_date(tomorrow_date)
        events = [Event.from_dict(event) for event in events_data]
        
        # Separate feedback-only events and pollable events
        feedback_only_events = [e for e in events if e.feedback_only]
        pollable_events = [e for e in events if e.is_pollable and not e.feedback_only]
        
        # Create feedback polls immediately for feedback_only events
        for fb_event in feedback_only_events:
            dummy_option = PollOption(
                event_id=fb_event.id,
                title=f"{fb_event.event_type.value.title()}: {fb_event.title}",
                event_type=fb_event.event_type,
            )
            await create_feedback_poll(guild, dummy_option, guild_settings)
        
        if not pollable_events:
            logger.info("Only feedback-only events tomorrow, no attendance poll needed")
            return []
        
        events = pollable_events
        if not events:
            logger.info(f"No pollable events for {tomorrow_date} in guild {guild.id}")
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
            poll_question = f"🗳️ Choose your attendance for {tomorrow_date}"
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
                poll_date=tomorrow_date,
                options=poll_options
            )
            
            # Save poll metadata
            await save_poll(poll_meta.to_dict())
            created_polls.append(poll_meta)
            
            logger.info(f"Created poll {poll_meta.id} for {len(event_chunk)} events")
        
        logger.info(f"Published {len(created_polls)} poll(s) for {tomorrow_date}")
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
        
        # Get student role (by name or ID)
        student_role = next(
            (r for r in guild.roles 
             if r.name.lower() == "student" or r.id == 1367172527012712620), None
        )
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

        # Build mapping of user -> polls they have not voted in yet
        member_ids = [member.id for member in members]
        user_to_polls: Dict[int, List[PollMeta]] = {}

        for poll_meta in active_polls:
            non_voter_ids = poll_meta.get_non_voters(member_ids)

            for uid in non_voter_ids:
                # Skip if they were already reminded for this poll earlier
                if uid in poll_meta.reminded_users:
                    already_reminded_count += 1
                    continue

                user_to_polls.setdefault(uid, []).append(poll_meta)

        # Now send at most one DM per user
        for user_id, polls_for_user in user_to_polls.items():
            try:
                user = guild.get_member(user_id)
                if not user:
                    continue

                # Use first poll for channel reference
                first_poll = polls_for_user[0]
                poll_channel = guild.get_channel(first_poll.channel_id)

                embed = discord.Embed(
                    title="📝 Attendance Poll Reminder",
                    description="You still have not voted in tomorrow's attendance poll. Please cast your vote!",
                    color=0xffa500
                )

                if poll_channel:
                    embed.add_field(
                        name="🗳️ Poll Channel",
                        value=f"#{poll_channel.name}",
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

                sent_count += 1

                # Mark reminded for all their outstanding polls
                for poll_meta in polls_for_user:
                    poll_meta.reminded_users.append(user_id)

            except discord.Forbidden:
                logger.warning(f"Cannot send DM to user {user_id} - DMs disabled")
                failed_count += 1
            except Exception as e:
                logger.error(f"Failed to send reminder to user {user_id}: {e}")
                failed_count += 1

        # Persist updates to polls
        for poll_meta in active_polls:
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
        
        # Mark poll as closed with aware datetime
        poll_meta.closed_at = datetime.now(timezone.utc)
        
        # Get organiser channel
        organiser_channel_id = guild_settings.get("organiser_channel_id")
        if not organiser_channel_id:
            logger.error(f"No organiser channel configured for guild {guild.id}")
            return False
        
        organiser_channel = guild.get_channel(organiser_channel_id)
        if not organiser_channel:
            logger.error(f"Organiser channel {organiser_channel_id} not found")
            return False
        
        # Sort answers by vote_count descending for consistent podium labels
        sorted_answers = sorted(ended_poll.answers, key=lambda a: a.vote_count, reverse=True)

        results_text = ""
        for i, answer in enumerate(sorted_answers):
            percentage = (answer.vote_count / ended_poll.total_votes * 100) if ended_poll.total_votes > 0 else 0
            emoji = "🥇" if i == 0 else "🥈" if i == 1 else "🥉" if i == 2 else "📝"
            results_text += f"{emoji} {answer.text}: **{answer.vote_count}** votes ({percentage:.1f}%)\n"
            
            # Update vote counts in metadata
            for option in poll_meta.options:
                if option.title == answer.text:
                    # Get actual voters
                    voters = [voter.id async for voter in answer.voters()]
                    option.votes = voters
                    break
        
        if results_text:
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
            
            embed.add_field(name="🏆 Results", value=results_text, inline=False)
            
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

async def publish_feedback_polls(
    bot: discord.Client, 
    guild: discord.Guild,
    guild_settings: Dict[str, Any]
) -> List[PollMeta]:
    """
    Publish feedback polls for today's events.
    
    Args:
        bot: Discord bot instance
        guild: Discord guild
        guild_settings: Guild-specific settings
    
    Returns:
        List of created PollMeta objects
    """
    try:
        logger.info(f"Publishing feedback polls for guild {guild.id}")
        
        # Get today's date in guild timezone
        timezone = guild_settings.get("timezone", "Europe/Helsinki")
        today_date = tz_today(timezone)
        
        # Get today's events (only pollable ones)
        events_data = await get_events_by_date(today_date)
        events = [Event.from_dict(event) for event in events_data]
        
        # Filter for pollable events only
        pollable_events = [e for e in events if e.is_pollable and not e.feedback_only]
        
        if not pollable_events:
            logger.info(f"No pollable events for feedback polls on {today_date} in guild {guild.id}")
            return []
        
        # Create feedback polls for each event
        created_polls = []
        
        for event in pollable_events:
            event_option = PollOption(
                event_id=event.id,
                title=f"{event.event_type.value.title()}: {event.title}",
                event_type=event.event_type,
            )
            
            feedback_poll = await create_feedback_poll(guild, event_option, guild_settings)
            if feedback_poll:
                created_polls.append(feedback_poll)
                logger.info(f"Created feedback poll for event {event.id}: {event.title}")
        
        logger.info(f"Published {len(created_polls)} feedback poll(s) for {today_date}")
        return created_polls
        
    except Exception as e:
        logger.error(f"Error publishing feedback polls for guild {guild.id}: {e}")
        return []

FEEDBACK_OPTIONS: Dict[EventType, List[str]] = {
    EventType.LECTURE: [
        "😻 It was super useful!",
        "🆗 I knew smth before, but still enjoyed it!",
        "😑 It could be better",
        "🏃‍♀️‍➡️ I was attending another class",
    ],
    EventType.CONTEST: [
        "🩷 Wow, I loved it!",
        "😿 It was too hard",
        "🙅‍♂️ I didn't participate",
    ],
    EventType.EXTRA_LECTURE: [
        "🤩 Cool – It was informative and useful",
        "👍 Okay – It was interesting but not so relevant",
        "😞 Meh – It could have been better",
        "🛑 I didn't participate",
    ],
    EventType.EVENING_ACTIVITY: [
        "❤️‍🔥 Cool – I want more like it",
        "😃 Okay – It was fun",
        "😕 Meh – I could do something better",
        "🙈 I didn't participate",
    ],
}

# Helper: publish a feedback poll for a single event option (no reminders)
async def create_feedback_poll(
    guild: discord.Guild,
    event_option: PollOption,
    guild_settings: Dict[str, Any],
) -> Optional[PollMeta]:
    """Publish a feedback poll for the given event option.

    Returns the PollMeta if created, otherwise None.
    """
    try:
        poll_channel_id = guild_settings.get("poll_channel_id")
        poll_channel = guild.get_channel(poll_channel_id) if poll_channel_id else None
        if not poll_channel:
            return None

        feedback_texts = FEEDBACK_OPTIONS.get(event_option.event_type)
        if not feedback_texts:
            return None

        question = f"📝 Feedback for {event_option.title}"

        poll = discord.Poll(question=question, multiple=False, duration=timedelta(hours=24))

        poll_options_meta: List[PollOption] = []
        for text in feedback_texts:
            poll.add_answer(text=text)
            poll_options_meta.append(
                PollOption(
                    event_id=event_option.event_id,
                    title=text,
                    event_type=event_option.event_type,
                )
            )

        message = await poll_channel.send(poll=poll)

        feedback_meta = PollMeta(
            id=str(message.id),
            guild_id=guild.id,
            channel_id=poll_channel.id,
            message_id=message.id,
            poll_date=event_option.event_id,  # Store related event id for reference
            options=poll_options_meta,
            is_feedback=True,
        )

        await save_poll(feedback_meta.to_dict())
        return feedback_meta
    except Exception as e:
        logger.error(f"Failed to create feedback poll for event {event_option.event_id}: {e}")
        return None