"""
Scheduler Service for CampPoll bot.
Handles all scheduling logic for polls, reminders, and other timed tasks.
"""

import logging
from datetime import datetime, timezone
from typing import Dict, Optional, Any, List
from zoneinfo import ZoneInfo

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
import discord

from models import GuildSettings
from storage import get_guild_settings, load_guild_settings
from utils.time import is_valid_timezone, parse_time
from services.poll_manager import (
    publish_attendance_poll, send_reminders,
    close_all_active_polls, publish_feedback_polls
)

logger = logging.getLogger(__name__)


class SchedulerService:
    """Service for managing scheduled tasks for guilds."""
    
    def __init__(self, bot: discord.Client):
        self.bot = bot
        self.scheduler = AsyncIOScheduler()
        self._job_registry: Dict[str, Dict[str, Any]] = {}
    
    def start(self):
        """Start the scheduler."""
        if not self.scheduler.running:
            self.scheduler.start()
            logger.info("Scheduler started")
    
    def shutdown(self):
        """Shutdown the scheduler."""
        if self.scheduler.running:
            self.scheduler.shutdown()
            logger.info("Scheduler stopped")
    
    async def setup_all_guild_jobs(self):
        """Setup jobs for all guilds from stored settings."""
        logger.info("Setting up scheduler for all guilds...")
        
        guild_settings = await load_guild_settings()
        
        for guild_id_str, settings in guild_settings.items():
            guild_id = int(guild_id_str)
            await self.setup_guild_jobs(guild_id, settings)
        
        logger.info(f"Scheduler setup complete with {len(self.scheduler.get_jobs())} jobs")
    
    async def setup_guild_jobs(self, guild_id: int, settings: Optional[Dict] = None):
        """Setup scheduled jobs for a specific guild."""
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
            
            # Remove existing jobs for this guild
            await self._remove_guild_jobs(guild_id)
            
            # Create job configurations
            job_configs = self._build_job_configs(guild_id, settings, timezone)
            
            # Add all jobs
            for job_config in job_configs:
                try:
                    self.scheduler.add_job(**job_config)
                    self._job_registry[job_config['id']] = {
                        'guild_id': guild_id,
                        'job_type': job_config.get('name', '').split(' - ')[0],
                        'created_at': datetime.now()
                    }
                except Exception as e:
                    logger.error(f"Failed to add job {job_config['id']}: {e}")
            
            logger.info(f"Setup {len(job_configs)} scheduled jobs for guild {guild_id} (timezone: {timezone})")
            
        except Exception as e:
            logger.error(f"Error setting up jobs for guild {guild_id}: {e}")
    
    async def _remove_guild_jobs(self, guild_id: int):
        """Remove all jobs for a specific guild."""
        job_ids_to_remove = [
            f"poll_publish_{guild_id}",
            f"poll_reminder_{guild_id}",
            f"poll_close_{guild_id}",
            f"feedback_publish_{guild_id}",
            f"cyprus_feedback_{guild_id}",
            f"cyprus_reminder_{guild_id}"
        ]
        
        for job_id in job_ids_to_remove:
            if self.scheduler.get_job(job_id):
                self.scheduler.remove_job(job_id)
                self._job_registry.pop(job_id, None)
    
    def _build_job_configs(self, guild_id: int, settings: Dict, timezone: str) -> List[Dict]:
        """Build job configuration list for a guild."""
        # Check if this is Cyprus camp mode
        camp_mode = settings.get("camp_mode", "standard")
        
        # Parse times with validation
        times = {}
        if camp_mode == "cyprus":
            # Cyprus mode: feedback polls and reminders
            time_keys = ["feedback_publish_time", "reminder_time"]
            defaults = ["23:00", "19:00"]
        else:
            # Standard mode: all polls
            time_keys = ["poll_publish_time", "reminder_time", "poll_close_time", "feedback_publish_time"]
            defaults = ["14:30", "19:00", "09:00", "22:00"]
        
        for key, default in zip(time_keys, defaults):
            time_str = settings.get(key, default)
            parsed_time = parse_time(time_str)
            if not parsed_time:
                logger.warning(f"Invalid {key} '{time_str}' for guild {guild_id}, using default {default}")
                parsed_time = parse_time(default)
            times[key] = parsed_time
        
        job_configs = []
        
        if camp_mode == "cyprus":
            # Cyprus mode: feedback polls and reminders
            
            # Cyprus feedback publish job
            job_configs.append({
                'func': self._run_cyprus_feedback_publish,
                'args': [guild_id],
                'trigger': CronTrigger(
                    hour=times["feedback_publish_time"][0],
                    minute=times["feedback_publish_time"][1],
                    timezone=ZoneInfo(timezone)
                ),
                'id': f"cyprus_feedback_{guild_id}",
                'name': f"Cyprus Feedback - Guild {guild_id}",
                'replace_existing': True,
                'coalesce': True,
                'max_instances': 1,
                'misfire_grace_time': 300,
            })
            
            # Cyprus reminder job
            job_configs.append({
                'func': self._run_poll_reminder,
                'args': [guild_id],
                'trigger': CronTrigger(
                    hour=times["reminder_time"][0],
                    minute=times["reminder_time"][1],
                    timezone=ZoneInfo(timezone)
                ),
                'id': f"cyprus_reminder_{guild_id}",
                'name': f"Cyprus Reminder - Guild {guild_id}",
                'replace_existing': True,
                'coalesce': True,
                'max_instances': 1,
                'misfire_grace_time': 300,
            })
        else:
            # Standard mode: all jobs
            # Poll publish job
            job_configs.append({
                'func': self._run_poll_publish,
                'args': [guild_id],
                'trigger': CronTrigger(
                    hour=times["poll_publish_time"][0],
                    minute=times["poll_publish_time"][1],
                    timezone=ZoneInfo(timezone)
                ),
                'id': f"poll_publish_{guild_id}",
                'name': f"Poll Publish - Guild {guild_id}",
                'replace_existing': True,
                'coalesce': True,
                'max_instances': 1,
                'misfire_grace_time': 300,
            })
            
            # Reminder job
            job_configs.append({
                'func': self._run_poll_reminder,
                'args': [guild_id],
                'trigger': CronTrigger(
                    hour=times["reminder_time"][0],
                    minute=times["reminder_time"][1],
                    timezone=ZoneInfo(timezone)
                ),
                'id': f"poll_reminder_{guild_id}",
                'name': f"Poll Reminder - Guild {guild_id}",
                'replace_existing': True,
                'coalesce': True,
                'max_instances': 1,
                'misfire_grace_time': 300,
            })
            
            # Poll close job
            job_configs.append({
                'func': self._run_poll_close,
                'args': [guild_id],
                'trigger': CronTrigger(
                    hour=times["poll_close_time"][0],
                    minute=times["poll_close_time"][1],
                    timezone=ZoneInfo(timezone)
                ),
                'id': f"poll_close_{guild_id}",
                'name': f"Poll Close - Guild {guild_id}",
                'replace_existing': True,
                'coalesce': True,
                'max_instances': 1,
                'misfire_grace_time': 300,
            })
            
            # Feedback publish job
            job_configs.append({
                'func': self._run_feedback_publish,
                'args': [guild_id],
                'trigger': CronTrigger(
                    hour=times["feedback_publish_time"][0],
                    minute=times["feedback_publish_time"][1],
                    timezone=ZoneInfo(timezone)
                ),
                'id': f"feedback_publish_{guild_id}",
                'name': f"Feedback Publish - Guild {guild_id}",
                'replace_existing': True,
                'coalesce': True,
                'max_instances': 1,
                'misfire_grace_time': 300,
            })
        
        return job_configs
    
    async def _run_poll_publish(self, guild_id: int):
        """Execute poll publishing task."""
        try:
            logger.info(f"Running poll publish task for guild {guild_id}")
            
            guild = self.bot.get_guild(guild_id)
            if not guild:
                logger.error(f"Guild {guild_id} not found")
                return
            
            settings = await get_guild_settings(guild_id)
            if not settings:
                logger.error(f"No settings found for guild {guild_id}")
                return
            
            polls = await publish_attendance_poll(self.bot, guild, settings)
            
            if polls:
                logger.info(f"Published {len(polls)} poll(s) for guild {guild_id}")
            else:
                logger.info(f"No events to poll for guild {guild_id}")
            
        except Exception as e:
            logger.error(f"Error in poll publish task for guild {guild_id}: {e}")
    
    async def _run_poll_reminder(self, guild_id: int):
        """Execute poll reminder task."""
        try:
            logger.info(f"Running poll reminder task for guild {guild_id}")
            
            guild = self.bot.get_guild(guild_id)
            if not guild:
                logger.error(f"Guild {guild_id} not found")
                return
            
            settings = await get_guild_settings(guild_id)
            if not settings:
                logger.error(f"No settings found for guild {guild_id}")
                return
            
            stats = await send_reminders(self.bot, guild, settings)
            
            # Only log/report if there were actual polls to process
            if stats.get("total_polls", 0) > 0:
                logger.info(f"Reminder task completed for guild {guild_id}: {stats}")
                
                # Send summary to alerts channel if there were failures
                if stats.get("failed", 0) > 0:
                    await self._send_reminder_summary(guild, settings, stats)
            else:
                logger.debug(f"No active polls for reminders in guild {guild_id}")
            
        except Exception as e:
            logger.error(f"Error in poll reminder task for guild {guild_id}: {e}")
    
    async def _send_reminder_summary(self, guild: discord.Guild, settings: Dict, stats: Dict):
        """Send reminder summary to alerts channel if there were failures."""
        try:
            alerts_channel_id = settings.get("alerts_channel_id")
            if not alerts_channel_id:
                logger.debug(f"No alerts channel configured for guild {guild.id}")
                return
            
            alerts_channel = guild.get_channel(alerts_channel_id)
            if not alerts_channel:
                logger.warning(f"Alerts channel {alerts_channel_id} not found in guild {guild.id}")
                return
            
            # Only send summary if there were actual issues
            failed_count = stats.get("failed", 0)
            sent_count = stats.get("sent", 0)
            
            if failed_count > 0:
                embed = discord.Embed(
                    title="⚠️ Reminder Summary",
                    description="Poll reminder summary for today",
                    color=0xFFA500
                )
                
                embed.add_field(name="✅ Sent", value=str(sent_count), inline=True)
                embed.add_field(name="❌ Failed", value=str(failed_count), inline=True)
                
                if failed_count > 0:
                    embed.add_field(
                        name="📝 Note", 
                        value="Failed reminders likely due to disabled DMs", 
                        inline=False
                    )
                
                await alerts_channel.send(embed=embed)
                logger.info(f"Sent reminder summary to alerts channel in guild {guild.id}")
                
        except Exception as e:
            logger.error(f"Error sending reminder summary for guild {guild.id}: {e}")
    
    async def _run_poll_close(self, guild_id: int):
        """Execute poll closing task."""
        try:
            logger.info(f"Running poll close task for guild {guild_id}")
            
            guild = self.bot.get_guild(guild_id)
            if not guild:
                logger.error(f"Guild {guild_id} not found")
                return
            
            settings = await get_guild_settings(guild_id)
            if not settings:
                logger.error(f"No settings found for guild {guild_id}")
                return
            
            closed_count = await close_all_active_polls(self.bot, guild, settings)
            logger.info(f"Closed {closed_count} poll(s) for guild {guild_id}")
            
        except Exception as e:
            logger.error(f"Error in poll close task for guild {guild_id}: {e}")
    
    async def _run_feedback_publish(self, guild_id: int):
        """Execute feedback poll publishing task."""
        try:
            logger.info(f"Running feedback publish task for guild {guild_id}")
            
            guild = self.bot.get_guild(guild_id)
            if not guild:
                logger.error(f"Guild {guild_id} not found")
                return
            
            settings = await get_guild_settings(guild_id)
            if not settings:
                logger.error(f"No settings found for guild {guild_id}")
                return
            
            polls = await publish_feedback_polls(self.bot, guild, settings)
            
            if polls:
                logger.info(f"Published {len(polls)} feedback poll(s) for guild {guild_id}")
            else:
                logger.info(f"No events for feedback polls in guild {guild_id}")
            
        except Exception as e:
            logger.error(f"Error in feedback publish task for guild {guild_id}: {e}")
    
    async def _run_cyprus_feedback_publish(self, guild_id: int):
        """Execute Cyprus feedback poll publishing task."""
        try:
            logger.info(f"Running Cyprus feedback publish task for guild {guild_id}")
            
            guild = self.bot.get_guild(guild_id)
            if not guild:
                logger.error(f"Guild {guild_id} not found")
                return
            
            settings = await get_guild_settings(guild_id)
            if not settings:
                logger.error(f"No settings found for guild {guild_id}")
                return
            
            # Import Cyprus feedback function
            from services.polls.cyprus_feedback import publish_cyprus_feedback_polls
            
            polls = await publish_cyprus_feedback_polls(self.bot, guild, settings)
            
            if polls:
                logger.info(f"Published {len(polls)} Cyprus feedback poll(s) for guild {guild_id}")
            else:
                logger.info(f"No events for Cyprus feedback polls in guild {guild_id}")
            
        except Exception as e:
            logger.error(f"Error in Cyprus feedback publish task for guild {guild_id}: {e}")
    
    def get_guild_jobs(self, guild_id: int) -> List[Dict]:
        """Get information about jobs for a specific guild."""
        guild_jobs = []
        for job_id, job_info in self._job_registry.items():
            if job_info['guild_id'] == guild_id:
                job = self.scheduler.get_job(job_id)
                if job:
                    guild_jobs.append({
                        'id': job_id,
                        'name': job.name,
                        'next_run': job.next_run_time,
                        'job_type': job_info['job_type'],
                        'created_at': job_info['created_at']
                    })
        return guild_jobs
    
    def get_scheduler_stats(self) -> Dict[str, Any]:
        """Get scheduler statistics."""
        return {
            'total_jobs': len(self.scheduler.get_jobs()),
            'running': self.scheduler.running,
            'guild_count': len(set(info['guild_id'] for info in self._job_registry.values())),
            'job_types': list(set(info['job_type'] for info in self._job_registry.values()))
        }
