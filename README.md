# 🗳️ CampPoll

A Discord bot for automated daily attendance polls in educational camp environments. Designed for camps with ≤100 participants, using lightweight JSON storage instead of a full RDBMS.

## ✨ Features

- **Daily Attendance Polls**: Publishes tomorrow-attendance poll at 15:00
- **Automatic Feedback Polls**: When attendance poll closes, bot posts separate feedback polls with emoji-options per event
- **Feedback-Only Mode**: Mark an event as `feedback_only` to skip attendance poll entirely and publish only feedback
- **Smart Reminders**: Single DM at 19:00 to users who haven't voted (feedback polls are excluded)
- **Auto-Close & CSV Export**: Poll closes 09:00 next day – summary + CSV in #organisers
- **Duplicate Guard**: Same *date ‑ title ‑ type* can't be added twice – bot replies "already exists"
- **Multi-Event Types**: Lectures, Contests, Extra Lectures, Evening Activities
- **Poll Splitting**: Automatically splits if >10 options (max 10 per poll)
- **Timezone Support**: IANA timezones per guild
- **Lightweight Storage**: Flat JSON files, ≤5 KB total
- **English Only**: All UI and documentation in English

## 🚀 Quick Start

### Prerequisites

- Python 3.12+
- Discord Bot Token with required permissions
- Administrator access in your Discord server

### Setup with Docker (Recommended)

1. **Clone the repository**
   ```bash
   git clone <repository-url>
   cd camp_poll
   ```

2. **Configure environment**
   ```bash
   cp .env.example .env
   # Edit .env with your Discord bot token
   ```

3. **Run with Docker Compose**
   ```bash
   docker compose up -d
   ```

### Manual Setup

1. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

2. **Set environment variables**
   ```bash
   export DISCORD_BOT_TOKEN="your_token_here"
   export TIMEZONE="Europe/Helsinki"  # Default timezone
   ```

3. **Run the bot**
   ```bash
   python bot.py
   ```

## ⚙️ Configuration

### Required Channels

1. **#polls** - Where daily attendance polls are published
2. **#organisers** - Where results and CSV files are sent
3. **#bot-alerts** - For failed DM notifications and system alerts

### Bot Permissions

- Send Messages
- Use Slash Commands
- Read Message History
- Send Messages in Threads
- Attach Files
- Add Reactions

### One-time Setup

```bash
# 1. Set the camp timezone (critical for scheduling)
/setTimezone Europe/Helsinki

# 2. Configure daily schedule
/setPollTimes 15:00;09:00;19:00
# Format: publish_time;close_time;reminder_time (24-hour HH:MM)
```

## 📋 Commands

All commands require Administrator permissions.

### Event Management

Format: `YYYY-MM-DD;Title` for all event commands

**Add Events** (optional `feedback_only:true/false` flag):
- `/addLecture <date;title> [feedback_only:true]` – Lecture. Example:
  `/addLecture 2025-06-12;Search Algorithms feedback_only:false`
- `/addContest <date;title> [feedback_only:true]` – Contest.
- `/addExtraLecture <date;title> [feedback_only:true]` – Extra lecture (not in attendance poll unless feedback_only=false).
- `/addEveningActivity <date;title> [feedback_only:true]` – Evening activity.

If `feedback_only:true` the bot *skips* attendance poll for that event day and immediately publishes the feedback-poll with preset emoji options.

**Edit Events**:
- `/editLecture <event_id> <date;title>`
- `/editContest <event_id> <date;title>`
- `/editExtraLecture <event_id> <date;title>`
- `/editEveningActivity <event_id> <date;title>`

**List Events**:
- `/listLectures <date>`
- `/listContests <date>`
- `/listExtraLectures <date>`
- `/listEveningActivities <date>`

**Delete Events**:
- `/deleteLecture <event_id>`
- `/deleteContest <event_id>`
- `/deleteExtraLecture <event_id>`
- `/deleteEveningActivity <event_id>`

### Poll Management

- `/endPoll <message_id>` - Close poll early
- `/exportAttendance <message_id>` - Export attendance CSV

## 🕐 Daily Timeline (Europe/Helsinki)

| Time | Action | Description |
|------|--------|-------------|
| **15:00** | 📢 **Publish** | Attendance poll for tomorrow's *non-feedback* Lectures & Contests |
| **19:00** | 📧 **Remind** | One DM to students who haven't voted |
| **09:00** next day | 📊 **Close** | Close poll; post summary & CSV in #organisers |

## 📊 Poll Format

```
**Which lectures/contests will you attend tomorrow (12 Jun)?**
🇦 Search Algorithms
🇧 Graph Challenge
🇨 Discrete Math
```

Students choose **one** option. If >10 events, bot splits into multiple polls.  
For feedback-only days the attendance poll step is skipped – only feedback polls appear.

## 📧 Reminder DM (19:00)

Bot sends *one* DM per student covering any still-open attendance polls. Feedback polls are ignored to avoid spam.

## 📁 Data Storage

The bot uses lightweight JSON storage suitable for ≤100 users:

- `data/events.json` - Event records
- `data/polls.json` - Poll metadata and votes

Expected footprint: **≤5KB total**

### CSV Export Format

Simple three-column format:
```csv
user_id,username,choice
123456,john_doe,Search Algorithms
789012,jane_smith,Graph Challenge
```

## 🔧 Project Layout

```
camp_poll/
├── bot.py            # entry point, Discord client + scheduler
├── config.py         # reads .env into pydantic settings
├── storage.py        # load/save JSON helpers with asyncio.Lock
├── models.py         # dataclasses for Event & Poll metadata
├── cmds/             # slash-command cogs
│   ├── admin.py      # admin commands
│   └── export.py     # export commands
├── services/
│   ├── poll_manager.py # create/close polls, send reminders
│   └── csv_service.py  # build and send CSV files
├── utils/
│   └── time.py       # TZ helpers
└── tests/            # pytest-asyncio
```

## 🐳 Docker Deployment

Uses `python:3.12-slim` base image with resource limits:

```yaml
services:
  campoll:
    build: .
    volumes:
      - ./data:/app/data
    environment:
      - DISCORD_BOT_TOKEN=${DISCORD_BOT_TOKEN}
    deploy:
      resources:
        limits:
          memory: 256M
          cpus: '0.5'
```

## 🧪 Testing

```bash
# Install test dependencies
pip install pytest pytest-asyncio

# Run tests
pytest tests/ -v
```

## 📦 Dependencies

```
discord.py==2.4.0
APScheduler==3.10.4
pandas==2.1.4
pytest==7.4.3
ruff==0.1.6
black==23.11.0
```

## 🚨 Admin Checklist

| When | Task | Commands |
|------|------|----------|
| Morning (before 15:00) | Add tomorrow's events | `/addLecture`, `/addContest` |
| 19:00 | — | Bot sends reminders automatically |
| 09:05 next day | Review summary & CSV | Check #organisers |
| Any time | Close poll early / export | `/endPoll`, `/exportAttendance` |

## 🔍 Why No Database?

- **Scale**: ≤100 users and tens of events → data footprint is negligible
- **Portability**: Flat files work on any VPS without DB server
- **Backup**: Simple `tar` of data directory is sufficient
- **Migration**: Can swap storage layer for SQLite later if needed

---

**Made with ❤️ for educational camps worldwide** 