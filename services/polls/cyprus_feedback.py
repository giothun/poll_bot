"""
Cyprus Camp Feedback Polls

Специальная система feedback опросов для Cyprus кэмпа.
Отправляет feedback опросы для событий текущего дня в 23:00.
"""

import logging
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional

import discord

from models import Event, EventType, PollMeta, PollOption
from storage import get_events_by_date, save_poll, get_polls_by_guild
from utils.feedback_templates import get_cyprus_feedback_options, is_cyprus_supported_event
from utils.time import tz_today

logger = logging.getLogger(__name__)


async def publish_cyprus_feedback_polls(
    bot: discord.Client,
    guild: discord.Guild,
    guild_settings: Dict[str, Any],
) -> List[PollMeta]:
    """
    Публикует Cyprus feedback опросы для событий текущего дня.
    
    Args:
        bot: Discord bot instance
        guild: Discord guild
        guild_settings: Guild settings dictionary
        
    Returns:
        List of created PollMeta objects
    """
    try:
        logger.info(f"Publishing Cyprus feedback polls for guild {guild.id}")
        
        timezone_str = guild_settings.get("timezone", "Europe/Nicosia")
        today_date = tz_today(timezone_str)
        
        # Получаем события сегодняшнего дня
        events_data = await get_events_by_date(today_date)
        events = [Event.from_dict(event) for event in events_data]
        
        # Фильтруем только поддерживаемые в Cyprus типы событий
        supported_events = [e for e in events if is_cyprus_supported_event(e.event_type)]
        
        if not supported_events:
            logger.info(f"No Cyprus-supported events for {today_date} in guild {guild.id}")
            return []
        
        poll_channel_id = guild_settings.get("poll_channel_id")
        if not poll_channel_id:
            logger.error(f"No poll channel configured for guild {guild.id}")
            return []
        
        poll_channel = guild.get_channel(poll_channel_id)
        if not poll_channel:
            logger.error(f"Poll channel {poll_channel_id} not found in guild {guild.id}")
            return []
        
        # Deduplicate per-event: avoid duplicate feedback polls for the same event/date
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
            pass

        created_polls: List[PollMeta] = []
        
        # Создаём отдельный опрос для каждого события
        for event in supported_events:
            if event.id in existing_feedback_event_ids:
                logger.info(f"Cyprus feedback poll for event {event.id} already exists; skipping")
                continue
            poll_meta = await create_cyprus_feedback_poll(
                guild, event, guild_settings, poll_channel
            )
            if poll_meta:
                created_polls.append(poll_meta)
                await save_poll(poll_meta.to_dict())
        
        logger.info(f"Created {len(created_polls)} Cyprus feedback polls for guild {guild.id}")
        return created_polls
        
    except Exception as e:
        logger.error(f"Error publishing Cyprus feedback polls for guild {guild.id}: {e}")
        return []


