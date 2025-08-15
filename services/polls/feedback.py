"""Feedback poll publishing services."""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any, Dict, List, Optional

import discord  # type: ignore

from models import Event, EventType, PollMeta, PollOption
from storage import get_events_by_date, save_poll, get_polls_by_guild
from utils.time import tz_today
from utils.discord import ensure_can_send

logger = logging.getLogger(__name__)


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
        "🥱 It was too easy",
        "😑 It was OK",
        "😕 I didn't like it",
    ],
    EventType.CONTEST_EDITORIAL: [
        "😻 It was super useful!",
        "🆗 It was OK",
        "😑 It could be better",
        "🏃‍♀️‍➡️ I didn't attend the analysis",
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
    EventType.CYPRUS_CONTEST: [
        "🩷 Wow, I loved it!",
        "😿 It was too hard",
        "🥱 It was too easy",
        "😑 It was OK",
        "😕 I didn't like it",
    ],
    EventType.CYPRUS_EDITORIAL: [
        "😻 It was super useful!",
        "🆗 It was OK",
        "😑 It could be better",
        "🏃‍♀️‍➡️ I didn't attend the analysis",
    ],
}


def get_event_type_display_name(event_type: EventType) -> str:
    """Return human-readable event type name for feedback poll titles."""
    display_names: Dict[EventType, str] = {
        EventType.CONTEST: "Contest",
        EventType.CONTEST_EDITORIAL: "Contest Analysis",
        EventType.EXTRA_LECTURE: "Extra Lecture",
        EventType.EVENING_ACTIVITY: "Evening Activity",
        EventType.LECTURE: "Lecture",
        EventType.CYPRUS_CONTEST: "🇨🇾 Cyprus Contest",
        EventType.CYPRUS_EDITORIAL: "🇨🇾 Cyprus Editorial",
    }
    return display_names.get(event_type, event_type.value.title())


async def publish_feedback_polls(
    bot: discord.Client, guild: discord.Guild, guild_settings: Dict[str, Any]
) -> List[PollMeta]:
    try:
        logger.info(f"Publishing feedback polls for guild {guild.id}")

        timezone = guild_settings.get("timezone", "Europe/Helsinki")
        today_date = tz_today(timezone)

        events_data = await get_events_by_date(today_date, guild_id=guild.id)
        events = [Event.from_dict(event) for event in events_data]

        # Include standard pollable events (lecture/contest), contest editorials, and Cyprus events (all feedback-only)
        pollable_events = [
            e for e in events
            if (e.is_pollable and not e.feedback_only) or e.event_type in [
                EventType.CONTEST_EDITORIAL, EventType.CYPRUS_CONTEST, EventType.CYPRUS_EDITORIAL
            ]
        ]
        if not pollable_events:
            logger.info(
                f"No pollable events for feedback polls on {today_date} in guild {guild.id}"
            )
            return []

        # Build a set of event_ids that already have active feedback polls for today
        existing_feedback_event_ids: set[str] = set()
        try:
            existing_polls = await get_polls_by_guild(guild.id)
            for poll in existing_polls:
                if (
                    poll.get("is_feedback", False)
                    and poll.get("poll_date") == today_date
                    and poll.get("closed_at") is None
                ):
                    for opt in poll.get("options", []) or []:
                        ev_id = opt.get("event_id")
                        if ev_id:
                            existing_feedback_event_ids.add(ev_id)
        except Exception:
            # If storage lookup fails, proceed without dedupe
            pass

        created_polls: List[PollMeta] = []
        for event in pollable_events:
            if event.id in existing_feedback_event_ids:
                logger.info(
                    f"Feedback poll for event {event.id} already exists; skipping"
                )
                continue
            readable_type = get_event_type_display_name(event.event_type)
            event_option = PollOption(
                event_id=event.id,
                title=f"{readable_type}: {event.title}",
                event_type=event.event_type,
            )
            feedback_poll = await create_feedback_poll(guild, event_option, guild_settings, today_date)
            if feedback_poll:
                created_polls.append(feedback_poll)
                logger.info(
                    f"Created feedback poll for event {event.id}: {event.title}"
                )

        logger.info(f"Published {len(created_polls)} feedback poll(s) for {today_date}")
        return created_polls
    except Exception as e:
        logger.error(f"Error publishing feedback polls for guild {guild.id}: {e}")
        return []


async def create_feedback_poll(
    guild: discord.Guild,
    event_option: PollOption,
    guild_settings: Dict[str, Any],
    poll_date: str,
) -> Optional[PollMeta]:
    try:
        poll_channel_id = guild_settings.get("poll_channel_id")
        poll_channel = await ensure_can_send(guild, poll_channel_id) if poll_channel_id else None
        if not poll_channel:
            logger.warning(f"Cannot send messages in feedback channel {poll_channel_id} (missing or no perms)")
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

        # Map Discord answers to our options by title to capture answer_id
        try:
            answer_ids_by_text = {a.text: str(a.id) for a in (message.poll.answers or [])}
            for opt in poll_options_meta:
                opt.answer_id = answer_ids_by_text.get(opt.title)
        except Exception as e:
            logger.debug(f"Could not map answer IDs for feedback poll: {e}")

        feedback_meta = PollMeta(
            id=str(message.id),
            guild_id=guild.id,
            channel_id=poll_channel.id,
            message_id=message.id,
            poll_date=poll_date,  # Используем реальную дату
            options=poll_options_meta,
            is_feedback=True,
        )

        await save_poll(feedback_meta.to_dict())
        return feedback_meta
    except Exception as e:
        logger.error(
            f"Failed to create feedback poll for event {event_option.event_id}: {e}"
        )
        return None


