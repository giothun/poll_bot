"""Reminder services for polls."""

from __future__ import annotations

import asyncio
import logging
import os
from typing import Any, Dict, List

import discord  # type: ignore

from models import PollMeta
from storage import load_polls, save_poll
from utils.time import tz_today, get_discord_timestamp, get_poll_closing_date
from utils.discord import create_reminder_embed

logger = logging.getLogger(__name__)


async def send_reminders(
    bot: discord.Client, guild: discord.Guild, guild_settings: Dict[str, Any]
) -> Dict[str, int]:
    try:
        logger.info(f"Sending poll reminders for guild {guild.id}")

        all_polls = await load_polls()
        active_polls: List[PollMeta] = [
            PollMeta.from_dict(poll)
            for poll in all_polls.values()
            if poll["guild_id"] == guild.id and poll["closed_at"] is None
        ]

        if not active_polls:
            logger.info(f"No active polls for guild {guild.id}")
            return {"sent": 0, "failed": 0, "already_reminded": 0, "total_polls": 0}

        # resolve student role
        student_role_id = 0
        try:
            role_id_value = guild_settings.get("student_role_id") or os.getenv("STUDENT_ROLE_ID", "0") or "0"
            student_role_id = int(role_id_value)
        except (TypeError, ValueError) as e:
            logger.warning(f"Invalid student_role_id '{role_id_value}' in guild {guild.id}: {e}")
            student_role_id = 0

        student_role = next(
            (r for r in guild.roles if r.name.lower() == "student" or (student_role_id and r.id == student_role_id)),
            None,
        )
        if not student_role:
            logger.warning(f"Student role not found in guild {guild.id}")
            return {"sent": 0, "failed": 0, "already_reminded": 0}

        members = [m for m in guild.members if not m.bot and student_role in m.roles]

        sent = failed = already = 0

        member_ids = [m.id for m in members]
        user_to_polls: Dict[int, List[PollMeta]] = {}
        for pm in active_polls:
            non_voters = pm.get_non_voters(member_ids)
            for uid in non_voters:
                if uid in pm.reminded_users:
                    already += 1
                    continue
                user_to_polls.setdefault(uid, []).append(pm)

        for user_id, polls_for_user in user_to_polls.items():
            try:
                user = guild.get_member(user_id)
                if not user:
                    continue

                first_poll = polls_for_user[0]
                poll_channel = guild.get_channel(first_poll.channel_id)

                close_time = guild_settings.get("poll_close_time", "09:00")
                publish_time = guild_settings.get("poll_publish_time", "14:30")
                timezone = guild_settings.get("timezone", "Europe/Helsinki")

                # Calculate the correct deadline date using the same logic as poll closing
                deadline_date = get_poll_closing_date(first_poll.poll_date, publish_time, close_time, timezone)
                deadline_ts = get_discord_timestamp(deadline_date, close_time, timezone, style="F")

                # Use the dedicated function for consistent formatting
                if poll_channel:
                    embed = create_reminder_embed(poll_channel.id, deadline_ts, timezone)
                else:
                    # If no poll channel, create a basic reminder
                    embed = discord.Embed(
                        title="📝 Attendance Poll Reminder",
                        description=(
                            "You still have not voted in the attendance poll for tomorrow's events. "
                            "Please cast your vote before the deadline!"
                        ),
                        color=0xFFA500,
                    )
                    embed.add_field(name="⏰ Deadline", value=deadline_ts, inline=False)
                    embed.set_footer(text="This is an automated reminder from CampPoll")

                await user.send(embed=embed)
                await asyncio.sleep(0.3)
                sent += 1
                for pm in polls_for_user:
                    pm.reminded_users.append(user_id)
            except discord.Forbidden:
                failed += 1
            except discord.HTTPException as e:
                if getattr(e, "status", None) == 429:
                    await asyncio.sleep(float(getattr(e, "retry_after", 2)) or 2)
                failed += 1
            except Exception as e:
                logger.error(f"Unexpected error sending reminder to user {user_id}: {e}")
                failed += 1

        for pm in active_polls:
            await save_poll(pm.to_dict())

        return {"sent": sent, "failed": failed, "already_reminded": already, "total_members": len(members), "total_polls": len(active_polls)}
    except Exception as e:
        logger.error(f"Error sending reminders for guild {guild.id}: {e}")
        return {"sent": 0, "failed": 0, "already_reminded": 0, "total_polls": 0}


