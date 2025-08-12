"""
Data models for CampPoll bot.
Defines the core entities: Event, EventType, PollMeta, etc.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import List, Dict, Optional

class EventType(Enum):
    """Types of events that can be scheduled."""
    LECTURE = "lecture"
    CONTEST = "contest"
    CONTEST_EDITORIAL = "contest_editorial"  # Contest editorial sessions
    EXTRA_LECTURE = "extra"  # Stored but not polled
    EVENING_ACTIVITY = "evening"  # Stored but not polled

@dataclass
class Event:
    """Represents a scheduled event."""
    id: str
    title: str
    date: str  # YYYY-MM-DD format
    event_type: EventType
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    feedback_only: bool = False  # if True, attendance poll is skipped and only feedback is posted
    
    def __post_init__(self):
        """Convert string event_type to EventType enum if needed."""
        if isinstance(self.event_type, str):
            try:
                self.event_type = EventType(self.event_type)
            except ValueError:
                # Fallback to a non-pollable type to avoid crashes on bad input
                self.event_type = EventType.EXTRA_LECTURE
    
    @property
    def is_pollable(self) -> bool:
        """Check if this event type should be included in polls."""
        return self.event_type in [EventType.LECTURE, EventType.CONTEST]
    
    def to_dict(self) -> Dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "id": self.id,
            "title": self.title,
            "date": self.date,
            "event_type": self.event_type.value,
            "created_at": self.created_at.isoformat(),
            "feedback_only": self.feedback_only
        }
    
    @classmethod
    def from_dict(cls, data: Dict) -> "Event":
        """Create Event from dictionary."""
        return cls(
            id=data["id"],
            title=data["title"],
            date=data["date"],
            event_type=EventType(data["event_type"]),
            created_at=datetime.fromisoformat(data["created_at"]),
            feedback_only=data.get("feedback_only", False)
        )

@dataclass
class PollOption:
    """Represents a poll option with vote tracking."""
    event_id: str
    title: str
    event_type: EventType
    votes: List[int] = field(default_factory=list)  # User IDs who voted
    answer_id: Optional[str] = None  # Discord poll answer id
    
    @property
    def vote_count(self) -> int:
        """Get the number of votes for this option."""
        return len(self.votes)
    
    def add_vote(self, user_id: int) -> bool:
        """Add a vote from a user. Returns True if vote was added."""
        if user_id not in self.votes:
            self.votes.append(user_id)
            return True
        return False
    
    def remove_vote(self, user_id: int) -> bool:
        """Remove a vote from a user. Returns True if vote was removed."""
        if user_id in self.votes:
            self.votes.remove(user_id)
            return True
        return False

@dataclass
class PollMeta:
    """Metadata for a published poll."""
    id: str
    guild_id: int
    channel_id: int
    message_id: int
    poll_date: str  # Date the poll is for (YYYY-MM-DD)
    options: List[PollOption] = field(default_factory=list)
    published_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    closed_at: Optional[datetime] = None
    reminded_users: List[int] = field(default_factory=list)  # Users who got reminders
    is_feedback: bool = False  # True for feedback polls that don't need reminders
    
    @property
    def is_closed(self) -> bool:
        """Check if the poll is closed."""
        return self.closed_at is not None
    
    @property
    def total_votes(self) -> int:
        """Get total number of unique voters."""
        all_voters = set()
        for option in self.options:
            all_voters.update(option.votes)
        return len(all_voters)
    
    def get_user_vote(self, user_id: int) -> Optional[str]:
        """Get which option a user voted for."""
        for option in self.options:
            if user_id in option.votes:
                return option.event_id
        return None
    
    def add_vote(self, user_id: int, event_id: str) -> bool:
        """Add a vote for an event. Removes any existing vote first."""
        # Remove existing vote
        for option in self.options:
            option.remove_vote(user_id)
        
        # Add new vote
        for option in self.options:
            if option.event_id == event_id:
                return option.add_vote(user_id)
        return False

    def record_vote_by_answer_id(self, user_id: int, answer_id: str) -> bool:
        """Record a vote by Discord answer_id. Removes existing vote first."""
        # Remove any existing vote
        for option in self.options:
            option.remove_vote(user_id)
        # Add to matching option by answer_id
        for option in self.options:
            if option.answer_id == answer_id:
                return option.add_vote(user_id)
        return False

    def remove_vote_by_answer_id(self, user_id: int, answer_id: str) -> bool:
        """Remove a vote for the option with the given answer_id."""
        for option in self.options:
            if option.answer_id == answer_id:
                return option.remove_vote(user_id)
        return False
    
    def get_non_voters(self, all_member_ids: List[int]) -> List[int]:
        """Get list of member IDs who haven't voted."""
        voters = set()
        for option in self.options:
            voters.update(option.votes)
        return [uid for uid in all_member_ids if uid not in voters]
    
    def to_dict(self) -> Dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "id": self.id,
            "guild_id": self.guild_id,
            "channel_id": self.channel_id,
            "message_id": self.message_id,
            "poll_date": self.poll_date,
            "options": [
                {
                    "event_id": opt.event_id,
                    "title": opt.title,
                    "event_type": opt.event_type.value,
                    "votes": opt.votes,
                    "answer_id": opt.answer_id
                }
                for opt in self.options
            ],
            "published_at": self.published_at.isoformat(),
            "closed_at": self.closed_at.isoformat() if self.closed_at else None,
            "reminded_users": self.reminded_users,
            "is_feedback": self.is_feedback
        }
    
    @classmethod
    def from_dict(cls, data: Dict) -> "PollMeta":
        """Create PollMeta from dictionary."""
        options = [
            PollOption(
                event_id=opt["event_id"],
                title=opt["title"],
                event_type=EventType(opt["event_type"]),
                votes=opt["votes"],
                answer_id=opt.get("answer_id")
            )
            for opt in data["options"]
        ]
        
        return cls(
            id=data["id"],
            guild_id=data["guild_id"],
            channel_id=data["channel_id"],
            message_id=data["message_id"],
            poll_date=data["poll_date"],
            options=options,
            published_at=datetime.fromisoformat(data["published_at"]),
            closed_at=datetime.fromisoformat(data["closed_at"]) if data["closed_at"] else None,
            reminded_users=data.get("reminded_users", []),
            is_feedback=data.get("is_feedback", False)
        )

