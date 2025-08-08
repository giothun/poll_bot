"""
Tests for validation utilities.
"""

import pytest
from datetime import date

from utils.validation import (
    ValidationResult, validate_date_format, validate_time_format,
    validate_timezone, validate_event_title, validate_date_title_format,
    validate_poll_times_format, validate_role_id, sanitize_filename,
    validate_message_content, is_safe_user_input
)


class TestValidationResult:
    """Test ValidationResult class."""
    
    def test_valid_result(self):
        result = ValidationResult(True, cleaned_value="test")
        assert result.is_valid
        assert bool(result) is True
        assert result.cleaned_value == "test"
        assert str(result) == "Valid"
    
    def test_invalid_result(self):
        result = ValidationResult(False, "Error message")
        assert not result.is_valid
        assert bool(result) is False
        assert result.error_message == "Error message"
        assert str(result) == "Invalid: Error message"


class TestDateValidation:
    """Test date format validation."""
    
    def test_valid_dates(self):
        valid_dates = ["2024-12-25", "2025-01-01", "2023-02-28", "2024-02-29"]  # Leap year
        
        for date_str in valid_dates:
            result = validate_date_format(date_str)
            assert result.is_valid, f"Date {date_str} should be valid"
            assert isinstance(result.cleaned_value, date)
    
    def test_invalid_date_formats(self):
        invalid_dates = [
            "25-12-2024",  # Wrong format
            "2024/12/25",  # Wrong separator
            "2024-13-01",  # Invalid month
            "2024-12-32",  # Invalid day
            "2023-02-29",  # Not a leap year
            "",            # Empty
            "not-a-date",  # Completely invalid
        ]
        
        for date_str in invalid_dates:
            result = validate_date_format(date_str)
            assert not result.is_valid, f"Date {date_str} should be invalid"
    
    def test_edge_cases(self):
        result = validate_date_format(None)
        assert not result.is_valid
        
        result = validate_date_format("   2024-12-25   ")  # With whitespace
        assert result.is_valid
        assert result.cleaned_value == date(2024, 12, 25)


class TestTimeValidation:
    """Test time format validation."""
    
    def test_valid_times(self):
        valid_times = ["00:00", "12:30", "23:59", "9:15"]
        
        for time_str in valid_times:
            result = validate_time_format(time_str)
            assert result.is_valid, f"Time {time_str} should be valid"
            assert isinstance(result.cleaned_value, tuple)
            assert len(result.cleaned_value) == 2
    
    def test_invalid_times(self):
        invalid_times = [
            "24:00",     # Invalid hour
            "12:60",     # Invalid minute
            "25:30",     # Invalid hour
            "12-30",     # Wrong separator
            "12:30:45",  # Seconds included
            "",          # Empty
            "noon",      # Text
        ]
        
        for time_str in invalid_times:
            result = validate_time_format(time_str)
            assert not result.is_valid, f"Time {time_str} should be invalid"


class TestTimezoneValidation:
    """Test timezone validation."""
    
    def test_valid_timezones(self):
        valid_timezones = [
            "Europe/Helsinki",
            "America/New_York", 
            "Asia/Tokyo",
            "UTC"
        ]
        
        for tz in valid_timezones:
            result = validate_timezone(tz)
            assert result.is_valid, f"Timezone {tz} should be valid"
    
    def test_invalid_timezones(self):
        invalid_timezones = [
            "Invalid/Timezone",
            "",
            "Europe/NonExistent"
        ]
        
        for tz in invalid_timezones:
            result = validate_timezone(tz)
            assert not result.is_valid, f"Timezone {tz} should be invalid"


class TestEventTitleValidation:
    """Test event title validation."""
    
    def test_valid_titles(self):
        valid_titles = [
            "Search Algorithms",
            "Introduction to Machine Learning",
            "Contest #1",
            "Workshop: Docker & Kubernetes"
        ]
        
        for title in valid_titles:
            result = validate_event_title(title)
            assert result.is_valid, f"Title '{title}' should be valid"
    
    def test_invalid_titles(self):
        invalid_titles = [
            "",           # Empty
            "   ",        # Only whitespace
            "a" * 101,    # Too long (default max 100)
            "Title\nwith\nnewlines",  # Contains newlines
        ]
        
        for title in invalid_titles:
            result = validate_event_title(title)
            assert not result.is_valid, f"Title '{title}' should be invalid"
    
    def test_title_length_limit(self):
        result = validate_event_title("a" * 50, max_length=50)
        assert result.is_valid
        
        result = validate_event_title("a" * 51, max_length=50)
        assert not result.is_valid


