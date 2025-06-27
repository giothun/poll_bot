"""
Admin commands for CampPoll bot.
Handles event management and bot configuration.
"""

import uuid
from datetime import datetime
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
from utils.time import is_valid_timezone, parse_time

logger = logging.getLogger(__name__)

class AdminCommands(commands.Cog):
    """Admin-only commands for managing the bot."""
    
    def __init__(self, bot: commands.Bot):
        self.bot = bot
    
    # Ensure that all application (slash) commands in this cog are restricted to server administrators
    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        """Global check for every app command in this cog."""
        if interaction.user and interaction.user.guild_permissions.administrator:
            return True

        await interaction.response.send_message(
            "❌ Only server administrators can use this command.",
            ephemeral=True,
        )
        return False
    
    async def cog_check(self, ctx) -> bool:
        """Ensure only administrators can use these commands."""
        return ctx.author.guild_permissions.administrator
    
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
            for channel, purpose in [
                (poll_channel, "poll"),
                (organiser_channel, "organiser"),
                (alerts_channel, "alerts")
            ]:
                perms = channel.permissions_for(interaction.guild.me)
                if not (perms.send_messages and perms.embed_links):
                    await interaction.followup.send(
                        f"❌ Bot needs 'Send Messages' and 'Embed Links' permissions in {channel.mention} ({purpose} channel)",
                        ephemeral=True
                    )
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
            embed = discord.Embed(
                title="✅ Bot Channels Configured",
                color=0x00ff00
            )
            embed.add_field(
                name="📊 Poll Channel",
                value=poll_channel.mention,
                inline=False
            )
            embed.add_field(
                name="📈 Results Channel",
                value=organiser_channel.mention,
                inline=False
            )
            embed.add_field(
                name="⚠️ Alerts Channel",
                value=alerts_channel.mention,
                inline=False
            )
            
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
            except:
                pass
    
    @app_commands.command(name="settimezone", description="Set the timezone for this server")
    @app_commands.describe(timezone="Timezone name (e.g., Europe/Helsinki, America/New_York)")
    async def set_timezone(self, interaction: discord.Interaction, timezone: str):
        """Set the timezone for poll scheduling."""
        try:
            await interaction.response.defer(ephemeral=True)
            
            if not is_valid_timezone(timezone):
                await interaction.followup.send(
                    f"❌ Invalid timezone: `{timezone}`\n"
                    "Please use a valid IANA timezone name (e.g., Europe/Helsinki, America/New_York)",
                    ephemeral=True
                )
                return
            
            # Get or create guild settings
            guild_settings = await get_guild_settings(interaction.guild_id)
            if not guild_settings:
                guild_settings = GuildSettings(guild_id=interaction.guild_id).to_dict()
            
            guild_settings["timezone"] = timezone
            
            # Save settings
            await save_guild_setting(guild_settings)
            
            await interaction.followup.send(
                f"✅ Timezone set to `{timezone}` for this server.",
                ephemeral=True
            )
            
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
            except:
                pass
    
    @app_commands.command(name="setpolltimes", description="Set poll timing (publish;close;reminder)")
    @app_commands.describe(times="Format: HH:MM;HH:MM;HH:MM (publish;close;reminder)")
    async def set_poll_times(self, interaction: discord.Interaction, times: str):
        """Set poll timing schedule."""
        try:
            await interaction.response.defer(ephemeral=True)
            
            parts = times.split(";")
            if len(parts) != 3:
                await interaction.followup.send(
                    "❌ Invalid format. Use: `HH:MM;HH:MM;HH:MM` (publish;close;reminder)\n"
                    "Example: `15:00;09:00;19:00`",
                    ephemeral=True
                )
                return
            
            publish_time, close_time, reminder_time = parts
            
            # Validate time formats
            for time_str, name in [(publish_time, "publish"), (close_time, "close"), (reminder_time, "reminder")]:
                if not parse_time(time_str.strip()):
                    await interaction.followup.send(
                        f"❌ Invalid {name} time format: `{time_str}`\n"
                        "Please use HH:MM format (24-hour)",
                        ephemeral=True
                    )
                    return
            
            # Get or create guild settings
            guild_settings = await get_guild_settings(interaction.guild_id)
            if not guild_settings:
                guild_settings = GuildSettings(guild_id=interaction.guild_id).to_dict()
            
            guild_settings["poll_publish_time"] = publish_time.strip()
            guild_settings["poll_close_time"] = close_time.strip()
            guild_settings["reminder_time"] = reminder_time.strip()
            
            # Save settings
            await save_guild_setting(guild_settings)
            
            embed = discord.Embed(
                title="✅ Poll Times Updated",
                color=0x00ff00
            )
            embed.add_field(name="📢 Publish Time", value=publish_time.strip(), inline=True)
            embed.add_field(name="⏰ Reminder Time", value=reminder_time.strip(), inline=True)
            embed.add_field(name="🔒 Close Time", value=close_time.strip(), inline=True)
            
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
            except:
                pass
    
    @app_commands.command(name="addlecture", description="Add a new lecture")
    @app_commands.describe(
        date_title="Format: YYYY-MM-DD;Title (e.g., 2025-06-12;Search Algorithms)",
        feedback_only="Skip attendance poll and publish only feedback"
    )
    async def add_lecture(self, interaction: discord.Interaction, date_title: str, feedback_only: bool = False):
        """Add a new lecture event."""
        await self._add_event_from_string(interaction, date_title, EventType.LECTURE, feedback_only)
    
    @app_commands.command(name="addcontest", description="Add a new contest")
    @app_commands.describe(
        date_title="Format: YYYY-MM-DD;Title (e.g., 2025-06-12;Graph Challenge)",
        feedback_only="Skip attendance poll and publish only feedback"
    )
    async def add_contest(self, interaction: discord.Interaction, date_title: str, feedback_only: bool = False):
        """Add a new contest event."""
        await self._add_event_from_string(interaction, date_title, EventType.CONTEST, feedback_only)
    
    @app_commands.command(name="addextralecture", description="Add an extra lecture (not included in polls)")
    @app_commands.describe(
        date_title="Format: YYYY-MM-DD;Title (e.g., 2025-06-12;DevOps 101)",
        feedback_only="Skip attendance poll and publish only feedback"
    )
    async def add_extra_lecture(self, interaction: discord.Interaction, date_title: str, feedback_only: bool = False):
        """Add an extra lecture event (not polled)."""
        await self._add_event_from_string(interaction, date_title, EventType.EXTRA_LECTURE, feedback_only)
    
    @app_commands.command(name="addeveningactivity", description="Add an evening activity (not included in polls)")
    @app_commands.describe(
        date_title="Format: YYYY-MM-DD;Title (e.g., 2025-06-12;Movie Night)",
        feedback_only="Skip attendance poll and publish only feedback"
    )
    async def add_evening_activity(self, interaction: discord.Interaction, date_title: str, feedback_only: bool = False):
        """Add an evening activity event (not polled)."""
        await self._add_event_from_string(interaction, date_title, EventType.EVENING_ACTIVITY, feedback_only)
    
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
            
            if ";" not in date_title:
                await interaction.followup.send(
                    "❌ Invalid format. Use: `YYYY-MM-DD;Title`\n"
                    "Example: `2025-06-12;Search Algorithms`",
                    ephemeral=True
                )
                return
            
            date, title = date_title.split(";", 1)
            
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
            
            await self._add_event(interaction, date.strip(), title.strip(), event_type, feedback_only)
            
        except Exception as e:
            logger.error(f"Error parsing event string: {e}")
            try:
                await interaction.followup.send(
                    "❌ An error occurred while parsing the event string.",
                    ephemeral=True
                )
            except:
                pass
    
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
                created_at=datetime.utcnow(),
                feedback_only=feedback_only,
            )
            
            # Save event
            await add_event(event.to_dict())
            
            embed = discord.Embed(
                title=f"✅ {event_type.value.title()} Added",
                color=0x00ff00
            )
            embed.add_field(name="📅 Date", value=date, inline=True)
            embed.add_field(name="📝 Title", value=title, inline=True)
            embed.add_field(name="🏷️ Type", value=event_type.value.replace("_", " ").title(), inline=True)
            if feedback_only:
                embed.add_field(name="⚙️ Mode", value="Feedback only", inline=False)
            embed.set_footer(text=f"Event ID: {event.id}")
            
            await interaction.followup.send(embed=embed, ephemeral=True)
            
            logger.info(f"Added {event_type.value} '{title}' for {date} in guild {interaction.guild_id}")
            
        except Exception as e:
            logger.error(f"Error adding event: {e}")
            try:
                await interaction.followup.send(
                    "❌ An error occurred while adding the event.",
                    ephemeral=True
                )
            except:
                pass
    
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
        date_title="New format: YYYY-MM-DD;Title"
    )
    async def edit_lecture(self, interaction: discord.Interaction, event_id: str, date_title: str):
        """Edit an existing lecture event."""
        await self._edit_event(interaction, event_id, date_title, EventType.LECTURE)
    
    @app_commands.command(name="editcontest", description="Edit a contest")
    @app_commands.describe(
        event_id="Event ID to edit",
        date_title="New format: YYYY-MM-DD;Title"
    )
    async def edit_contest(self, interaction: discord.Interaction, event_id: str, date_title: str):
        """Edit an existing contest event."""
        await self._edit_event(interaction, event_id, date_title, EventType.CONTEST)
    
    @app_commands.command(name="editextralecture", description="Edit an extra lecture")
    @app_commands.describe(
        event_id="Event ID to edit",
        date_title="New format: YYYY-MM-DD;Title"
    )
    async def edit_extra_lecture(self, interaction: discord.Interaction, event_id: str, date_title: str):
        """Edit an existing extra lecture event."""
        await self._edit_event(interaction, event_id, date_title, EventType.EXTRA_LECTURE)
    
    @app_commands.command(name="editeveningactivity", description="Edit an evening activity")
    @app_commands.describe(
        event_id="Event ID to edit",
        date_title="New format: YYYY-MM-DD;Title"
    )
    async def edit_evening_activity(self, interaction: discord.Interaction, event_id: str, date_title: str):
        """Edit an existing evening activity event."""
        await self._edit_event(interaction, event_id, date_title, EventType.EVENING_ACTIVITY)
    
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

async def setup(bot: commands.Bot):
    """Setup function for the cog."""
    await bot.add_cog(AdminCommands(bot))