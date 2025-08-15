"""
Test commands for CampPoll bot.
Contains commands for testing bot functionality.
"""

import uuid
import discord
from discord.ext import commands
from discord import app_commands
import logging
from datetime import datetime

from models import Event, EventType
from services.poll_manager import publish_attendance_poll, publish_feedback_polls
from storage import get_guild_settings, add_event, get_events_by_date

logger = logging.getLogger(__name__)

class TestCommands(commands.Cog):
    """Commands for testing bot functionality."""
    
    def __init__(self, bot: commands.Bot):
        self.bot = bot
    
    async def cog_check(self, ctx) -> bool:
        """Ensure only administrators can use these commands."""
        return ctx.author.guild_permissions.administrator
    
    @app_commands.command(name="testpoll", description="Create a test poll immediately")
    async def test_poll(self, interaction: discord.Interaction):
        """Create a test poll with sample events."""
        try:
            # Get guild settings
            settings = await get_guild_settings(interaction.guild_id)
            if not settings:
                await interaction.response.send_message(
                    "❌ No guild settings found. Please configure the bot first using `/setup`.",
                    ephemeral=True
                )
                return
            
            # Acknowledge the command immediately
            await interaction.response.send_message(
                "Creating test poll...",
                ephemeral=True
            )
            
            # Create test events
            today = datetime.now().strftime("%Y-%m-%d")
            
            # Check if we already have events for today
            existing_events = await get_events_by_date(today, guild_id=interaction.guild_id)
            if existing_events:
                # Use existing events
                logger.info(f"Using {len(existing_events)} existing events for test poll")
            else:
                # Create new test events
                test_events = [
                    Event(
                        id=str(uuid.uuid4()),
                        title="Test Lecture",
                        date=today,
                        event_type=EventType.LECTURE,
                        guild_id=interaction.guild_id,
                    ),
                    Event(
                        id=str(uuid.uuid4()),
                        title="Test Contest",
                        date=today,
                        event_type=EventType.CONTEST,
                        guild_id=interaction.guild_id,
                    )
                ]
                
                # Save test events
                for event in test_events:
                    await add_event(event.to_dict())
                    logger.info(f"Created test event: {event.title} for {event.date}")
            
            # Publish test poll
            polls = await publish_attendance_poll(self.bot, interaction.guild, settings)
            
            if polls:
                await interaction.edit_original_response(
                    content="✅ Test poll created successfully!",
                )
            else:
                await interaction.edit_original_response(
                    content="❌ Failed to create test poll. Check the logs for details.",
                )
            
        except Exception as e:
            logger.error(f"Error creating test poll: {e}")
            try:
                await interaction.edit_original_response(
                    content="❌ An error occurred while creating the test poll.",
                )
            except:
                pass
    
    @app_commands.command(name="testfeedback", description="Create test feedback polls immediately")
    async def test_feedback(self, interaction: discord.Interaction):
        """Create test feedback polls with sample events."""
        try:
            # Get guild settings
            settings = await get_guild_settings(interaction.guild_id)
            if not settings:
                await interaction.response.send_message(
                    "❌ No guild settings found. Please configure the bot first using `/setup`.",
                    ephemeral=True
                )
                return
            
            # Acknowledge the command immediately
            await interaction.response.send_message(
                "Creating test feedback polls...",
                ephemeral=True
            )
            
            # Create test events for today
            today = datetime.now().strftime("%Y-%m-%d")
            
            # Check if we already have events for today
            existing_events = await get_events_by_date(today, guild_id=interaction.guild_id)
            if existing_events:
                # Use existing events
                logger.info(f"Using {len(existing_events)} existing events for test feedback polls")
            else:
                # Create new test events
                test_events = [
                    Event(
                        id=str(uuid.uuid4()),
                        title="Test Lecture for Feedback",
                        date=today,
                        event_type=EventType.LECTURE,
                        guild_id=interaction.guild_id,
                    ),
                    Event(
                        id=str(uuid.uuid4()),
                        title="Test Contest for Feedback",
                        date=today,
                        event_type=EventType.CONTEST,
                        guild_id=interaction.guild_id,
                    )
                ]
                
                # Save test events
                for event in test_events:
                    await add_event(event.to_dict())
                    logger.info(f"Created test event: {event.title} for {event.date}")
            
            # Publish test feedback polls
            polls = await publish_feedback_polls(self.bot, interaction.guild, settings)
            
            if polls:
                await interaction.edit_original_response(
                    content=f"✅ {len(polls)} test feedback poll(s) created successfully!",
                )
            else:
                await interaction.edit_original_response(
                    content="❌ Failed to create test feedback polls. Check the logs for details.",
                )
            
        except Exception as e:
            logger.error(f"Error creating test feedback polls: {e}")
            try:
                await interaction.edit_original_response(
                    content="❌ An error occurred while creating the test feedback polls.",
                )
            except:
                pass

async def setup(bot: commands.Bot):
    """Setup function for the cog."""
    await bot.add_cog(TestCommands(bot)) 