"""Poll closing services."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List

import discord  # type: ignore

from models import PollMeta
from storage import load_polls, save_poll
from utils.time import tz_today, to_unix_timestamp, get_poll_closing_date
from services.csv_service import create_attendance_csv

logger = logging.getLogger(__name__)


async def close_poll(
    bot: discord.Client, guild: discord.Guild, poll_meta: PollMeta, guild_settings: Dict[str, Any]
) -> bool:
    try:
        poll_channel = guild.get_channel(poll_meta.channel_id)
        if not poll_channel:
            return False

        try:
            poll_message = await poll_channel.fetch_message(poll_meta.message_id)
            if not poll_message or not poll_message.poll:
                return False
        except discord.NotFound:
            return False

        try:
            ended_poll = await poll_message.poll.end()
        except Exception as e:
            logger.error(f"Error ending poll {poll_meta.id}: {e}")
            return False

        poll_meta.closed_at = datetime.now(timezone.utc)

        organiser_channel_id = guild_settings.get("organiser_channel_id")
        if not organiser_channel_id:
            logger.warning(f"No organiser channel configured for guild {guild.id}")
            return False
            
        organiser_channel = guild.get_channel(organiser_channel_id)
        if not organiser_channel:
            logger.error(f"Organiser channel {organiser_channel_id} not found in guild {guild.id}")
            return False

        sorted_answers = sorted(ended_poll.answers, key=lambda a: a.vote_count, reverse=True)

        results_text = ""
        for i, answer in enumerate(sorted_answers):
            percentage = (answer.vote_count / ended_poll.total_votes * 100) if ended_poll.total_votes > 0 else 0
            emoji = "🥇" if i == 0 else "🥈" if i == 1 else "🥉" if i == 2 else "📝"
            results_text += f"{emoji} {answer.text}: **{answer.vote_count}** votes ({percentage:.1f}%)\n"

            for option in poll_meta.options:
                if option.title == answer.text:
                    voters = [voter.id async for voter in answer.voters()]
                    option.votes = voters
                    break

        if results_text:
            embed = discord.Embed(
                title=f"📊 Poll Results - {poll_meta.poll_date}",
                description=f"Attendance poll results",
                color=0x00FF00,
            )
            embed.add_field(name="📈 Total Votes", value=str(ended_poll.total_votes), inline=True)
            embed.add_field(name="📝 Options", value=str(len(ended_poll.answers)), inline=True)
            embed.add_field(name="🏆 Results", value=results_text, inline=False)
            closed_timestamp = to_unix_timestamp(poll_meta.closed_at)
            embed.set_footer(text=f"Poll closed at <t:{closed_timestamp}:F>")

            await organiser_channel.send(embed=embed)

            csv_content = await create_attendance_csv(poll_meta)
            if csv_content:
                csv_file = discord.File(
                    csv_content,
                    filename=f"attendance_{poll_meta.poll_date}_{poll_meta.id[:8]}.csv",
                )
                await organiser_channel.send(content="📄 Detailed attendance data:", file=csv_file)

            await save_poll(poll_meta.to_dict())
            return True
        return False
    except Exception as e:
        logger.error(f"Error closing poll {poll_meta.id}: {e}")
        return False


async def close_all_active_polls(
    bot: discord.Client, guild: discord.Guild, guild_settings: Dict[str, Any]
) -> int:
    try:
        timezone = guild_settings.get("timezone", "Europe/Helsinki")
        today_date = tz_today(timezone)
        publish_time = guild_settings.get("poll_publish_time", "14:30")
        close_time = guild_settings.get("poll_close_time", "09:00")

        # get_poll_closing_date now imported from utils.time

        all_polls = await load_polls()
        active_polls = [
            PollMeta.from_dict(poll)
            for poll in all_polls.values()
            if poll["guild_id"] == guild.id and poll["closed_at"] is None
        ]

        closed_count = 0
        for poll_meta in active_polls:
            should_close = False
            if poll_meta.is_feedback:
                should_close = True
            else:
                expected_close_date = get_poll_closing_date(
                    poll_meta.poll_date, publish_time, close_time, timezone
                )
                if expected_close_date == today_date:
                    should_close = True

            if should_close and await close_poll(bot, guild, poll_meta, guild_settings):
                closed_count += 1

        return closed_count
    except Exception as e:
        logger.error(f"Error closing active polls for guild {guild.id}: {e}")
        return 0