async def create_cyprus_feedback_poll(
    guild: discord.Guild,
    event: Event,
    guild_settings: Dict[str, Any],
    poll_channel: discord.TextChannel
) -> Optional[PollMeta]:
    """
    Создаёт Cyprus feedback опрос для конкретного события.
    
    Args:
        guild: Discord guild
        event: Event object
        guild_settings: Guild settings
        poll_channel: Channel to post poll to
        
    Returns:
        PollMeta object or None if failed
    """
    try:
        # Check bot permissions in the target channel
        try:
            bot_permissions = poll_channel.permissions_for(guild.me)
            if not getattr(bot_permissions, "send_messages", False):
                logger.error(
                    f"No permission to send messages in feedback channel {poll_channel.id}"
                )
                return None
        except Exception:
            # If permission check fails for any reason, proceed to avoid blocking in tests
            pass
        # Получаем Cyprus шаблон для этого типа события
        feedback_options = get_cyprus_feedback_options(event.event_type)
        if not feedback_options:
            logger.warning(f"No Cyprus feedback template for event type {event.event_type}")
            return None
        
        # Формируем вопрос
        event_type_name = _get_event_type_display_name(event.event_type)
        question = f"📝 Feedback: {event_type_name} - {event.title}"
        
        # Создаём Discord poll
        poll = discord.Poll(
            question=question,
            duration=timedelta(hours=24),  # Опрос активен 24 часа
            multiple=False  # ВАЖНО: только один ответ!
        )
        
        # Добавляем варианты ответов из Cyprus шаблона
        poll_options: List[PollOption] = []
        for i, option in enumerate(feedback_options):
            answer_text = option.format()  # emoji + text
            poll.add_answer(text=answer_text)
            
            # Создаём PollOption для метаданных (хотя для Cyprus не так критично)
            poll_option = PollOption(
                event_id=event.id,
                title=answer_text,
                event_type=event.event_type,
                votes=[]
            )
            poll_options.append(poll_option)
        
        # Отправляем опрос в канал
        message = await poll_channel.send(poll=poll)
        
        # Try to map Discord answer IDs to our options by matching text
        try:
            poll_obj = getattr(message, "poll", None)
            answers = getattr(poll_obj, "answers", []) or []
            answer_ids_by_text = {getattr(a, "text", None): str(getattr(a, "id", "")) for a in answers}
            for opt in poll_options:
                opt.answer_id = answer_ids_by_text.get(opt.title)
        except Exception as e:
            logger.debug(f"Could not map answer IDs for Cyprus feedback poll: {e}")

        # Создаём метаданные опроса
        poll_meta = PollMeta(
            id=f"cyprus_feedback_{event.id}_{int(datetime.now().timestamp())}",
            guild_id=guild.id,
            channel_id=poll_channel.id,
            message_id=message.id,
            poll_date=event.date,  # Используем реальную дату события
            options=poll_options,
            is_feedback=True
        )
        
        logger.info(f"Created Cyprus feedback poll for event {event.id} ({event.title})")
        return poll_meta
        
    except Exception as e:
        logger.error(f"Error creating Cyprus feedback poll for event {event.id}: {e}")
        return None


def _get_event_type_display_name(event_type: EventType) -> str:
    """
    Получить отображаемое имя типа события.
    
    Args:
        event_type: EventType enum
        
    Returns:
        Human-readable event type name
    """
    display_names = {
        EventType.CONTEST: "Contest",
        EventType.CONTEST_EDITORIAL: "Contest Editorial",
        EventType.EXTRA_LECTURE: "Extra Lecture",
        EventType.EVENING_ACTIVITY: "Evening Activity"
    }
    return display_names.get(event_type, event_type.value.title())


async def get_cyprus_feedback_results(poll_meta: PollMeta, guild: discord.Guild) -> Optional[Dict]:
    """
    Получить результаты Cyprus feedback опроса.
    
    Args:
        poll_meta: Poll metadata
        guild: Discord guild
        
    Returns:
        Dictionary with poll results or None if failed
    """
    try:
        poll_channel = guild.get_channel(poll_meta.channel_id)
        if not poll_channel:
            return None
        
        message = await poll_channel.fetch_message(poll_meta.message_id)
        if not message or not message.poll:
            return None
        
        poll = message.poll
        # Use the event_id from the first option (all options refer to the same event)
        derived_event_id = poll_meta.options[0].event_id if poll_meta.options else None

        results = {
            "poll_id": poll_meta.id,
            "event_id": derived_event_id,
            "total_votes": poll.total_votes,
            "answers": []
        }
        
        for answer in poll.answers:
            answer_data = {
                "text": answer.text,
                "votes": answer.vote_count,
                "percentage": (answer.vote_count / poll.total_votes * 100) if poll.total_votes > 0 else 0
            }
            results["answers"].append(answer_data)
        
        return results
        
    except Exception as e:
        logger.error(f"Error getting Cyprus feedback results for poll {poll_meta.id}: {e}")
        return None
