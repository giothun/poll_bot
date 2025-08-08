"""Poll Manager facade: re-exports modular poll services and provides shared helpers."""

import logging
from utils.time import parse_time

# Re-export poll services from modular components
from services.polls.attendance import publish_attendance_poll, chunk_events
from services.polls.feedback import publish_feedback_polls, create_feedback_poll
from services.polls.reminders import send_reminders
from services.polls.closing import close_all_active_polls, close_poll

logger = logging.getLogger(__name__)


# get_poll_closing_date function moved to utils/time.py to avoid circular imports