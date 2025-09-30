"""
Core vocabulary system components.

This package contains the fundamental building blocks of the vocabulary system:
- Configuration and database management
- Authentication and authorization
- Definition lookup and validation
- Deduplication services
"""

from .config import get_db_config, VocabularyConfig
from .auth import get_current_user
from .comprehensive_definition_lookup import ComprehensiveDefinitionLookup, enhance_candidate_with_definitions
from .english_word_validator import validate_english_word, validate_english_words
from .vocabulary_deduplicator import is_duplicate_term, filter_duplicate_candidates, get_existing_terms
from .custom_database_manager import CustomDatabaseManager

__all__ = [
    'get_db_config',
    'VocabularyConfig', 
    'get_current_user',
    'ComprehensiveDefinitionLookup',
    'enhance_candidate_with_definitions',
    'validate_english_word',
    'validate_english_words',
    'is_duplicate_term',
    'filter_duplicate_candidates',
    'get_existing_terms',
    'CustomDatabaseManager'
]