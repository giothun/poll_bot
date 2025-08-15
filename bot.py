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
import os

import discord
from discord.ext import commands
from services.scheduler_service import SchedulerService

from config import get_config
from models import GuildSettings, PollMeta
from storage import (
    get_guild_settings, load_guild_settings, get_poll,
    save_poll
)
from services.poll_manager import (
    publish_attendance_poll, send_reminders,
    close_all_active_polls, publish_feedback_polls
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
        intents.polls = True  # Enable poll events
        
        super().__init__(
            command_prefix='!',  # Not used for slash commands
            intents=intents,
            help_command=None
        )
        
        # Configuration
        self.config = get_config()
        
        # Scheduler service (single source of scheduling)
        self.scheduler_service = SchedulerService(self)
        
        # Track if bot is ready
        self.is_ready = False
    
    async def setup_hook(self):
        """Called when the bot is starting up."""
        logger.info("Setting up CampPoll bot...")
        
        # Ensure data directory exists
        Path(self.config.data_dir).mkdir(parents=True, exist_ok=True)
        
        # Load command modules
        try:
            await self.load_extension('cmds.admin')
            await self.load_extension('cmds.export')
            if os.getenv("ENABLE_TEST_COMMANDS", "0") == "1":
                await self.load_extension('cmds.test_commands')
            logger.info("Loaded command modules")
        except Exception as e:
            logger.error(f"Failed to load commands: {e}")
        
        # Setup scheduler via service
        await self.scheduler_service.setup_all_guild_jobs()
        
        # Setup error handler for app commands
        self.tree.on_error = self.on_app_command_error

        # Intent self-check (best-effort): warn if critical intents are disabled in code
        if not self.intents.message_content:
            logger.warning("Message Content intent is disabled in code. Poll vote events may not fire. Enable it both in code and Discord Developer Portal.")
        if not getattr(self.intents, "polls", False):
            logger.warning("Polls intent is disabled in code. Poll vote events will not fire. Enable it both in code and Discord Developer Portal.")
        
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
        self.scheduler_service.start()
        
        self.is_ready = True
        
        # Set bot status
        activity = discord.Activity(
            type=discord.ActivityType.watching,
            name="for attendance polls 📊"
        )
        await self.change_presence(activity=activity)
    
    # Removed legacy on_interaction with custom_id; Discord polls use poll events
    
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
    
    # Scheduling is delegated to SchedulerService
    
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
    
    async def run_feedback_publish(self, guild_id: int):
        """Run the feedback poll publishing task."""
        try:
            logger.info(f"Running feedback publish task for guild {guild_id}")
            
            guild = self.get_guild(guild_id)
            if not guild:
                logger.error(f"Guild {guild_id} not found")
                return
            
            settings = await get_guild_settings(guild_id)
            if not settings:
                logger.error(f"No settings found for guild {guild_id}")
                return
            
            # Publish feedback polls using unified options in all modes
            polls = await publish_feedback_polls(self, guild, settings)
            
            if polls:
                logger.info(f"Published {len(polls)} feedback poll(s) for guild {guild_id}")
            else:
                logger.info(f"No events for feedback polls in guild {guild_id}")
            
        except Exception as e:
            logger.error(f"Error in feedback publish task for guild {guild_id}: {e}")
    
    async def on_error(self, event, *args, **kwargs):
        """Global error handler."""
        logger.error(f"Error in event {event}", exc_info=True)
    
    async def on_app_command_error(self, interaction: discord.Interaction, error: discord.app_commands.AppCommandError):
        """Handle app command errors."""
        if isinstance(error, discord.app_commands.CheckFailure):
            logger.warning(f"Permission check failed for user {interaction.user.name} ({interaction.user.id}) on command {interaction.command.name}")
            try:
                if not interaction.response.is_done():
                    await interaction.response.send_message(
                        "❌ You don't have permission to use this command. Only server administrators or users with the 'Organisers' role can use bot commands.",
                        ephemeral=True
                    )
                else:
                    await interaction.followup.send(
                        "❌ You don't have permission to use this command. Only server administrators or users with the 'Organisers' role can use bot commands.",
                        ephemeral=True
                    )
            except Exception as e:
                logger.error(f"Failed to send permission error message: {e}")
        else:
            logger.error(f"App command error in {interaction.command.name}: {error}", exc_info=True)
            try:
                if not interaction.response.is_done():
                    await interaction.response.send_message(
                        "❌ An error occurred while processing the command.",
                        ephemeral=True
                    )
                else:
                    await interaction.followup.send(
                        "❌ An error occurred while processing the command.",
                        ephemeral=True
                    )
            except Exception as e:
                logger.error(f"Failed to send error message: {e}")
    
    async def close(self):
        """Cleanup when bot shuts down."""
        logger.info("Shutting down bot...")
        
        self.scheduler_service.shutdown()
        
        await super().close()

    async def on_raw_poll_vote_add(self, payload: discord.RawPollVoteActionEvent):
        """Called when a poll vote is added (works even if message is not cached)."""
        try:
            # Get poll metadata
            poll_data = await get_poll(str(payload.message_id))
            if not poll_data:
                return
            
            poll_meta = PollMeta.from_dict(poll_data)
            
            # Add vote by answer_id via domain method
            if poll_meta.record_vote_by_answer_id(payload.user_id, str(payload.answer_id)):
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
            
            # Remove vote by answer_id via domain method
            if poll_meta.remove_vote_by_answer_id(payload.user_id, str(payload.answer_id)):
                await save_poll(poll_meta.to_dict())
                logger.info(f"User {payload.user_id} removed vote for option {payload.answer_id} in poll {payload.message_id}")
            
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