class TestDateTitleValidation:
    """Test date;title format validation."""
    
    def test_valid_date_title(self):
        valid_inputs = [
            "2024-12-25;Christmas Workshop",
            "2025-01-01;New Year Contest",
            "2024-06-15;Advanced Algorithms"
        ]
        
        for input_str in valid_inputs:
            result = validate_date_title_format(input_str)
            assert result.is_valid, f"Input '{input_str}' should be valid"
            date_obj, title = result.cleaned_value
            assert isinstance(date_obj, date)
            assert isinstance(title, str)
    
    def test_invalid_date_title(self):
        invalid_inputs = [
            "2024-12-25",           # Missing semicolon
            "2024-12-25;",          # Empty title
            "invalid-date;Title",   # Invalid date
            "2024-12-25;  ",        # Whitespace-only title
            "",                     # Empty string
        ]
        
        for input_str in invalid_inputs:
            result = validate_date_title_format(input_str)
            assert not result.is_valid, f"Input '{input_str}' should be invalid"


class TestPollTimesValidation:
    """Test poll times format validation."""
    
    def test_valid_poll_times(self):
        valid_inputs = [
            "14:30;09:00;19:00",
            "15:00;10:30;20:15",
            "9:00;8:30;18:45"
        ]
        
        for input_str in valid_inputs:
            result = validate_poll_times_format(input_str)
            assert result.is_valid, f"Input '{input_str}' should be valid"
            publish, close, reminder = result.cleaned_value
            assert all(len(time_tuple) == 2 for time_tuple in [publish, close, reminder])
    
    def test_invalid_poll_times(self):
        invalid_inputs = [
            "14:30;09:00",          # Only 2 times
            "14:30;09:00;19:00;22:00",  # Too many times
            "25:30;09:00;19:00",    # Invalid time
            "",                     # Empty
            "14:30,09:00,19:00",    # Wrong separator
        ]
        
        for input_str in invalid_inputs:
            result = validate_poll_times_format(input_str)
            assert not result.is_valid, f"Input '{input_str}' should be invalid"


class TestRoleIdValidation:
    """Test Discord role ID validation."""
    
    def test_valid_role_ids(self):
        valid_ids = [
            "123456789012345678",  # 18 digits
            "987654321098765432",  # 18 digits
            "1234567890123456789", # 19 digits
        ]
        
        for role_id in valid_ids:
            result = validate_role_id(role_id)
            assert result.is_valid, f"Role ID '{role_id}' should be valid"
            assert isinstance(result.cleaned_value, int)
    
    def test_invalid_role_ids(self):
        invalid_ids = [
            "123",          # Too short
            "0",            # Zero
            "-123456789012345678",  # Negative
            "not_a_number", # Non-numeric
            "",             # Empty
        ]
        
        for role_id in invalid_ids:
            result = validate_role_id(role_id)
            assert not result.is_valid, f"Role ID '{role_id}' should be invalid"


class TestFilenameValidation:
    """Test filename sanitization."""
    
    def test_sanitize_filename(self):
        test_cases = [
            ("normal_file.txt", "normal_file.txt"),
            ("file with spaces.txt", "file with spaces.txt"),
            ("file<>with|bad*chars.txt", "file_with_bad_chars.txt"),
            ("file\\with/slashes.txt", "file_with_slashes.txt"),
            ("file___multiple___underscores.txt", "file_multiple_underscores.txt"),
            ("", "untitled"),
            ("a" * 200 + ".txt", "a" * 96 + ".txt"),  # Truncated to 100 chars
        ]
        
        for input_name, expected in test_cases:
            result = sanitize_filename(input_name)
            assert result == expected, f"Expected '{expected}', got '{result}'"


class TestMessageValidation:
    """Test message content validation."""
    
    def test_valid_messages(self):
        valid_messages = [
            "Hello, world!",
            "This is a normal message with some special chars: @#$%",
            "A" * 1500,  # Long but under limit
        ]
        
        for msg in valid_messages:
            result = validate_message_content(msg)
            assert result.is_valid, f"Message should be valid"
    
    def test_invalid_messages(self):
        result = validate_message_content("")
        assert not result.is_valid
        
        result = validate_message_content("A" * 2001)  # Over Discord limit
        assert not result.is_valid


class TestUserInputSafety:
    """Test user input safety checks."""
    
    def test_safe_inputs(self):
        safe_inputs = [
            "Normal text",
            "Text with numbers 123",
            "Some special chars: !@#$%^&*()",
        ]
        
        for input_str in safe_inputs:
            assert is_safe_user_input(input_str), f"Input should be safe: '{input_str}'"
    
    def test_unsafe_inputs(self):
        unsafe_inputs = [
            "DROP TABLE users",
            "UNION SELECT * FROM passwords",
            "<script>alert('xss')</script>",
            "INSERT INTO admin VALUES",
        ]
        
        for input_str in unsafe_inputs:
            assert not is_safe_user_input(input_str), f"Input should be unsafe: '{input_str}'"
    
    def test_newline_handling(self):
        text_with_newlines = "Line 1\nLine 2\nLine 3"
        
        assert not is_safe_user_input(text_with_newlines, allow_newlines=False)
        assert is_safe_user_input(text_with_newlines, allow_newlines=True)
