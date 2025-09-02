"""Tests for validation utilities."""

import pytest
from pronunciation_similarity.utils.validation import (
    validate_database_config,
    validate_word_input,
    validate_similarity_threshold,
    validate_batch_size,
    validate_word_id,
    ValidationError
)


class TestDatabaseValidation:
    """Test database configuration validation"""

    def test_valid_config(self):
        """Test valid database configuration"""
        config = {
            'host': 'localhost',
            'port': 3306,
            'database': 'test_db',
            'user': 'testuser',
            'password': 'password123'
        }
        
        result = validate_database_config(config)
        assert result == config

    def test_valid_ip_host(self):
        """Test valid IP address host"""
        config = {
            'host': '192.168.1.1',
            'port': 3306,
            'database': 'test_db',
            'user': 'testuser',
            'password': 'password123'
        }
        
        result = validate_database_config(config)
        assert result['host'] == '192.168.1.1'

    def test_missing_required_field(self):
        """Test missing required field"""
        config = {
            'host': 'localhost',
            'port': 3306,
            # Missing 'database'
            'user': 'testuser',
            'password': 'password123'
        }
        
        with pytest.raises(ValidationError, match="Missing required database fields"):
            validate_database_config(config)

    def test_invalid_port(self):
        """Test invalid port number"""
        config = {
            'host': 'localhost',
            'port': 70000,  # Invalid port
            'database': 'test_db',
            'user': 'testuser',
            'password': 'password123'
        }
        
        with pytest.raises(ValidationError, match="Database port must be between"):
            validate_database_config(config)

    def test_empty_host(self):
        """Test empty host"""
        config = {
            'host': '',
            'port': 3306,
            'database': 'test_db',
            'user': 'testuser',
            'password': 'password123'
        }
        
        with pytest.raises(ValidationError, match="Database host cannot be empty"):
            validate_database_config(config)

    def test_invalid_host_format(self):
        """Test invalid host format"""
        config = {
            'host': 'invalid..host',
            'port': 3306,
            'database': 'test_db',
            'user': 'testuser',
            'password': 'password123'
        }
        
        with pytest.raises(ValidationError, match="Invalid database host format"):
            validate_database_config(config)


class TestWordValidation:
    """Test word input validation"""

    def test_valid_word(self):
        """Test valid word input"""
        result = validate_word_input("hello")
        assert result == "hello"

    def test_valid_word_with_spaces(self):
        """Test valid compound word with spaces"""
        result = validate_word_input(" hello world ")
        assert result == "hello world"

    def test_valid_word_with_hyphen(self):
        """Test valid hyphenated word"""
        result = validate_word_input("well-being")
        assert result == "well-being"

    def test_valid_word_with_apostrophe(self):
        """Test valid word with apostrophe"""
        result = validate_word_input("don't")
        assert result == "don't"

    def test_empty_word_not_allowed(self):
        """Test empty word not allowed by default"""
        with pytest.raises(ValidationError, match="Word cannot be empty"):
            validate_word_input("")

    def test_empty_word_allowed(self):
        """Test empty word allowed when specified"""
        result = validate_word_input("", allow_empty=True)
        assert result == ""

    def test_word_too_long(self):
        """Test word that's too long"""
        long_word = "a" * 101
        with pytest.raises(ValidationError, match="Word too long"):
            validate_word_input(long_word)

    def test_invalid_word_format(self):
        """Test word with invalid characters"""
        with pytest.raises(ValidationError, match="Invalid word format"):
            validate_word_input("hello123")

    def test_non_string_input(self):
        """Test non-string input"""
        with pytest.raises(ValidationError, match="Word must be a string"):
            validate_word_input(123)


class TestThresholdValidation:
    """Test similarity threshold validation"""

    def test_valid_threshold(self):
        """Test valid threshold values"""
        assert validate_similarity_threshold(0.5) == 0.5
        assert validate_similarity_threshold(0.0) == 0.0
        assert validate_similarity_threshold(1.0) == 1.0

    def test_threshold_out_of_range(self):
        """Test threshold outside valid range"""
        with pytest.raises(ValidationError, match="must be between 0.0 and 1.0"):
            validate_similarity_threshold(1.5)
        
        with pytest.raises(ValidationError, match="must be between 0.0 and 1.0"):
            validate_similarity_threshold(-0.1)

    def test_threshold_non_numeric(self):
        """Test non-numeric threshold"""
        with pytest.raises(ValidationError, match="must be a number"):
            validate_similarity_threshold("not_a_number")


class TestBatchSizeValidation:
    """Test batch size validation"""

    def test_valid_batch_size(self):
        """Test valid batch size"""
        result = validate_batch_size(1000)
        assert result == 1000

    def test_batch_size_too_small(self):
        """Test batch size too small"""
        with pytest.raises(ValidationError, match="must be between"):
            validate_batch_size(0, min_size=1)

    def test_batch_size_too_large(self):
        """Test batch size too large"""
        with pytest.raises(ValidationError, match="must be between"):
            validate_batch_size(20000, max_size=10000)

    def test_batch_size_non_integer(self):
        """Test non-integer batch size"""
        with pytest.raises(ValidationError, match="must be an integer"):
            validate_batch_size("1000")


class TestWordIdValidation:
    """Test word ID validation"""

    def test_valid_word_id(self):
        """Test valid word ID"""
        result = validate_word_id(12345)
        assert result == 12345

    def test_word_id_string_conversion(self):
        """Test word ID string conversion"""
        result = validate_word_id("12345")
        assert result == 12345

    def test_zero_word_id(self):
        """Test zero word ID (invalid)"""
        with pytest.raises(ValidationError, match="must be positive"):
            validate_word_id(0)

    def test_negative_word_id(self):
        """Test negative word ID"""
        with pytest.raises(ValidationError, match="must be positive"):
            validate_word_id(-1)

    def test_non_integer_word_id(self):
        """Test non-integer word ID"""
        with pytest.raises(ValidationError, match="must be an integer"):
            validate_word_id("not_a_number")