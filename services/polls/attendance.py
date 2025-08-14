"""Attendance poll publishing services."""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any, Dict, List

import discord  # type: ignore

from models import Event, PollMeta, PollOption
from storage import get_events_by_date, save_poll, get_polls_by_guild
from utils.time import tz_tomorrow

logger = logging.getLogger(__name__)


def chunk_events(events: List[Event], max_size: int = 10) -> List[List[Event]]:
    chunks: List[List[Event]] = []
    for i in range(0, len(events), max_size):
        chunks.append(events[i : i + max_size])
    return chunks


async def publish_attendance_poll(
    bot: discord.Client,
    guild: discord.Guild,
    guild_settings: Dict[str, Any],
) -> List[PollMeta]:
    try:
        logger.info(f"Publishing attendance poll for guild {guild.id}")

        timezone = guild_settings.get("timezone", "Europe/Helsinki")
        tomorrow_date = tz_tomorrow(timezone)

        # Get tomorrow's events
        events_data = await get_events_by_date(tomorrow_date)
        events = [Event.from_dict(event) for event in events_data]

        # Filter pollable events
        pollable_events = [e for e in events if e.is_pollable and not e.feedback_only]

        if not pollable_events:
            logger.info(
                f"No pollable events for {tomorrow_date} in guild {guild.id}"
            )
            return []

        # Deduplicate: if there are already active attendance polls for this date, skip
        try:
            existing_polls = await get_polls_by_guild(guild.id)
            if any(
                (not poll.get("is_feedback", False))
                and poll.get("poll_date") == tomorrow_date
                and poll.get("closed_at") is None
                for poll in existing_polls
            ):
                logger.info(
                    f"Attendance poll(s) for {tomorrow_date} already exist in guild {guild.id}; skipping publish"
                )
                return []
        except Exception:
            # If storage lookup fails, proceed to avoid blocking publish entirely
            pass

        poll_channel_id = guild_settings.get("poll_channel_id")
        if not poll_channel_id:
            logger.error(f"No poll channel configured for guild {guild.id}")
            return []

        poll_channel = guild.get_channel(poll_channel_id)
        if not poll_channel:
            logger.error(
                f"Poll channel {poll_channel_id} not found in guild {guild.id}"
            )
            return []

        # Check bot permissions
        bot_permissions = poll_channel.permissions_for(guild.me)
        if not bot_permissions.send_messages:
            logger.error(f"No permission to send messages in channel {poll_channel_id}")
            return []

        event_chunks = chunk_events(pollable_events, max_size=10)
        created_polls: List[PollMeta] = []

        for chunk_index, event_chunk in enumerate(event_chunks):
            poll_question = f"🗳️ Choose your attendance for {tomorrow_date}"
            if len(event_chunks) > 1:
                poll_question += f" (Poll {chunk_index + 1}/{len(event_chunks)})"

            poll = discord.Poll(
                question=poll_question, duration=timedelta(hours=24), multiple=True
            )

            poll_options: List[PollOption] = []
            for event in event_chunk:
                option_text = f"{event.event_type.value.title()}: {event.title}"
                poll.add_answer(text=option_text)
                poll_options.append(
                    PollOption(
                        event_id=event.id,
                        title=option_text,
                        event_type=event.event_type,
                    )
                )

            message = await poll_channel.send(poll=poll)

            # Map Discord answers to our options by title to capture answer_id
            try:
                answer_ids_by_text = {
                    a.text: str(a.id) for a in (message.poll.answers or [])
                }
                for opt in poll_options:
                    opt.answer_id = answer_ids_by_text.get(opt.title)
            except Exception as e:
                logger.debug(f"Could not map answer IDs for attendance poll: {e}")

            poll_meta = PollMeta(
                id=str(message.id),
                guild_id=guild.id,
                channel_id=poll_channel.id,
                message_id=message.id,
                poll_date=tomorrow_date,
                options=poll_options,
            )

            await save_poll(poll_meta.to_dict())
            created_polls.append(poll_meta)

            logger.info(
                f"Created poll {poll_meta.id} for {len(event_chunk)} events"
            )

        logger.info(f"Published {len(created_polls)} poll(s) for {tomorrow_date}")
        return created_polls
    except Exception as e:
        logger.error(
            f"Error publishing attendance poll for guild {guild.id}: {e}"
        )
        return []


