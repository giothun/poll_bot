# 🗳️ CampPoll

A Discord bot for automated daily attendance polls in educational camp environments. Designed for camps with ≤100 participants, using lightweight JSON storage instead of a full RDBMS.

## ✨ Features

- **Daily Attendance Polls**: Publishes tomorrow-attendance poll at 14:30
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
   cd poll_bot
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
/setPollTimes 14:30;09:00;19:00
# Format: publish_time;close_time;reminder_time (24-hour HH:MM)
# Note: Feedback polls publish at 22:00 by default
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
| **14:30** | 📢 **Publish** | Attendance poll for tomorrow's *non-feedback* Lectures & Contests |
| **19:00** | 📧 **Remind** | One DM to students who haven't voted |
| **09:00** next day | 📊 **Close** | Close poll; post summary & CSV in #organisers |
| **22:00** | 📝 **Feedback** | Publish feedback polls for today's events |

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
discord.py==2.5.2
APScheduler==3.10.4
python-dotenv==1.0.0
pandas==2.1.4
pytest==7.4.3
pytest-asyncio==0.21.1
ruff==0.1.6
black==23.11.0
```

## 🔐 Gateway Intents

Enable these in both code and the Discord Developer Portal (Bot → Privileged Gateway Intents):
- Polls
- Message Content
- Server Members (required for reminders and name export)

## 🧪 Test Commands

Set `ENABLE_TEST_COMMANDS=1` in the environment to load extra test commands from `cmds/test_commands.py` (disabled by default in production).

## 🚨 Admin Checklist

| When | Task | Commands |
|------|------|----------|
| Morning (before 15:00) | Add tomorrow's events | `/addLecture`, `/addContest` |
| 19:00 | — | Bot sends reminders automatically |
| 09:05 next day | Review summary & CSV | Check #organisers |
| Any time | Close poll early / export | `/endPoll`, `/exportAttendance` |

## 🇨🇾 Cyprus Camp Mode

Special mode for Cyprus camps with feedback-only polls and single-choice responses.

### Setup
```bash
# Switch to Cyprus mode (one command setup)
/setcampmode cyprus
```

### Cyprus Features

- **23:00 Cyprus Time**: Daily feedback polls for today's events
- **Single Choice**: Each user can select only one response 
- **No Attendance**: No attendance polls at 14:30
- **No Reminders**: No DM reminders at 19:00
- **Feedback Only**: Focus on event quality feedback

### Supported Event Types

| Event Type | Feedback Options | Add Command |
|------------|------------------|-------------|
| **Contest** | 🩷 Loved it / 😿 Too hard / 🥱 Too easy | `/addContest` |
| **Contest Editorial** | 😻 Super useful / 🆗 Haven't got everything / 😑 Could be better / 🏃‍♀️‍➡️ Didn't attend | `/addContestEditorial` |
| **Extra Lecture** | 🤩 Informative / 👍 Interesting / 😞 Could be better / 🛑 Didn't participate | `/addExtraLecture` |
| **Evening Activity** | ❤️‍🔥 Want more / 😃 Fun / 😕 Could do better / 🙈 Didn't participate | `/addEveningActivity` |

### Cyprus Commands

**Add Events**:
```bash
/addContest 2024-06-12;Graph Algorithms Contest
/addContestEditorial 2024-06-12;Contest A Editorial
/addExtraLecture 2024-06-13;Advanced Data Structures
/addEveningActivity 2024-06-13;Board Game Night
```

**List Events**:
```bash
/listContests 2024-06-12
/listContestEditorials 2024-06-12
/listExtraLectures 2024-06-13
/listEveningActivities 2024-06-13
```

**Edit Events**:
```bash
/editContest event_123 2024-06-12;Updated Contest Title
/editContestEditorial event_124 2024-06-12;Updated Editorial
```

**Delete Events**:
```bash
/deleteContest event_123
/deleteContestEditorial event_124
```

### Cyprus Daily Timeline (Europe/Nicosia)

| Time | Action | Description |
|------|--------|-------------|
| **23:00** | 📝 **Feedback** | Daily feedback polls for today's events |
| **00:01** | 🔄 **Continue** | Polls remain active for 24 hours |

### Switch Back to Standard Mode

```bash
/setcampmode standard
```

## 🔍 Why No Database?

- **Scale**: ≤100 users and tens of events → data footprint is negligible
- **Portability**: Flat files work on any VPS without DB server
- **Backup**: Simple `tar` of data directory is sufficient
- **Migration**: Can swap storage layer for SQLite later if needed

---

**Made with ❤️ for educational camps worldwide** 