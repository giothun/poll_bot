"""
CampPoll Discord Bot - Main Entry Point

A Discord bot for automated daily attendance polls for lectures and contests.
Supports timezone-aware scheduling, CSV exports, and poll management.
"""

import asyncio
import logging
import sys
from datetime import datetime
from pathlib import Path

import discord
from discord.ext import commands
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from config import get_config
from models import GuildSettings, PollMeta
from storage import (
    get_guild_settings, load_guild_settings, get_poll,
    save_poll
)
from services.poll_manager import (
    publish_attendance_poll, send_reminders, 
    close_all_active_polls
)
from utils.time import is_valid_timezone

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)

logger = logging.getLogger(__name__)

class CampPollBot(commands.Bot):
    """Main bot class with scheduler integration."""
    
    def __init__(self):
        # Bot setup
        intents = discord.Intents.default()
        intents.message_content = True
        intents.members = True
        intents.guilds = True
        intents.guild_scheduled_events = True
        intents.polls = True  # Enable poll events
        
        super().__init__(
            command_prefix='!',  # Not used for slash commands
            intents=intents,
            help_command=None
        )
        
        # Configuration
        self.config = get_config()
        
        # Scheduler
        self.scheduler = AsyncIOScheduler()
        
        # Track if bot is ready
        self.is_ready = False
    
    async def setup_hook(self):
        """Called when the bot is starting up."""
        logger.info("Setting up CampPoll bot...")
        
        # Ensure data directory exists
        Path(self.config.data_dir).mkdir(exist_ok=True)
        
        # Load command modules
        try:
            await self.load_extension('cmds.admin')
            await self.load_extension('cmds.export')
            await self.load_extension('cmds.test_commands')
            logger.info("Loaded command modules")
        except Exception as e:
            logger.error(f"Failed to load commands: {e}")
        
        # Setup scheduler
        await self.setup_scheduler()
        
        # Sync slash commands
        try:
            synced = await self.tree.sync()
            logger.info(f"Synced {len(synced)} command(s)")
        except Exception as e:
            logger.error(f"Failed to sync commands: {e}")
    
    async def on_ready(self):
        """Called when bot is connected and ready."""
        logger.info(f'Bot logged in as {self.user} (ID: {self.user.id})')
        logger.info(f'Connected to {len(self.guilds)} guild(s)')
        
        # Start scheduler
        if not self.scheduler.running:
            self.scheduler.start()
            logger.info("Scheduler started")
        
        self.is_ready = True
        
        # Set bot status
        activity = discord.Activity(
            type=discord.ActivityType.watching,
            name="for attendance polls 📊"
        )
        await self.change_presence(activity=activity)
    
    async def on_interaction(self, interaction: discord.Interaction):
        """Handle button interactions."""
        if not interaction.data or not interaction.data.get("custom_id"):
            return
        
        custom_id = interaction.data["custom_id"]
        
        # Handle poll votes
        if custom_id.startswith("poll_"):
            try:
                # Parse custom_id (format: poll_<poll_id>_<event_id>)
                _, poll_id, event_id = custom_id.split("_")
                
                # Get poll metadata
                poll_data = await get_poll(poll_id)
                if not poll_data:
                    await interaction.response.send_message(
                        "❌ Poll not found.",
                        ephemeral=True
                    )
                    return
                
                poll_meta = PollMeta.from_dict(poll_data)
                
                # Check if poll is still active
                if poll_meta.is_closed:
                    await interaction.response.send_message(
                        "❌ This poll is closed.",
                        ephemeral=True
                    )
                    return
                
                # Add vote
                success = poll_meta.add_vote(interaction.user.id, event_id)
                
                if success:
                    # Save updated poll
                    await save_poll(poll_meta.to_dict())
                    
                    # Get event title
                    event_title = None
                    for option in poll_meta.options:
                        if option.event_id == event_id:
                            event_title = option.title
                            break
                    
                    await interaction.response.send_message(
                        f"✅ Your vote for **{event_title}** has been recorded.",
                        ephemeral=True
                    )
                else:
                    await interaction.response.send_message(
                        "❌ Failed to record your vote. Please try again.",
                        ephemeral=True
                    )
                
            except Exception as e:
                logger.error(f"Error handling poll vote: {e}")
                await interaction.response.send_message(
                    "❌ An error occurred while processing your vote.",
                    ephemeral=True
                )
        else:
            # Let other interaction handlers process it
            await super().on_interaction(interaction)
    
    async def on_guild_join(self, guild):
        """Called when bot joins a new guild."""
        logger.info(f"Joined guild: {guild.name} (ID: {guild.id})")
        
        # Setup default settings for new guild
        await self.setup_guild_jobs(guild.id)
        
        # Send welcome message if possible
        try:
            # Try to find a general channel
            for channel in guild.text_channels:
                if channel.permissions_for(guild.me).send_messages:
                    embed = discord.Embed(
                        title="👋 CampPoll Bot Added!",
                        description="Thanks for adding me to your server!",
                        color=0x00ff00
                    )
                    embed.add_field(
                        name="🚀 Getting Started",
                        value="Use `/settimezone` to configure your timezone\nUse `/setpolltimes` to set poll schedule",
                        inline=False
                    )
                    embed.add_field(
                        name="📋 Add Events",
                        value="Use `/addlecture` and `/addcontest` to add events",
                        inline=False
                    )
                    embed.add_field(
                        name="⚙️ Admin Only",
                        value="All commands require Administrator permissions",
                        inline=False
                    )
                    
                    await channel.send(embed=embed)
                    break
        except Exception as e:
            logger.warning(f"Could not send welcome message to {guild.name}: {e}")
    
    async def setup_scheduler(self):
        """Setup the task scheduler."""
        logger.info("Setting up scheduler...")
        
        # Load all guild settings and setup jobs
        guild_settings = await load_guild_settings()
        
        for guild_id_str, settings in guild_settings.items():
            guild_id = int(guild_id_str)
            await self.setup_guild_jobs(guild_id, settings)
        
        logger.info(f"Scheduler setup complete with {len(self.scheduler.get_jobs())} jobs")
    
    async def setup_guild_jobs(self, guild_id: int, settings: dict = None):
        """Setup scheduled jobs for a guild."""
        try:
            if not settings:
                settings = await get_guild_settings(guild_id)
                if not settings:
                    # Create default settings
                    settings = GuildSettings(guild_id=guild_id).to_dict()
            
            timezone = settings.get("timezone", "Europe/Helsinki")
            
            if not is_valid_timezone(timezone):
                logger.error(f"Invalid timezone {timezone} for guild {guild_id}")
                return
            
            # Parse times
            publish_time = settings.get("poll_publish_time", "15:00").split(":")
            reminder_time = settings.get("reminder_time", "19:00").split(":")
            close_time = settings.get("poll_close_time", "09:00").split(":")
            
            # Remove existing jobs for this guild
            job_ids = [
                f"poll_publish_{guild_id}",
                f"poll_reminder_{guild_id}",
                f"poll_close_{guild_id}"
            ]
            
            for job_id in job_ids:
                if self.scheduler.get_job(job_id):
                    self.scheduler.remove_job(job_id)
            
            # Add publish job (daily at publish time)
            self.scheduler.add_job(
                func=self.run_poll_publish,
                args=[guild_id],
                trigger=CronTrigger(
                    hour=int(publish_time[0]),
                    minute=int(publish_time[1]),
                    timezone=timezone
                ),
                id=f"poll_publish_{guild_id}",
                name=f"Poll Publish - Guild {guild_id}",
                replace_existing=True
            )
            
            # Add reminder job (daily at reminder time)
            self.scheduler.add_job(
                func=self.run_poll_reminder,
                args=[guild_id],
                trigger=CronTrigger(
                    hour=int(reminder_time[0]),
                    minute=int(reminder_time[1]),
                    timezone=timezone
                ),
                id=f"poll_reminder_{guild_id}",
                name=f"Poll Reminder - Guild {guild_id}",
                replace_existing=True
            )
            
            # Add close job (daily at close time)
            self.scheduler.add_job(
                func=self.run_poll_close,
                args=[guild_id],
                trigger=CronTrigger(
                    hour=int(close_time[0]),
                    minute=int(close_time[1]),
                    timezone=timezone
                ),
                id=f"poll_close_{guild_id}",
                name=f"Poll Close - Guild {guild_id}",
                replace_existing=True
            )
            
            logger.info(f"Setup scheduled jobs for guild {guild_id} (timezone: {timezone})")
            
        except Exception as e:
            logger.error(f"Error setting up jobs for guild {guild_id}: {e}")
    
    async def run_poll_publish(self, guild_id: int):
        """Run the poll publishing task."""
        try:
            logger.info(f"Running poll publish task for guild {guild_id}")
            
            guild = self.get_guild(guild_id)
            if not guild:
                logger.error(f"Guild {guild_id} not found")
                return
            
            settings = await get_guild_settings(guild_id)
            if not settings:
                logger.error(f"No settings found for guild {guild_id}")
                return
            
            # Publish poll
            polls = await publish_attendance_poll(self, guild, settings)
            
            if polls:
                logger.info(f"Published {len(polls)} poll(s) for guild {guild_id}")
            else:
                logger.info(f"No events to poll for guild {guild_id}")
            
        except Exception as e:
            logger.error(f"Error in poll publish task for guild {guild_id}: {e}")
    
    async def run_poll_reminder(self, guild_id: int):
        """Run the poll reminder task."""
        try:
            logger.info(f"Running poll reminder task for guild {guild_id}")
            
            guild = self.get_guild(guild_id)
            if not guild:
                logger.error(f"Guild {guild_id} not found")
                return
            
            settings = await get_guild_settings(guild_id)
            if not settings:
                logger.error(f"No settings found for guild {guild_id}")
                return
            
            # Send reminders
            stats = await send_reminders(self, guild, settings)
            logger.info(f"Reminder task completed for guild {guild_id}: {stats}")
            
        except Exception as e:
            logger.error(f"Error in poll reminder task for guild {guild_id}: {e}")
    
    async def run_poll_close(self, guild_id: int):
        """Run the poll closing task."""
        try:
            logger.info(f"Running poll close task for guild {guild_id}")
            
            guild = self.get_guild(guild_id)
            if not guild:
                logger.error(f"Guild {guild_id} not found")
                return
            
            settings = await get_guild_settings(guild_id)
            if not settings:
                logger.error(f"No settings found for guild {guild_id}")
                return
            
            # Close polls
            closed_count = await close_all_active_polls(self, guild, settings)
            logger.info(f"Closed {closed_count} poll(s) for guild {guild_id}")
            
        except Exception as e:
            logger.error(f"Error in poll close task for guild {guild_id}: {e}")
    
    async def on_error(self, event, *args, **kwargs):
        """Global error handler."""
        logger.error(f"Error in event {event}", exc_info=True)
    
    async def close(self):
        """Cleanup when bot shuts down."""
        logger.info("Shutting down bot...")
        
        if self.scheduler.running:
            self.scheduler.shutdown()
            logger.info("Scheduler stopped")
        
        await super().close()

    async def on_poll_vote_add(self, user: discord.User, answer: discord.PollAnswer):
        """Called when a user votes in a poll."""
        try:
            poll = answer.poll
            if not poll:
                return
            
            # Get poll metadata
            poll_data = await get_poll(str(poll.message.id))
            if not poll_data:
                return
            
            poll_meta = PollMeta.from_dict(poll_data)
            
            # Add vote
            success = poll_meta.add_vote(user.id, str(answer.id))
            
            if success:
                # Save updated poll
                await save_poll(poll_meta.to_dict())
                logger.info(f"User {user.id} voted for '{answer.text}' in poll {poll.message.id} (total votes: {answer.vote_count})")
            
        except Exception as e:
            logger.error(f"Error handling poll vote: {e}")
    
    async def on_poll_vote_remove(self, user: discord.User, answer: discord.PollAnswer):
        """Called when a user removes their vote from a poll."""
        try:
            poll = answer.poll
            if not poll:
                return
            
            # Get poll metadata
            poll_data = await get_poll(str(poll.message.id))
            if not poll_data:
                return
            
            poll_meta = PollMeta.from_dict(poll_data)
            
            # Remove vote
            for option in poll_meta.options:
                if option.title == answer.text:
                    success = option.remove_vote(user.id)
                    if success:
                        # Save updated poll
                        await save_poll(poll_meta.to_dict())
                        logger.info(f"User {user.id} removed vote for '{answer.text}' in poll {poll.message.id} (remaining votes: {answer.vote_count})")
                    break
            
        except Exception as e:
            logger.error(f"Error handling poll vote removal: {e}")

    async def on_raw_poll_vote_add(self, payload: discord.RawPollVoteActionEvent):
        """Called when a poll vote is added (works even if message is not cached)."""
        try:
            # Get poll metadata
            poll_data = await get_poll(str(payload.message_id))
            if not poll_data:
                return
            
            poll_meta = PollMeta.from_dict(poll_data)
            
            # Add vote
            success = poll_meta.add_vote(payload.user_id, str(payload.answer_id))
            
            if success:
                # Save updated poll
                await save_poll(poll_meta.to_dict())
                logger.info(f"User {payload.user_id} voted for option {payload.answer_id} in poll {payload.message_id}")
            
        except Exception as e:
            logger.error(f"Error handling raw poll vote: {e}")
    
    async def on_raw_poll_vote_remove(self, payload: discord.RawPollVoteActionEvent):
        """Called when a poll vote is removed (works even if message is not cached)."""
        try:
            # Get poll metadata
            poll_data = await get_poll(str(payload.message_id))
            if not poll_data:
                return
            
            poll_meta = PollMeta.from_dict(poll_data)
            
            # Remove vote
            for option in poll_meta.options:
                if option.event_id == str(payload.answer_id):
                    success = option.remove_vote(payload.user_id)
                    if success:
                        # Save updated poll
                        await save_poll(poll_meta.to_dict())
                        logger.info(f"User {payload.user_id} removed vote for option {payload.answer_id} in poll {payload.message_id}")
                    break
            
        except Exception as e:
            logger.error(f"Error handling raw poll vote removal: {e}")

async def main():
    """Main function to run the bot."""
    try:
        # Create and run bot
        bot = CampPollBot()
        
        async with bot:
            await bot.start(bot.config.token)
    
    except KeyboardInterrupt:
        logger.info("Bot shutdown requested")
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
    finally:
        logger.info("Bot shutdown complete")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Process interrupted")
    except Exception as e:
        logger.critical(f"Failed to start bot: {e}", exc_info=True)
        sys.exit(1) 