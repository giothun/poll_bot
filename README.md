# 🗳️ CampPoll

A Discord bot for automated daily attendance polls in educational camp environments. Designed for camps with ≤100 participants, using lightweight JSON storage instead of a full RDBMS.

## ✨ Features

- **Daily Automated Polls**: Creates single attendance poll at 15:00 for tomorrow's events
- **Smart Reminders**: One DM reminder at 19:00 to users who haven't voted
- **Auto-Close & Results**: Closes at 09:00 next day with summary + CSV in #organisers
- **Multi-Event Types**: Lectures, Contests, Extra Lectures, Evening Activities
- **Poll Splitting**: Automatically splits if >10 options (max 10 per poll)
- **Timezone Support**: Full IANA timezone support for international camps
- **Simple Storage**: Flat JSON files (events.json, polls.json) with ≤5KB footprint
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

**Add Events**:
- `/addLecture <date;title>` - Add lecture (included in polls)
  - Example: `/addLecture 2025-06-12;Search Algorithms`
- `/addContest <date;title>` - Add contest (included in polls)
  - Example: `/addContest 2025-06-12;Graph Challenge`
- `/addExtraLecture <date;title>` - Add extra lecture (not polled)
  - Example: `/addExtraLecture 2025-06-12;DevOps 101`
- `/addEveningActivity <date;title>` - Add evening activity (not polled)
  - Example: `/addEveningActivity 2025-06-12;Movie Night`

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
| **15:00** | 📢 **Publish** | Single poll for tomorrow's Lectures & Contests (max 10 options) |
| **19:00** | 📧 **Remind** | One DM to students who haven't voted |
| **09:00** next day | 📊 **Close** | Close poll; post summary & CSV in #organisers |

## 📊 Poll Format

```
**Which lectures/contests will you attend tomorrow (12 Jun)?**
🇦 Search Algorithms
🇧 Graph Challenge
🇨 Discrete Math
```

Students can choose **one** option. If >10 events, the bot creates additional polls automatically.

## 📧 Reminder DM (19:00)

```
Reminder: please choose which lectures/contests you plan to attend tomorrow. The poll closes at 09:00.
```

If a DM fails (user disabled messages), a warning is posted in #bot-alerts.

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