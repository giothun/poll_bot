"""
Cyprus Camp Feedback Templates

Специальные шаблоны для Cyprus кэмпа с предопределёнными вариантами ответов
для каждого типа активности.
"""

from models import EventType
from typing import Dict, List


class FeedbackOption:
    """Опция feedback с emoji и текстом."""
    def __init__(self, emoji: str, text: str):
        self.emoji = emoji
        self.text = text
    
    def format(self) -> str:
        """Форматирует опцию для Discord poll."""
        return f"{self.emoji} {self.text}"


# Cyprus Camp Feedback Templates
CYPRUS_FEEDBACK_TEMPLATES: Dict[EventType, List[FeedbackOption]] = {
    EventType.CONTEST: [
        FeedbackOption("🩷", "Wow, I loved it!"),
        FeedbackOption("😿", "It was too hard"),
        FeedbackOption("🥱", "It was too easy"),
        FeedbackOption("😑", "It was OK"),
        FeedbackOption("😕", "I didn’t like it"),
    ],
    
    EventType.CONTEST_EDITORIAL: [
        FeedbackOption("😻", "It was super useful!"),
        FeedbackOption("🆗", "I haven't got everything knew smth before, but still enjoyed it!"),
        FeedbackOption("😑", "It could be better"),
        FeedbackOption("🏃‍♀️‍➡️", "I didn't attend the editorial")
    ],
    
    EventType.EXTRA_LECTURE: [
        FeedbackOption("🤩", "Cool – It was informative and useful"),
        FeedbackOption("👍", "Okay – It was interesting but not so relevant"),
        FeedbackOption("😞", "Meh – It could have been better"),
        FeedbackOption("🛑", "I didn't participate")
    ],
    
    EventType.EVENING_ACTIVITY: [
        FeedbackOption("❤️‍🔥", "Cool – I want more like it"),
        FeedbackOption("😃", "Okay – It was fun"),
        FeedbackOption("😕", "Meh – I could do something better"),
        FeedbackOption("🙈", "I didn't participate")
    ]
}


def get_cyprus_feedback_options(event_type: EventType) -> List[FeedbackOption]:
    """
    Получить Cyprus feedback опции для типа события.
    
    Args:
        event_type: Тип события
        
    Returns:
        Список FeedbackOption или пустой список если тип не поддерживается
    """
    return CYPRUS_FEEDBACK_TEMPLATES.get(event_type, [])


def is_cyprus_supported_event(event_type: EventType) -> bool:
    """
    Проверить поддерживается ли тип события в Cyprus режиме.
    
    Args:
        event_type: Тип события
        
    Returns:
        True если поддерживается, False иначе
    """
    return event_type in CYPRUS_FEEDBACK_TEMPLATES


# Конфигурация Cyprus кэмпа
CYPRUS_CAMP_CONFIG = {
    "timezone": "Europe/Nicosia",  # UTC+3
    "feedback_time": "23:00",
    "attendance_polls_enabled": False,
    "reminders_enabled": False,
    "feedback_polls_enabled": True,
    "poll_close_enabled": False,  # Feedback polls не закрываются автоматически
    "single_choice_polls": True,  # Только один ответ разрешён
}


def get_cyprus_config() -> Dict[str, any]:
    """Получить конфигурацию Cyprus кэмпа."""
    return CYPRUS_CAMP_CONFIG.copy()

