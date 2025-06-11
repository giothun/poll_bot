"""
CSV Service for CampPoll bot.
Handles creation and export of attendance data in CSV format.
"""

import pandas as pd
from typing import Optional
from io import StringIO, BytesIO
import logging

from models import PollMeta

logger = logging.getLogger(__name__)

async def create_attendance_csv(poll_meta: PollMeta, guild_members=None) -> Optional[BytesIO]:
    """
    Create a simple CSV file with attendance data matching spec format: user_id,username,choice
    
    Args:
        poll_meta: Poll metadata with voting information
        guild_members: Optional dict of user_id -> username for lookup
    
    Returns:
        BytesIO object containing CSV data, or None if error
    """
    try:
        # Prepare data for CSV in simple format: user_id,username,choice
        csv_data = []
        
        # Get all unique voters
        for option in poll_meta.options:
            for user_id in option.votes:
                username = "Unknown"
                if guild_members and user_id in guild_members:
                    username = guild_members[user_id]
                
                csv_data.append({
                    "user_id": str(user_id),
                    "username": username,
                    "choice": option.title
                })
        
        # Create DataFrame
        df = pd.DataFrame(csv_data)
        
        # Convert to CSV
        csv_buffer = StringIO()
        df.to_csv(csv_buffer, index=False, encoding='utf-8')
        
        # Convert to BytesIO for Discord file upload
        bytes_buffer = BytesIO()
        bytes_buffer.write(csv_buffer.getvalue().encode('utf-8'))
        bytes_buffer.seek(0)
        
        logger.info(f"Created simple CSV with {len(csv_data)} vote records for poll {poll_meta.id}")
        return bytes_buffer
        
    except Exception as e:
        logger.error(f"Error creating CSV for poll {poll_meta.id}: {e}")
        return None

async def create_summary_csv(polls: list[PollMeta], date_range: str = "") -> Optional[BytesIO]:
    """
    Create a summary CSV with multiple polls data.
    
    Args:
        polls: List of poll metadata
        date_range: Optional date range description
    
    Returns:
        BytesIO object containing CSV data, or None if error
    """
    try:
        csv_data = []
        
        # Add header information
        csv_data.append({
            "Date Range": date_range,
            "Total Polls": len(polls),
            "Generated At": pd.Timestamp.now().strftime("%Y-%m-%d %H:%M:%S UTC"),
            "Poll ID": "",
            "Poll Date": "",
            "Event Title": "",
            "Event Type": "",
            "Votes": "",
            "Percentage": "",
            "Status": "HEADER"
        })
        
        csv_data.append({key: "" for key in csv_data[0].keys()})
        
        # Add data for each poll
        for poll in sorted(polls, key=lambda x: x.poll_date):
            # Add poll header
            csv_data.append({
                "Date Range": "",
                "Total Polls": "",
                "Generated At": "",
                "Poll ID": poll.id,
                "Poll Date": poll.poll_date,
                "Event Title": f"POLL SUMMARY ({poll.total_votes} total votes)",
                "Event Type": "",
                "Votes": "",
                "Percentage": "",
                "Status": "CLOSED" if poll.is_closed else "ACTIVE"
            })
            
            # Add option details
            for option in sorted(poll.options, key=lambda x: x.vote_count, reverse=True):
                percentage = (option.vote_count / poll.total_votes * 100) if poll.total_votes > 0 else 0
                csv_data.append({
                    "Date Range": "",
                    "Total Polls": "",
                    "Generated At": "",
                    "Poll ID": "",
                    "Poll Date": "",
                    "Event Title": option.title,
                    "Event Type": option.event_type.value,
                    "Votes": option.vote_count,
                    "Percentage": f"{percentage:.1f}%",
                    "Status": ""
                })
            
            # Add separator
            csv_data.append({key: "" for key in csv_data[0].keys()})
        
        # Create DataFrame and export
        df = pd.DataFrame(csv_data)
        
        csv_buffer = StringIO()
        df.to_csv(csv_buffer, index=False, encoding='utf-8')
        
        bytes_buffer = BytesIO()
        bytes_buffer.write(csv_buffer.getvalue().encode('utf-8'))
        bytes_buffer.seek(0)
        
        logger.info(f"Created summary CSV for {len(polls)} polls")
        return bytes_buffer
        
    except Exception as e:
        logger.error(f"Error creating summary CSV: {e}")
        return None

def validate_csv_data(poll_meta: PollMeta) -> bool:
    """
    Validate poll metadata before CSV creation.
    
    Args:
        poll_meta: Poll metadata to validate
    
    Returns:
        True if valid, False otherwise
    """
    if not poll_meta.id:
        return False
    
    if not poll_meta.poll_date:
        return False
    
    if not poll_meta.options:
        return False
    
    # Check if options have valid data
    for option in poll_meta.options:
        if not option.event_id or not option.title:
            return False
    
    return True

async def export_user_votes(poll_meta: PollMeta) -> Optional[BytesIO]:
    """
    Export detailed user vote information.
    
    Args:
        poll_meta: Poll metadata
    
    Returns:
        BytesIO with user vote CSV data
    """
    try:
        if not validate_csv_data(poll_meta):
            logger.error(f"Invalid poll data for CSV export: {poll_meta.id}")
            return None
        
        user_data = []
        
        # Create a row for each user who voted
        for option in poll_meta.options:
            for user_id in option.votes:
                user_data.append({
                    "User ID": str(user_id),
                    "Poll ID": poll_meta.id,
                    "Poll Date": poll_meta.poll_date,
                    "Voted For Event": option.event_id,
                    "Event Title": option.title,
                    "Event Type": option.event_type.value,
                    "Vote Timestamp": poll_meta.published_at.strftime("%Y-%m-%d %H:%M:%S UTC")
                })
        
        if not user_data:
            # No votes, create empty structure
            user_data.append({
                "User ID": "No votes received",
                "Poll ID": poll_meta.id,
                "Poll Date": poll_meta.poll_date,
                "Voted For Event": "",
                "Event Title": "",
                "Event Type": "",
                "Vote Timestamp": ""
            })
        
        # Create DataFrame
        df = pd.DataFrame(user_data)
        
        # Sort by User ID
        if len(user_data) > 1 or user_data[0]["User ID"] != "No votes received":
            df = df.sort_values("User ID")
        
        # Export to CSV
        csv_buffer = StringIO()
        df.to_csv(csv_buffer, index=False, encoding='utf-8')
        
        bytes_buffer = BytesIO()
        bytes_buffer.write(csv_buffer.getvalue().encode('utf-8'))
        bytes_buffer.seek(0)
        
        return bytes_buffer
        
    except Exception as e:
        logger.error(f"Error exporting user votes for poll {poll_meta.id}: {e}")
        return None 