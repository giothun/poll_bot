"""
Tests for scheduler service.
"""

import pytest
from unittest.mock import Mock, AsyncMock, patch
from datetime import datetime
from zoneinfo import ZoneInfo

from services.scheduler_service import SchedulerService
from models import GuildSettings


class TestSchedulerService:
    """Test SchedulerService functionality."""
    
    @pytest.fixture
    def mock_bot(self):
        """Create a mock bot for testing."""
        bot = Mock()
        bot.get_guild.return_value = Mock()
        return bot
    
    @pytest.fixture
    def scheduler_service(self, mock_bot):
        """Create a SchedulerService instance for testing."""
        return SchedulerService(mock_bot)
    
    def test_scheduler_initialization(self, mock_bot):
        """Test that scheduler service initializes correctly."""
        service = SchedulerService(mock_bot)
        
        assert service.bot == mock_bot
        assert service.scheduler is not None
        assert service._job_registry == {}
    
    def test_start_scheduler(self, scheduler_service):
        """Test starting the scheduler."""
        # Replace scheduler with a mock
        mock_scheduler = Mock()
        mock_scheduler.running = False
        scheduler_service.scheduler = mock_scheduler
        
        scheduler_service.start()
        
        mock_scheduler.start.assert_called_once()
    
    def test_start_scheduler_already_running(self, scheduler_service):
        """Test starting scheduler when already running."""
        # Replace scheduler with a mock  
        mock_scheduler = Mock()
        mock_scheduler.running = True
        scheduler_service.scheduler = mock_scheduler
        
        scheduler_service.start()
        
        mock_scheduler.start.assert_not_called()
    
    def test_shutdown_scheduler(self, scheduler_service):
        """Test shutting down the scheduler."""
        # Replace scheduler with a mock
        mock_scheduler = Mock()
        mock_scheduler.running = True
        scheduler_service.scheduler = mock_scheduler
        
        scheduler_service.shutdown()
        
        mock_scheduler.shutdown.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_remove_guild_jobs(self, scheduler_service):
        """Test removing all jobs for a guild."""
        guild_id = 123456
        
        # Mock scheduler with some existing jobs
        mock_job = Mock()
        mock_job.id = f"poll_publish_{guild_id}"
        scheduler_service.scheduler.get_job = Mock(return_value=mock_job)
        scheduler_service.scheduler.remove_job = Mock()
        
        # Add job to registry
        scheduler_service._job_registry[f"poll_publish_{guild_id}"] = {
            'guild_id': guild_id,
            'job_type': 'Poll Publish',
            'created_at': datetime.now()
        }
        
        await scheduler_service._remove_guild_jobs(guild_id)
        
        # Should remove all job types for the guild
        expected_calls = 4  # publish, reminder, close, feedback
        assert scheduler_service.scheduler.remove_job.call_count == expected_calls
    
    def test_build_job_configs(self, scheduler_service):
        """Test building job configurations for a guild."""
        guild_id = 123456
        settings = {
            "poll_publish_time": "14:30",
            "reminder_time": "19:00", 
            "poll_close_time": "09:00",
            "feedback_publish_time": "22:00"
        }
        timezone = "Europe/Helsinki"
        
        configs = scheduler_service._build_job_configs(guild_id, settings, timezone)
        
        assert len(configs) == 4
        
        # Check that all job types are present
        job_ids = [config['id'] for config in configs]
        assert f"poll_publish_{guild_id}" in job_ids
        assert f"poll_reminder_{guild_id}" in job_ids
        assert f"poll_close_{guild_id}" in job_ids
        assert f"feedback_publish_{guild_id}" in job_ids
        
        # Check that triggers are properly configured
        for config in configs:
            assert 'trigger' in config
            assert 'func' in config
            assert config['args'] == [guild_id]
    
    def test_build_job_configs_invalid_times(self, scheduler_service):
        """Test building job configs with invalid time formats."""
        guild_id = 123456
        settings = {
            "poll_publish_time": "25:70",  # Invalid time
            "reminder_time": "19:00",
            "poll_close_time": "09:00", 
            "feedback_publish_time": "22:00"
        }
        timezone = "Europe/Helsinki"
        
        # Should not raise exception, should use defaults
        configs = scheduler_service._build_job_configs(guild_id, settings, timezone)
        assert len(configs) == 4
    
    @pytest.mark.asyncio
    @patch('services.scheduler_service.get_guild_settings')
    async def test_setup_guild_jobs_new_guild(self, mock_get_settings, scheduler_service):
        """Test setting up jobs for a new guild."""
        guild_id = 123456
        mock_get_settings.return_value = None
        
        # Mock scheduler methods
        scheduler_service.scheduler.add_job = Mock()
        scheduler_service.scheduler.get_job = Mock(return_value=None)
        
        await scheduler_service.setup_guild_jobs(guild_id)
        
        # Should create 4 jobs (publish, reminder, close, feedback)
        assert scheduler_service.scheduler.add_job.call_count == 4
        
        # Should add entries to job registry
        assert len(scheduler_service._job_registry) == 4
    
    @pytest.mark.asyncio
    @patch('services.scheduler_service.get_guild_settings')
    async def test_setup_guild_jobs_existing_guild(self, mock_get_settings, scheduler_service):
        """Test setting up jobs for an existing guild."""
        guild_id = 123456
        settings = GuildSettings(
            guild_id=guild_id,
            timezone="America/New_York",
            poll_publish_time="15:00"
        ).to_dict()
        
        mock_get_settings.return_value = settings
        
        # Mock scheduler methods
        scheduler_service.scheduler.add_job = Mock()
        scheduler_service.scheduler.get_job = Mock(return_value=None)
        
        await scheduler_service.setup_guild_jobs(guild_id)
        
        # Should use provided settings
        mock_get_settings.assert_called_once_with(guild_id)
        assert scheduler_service.scheduler.add_job.call_count == 4
    
    @pytest.mark.asyncio
    @patch('services.scheduler_service.get_guild_settings')
    async def test_setup_guild_jobs_invalid_timezone(self, mock_get_settings, scheduler_service):
        """Test handling invalid timezone in guild settings."""
        guild_id = 123456
        settings = {
            "guild_id": guild_id,
            "timezone": "Invalid/Timezone"
        }
        
        mock_get_settings.return_value = settings
        scheduler_service.scheduler.add_job = Mock()
        
        await scheduler_service.setup_guild_jobs(guild_id)
        
        # Should not add any jobs due to invalid timezone
        scheduler_service.scheduler.add_job.assert_not_called()
    
    def test_get_guild_jobs(self, scheduler_service):
        """Test getting job information for a guild."""
        guild_id = 123456
        
        # Add some jobs to registry
        scheduler_service._job_registry = {
            f"poll_publish_{guild_id}": {
                'guild_id': guild_id,
                'job_type': 'Poll Publish',
                'created_at': datetime.now()
            },
            f"poll_reminder_{guild_id}": {
                'guild_id': guild_id,
                'job_type': 'Poll Reminder',
                'created_at': datetime.now()
            },
            "other_guild_job": {
                'guild_id': 999999,
                'job_type': 'Other',
                'created_at': datetime.now()
            }
        }
        
        # Mock scheduler jobs
        mock_job1 = Mock()
        mock_job1.name = "Poll Publish - Guild 123456"
        mock_job1.next_run_time = datetime.now()
        
        mock_job2 = Mock()
        mock_job2.name = "Poll Reminder - Guild 123456"
        mock_job2.next_run_time = datetime.now()
        
        scheduler_service.scheduler.get_job = Mock(side_effect=[mock_job1, mock_job2, None])
        
        result = scheduler_service.get_guild_jobs(guild_id)
        
        assert len(result) == 2
        assert result[0]['job_type'] == 'Poll Publish'
        assert result[1]['job_type'] == 'Poll Reminder'
    
    def test_get_scheduler_stats(self, scheduler_service):
        """Test getting scheduler statistics."""
        # Add some jobs to registry
        scheduler_service._job_registry = {
            "job1": {'guild_id': 123, 'job_type': 'Poll Publish', 'created_at': datetime.now()},
            "job2": {'guild_id': 123, 'job_type': 'Poll Reminder', 'created_at': datetime.now()},
            "job3": {'guild_id': 456, 'job_type': 'Poll Publish', 'created_at': datetime.now()},
        }
        
        # Mock scheduler
        mock_scheduler = Mock()
        mock_scheduler.get_jobs.return_value = [Mock(), Mock(), Mock()]
        mock_scheduler.running = True
        scheduler_service.scheduler = mock_scheduler
        
        stats = scheduler_service.get_scheduler_stats()
        
        assert stats['total_jobs'] == 3
        assert stats['running'] is True
        assert stats['guild_count'] == 2  # Two unique guild IDs
        assert 'Poll Publish' in stats['job_types']
        assert 'Poll Reminder' in stats['job_types']
    
    @pytest.mark.asyncio
    @patch('services.scheduler_service.publish_attendance_poll')
    @patch('services.scheduler_service.get_guild_settings')
    async def test_run_poll_publish(self, mock_get_settings, mock_publish_poll, scheduler_service):
        """Test running poll publish task."""
        guild_id = 123456
        mock_guild = Mock()
        mock_settings = {"timezone": "Europe/Helsinki"}
        
        scheduler_service.bot.get_guild.return_value = mock_guild
        mock_get_settings.return_value = mock_settings
        mock_publish_poll.return_value = [Mock(), Mock()]  # 2 polls created
        
        await scheduler_service._run_poll_publish(guild_id)
        
        mock_publish_poll.assert_called_once_with(scheduler_service.bot, mock_guild, mock_settings)
    
    @pytest.mark.asyncio
    async def test_run_poll_publish_guild_not_found(self, scheduler_service):
        """Test poll publish task when guild is not found."""
        guild_id = 123456
        scheduler_service.bot.get_guild.return_value = None
        
        # Should not raise exception
        await scheduler_service._run_poll_publish(guild_id)
    
    @pytest.mark.asyncio
    @patch('services.scheduler_service.send_reminders')
    @patch('services.scheduler_service.get_guild_settings')
    async def test_run_poll_reminder(self, mock_get_settings, mock_send_reminders, scheduler_service):
        """Test running poll reminder task."""
        guild_id = 123456
        mock_guild = Mock()
        mock_settings = {"timezone": "Europe/Helsinki"}
        
        scheduler_service.bot.get_guild.return_value = mock_guild
        mock_get_settings.return_value = mock_settings
        mock_send_reminders.return_value = {"sent": 5, "failed": 1, "total_polls": 2}
        
        await scheduler_service._run_poll_reminder(guild_id)
        
        mock_send_reminders.assert_called_once_with(scheduler_service.bot, mock_guild, mock_settings)
    
    @pytest.mark.asyncio
    @patch('services.scheduler_service.send_reminders')
    @patch('services.scheduler_service.get_guild_settings')
    async def test_run_poll_reminder_no_polls(self, mock_get_settings, mock_send_reminders, scheduler_service):
        """Test running poll reminder task when no active polls exist."""
        guild_id = 123456
        mock_guild = Mock()
        mock_settings = {"timezone": "Europe/Helsinki"}
        
        scheduler_service.bot.get_guild.return_value = mock_guild
        mock_get_settings.return_value = mock_settings
        mock_send_reminders.return_value = {"sent": 0, "failed": 0, "total_polls": 0}
        
        await scheduler_service._run_poll_reminder(guild_id)
        
        mock_send_reminders.assert_called_once_with(scheduler_service.bot, mock_guild, mock_settings)
    
    @pytest.mark.asyncio
    @patch('services.scheduler_service.close_all_active_polls')
    @patch('services.scheduler_service.get_guild_settings')
    async def test_run_poll_close(self, mock_get_settings, mock_close_polls, scheduler_service):
        """Test running poll close task."""
        guild_id = 123456
        mock_guild = Mock()
        mock_settings = {"timezone": "Europe/Helsinki"}
        
        scheduler_service.bot.get_guild.return_value = mock_guild
        mock_get_settings.return_value = mock_settings
        mock_close_polls.return_value = 3  # 3 polls closed
        
        await scheduler_service._run_poll_close(guild_id)
        
        mock_close_polls.assert_called_once_with(scheduler_service.bot, mock_guild, mock_settings)
    
    @pytest.mark.asyncio
    @patch('services.scheduler_service.publish_feedback_polls')
    @patch('services.scheduler_service.get_guild_settings')
    async def test_run_feedback_publish(self, mock_get_settings, mock_publish_feedback, scheduler_service):
        """Test running feedback publish task."""
        guild_id = 123456
        mock_guild = Mock()
        mock_settings = {"timezone": "Europe/Helsinki"}
        
        scheduler_service.bot.get_guild.return_value = mock_guild
        mock_get_settings.return_value = mock_settings
        mock_publish_feedback.return_value = [Mock()]  # 1 feedback poll created
        
        await scheduler_service._run_feedback_publish(guild_id)
        
        mock_publish_feedback.assert_called_once_with(scheduler_service.bot, mock_guild, mock_settings)