@dataclass
class GuildSettings:
    """Per-guild configuration settings."""
    guild_id: int
    timezone: str = "Europe/Helsinki"
    poll_publish_time: str = "14:30"
    poll_close_time: str = "09:00"
    reminder_time: str = "19:00"
    feedback_publish_time: str = "22:00"
    poll_channel_id: Optional[int] = None
    organiser_channel_id: Optional[int] = None
    alerts_channel_id: Optional[int] = None
    student_role_id: Optional[int] = None
    organiser_role_id: Optional[int] = None
    student_role_name: str = "student"
    organiser_role_name: str = "organisers"
    
    def to_dict(self) -> Dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "guild_id": self.guild_id,
            "timezone": self.timezone,
            "poll_publish_time": self.poll_publish_time,
            "poll_close_time": self.poll_close_time,
            "reminder_time": self.reminder_time,
            "feedback_publish_time": self.feedback_publish_time,
            "poll_channel_id": self.poll_channel_id,
            "organiser_channel_id": self.organiser_channel_id,
            "alerts_channel_id": self.alerts_channel_id,
            "student_role_id": self.student_role_id,
            "organiser_role_id": self.organiser_role_id,
            "student_role_name": self.student_role_name,
            "organiser_role_name": self.organiser_role_name
        }
    
    @classmethod
    def from_dict(cls, data: Dict) -> "GuildSettings":
        """Create GuildSettings from dictionary."""
        return cls(**data) 