"""
Export and poll management commands for CampPoll bot.
Handles poll closing and attendance data export.
"""

from typing import Optional
import discord
from discord.ext import commands
from discord import app_commands
import logging

from models import PollMeta
from storage import get_poll, load_polls
from services.poll_manager import close_poll
from services.csv_service import create_attendance_csv, export_user_votes
from storage import get_guild_settings

logger = logging.getLogger(__name__)

class ExportCommands(commands.Cog):
    """Commands for poll management and data export."""
    
    def __init__(self, bot: commands.Bot):
        self.bot = bot
    
    async def cog_check(self, ctx) -> bool:
        """Ensure only administrators can use these commands."""
        return ctx.author.guild_permissions.administrator
    
    @app_commands.command(name="endpoll", description="Manually close a poll early")
    @app_commands.describe(message_id="The message ID of the poll to close")
    async def end_poll(self, interaction: discord.Interaction, message_id: str):
        """Manually close an active poll."""
        try:
            await interaction.response.defer(ephemeral=True)
            
            # Find the poll by message ID
            all_polls = await load_polls()
            target_poll = None
            
            for poll_data in all_polls.values():
                if (str(poll_data.get("message_id")) == message_id and 
                    poll_data.get("guild_id") == interaction.guild_id and
                    poll_data.get("closed_at") is None):
                    target_poll = PollMeta.from_dict(poll_data)
                    break
            
            if not target_poll:
                await interaction.followup.send(
                    f"❌ No active poll found with message ID `{message_id}` in this server.",
                    ephemeral=True
                )
                return
            
            # Get guild settings
            guild_settings = await get_guild_settings(interaction.guild_id)
            if not guild_settings:
                await interaction.followup.send(
                    "❌ No guild settings found. Please configure the bot first.",
                    ephemeral=True
                )
                return
            
            # Close the poll
            success = await close_poll(self.bot, interaction.guild, target_poll, guild_settings)
            
            if success:
                embed = discord.Embed(
                    title="✅ Poll Closed",
                    description=f"Poll for **{target_poll.poll_date}** has been closed manually.",
                    color=0x00ff00
                )
                embed.add_field(
                    name="📊 Final Stats",
                    value=f"**{target_poll.total_votes}** total votes\n**{len(target_poll.options)}** options",
                    inline=True
                )
                embed.add_field(
                    name="📄 Results",
                    value="Results and CSV sent to organizers channel",
                    inline=True
                )
                embed.set_footer(text=f"Poll ID: {target_poll.id}")
                
                await interaction.followup.send(embed=embed, ephemeral=True)
                
                logger.info(f"Manually closed poll {target_poll.id} in guild {interaction.guild_id}")
            else:
                await interaction.followup.send(
                    "❌ Failed to close the poll. Please check logs for details.",
                    ephemeral=True
                )
                
        except Exception as e:
            logger.error(f"Error ending poll: {e}")
            await interaction.followup.send(
                "❌ An error occurred while closing the poll.",
                ephemeral=True
            )
    
    @app_commands.command(name="exportattendance", description="Export attendance data for a poll")
    @app_commands.describe(message_id="The message ID of the poll to export")
    async def export_attendance(self, interaction: discord.Interaction, message_id: str):
        """Export detailed attendance data as CSV."""
        try:
            await interaction.response.defer(ephemeral=True)
            
            # Find the poll by message ID
            all_polls = await load_polls()
            target_poll = None
            
            for poll_data in all_polls.values():
                if (str(poll_data.get("message_id")) == message_id and 
                    poll_data.get("guild_id") == interaction.guild_id):
                    target_poll = PollMeta.from_dict(poll_data)
                    break
            
            if not target_poll:
                await interaction.followup.send(
                    f"❌ No poll found with message ID `{message_id}` in this server.",
                    ephemeral=True
                )
                return
            
            # Build optional user_id -> display_name map for readability
            members_map = {}
            try:
                for m in interaction.guild.members:
                    if not m.bot:
                        members_map[m.id] = m.display_name
            except Exception:
                members_map = {}

            # Create CSV with optional member names
            csv_data = await create_attendance_csv(target_poll, members_map or None)
            
            if not csv_data:
                await interaction.followup.send(
                    "❌ Failed to generate CSV data. Please try again.",
                    ephemeral=True
                )
                return
            
            # Create file
            filename = f"attendance_{target_poll.poll_date}_{target_poll.id[:8]}.csv"
            csv_file = discord.File(csv_data, filename=filename)
            
            # Create info embed
            embed = discord.Embed(
                title="📄 Attendance Export",
                description=f"Detailed attendance data for poll on **{target_poll.poll_date}**",
                color=0x007bff
            )
            
            embed.add_field(
                name="📊 Poll Stats",
                value=f"**{target_poll.total_votes}** total votes\n**{len(target_poll.options)}** options",
                inline=True
            )
            
            status = "🔒 Closed" if target_poll.is_closed else "🔓 Active"
            embed.add_field(
                name="📈 Status",
                value=status,
                inline=True
            )
            
            embed.add_field(
                name="📅 Export Details",
                value=f"Poll Date: {target_poll.poll_date}\nExported: {discord.utils.utcnow().strftime('%Y-%m-%d %H:%M UTC')}",
                inline=False
            )
            
            embed.set_footer(text=f"Poll ID: {target_poll.id}")
            
            await interaction.followup.send(
                embed=embed,
                file=csv_file,
                ephemeral=True
            )
            
            logger.info(f"Exported attendance data for poll {target_poll.id}")
            
        except Exception as e:
            logger.error(f"Error exporting attendance: {e}")
            await interaction.followup.send(
                "❌ An error occurred while exporting attendance data.",
                ephemeral=True
            )
    
    @app_commands.command(name="exportuservotes", description="Export detailed user vote data")
    @app_commands.describe(message_id="The message ID of the poll to export")
    async def export_user_votes(self, interaction: discord.Interaction, message_id: str):
        """Export user-specific voting data."""
        try:
            await interaction.response.defer(ephemeral=True)
            
            # Find the poll
            all_polls = await load_polls()
            target_poll = None
            
            for poll_data in all_polls.values():
                if (str(poll_data.get("message_id")) == message_id and 
                    poll_data.get("guild_id") == interaction.guild_id):
                    target_poll = PollMeta.from_dict(poll_data)
                    break
            
            if not target_poll:
                await interaction.followup.send(
                    f"❌ No poll found with message ID `{message_id}` in this server.",
                    ephemeral=True
                )
                return
            
            # Create user votes CSV
            csv_data = await export_user_votes(target_poll)
            
            if not csv_data:
                await interaction.followup.send(
                    "❌ Failed to generate user votes CSV. Please try again.",
                    ephemeral=True
                )
                return
            
            # Create file
            filename = f"user_votes_{target_poll.poll_date}_{target_poll.id[:8]}.csv"
            csv_file = discord.File(csv_data, filename=filename)
            
            # Create info embed
            embed = discord.Embed(
                title="👥 User Votes Export",
                description=f"Individual vote data for poll on **{target_poll.poll_date}**",
                color=0x9932cc
            )
            
            embed.add_field(
                name="📊 Voting Summary",
                value=f"**{target_poll.total_votes}** users voted",
                inline=True
            )
            
            embed.add_field(
                name="🔒 Privacy Notice", 
                value="Contains user IDs - handle securely",
                inline=True
            )
            
            embed.set_footer(text=f"Poll ID: {target_poll.id}")
            
            await interaction.followup.send(
                embed=embed,
                file=csv_file,
                ephemeral=True
            )
            
            logger.info(f"Exported user votes for poll {target_poll.id}")
            
        except Exception as e:
            logger.error(f"Error exporting user votes: {e}")
            await interaction.followup.send(
                "❌ An error occurred while exporting user votes.",
                ephemeral=True
            )
    
    @app_commands.command(name="listactivepolls", description="List all active polls in this server")
    async def list_active_polls(self, interaction: discord.Interaction):
        """List all active polls for this guild."""
        try:
            all_polls = await load_polls()
            active_polls = [
                PollMeta.from_dict(poll) for poll in all_polls.values()
                if poll["guild_id"] == interaction.guild_id and poll["closed_at"] is None
            ]
            
            if not active_polls:
                await interaction.response.send_message(
                    "📅 No active polls found in this server.",
                    ephemeral=True
                )
                return
            
            embed = discord.Embed(
                title="🗳️ Active Polls",
                description=f"Currently active polls in this server",
                color=0x007bff
            )
            
            for i, poll in enumerate(active_polls, 1):
                channel = interaction.guild.get_channel(poll.channel_id)
                channel_name = channel.name if channel else "Unknown Channel"
                
                embed.add_field(
                    name=f"{i}. Poll for {poll.poll_date}",
                    value=(
                        f"**Options:** {len(poll.options)}\n"
                        f"**Votes:** {poll.total_votes}\n"
                        f"**Channel:** #{channel_name}\n"
                        f"**Message ID:** `{poll.message_id}`"
                    ),
                    inline=False
                )
            
            embed.set_footer(text=f"Total active polls: {len(active_polls)}")
            
            await interaction.response.send_message(embed=embed, ephemeral=True)
            
        except Exception as e:
            logger.error(f"Error listing active polls: {e}")
            await interaction.response.send_message(
                "❌ An error occurred while listing active polls.",
                ephemeral=True
            )

async def setup(bot: commands.Bot):
    """Setup function for the cog."""
    await bot.add_cog(ExportCommands(bot)) 