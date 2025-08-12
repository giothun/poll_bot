"""
Admin commands for CampPoll bot.
Handles event management and bot configuration.
"""

import uuid
import asyncio
from datetime import datetime, timezone
from typing import Optional
import discord
from discord.ext import commands
from discord import app_commands
import logging

from models import Event, EventType, GuildSettings
from storage import (
    add_event, get_events_by_date, get_events_by_type,
    update_event, delete_event, get_guild_settings,
    save_guild_setting
)
from utils.validation import (
    validate_timezone, validate_date_title_format, validate_poll_times_format,
    validate_role_id, validate_channel_permissions, get_missing_permissions
)
from utils.discord import (
    create_success_embed, create_error_embed, create_info_embed,
    create_event_embed, safe_send_message, EmbedBuilder
)
from utils.messages import MessageType, format_message, format_event_display
from services.poll_manager import publish_attendance_poll, send_reminders, publish_feedback_polls
from utils.time import tz_tomorrow

logger = logging.getLogger(__name__)

class AdminCommands(commands.Cog):
    """Admin-only commands for managing the bot."""
    
    def __init__(self, bot: commands.Bot):
        self.bot = bot
    
    # Ensure that all application (slash) commands in this cog are restricted to server administrators or Organisers role
    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        """Global check for every app command in this cog."""
        user = interaction.user
        
        if not user:
            return False
        
        # Check administrator permissions
        if user.guild_permissions and user.guild_permissions.administrator:
            return True
        
        # Check for Organisers role (by name or configured ID)
        guild_settings = await get_guild_settings(interaction.guild_id)
        configured_role_id = (guild_settings or {}).get("organiser_role_id") if guild_settings else None
        organiser_role = next(
            (r for r in user.roles 
             if r.name.lower() == "organisers" or (configured_role_id and r.id == configured_role_id)), None
        )
        if organiser_role:
            return True

        # Send error message if no permission
        if not interaction.response.is_done():
            error_msg = format_message(MessageType.ERROR, 'permission_denied')
            error_msg += " Only server administrators or users with the 'Organisers' role can use this command."
            await interaction.response.send_message(error_msg, ephemeral=True)
        
        return False
    
    async def cog_check(self, ctx) -> bool:
        """Ensure only administrators or Organisers can use these commands."""
        if not ctx.author:
            return False
            
        # Check administrator permissions
        if ctx.author.guild_permissions and ctx.author.guild_permissions.administrator:
            return True
        
        # Check for Organisers role (by name or configured ID)
        guild_settings = await get_guild_settings(ctx.guild.id)
        configured_role_id = (guild_settings or {}).get("organiser_role_id") if guild_settings else None
        organiser_role = next(
            (r for r in ctx.author.roles 
             if r.name.lower() == "organisers" or (configured_role_id and r.id == configured_role_id)), None
        )
        return organiser_role is not None
    
    @app_commands.command(name="setchannels", description="Set up bot channels")
    @app_commands.describe(
        poll_channel="Channel for daily attendance polls",
        organiser_channel="Channel for poll results and exports",
        alerts_channel="Channel for bot alerts and warnings"
    )
    async def set_channels(
        self,
        interaction: discord.Interaction,
        poll_channel: discord.TextChannel,
        organiser_channel: discord.TextChannel,
        alerts_channel: discord.TextChannel
    ):
        """Set up bot channels for polls, results, and alerts."""
        try:
            await interaction.response.defer(ephemeral=True)
            
            # Verify bot permissions in each channel
            required_permissions = ['send_messages', 'embed_links']
            for channel, purpose in [
                (poll_channel, "poll"),
                (organiser_channel, "organiser"),
                (alerts_channel, "alerts")
            ]:
                missing_perms = get_missing_permissions(channel, required_permissions)
                if missing_perms:
                    error_msg = format_message(
                        MessageType.ERROR,
                        'missing_permissions',
                        permissions=', '.join(missing_perms),
                        channel=f"{channel.mention} ({purpose} channel)"
                    )
                    await interaction.followup.send(error_msg, ephemeral=True)
                    return
            
            # Get or create guild settings
            guild_settings = await get_guild_settings(interaction.guild_id)
            if not guild_settings:
                guild_settings = GuildSettings(guild_id=interaction.guild_id).to_dict()
            
            # Update channel IDs
            guild_settings["poll_channel_id"] = poll_channel.id
            guild_settings["organiser_channel_id"] = organiser_channel.id
            guild_settings["alerts_channel_id"] = alerts_channel.id
            
            # Save settings
            await save_guild_setting(guild_settings)
            
            # Create response embed
            embed = (EmbedBuilder("Bot Channels Configured")
                    .add_field("📊 Poll Channel", poll_channel.mention, inline=False)
                    .add_field("📈 Results Channel", organiser_channel.mention, inline=False)
                    .add_field("⚠️ Alerts Channel", alerts_channel.mention, inline=False)
                    .build())
            
            await interaction.followup.send(embed=embed, ephemeral=True)
            
            # Send test messages to verify permissions
            try:
                test_embed = discord.Embed(
                    title="✅ Channel Setup Test",
                    description="This is a test message to verify bot permissions.",
                    color=0x00ff00
                )
                
                await poll_channel.send(embed=test_embed)
                await organiser_channel.send(embed=test_embed)
                await alerts_channel.send(embed=test_embed)
            except Exception as e:
                await interaction.followup.send(
                    f"⚠️ Warning: Could not send test messages to all channels. Please verify permissions manually.\nError: {str(e)}",
                    ephemeral=True
                )
            
            logger.info(
                f"Channels configured for guild {interaction.guild_id}: "
                f"poll={poll_channel.id}, "
                f"organiser={organiser_channel.id}, "
                f"alerts={alerts_channel.id}"
            )
            
            # Reload scheduler with new settings
            await self.bot.setup_guild_jobs(interaction.guild_id, guild_settings)
            
        except Exception as e:
            logger.error(f"Error setting channels: {e}")
            try:
                await interaction.followup.send(
                    "❌ An error occurred while setting up channels.",
                    ephemeral=True
                )
            except discord.HTTPException as e:
                logger.warning(f"Failed to send error response: {e}")

    @app_commands.command(name="setstudentroleid", description="Set the Student role ID for reminders")
    @app_commands.describe(role_id="Numeric ID of the Student role")
    async def set_student_role_id(self, interaction: discord.Interaction, role_id: str):
        """Store student_role_id in guild settings (used for reminders)."""
        try:
            await interaction.response.defer(ephemeral=True)
            
            # Validate role ID
            validation_result = validate_role_id(role_id)
            if not validation_result:
                error_msg = format_message(MessageType.ERROR, 'invalid_format', 
                                         expected_format="valid Discord role ID")
                await interaction.followup.send(f"{error_msg}\n{validation_result.error_message}", ephemeral=True)
                return

            settings = await get_guild_settings(interaction.guild_id)
            if not settings:
                settings = GuildSettings(guild_id=interaction.guild_id).to_dict()
            settings["student_role_id"] = validation_result.cleaned_value
            await save_guild_setting(settings)

            success_msg = format_message(MessageType.SUCCESS, 'settings_updated', 
                                       setting_name=f"student_role_id to `{validation_result.cleaned_value}`")
            await interaction.followup.send(success_msg, ephemeral=True)
        except Exception as e:
            logger.error(f"Error setting student_role_id: {e}")
            try:
                await interaction.followup.send("❌ Failed to set student_role_id.", ephemeral=True)
            except discord.HTTPException as e:
                logger.warning(f"Failed to send error response: {e}")

    @app_commands.command(name="setorganiserroleid", description="Set the Organisers role ID for admin checks")
    @app_commands.describe(role_id="Numeric ID of the Organisers role")
    async def set_organiser_role_id(self, interaction: discord.Interaction, role_id: str):
        """Store organiser_role_id in guild settings (used for permission checks)."""
        try:
            await interaction.response.defer(ephemeral=True)
            try:
                parsed = int(role_id)
                if parsed <= 0:
                    raise ValueError
            except ValueError:
                await interaction.followup.send("❌ Invalid role ID.", ephemeral=True)
                return

            settings = await get_guild_settings(interaction.guild_id)
            if not settings:
                settings = GuildSettings(guild_id=interaction.guild_id).to_dict()
            settings["organiser_role_id"] = parsed
            await save_guild_setting(settings)

            await interaction.followup.send(f"✅ organiser_role_id set to `{parsed}`.", ephemeral=True)
        except Exception as e:
            logger.error(f"Error setting organiser_role_id: {e}")
            try:
                await interaction.followup.send("❌ Failed to set organiser_role_id.", ephemeral=True)
            except discord.HTTPException as e:
                logger.warning(f"Failed to send error response: {e}")
    
    @app_commands.command(name="settimezone", description="Set the timezone for this server")
    @app_commands.describe(timezone="Timezone name (e.g., Europe/Helsinki, America/New_York)")
    async def set_timezone(self, interaction: discord.Interaction, timezone: str):
        """Set the timezone for poll scheduling."""
        try:
            await interaction.response.defer(ephemeral=True)
            
            # Validate timezone
            validation_result = validate_timezone(timezone)
            if not validation_result:
                error_msg = format_message(MessageType.ERROR, 'invalid_timezone', timezone=timezone)
                await interaction.followup.send(f"{error_msg}\n{validation_result.error_message}", ephemeral=True)
                return
            
            # Get or create guild settings
            guild_settings = await get_guild_settings(interaction.guild_id)
            if not guild_settings:
                guild_settings = GuildSettings(guild_id=interaction.guild_id).to_dict()
            
            guild_settings["timezone"] = validation_result.cleaned_value
            
            # Save settings
            await save_guild_setting(guild_settings)
            
            success_msg = format_message(MessageType.SUCCESS, 'settings_updated', 
                                       setting_name=f"timezone to `{validation_result.cleaned_value}`")
            await interaction.followup.send(success_msg, ephemeral=True)
            
            logger.info(f"Timezone set to {timezone} for guild {interaction.guild_id}")
            
            # Reload scheduler with new settings
            await self.bot.setup_guild_jobs(interaction.guild_id, guild_settings)
            
        except Exception as e:
            logger.error(f"Error setting timezone: {e}")
            try:
                await interaction.followup.send(
                    "❌ An error occurred while setting the timezone.",
                    ephemeral=True
                )
            except discord.HTTPException as e:
                logger.warning(f"Failed to send error response: {e}")
    
    @app_commands.command(name="setpolltimes", description="Set poll timing (publish;close;reminder)")
    @app_commands.describe(times="Format: HH:MM;HH:MM;HH:MM (publish;close;reminder)")
    async def set_poll_times(self, interaction: discord.Interaction, times: str):
        """Set poll timing schedule."""
        try:
            await interaction.response.defer(ephemeral=True)
            
            # Validate poll times format
            validation_result = validate_poll_times_format(times)
            if not validation_result:
                error_msg = format_message(MessageType.ERROR, 'invalid_format', 
                                         expected_format="HH:MM;HH:MM;HH:MM (publish;close;reminder)")
                await interaction.followup.send(f"{error_msg}\n{validation_result.error_message}", ephemeral=True)
                return
            
            publish_time_tuple, close_time_tuple, reminder_time_tuple = validation_result.cleaned_value
            publish_time = f"{publish_time_tuple[0]:02d}:{publish_time_tuple[1]:02d}"
            close_time = f"{close_time_tuple[0]:02d}:{close_time_tuple[1]:02d}"
            reminder_time = f"{reminder_time_tuple[0]:02d}:{reminder_time_tuple[1]:02d}"
            
            # Get or create guild settings
            guild_settings = await get_guild_settings(interaction.guild_id)
            if not guild_settings:
                guild_settings = GuildSettings(guild_id=interaction.guild_id).to_dict()
            
            guild_settings["poll_publish_time"] = publish_time.strip()
            guild_settings["poll_close_time"] = close_time.strip()
            guild_settings["reminder_time"] = reminder_time.strip()
            
            # Save settings
            await save_guild_setting(guild_settings)
            
            embed = (EmbedBuilder("Poll Times Updated")
                    .add_field("📢 Publish Time", publish_time, inline=True)
                    .add_field("⏰ Reminder Time", reminder_time, inline=True)
                    .add_field("🔒 Close Time", close_time, inline=True)
                    .build())
            
            await interaction.followup.send(embed=embed, ephemeral=True)
            
            logger.info(f"Poll times updated for guild {interaction.guild_id}: {times}")
            
            # Reload scheduler with new settings
            await self.bot.setup_guild_jobs(interaction.guild_id, guild_settings)
            
        except Exception as e:
            logger.error(f"Error setting poll times: {e}")
            try:
                await interaction.followup.send(
                    "❌ An error occurred while setting poll times.",
                    ephemeral=True
                )
            except discord.HTTPException as e:
                logger.warning(f"Failed to send error response: {e}")
    
    @app_commands.command(name="setcampmode", description="Set camp operation mode")
    @app_commands.describe(
        mode="Mode: 'cyprus' for feedback-only at 23:00, 'standard' for full polls"
    )
    async def set_camp_mode(self, interaction: discord.Interaction, mode: str):
        """Set the camp operation mode."""
        try:
            await interaction.response.defer(ephemeral=True)
            
            if mode.lower() not in ["cyprus", "standard"]:
                await interaction.followup.send(
                    "❌ Mode must be 'cyprus' or 'standard'", 
                    ephemeral=True
                )
                return
            
            mode = mode.lower()
            guild_settings = await get_guild_settings(interaction.guild_id)
            if not guild_settings:
                guild_settings = GuildSettings(guild_id=interaction.guild_id).to_dict()
            
            # Set camp mode
            guild_settings["camp_mode"] = mode
            
            if mode == "cyprus":
                # Cyprus mode: configure defaults
                guild_settings["timezone"] = "Europe/Nicosia"
                guild_settings["feedback_publish_time"] = "23:00"
                mode_description = "Cyprus Camp (feedback-only at 23:00 Cyprus time)"
            else:
                # Standard mode: keep existing settings or use defaults
                if "timezone" not in guild_settings:
                    guild_settings["timezone"] = "Europe/Helsinki"
                mode_description = "Standard Camp (full poll schedule)"
            
            await save_guild_setting(guild_settings)
            
            # Update scheduler with new mode
            await self.bot.setup_guild_jobs(interaction.guild_id, guild_settings)
            
            # Create success embed
            embed_builder = (EmbedBuilder("Camp Mode Updated")
                    .add_field("🏕️ Mode", mode.title(), inline=True)
                    .add_field("📍 Description", mode_description, inline=False))
            
            if mode == "cyprus":
                embed_builder.add_field(
                    "⏰ Schedule", 
                    "• 23:00 Cyprus Time: Daily feedback polls\n• No attendance polls\n• No reminders", 
                    inline=False
                )
            
            embed = embed_builder.build()
            
            await interaction.followup.send(embed=embed, ephemeral=True)
            
            logger.info(f"Camp mode set to '{mode}' for guild {interaction.guild_id}")
            
        except Exception as e:
            logger.error(f"Error setting camp mode: {e}")
            try:
                await interaction.followup.send(
                    "❌ An error occurred while setting camp mode.",
                    ephemeral=True
                )
            except discord.HTTPException as e:
                logger.warning(f"Failed to send error response: {e}")
    
    @app_commands.command(name="addlecture", description="Add a new lecture")
    @app_commands.describe(
        date_title="Format: DATE;Title (DATE: 2025-06-12, 06-12, or 12 for next occurrence)",
        feedback_only="Skip attendance poll and publish only feedback"
    )
    async def add_lecture(self, interaction: discord.Interaction, date_title: str, feedback_only: bool = False):
        """Add a new lecture event."""
        await self._add_event_from_string(interaction, date_title, EventType.LECTURE, feedback_only)
    
    @app_commands.command(name="addcontest", description="Add a new contest")
    @app_commands.describe(
        date_title="Format: DATE;Title (DATE: 2025-06-12, 06-12, or 12 for next occurrence)",
        feedback_only="Skip attendance poll and publish only feedback"
    )
    async def add_contest(self, interaction: discord.Interaction, date_title: str, feedback_only: bool = False):
        """Add a new contest event."""
        await self._add_event_from_string(interaction, date_title, EventType.CONTEST, feedback_only)
    
    @app_commands.command(name="addextralecture", description="Add an extra lecture (not included in polls)")
    @app_commands.describe(
        date_title="Format: DATE;Title (DATE: 2025-06-12, 06-12, or 12 for next occurrence)",
        feedback_only="Skip attendance poll and publish only feedback"
    )
    async def add_extra_lecture(self, interaction: discord.Interaction, date_title: str, feedback_only: bool = False):
        """Add an extra lecture event (not polled)."""
        await self._add_event_from_string(interaction, date_title, EventType.EXTRA_LECTURE, feedback_only)
    
    @app_commands.command(name="addeveningactivity", description="Add an evening activity (not included in polls)")
    @app_commands.describe(
        date_title="Format: DATE;Title (DATE: 2025-06-12, 06-12, or 12 for next occurrence)",
        feedback_only="Skip attendance poll and publish only feedback"
    )
    async def add_evening_activity(self, interaction: discord.Interaction, date_title: str, feedback_only: bool = False):
        """Add an evening activity event (not polled)."""
        await self._add_event_from_string(interaction, date_title, EventType.EVENING_ACTIVITY, feedback_only)
    
    @app_commands.command(name="addcontesteditorial", description="Add a contest editorial session")
    @app_commands.describe(
        date_title="Format: DATE;Title (DATE: 2025-06-12, 06-12, or 12 for next occurrence)"
    )
    async def add_contest_editorial(self, interaction: discord.Interaction, date_title: str):
        """Add a contest editorial event (Cyprus camp mode)."""
        await self._add_event_from_string(interaction, date_title, EventType.CONTEST_EDITORIAL, feedback_only=True)
    
    async def _add_event_from_string(
        self,
        interaction: discord.Interaction,
        date_title: str,
        event_type: EventType,
        feedback_only: bool = False,
    ):
        """Parse date;title string and add event."""
        try:
            await interaction.response.defer(ephemeral=True)
            
            # Validate date;title format
            validation_result = validate_date_title_format(date_title)
            if not validation_result:
                error_msg = format_message(MessageType.ERROR, 'invalid_format', 
                                         expected_format="DATE;Title (DATE: 2025-06-12, 06-12, or 12)")
                await interaction.followup.send(f"{error_msg}\n{validation_result.error_message}", ephemeral=True)
                return
            
            date, title = validation_result.cleaned_value
            date_str = date.strftime("%Y-%m-%d")
            
            # Prevent duplicate events (same date, title, and type)
            existing_events = await get_events_by_date(date_str)
            if any(
                e.get("event_type") == event_type.value and e.get("title", "").strip().lower() == title.strip().lower()
                for e in existing_events
            ):
                duplicate_msg = format_message(MessageType.ERROR, 'duplicate_event',
                                             event_type=event_type.value.title(), 
                                             title=title, date=date_str)
                await interaction.followup.send(duplicate_msg, ephemeral=True)
                return
            
            await self._add_event(interaction, date_str, title, event_type, feedback_only)
            
        except Exception as e:
            logger.error(f"Error parsing event string: {e}")
            try:
                await interaction.followup.send(
                    "❌ An error occurred while parsing the event string.",
                    ephemeral=True
                )
            except discord.HTTPException as e:
                logger.warning(f"Failed to send error response: {e}")
    
    async def _add_event(
        self,
        interaction: discord.Interaction,
        date: str,
        title: str,
        event_type: EventType,
        feedback_only: bool = False,
    ):
        """Add a new event."""
        try:
            # Validate date format
            try:
                datetime.strptime(date, "%Y-%m-%d")
            except ValueError:
                await interaction.followup.send(
                    f"❌ Invalid date format: `{date}`\n"
                    "Please use YYYY-MM-DD format",
                    ephemeral=True
                )
                return
            
            # Prevent duplicate events (same date, title, and type)
            existing_events = await get_events_by_date(date)
            if any(
                e.get("event_type") == event_type.value and e.get("title", "").strip().lower() == title.strip().lower()
                for e in existing_events
            ):
                await interaction.followup.send(
                    f"❌ {event_type.value.title()} '{title}' on {date} already exists.",
                    ephemeral=True
                )
                return
            
            # Create event
            event = Event(
                id=str(uuid.uuid4()),
                title=title,
                date=date,
                event_type=event_type,
                created_at=datetime.now(timezone.utc),
                feedback_only=feedback_only,
            )
            
            # Save event
            await add_event(event.to_dict())
            
            # Create embed using the new utility
            embed = create_event_embed(event, show_details=True)
            
            await interaction.followup.send(embed=embed, ephemeral=True)
            
            logger.info(f"Added {event_type.value} '{title}' for {date} in guild {interaction.guild_id}")
            
        except Exception as e:
            logger.error(f"Error adding event: {e}")
            try:
                await interaction.followup.send(
                    "❌ An error occurred while adding the event.",
                    ephemeral=True
                )
            except discord.HTTPException as e:
                logger.warning(f"Failed to send error response: {e}")
    
    @app_commands.command(name="listlectures", description="List lectures for a date")
    @app_commands.describe(date="Date in YYYY-MM-DD format")
    async def list_lectures(self, interaction: discord.Interaction, date: str):
        """List lectures for a specific date."""
        await self._list_events(interaction, date, EventType.LECTURE)
    
    @app_commands.command(name="listcontests", description="List contests for a date")
    @app_commands.describe(date="Date in YYYY-MM-DD format")
    async def list_contests(self, interaction: discord.Interaction, date: str):
        """List contests for a specific date."""
        await self._list_events(interaction, date, EventType.CONTEST)
    
    @app_commands.command(name="listextralectures", description="List extra lectures for a date")
    @app_commands.describe(date="Date in YYYY-MM-DD format")
    async def list_extra_lectures(self, interaction: discord.Interaction, date: str):
        """List extra lectures for a specific date."""
        await self._list_events(interaction, date, EventType.EXTRA_LECTURE)
    
    @app_commands.command(name="listeveningactivities", description="List evening activities for a date")
    @app_commands.describe(date="Date in YYYY-MM-DD format")
    async def list_evening_activities(self, interaction: discord.Interaction, date: str):
        """List evening activities for a specific date."""
        await self._list_events(interaction, date, EventType.EVENING_ACTIVITY)
    
    @app_commands.command(name="listcontesteditorials", description="List contest editorials for a date")
    @app_commands.describe(date="Date in YYYY-MM-DD format")
    async def list_contest_editorials(self, interaction: discord.Interaction, date: str):
        """List contest editorials for a specific date."""
        await self._list_events(interaction, date, EventType.CONTEST_EDITORIAL)
    
    async def _list_events(self, interaction: discord.Interaction, date: str, event_type: EventType):
        """Helper method to list events."""
        try:
            # Validate date format
            try:
                datetime.strptime(date, "%Y-%m-%d")
            except ValueError:
                await interaction.response.send_message(
                    f"❌ Invalid date format: `{date}`\n"
                    "Please use YYYY-MM-DD format (e.g., 2024-12-25)",
                    ephemeral=True
                )
                return
            
            # Get events
            events_data = await get_events_by_type(event_type.value, date)
            
            if not events_data:
                await interaction.response.send_message(
                    f"📅 No {event_type.value.replace('_', ' ')}s found for {date}",
                    ephemeral=True
                )
                return
            
            # Create embed
            embed = discord.Embed(
                title=f"📋 {event_type.value.replace('_', ' ').title()}s for {date}",
                color=0x007bff
            )
            
            for i, event_data in enumerate(events_data, 1):
                event = Event.from_dict(event_data)
                pollable_text = " 🗳️" if event.is_pollable else ""
                embed.add_field(
                    name=f"{i}. {event.title}{pollable_text}",
                    value=f"ID: `{event.id}`\nCreated: {event.created_at.strftime('%Y-%m-%d %H:%M UTC')}",
                    inline=False
                )
            
            embed.set_footer(text=f"Total: {len(events_data)} events")
            
            await interaction.response.send_message(embed=embed, ephemeral=True)
            
        except Exception as e:
            logger.error(f"Error listing events: {e}")
            await interaction.response.send_message(
                "❌ An error occurred while listing events.",
                ephemeral=True
            )
    
    @app_commands.command(name="editlecture", description="Edit a lecture")
    @app_commands.describe(
        event_id="Event ID to edit",
        date_title="New format: DATE;Title (DATE: 2025-06-12, 06-12, or 12 for next occurrence)"
    )
    async def edit_lecture(self, interaction: discord.Interaction, event_id: str, date_title: str):
        """Edit an existing lecture event."""
        await self._edit_event(interaction, event_id, date_title, EventType.LECTURE)
    
    @app_commands.command(name="editcontest", description="Edit a contest")
    @app_commands.describe(
        event_id="Event ID to edit",
        date_title="New format: DATE;Title (DATE: 2025-06-12, 06-12, or 12 for next occurrence)"
    )
    async def edit_contest(self, interaction: discord.Interaction, event_id: str, date_title: str):
        """Edit an existing contest event."""
        await self._edit_event(interaction, event_id, date_title, EventType.CONTEST)
    
    @app_commands.command(name="editextralecture", description="Edit an extra lecture")
    @app_commands.describe(
        event_id="Event ID to edit",
        date_title="New format: DATE;Title (DATE: 2025-06-12, 06-12, or 12 for next occurrence)"
    )
    async def edit_extra_lecture(self, interaction: discord.Interaction, event_id: str, date_title: str):
        """Edit an existing extra lecture event."""
        await self._edit_event(interaction, event_id, date_title, EventType.EXTRA_LECTURE)
    
    @app_commands.command(name="editeveningactivity", description="Edit an evening activity")
    @app_commands.describe(
        event_id="Event ID to edit",
        date_title="New format: DATE;Title (DATE: 2025-06-12, 06-12, or 12 for next occurrence)"
    )
    async def edit_evening_activity(self, interaction: discord.Interaction, event_id: str, date_title: str):
        """Edit an existing evening activity event."""
        await self._edit_event(interaction, event_id, date_title, EventType.EVENING_ACTIVITY)
    
    @app_commands.command(name="editcontesteditorial", description="Edit a contest editorial")
    @app_commands.describe(
        event_id="Event ID to edit",
        date_title="Format: DATE;Title (DATE: 2025-06-12, 06-12, or 12 for next occurrence)"
    )
    async def edit_contest_editorial(self, interaction: discord.Interaction, event_id: str, date_title: str):
        """Edit an existing contest editorial event."""
        await self._edit_event(interaction, event_id, date_title, EventType.CONTEST_EDITORIAL)
    
    async def _edit_event(self, interaction: discord.Interaction, event_id: str, date_title: str, event_type: EventType):
        """Helper method to edit events."""
        try:
            # Parse date;title format
            parts = date_title.split(";", 1)
            if len(parts) != 2:
                await interaction.response.send_message(
                    f"❌ Invalid format. Use: `YYYY-MM-DD;Title`\n"
                    f"Example: `2025-06-12;Updated {event_type.value.title()}`",
                    ephemeral=True
                )
                return
            
            date, title = parts
            
            # Validate date format
            try:
                datetime.strptime(date.strip(), "%Y-%m-%d")
            except ValueError:
                await interaction.response.send_message(
                    f"❌ Invalid date format: `{date.strip()}`\n"
                    "Please use YYYY-MM-DD format (e.g., 2024-12-25)",
                    ephemeral=True
                )
                return
            
            # Create updated event
            updated_event = Event(
                id=event_id,
                title=title.strip(),
                date=date.strip(),
                event_type=event_type,
                created_at=datetime.utcnow()  # Keep original creation time in real implementation
            )
            
            # Update event
            success = await update_event(event_id, updated_event.to_dict())
            
            if success:
                embed = discord.Embed(
                    title=f"✅ {event_type.value.replace('_', ' ').title()} Updated",
                    color=0x00ff00
                )
                embed.add_field(name="📅 Date", value=date.strip(), inline=True)
                embed.add_field(name="📝 Title", value=title.strip(), inline=True)
                embed.set_footer(text=f"Event ID: {event_id}")
                
                await interaction.response.send_message(embed=embed, ephemeral=True)
                logger.info(f"Updated {event_type.value} '{title}' for {date} in guild {interaction.guild_id}")
            else:
                await interaction.response.send_message(
                    f"❌ Event `{event_id}` not found or could not be updated.",
                    ephemeral=True
                )
                
        except Exception as e:
            logger.error(f"Error editing event: {e}")
            await interaction.response.send_message(
                "❌ An error occurred while editing the event.",
                ephemeral=True
            )

    @app_commands.command(name="deletelecture", description="Delete a lecture by ID")
    @app_commands.describe(event_id="The lecture ID to delete")
    async def delete_lecture(self, interaction: discord.Interaction, event_id: str):
        """Delete a lecture by its ID."""
        await self._delete_event(interaction, event_id, "lecture")
    
    @app_commands.command(name="deletecontest", description="Delete a contest by ID")
    @app_commands.describe(event_id="The contest ID to delete")
    async def delete_contest(self, interaction: discord.Interaction, event_id: str):
        """Delete a contest by its ID."""
        await self._delete_event(interaction, event_id, "contest")
    
    @app_commands.command(name="deleteextralecture", description="Delete an extra lecture by ID")
    @app_commands.describe(event_id="The extra lecture ID to delete")
    async def delete_extra_lecture(self, interaction: discord.Interaction, event_id: str):
        """Delete an extra lecture by its ID."""
        await self._delete_event(interaction, event_id, "extra lecture")
    
    @app_commands.command(name="deleteeveningactivity", description="Delete an evening activity by ID")
    @app_commands.describe(event_id="The evening activity ID to delete")
    async def delete_evening_activity(self, interaction: discord.Interaction, event_id: str):
        """Delete an evening activity by its ID."""
        await self._delete_event(interaction, event_id, "evening activity")
    
    @app_commands.command(name="deletecontesteditorial", description="Delete a contest editorial by ID")
    @app_commands.describe(event_id="The contest editorial ID to delete")
    async def delete_contest_editorial(self, interaction: discord.Interaction, event_id: str):
        """Delete a contest editorial by its ID."""
        await self._delete_event(interaction, event_id, "contest editorial")
    
    async def _delete_event(self, interaction: discord.Interaction, event_id: str, event_name: str):
        """Helper method to delete events."""
        try:
            success = await delete_event(event_id)
            
            if success:
                await interaction.response.send_message(
                    f"✅ {event_name.title()} `{event_id}` has been deleted.",
                    ephemeral=True
                )
                logger.info(f"Deleted {event_name} {event_id} in guild {interaction.guild_id}")
            else:
                await interaction.response.send_message(
                    f"❌ {event_name.title()} `{event_id}` not found or could not be deleted.",
                    ephemeral=True
                )
                
        except Exception as e:
            logger.error(f"Error deleting {event_name}: {e}")
            await interaction.response.send_message(
                f"❌ An error occurred while deleting the {event_name}.",
                ephemeral=True
            )

    @app_commands.command(name="createtestpoll", description="Create a test poll to verify bot functionality")
    @app_commands.describe(
        send_reminders="Send reminders immediately after creating the poll (default False)",
        create_feedback="Also create feedback polls (default False)"
    )
    async def create_test_poll(
        self, 
        interaction: discord.Interaction, 
        send_reminders: bool = False,
        create_feedback: bool = False
    ):
        """Create a test poll with automatic events to verify bot functionality."""
        try:
            await interaction.response.defer(ephemeral=True)
            
            # Check guild settings
            guild_settings = await get_guild_settings(interaction.guild_id)
            if not guild_settings:
                await interaction.followup.send(
                    "❌ Server settings not found. Please configure the bot first using `/setchannels`.",
                    ephemeral=True
                )
                return
            
            # Check if poll channel is configured
            poll_channel_id = guild_settings.get("poll_channel_id")
            if not poll_channel_id:
                await interaction.followup.send(
                    "❌ Poll channel not configured. Use `/setchannels` to set it up.",
                    ephemeral=True
                )
                return
            
            poll_channel = interaction.guild.get_channel(poll_channel_id)
            if not poll_channel:
                await interaction.followup.send(
                    f"❌ Poll channel #{poll_channel_id} not found.",
                    ephemeral=True
                )
                return
            
            # Get tomorrow's date
            timezone = guild_settings.get("timezone", "Europe/Helsinki")
            tomorrow_date = tz_tomorrow(timezone)
            
            # Create test events
            test_events = [
                {
                    "title": "🔬 Test Algorithms Lecture",
                    "event_type": EventType.LECTURE,
                    "feedback_only": False
                },
                {
                    "title": "🏆 Test Contest",
                    "event_type": EventType.CONTEST,
                    "feedback_only": False
                }
            ]
            
            created_events = []
            
            for event_data in test_events:
                # Check for duplicates
                existing_events = await get_events_by_date(tomorrow_date)
                if any(
                    e.get("event_type") == event_data["event_type"].value and 
                    e.get("title", "").strip().lower() == event_data["title"].strip().lower()
                    for e in existing_events
                ):
                    continue
                
                # Create event
                event = Event(
                    id=str(uuid.uuid4()),
                    title=event_data["title"],
                    date=tomorrow_date,
                    event_type=event_data["event_type"],
                    created_at=datetime.now(timezone.utc),
                    feedback_only=event_data["feedback_only"],
                )
                
                await add_event(event.to_dict())
                created_events.append(event)
                logger.info(f"Created test event: {event.title} for {tomorrow_date}")
            
            if not created_events:
                await interaction.followup.send(
                    f"❌ Test events for {tomorrow_date} already exist.",
                    ephemeral=True
                )
                return
            
            # Send initial confirmation
            initial_embed = EmbedBuilder("⏳ Test Poll Setup")
            initial_embed.add_field(
                "📅 Event Date", 
                tomorrow_date, 
                inline=True
            )
            initial_embed.add_field(
                "🎯 Events Created", 
                "\n".join([f"• {event.title}" for event in created_events]), 
                inline=False
            )
            initial_embed.add_field(
                "📍 Channel", 
                poll_channel.mention, 
                inline=True
            )
            initial_embed.add_field(
                "⏰ Status", 
                "Events created successfully. Poll will be published in 1 minute...", 
                inline=False
            )
            
            await interaction.followup.send(embed=initial_embed.build(), ephemeral=True)
            
            # Wait 1 minute before publishing the poll
            await asyncio.sleep(60)
            
            # Publish attendance poll
            published_polls = await publish_attendance_poll(
                self.bot, 
                interaction.guild, 
                guild_settings
            )
            
            # Create final results embed
            final_embed = EmbedBuilder("✅ Test Poll Created")
            final_embed.add_field(
                "📅 Event Date", 
                tomorrow_date, 
                inline=True
            )
            final_embed.add_field(
                "📊 Polls Published", 
                str(len(published_polls)) if published_polls else "0", 
                inline=True
            )
            final_embed.add_field(
                "🎯 Events", 
                "\n".join([f"• {event.title}" for event in created_events]), 
                inline=False
            )
            final_embed.add_field(
                "📍 Channel", 
                poll_channel.mention, 
                inline=True
            )
            
            # Send reminders if requested
            if send_reminders:
                try:
                    reminder_stats = await send_reminders(
                        self.bot, 
                        interaction.guild, 
                        guild_settings
                    )
                    final_embed.add_field(
                        "📨 Reminders", 
                        f"Sent: {reminder_stats.get('sent', 0)}\nFailed: {reminder_stats.get('failed', 0)}", 
                        inline=True
                    )
                except Exception as e:
                    logger.error(f"Error sending test reminders: {e}")
                    final_embed.add_field(
                        "⚠️ Reminders", 
                        "Error sending", 
                        inline=True
                    )
            
            # Create feedback polls if requested
            if create_feedback:
                try:
                    feedback_polls = await publish_feedback_polls(
                        self.bot, 
                        interaction.guild, 
                        guild_settings
                    )
                    final_embed.add_field(
                        "💬 Feedback Polls", 
                        f"Created: {len(feedback_polls) if feedback_polls else 0}", 
                        inline=True
                    )
                except Exception as e:
                    logger.error(f"Error creating test feedback polls: {e}")
                    final_embed.add_field(
                        "⚠️ Feedback", 
                        "Error creating", 
                        inline=True
                    )
            
            final_embed.add_field(
                "ℹ️ Note", 
                "This is a test poll to verify bot functionality. Events are created for tomorrow.", 
                inline=False
            )
            
            # Send updated results via edit (use a new message since we can't edit across long delays)
            try:
                await interaction.user.send(embed=final_embed.build())
            except discord.Forbidden:
                # If DM fails, send to channel (this might be visible to others)
                await poll_channel.send(f"{interaction.user.mention} Your test poll results:", embed=final_embed.build())
            
            # Send notification to poll channel
            notification_embed = discord.Embed(
                title="🧪 Test Poll Created",
                description=f"Administrator {interaction.user.mention} created a test poll to verify bot functionality.",
                color=0x007bff
            )
            notification_embed.add_field(
                name="📅 Events for", 
                value=tomorrow_date, 
                inline=True
            )
            notification_embed.add_field(
                name="🎯 Number of Events", 
                value=str(len(created_events)), 
                inline=True
            )
            
            try:
                await poll_channel.send(embed=notification_embed)
            except Exception as e:
                logger.warning(f"Could not send notification to poll channel: {e}")
            
            logger.info(
                f"Test poll created by {interaction.user.id} in guild {interaction.guild_id}: "
                f"{len(created_events)} events, {len(published_polls) if published_polls else 0} polls"
            )
            
        except Exception as e:
            logger.error(f"Error creating test poll: {e}")
            try:
                await interaction.followup.send(
                    "❌ An error occurred while creating the test poll.",
                    ephemeral=True
                )
            except discord.HTTPException as e:
                logger.warning(f"Failed to send error response: {e}")

    @app_commands.command(name="quicktestpoll", description="Create a test poll immediately (no delay)")
    @app_commands.describe(
        send_reminders="Send reminders immediately after creating the poll (default False)",
        create_feedback="Also create feedback polls (default False)"
    )
    async def quick_test_poll(
        self, 
        interaction: discord.Interaction, 
        send_reminders: bool = False,
        create_feedback: bool = False
    ):
        """Create a test poll immediately without delay for quick testing."""
        try:
            await interaction.response.defer(ephemeral=True)
            
            # Check guild settings
            guild_settings = await get_guild_settings(interaction.guild_id)
            if not guild_settings:
                await interaction.followup.send(
                    "❌ Server settings not found. Please configure the bot first using `/setchannels`.",
                    ephemeral=True
                )
                return
            
            # Check if poll channel is configured
            poll_channel_id = guild_settings.get("poll_channel_id")
            if not poll_channel_id:
                await interaction.followup.send(
                    "❌ Poll channel not configured. Use `/setchannels` to set it up.",
                    ephemeral=True
                )
                return
            
            poll_channel = interaction.guild.get_channel(poll_channel_id)
            if not poll_channel:
                await interaction.followup.send(
                    f"❌ Poll channel #{poll_channel_id} not found.",
                    ephemeral=True
                )
                return
            
            # Get tomorrow's date
            timezone = guild_settings.get("timezone", "Europe/Helsinki")
            tomorrow_date = tz_tomorrow(timezone)
            
            # Create test events
            test_events = [
                {
                    "title": "⚡ Quick Test Lecture",
                    "event_type": EventType.LECTURE,
                    "feedback_only": False
                },
                {
                    "title": "⚡ Quick Test Contest",
                    "event_type": EventType.CONTEST,
                    "feedback_only": False
                }
            ]
            
            created_events = []
            
            for event_data in test_events:
                # Check for duplicates
                existing_events = await get_events_by_date(tomorrow_date)
                if any(
                    e.get("event_type") == event_data["event_type"].value and 
                    e.get("title", "").strip().lower() == event_data["title"].strip().lower()
                    for e in existing_events
                ):
                    continue
                
                # Create event
                event = Event(
                    id=str(uuid.uuid4()),
                    title=event_data["title"],
                    date=tomorrow_date,
                    event_type=event_data["event_type"],
                    created_at=datetime.now(timezone.utc),
                    feedback_only=event_data["feedback_only"],
                )
                
                await add_event(event.to_dict())
                created_events.append(event)
                logger.info(f"Created quick test event: {event.title} for {tomorrow_date}")
            
            if not created_events:
                await interaction.followup.send(
                    f"❌ Quick test events for {tomorrow_date} already exist.",
                    ephemeral=True
                )
                return
            
            # Publish attendance poll immediately
            published_polls = await publish_attendance_poll(
                self.bot, 
                interaction.guild, 
                guild_settings
            )
            
            # Create results embed
            embed = EmbedBuilder("⚡ Quick Test Poll Created")
            embed.add_field(
                "📅 Event Date", 
                tomorrow_date, 
                inline=True
            )
            embed.add_field(
                "📊 Polls Published", 
                str(len(published_polls)) if published_polls else "0", 
                inline=True
            )
            embed.add_field(
                "🎯 Events", 
                "\n".join([f"• {event.title}" for event in created_events]), 
                inline=False
            )
            embed.add_field(
                "📍 Channel", 
                poll_channel.mention, 
                inline=True
            )
            
            # Send reminders if requested
            if send_reminders:
                try:
                    reminder_stats = await send_reminders(
                        self.bot, 
                        interaction.guild, 
                        guild_settings
                    )
                    embed.add_field(
                        "📨 Reminders", 
                        f"Sent: {reminder_stats.get('sent', 0)}\nFailed: {reminder_stats.get('failed', 0)}", 
                        inline=True
                    )
                except Exception as e:
                    logger.error(f"Error sending quick test reminders: {e}")
                    embed.add_field(
                        "⚠️ Reminders", 
                        "Error sending", 
                        inline=True
                    )
            
            # Create feedback polls if requested
            if create_feedback:
                try:
                    feedback_polls = await publish_feedback_polls(
                        self.bot, 
                        interaction.guild, 
                        guild_settings
                    )
                    embed.add_field(
                        "💬 Feedback Polls", 
                        f"Created: {len(feedback_polls) if feedback_polls else 0}", 
                        inline=True
                    )
                except Exception as e:
                    logger.error(f"Error creating quick test feedback polls: {e}")
                    embed.add_field(
                        "⚠️ Feedback", 
                        "Error creating", 
                        inline=True
                    )
            
            embed.add_field(
                "ℹ️ Note", 
                "This is a quick test poll for immediate verification of bot functionality.", 
                inline=False
            )
            
            await interaction.followup.send(embed=embed.build(), ephemeral=True)
            
            logger.info(
                f"Quick test poll created by {interaction.user.id} in guild {interaction.guild_id}: "
                f"{len(created_events)} events, {len(published_polls) if published_polls else 0} polls"
            )
            
        except Exception as e:
            logger.error(f"Error creating quick test poll: {e}")
            try:
                await interaction.followup.send(
                    "❌ An error occurred while creating the quick test poll.",
                    ephemeral=True
                )
            except discord.HTTPException as e:
                logger.warning(f"Failed to send error response: {e}")

async def setup(bot: commands.Bot):
    """Setup function for the cog."""
    await bot.add_cog(AdminCommands(bot))