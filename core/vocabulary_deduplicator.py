#!/usr/bin/env python3
"""
Vocabulary Deduplication System
Centralized system to prevent duplicate terms from entering the candidate queue
"""

import mysql.connector
from typing import Set, List, Dict, Any, Optional, Tuple
from .config import get_db_config
import logging

logger = logging.getLogger(__name__)

class VocabularyDeduplicator:
    """Centralized deduplication system for vocabulary terms"""
    
    def __init__(self):
        self.db_config = get_db_config()
        self._existing_terms_cache = None
        self._cache_timestamp = None
        
    def get_all_existing_terms(self, force_refresh: bool = False) -> Set[str]:
        """
        Get all existing terms from both main vocabulary and candidates
        Uses caching for performance during batch operations
        """
        import time
        from datetime import datetime, timedelta
        
        # Use cache if it's fresh (less than 5 minutes old) and not forced refresh
        if (not force_refresh and 
            self._existing_terms_cache is not None and 
            self._cache_timestamp and 
            datetime.now() - self._cache_timestamp < timedelta(minutes=5)):
            return self._existing_terms_cache.copy()
        
        try:
            conn = mysql.connector.connect(**self.db_config)
            cursor = conn.cursor()
            
            existing_terms = set()
            
            # Get terms from main vocabulary table (defined words)
            try:
                cursor.execute("SELECT LOWER(TRIM(term)) FROM vocab.defined WHERE term IS NOT NULL AND term != ''")
                main_vocab = {row[0] for row in cursor.fetchall() if row[0]}
                existing_terms.update(main_vocab)
                logger.debug(f"Found {len(main_vocab)} terms in main vocabulary")
            except Exception as e:
                logger.warning(f"Could not access main vocabulary table 'defined': {e}")
            
            # Get terms from candidate words
            try:
                cursor.execute("SELECT LOWER(TRIM(term)) FROM vocab.candidate_words WHERE term IS NOT NULL AND term != ''")
                candidate_terms = {row[0] for row in cursor.fetchall() if row[0]}
                existing_terms.update(candidate_terms)
                logger.debug(f"Found {len(candidate_terms)} terms in candidate_words")
            except Exception as e:
                logger.warning(f"Could not access candidate_words table: {e}")
            
            # Try other possible vocabulary tables
            try:
                cursor.execute("SHOW TABLES LIKE '%vocab%'")
                vocab_tables = [row[0] for row in cursor.fetchall()]
                
                for table in vocab_tables:
                    if table not in ['defined', 'candidate_words']:
                        try:
                            # Try common column names for vocabulary terms
                            for col in ['word', 'term', 'vocabulary', 'lemma']:
                                try:
                                    cursor.execute(f"SELECT LOWER(TRIM({col})) FROM {table} WHERE {col} IS NOT NULL AND {col} != '' LIMIT 1000")
                                    table_terms = {row[0] for row in cursor.fetchall() if row[0]}
                                    if table_terms:
                                        existing_terms.update(table_terms)
                                        logger.debug(f"Found {len(table_terms)} terms in {table}.{col}")
                                        break
                                except:
                                    continue
                        except Exception as e:
                            logger.debug(f"Could not access table {table}: {e}")
                            
            except Exception as e:
                logger.debug(f"Could not check for additional vocabulary tables: {e}")
            
            # Cache the results
            self._existing_terms_cache = existing_terms.copy()
            self._cache_timestamp = datetime.now()
            
            logger.info(f"Loaded {len(existing_terms)} existing terms for deduplication")
            return existing_terms
            
        except Exception as e:
            logger.error(f"Database error getting existing terms: {e}")
            return self._existing_terms_cache or set()
        finally:
            if 'conn' in locals() and conn.is_connected():
                cursor.close()
                conn.close()
    
    def is_duplicate_term(self, term: str, existing_terms: Optional[Set[str]] = None) -> Tuple[bool, str]:
        """
        Check if a term is already present in vocabulary or candidates
        Returns (is_duplicate, reason)
        """
        if not term or not isinstance(term, str):
            return True, "invalid_term"
        
        term_lower = term.lower().strip()
        
        if not term_lower or len(term_lower) < 2:
            return True, "too_short"
        
        # Use provided existing_terms or get them fresh
        if existing_terms is None:
            existing_terms = self.get_all_existing_terms()
        
        if term_lower in existing_terms:
            return True, "already_exists"
        
        # Check for very similar terms (optional - can be disabled for performance)
        # This catches variations like "running" vs "runs" etc.
        similar_terms = self._find_similar_terms(term_lower, existing_terms)
        if similar_terms:
            return True, f"similar_exists:{similar_terms[0]}"
        
        return False, "unique"
    
    def _find_similar_terms(self, term: str, existing_terms: Set[str], max_check: int = 1000) -> List[str]:
        """
        Find very similar terms (same root, different inflection)
        Limited checking for performance
        """
        if len(term) < 4:  # Skip similarity check for very short terms
            return []
        
        similar = []
        checked = 0
        
        # Check for exact prefix/suffix matches that might indicate same root
        term_root = term[:6]  # First 6 characters as rough root
        
        for existing in existing_terms:
            if checked >= max_check:  # Limit to prevent performance issues
                break
                
            if len(existing) < 4:
                continue
                
            # Check if they share significant prefix (possible same root)
            if (existing.startswith(term_root) and 
                abs(len(existing) - len(term)) <= 3):
                similar.append(existing)
                checked += 1
            elif (term.startswith(existing[:6]) and 
                  abs(len(existing) - len(term)) <= 3):
                similar.append(existing)
                checked += 1
            
            checked += 1
        
        return similar[:3]  # Return max 3 similar terms
    
    def filter_duplicate_candidates(self, candidates: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], Dict[str, int]]:
        """
        Filter out duplicate candidates from a list
        Returns (filtered_candidates, stats)
        """
        if not candidates:
            return [], {"total": 0, "unique": 0, "duplicates": 0, "invalid": 0}
        
        # Get existing terms once for efficiency
        existing_terms = self.get_all_existing_terms()
        
        filtered_candidates = []
        stats = {
            "total": len(candidates),
            "unique": 0,
            "duplicates": 0,
            "invalid": 0,
            "duplicate_reasons": {}
        }
        
        seen_in_batch = set()  # Track terms within this batch
        
        for candidate in candidates:
            # Extract term from candidate (handle different formats)
            term = None
            if isinstance(candidate, dict):
                term = candidate.get('term') or candidate.get('word') or candidate.get('lemma')
            elif hasattr(candidate, 'term'):
                term = candidate.term
            else:
                term = str(candidate)
            
            if not term:
                stats["invalid"] += 1
                continue
            
            term_lower = term.lower().strip()
            
            # Check if we've already seen this term in this batch
            if term_lower in seen_in_batch:
                stats["duplicates"] += 1
                stats["duplicate_reasons"]["duplicate_in_batch"] = stats["duplicate_reasons"].get("duplicate_in_batch", 0) + 1
                continue
            
            # Check against existing vocabulary
            is_duplicate, reason = self.is_duplicate_term(term, existing_terms)
            
            if is_duplicate:
                stats["duplicates"] += 1
                stats["duplicate_reasons"][reason] = stats["duplicate_reasons"].get(reason, 0) + 1
                logger.debug(f"Filtered duplicate term '{term}': {reason}")
            else:
                filtered_candidates.append(candidate)
                seen_in_batch.add(term_lower)
                stats["unique"] += 1
        
        return filtered_candidates, stats
    
    def clear_cache(self):
        """Clear the existing terms cache (useful after database updates)"""
        self._existing_terms_cache = None
        self._cache_timestamp = None
        logger.debug("Cleared deduplication cache")

# Global instance for easy importing
vocabulary_deduplicator = VocabularyDeduplicator()

# Convenience functions
def is_duplicate_term(term: str) -> Tuple[bool, str]:
    """Convenience function to check if a term is duplicate"""
    return vocabulary_deduplicator.is_duplicate_term(term)

def filter_duplicate_candidates(candidates: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], Dict[str, int]]:
    """Convenience function to filter duplicate candidates"""
    return vocabulary_deduplicator.filter_duplicate_candidates(candidates)

def get_existing_terms() -> Set[str]:
    """Convenience function to get all existing terms"""
    return vocabulary_deduplicator.get_all_existing_terms()

# Test function
def test_deduplicator():
    """Test the deduplication system"""
    dedup = VocabularyDeduplicator()
    
    print("Testing Vocabulary Deduplication System")
    print("=" * 50)
    
    # Test getting existing terms
    existing = dedup.get_all_existing_terms()
    print(f"Found {len(existing)} existing terms")
    
    # Test some sample terms
    test_terms = [
        "wonderful",      # Likely exists
        "test_unique_123",  # Likely unique
        "",              # Invalid
        "a",             # Too short
        "magnificent",   # Might exist
    ]
    
    print("\nTesting individual terms:")
    for term in test_terms:
        is_dup, reason = dedup.is_duplicate_term(term)
        status = "DUPLICATE" if is_dup else "UNIQUE"
        print(f"  {term:15} -> {status:9} ({reason})")
    
    # Test batch filtering
    test_candidates = [
        {"term": "wonderful"},
        {"term": "unique_test_word_12345"},
        {"term": "another_unique_word_67890"},
        {"term": "wonderful"},  # Duplicate within batch
        {"term": ""},           # Invalid
    ]
    
    print("\nTesting batch filtering:")
    filtered, stats = dedup.filter_duplicate_candidates(test_candidates)
    
    print(f"  Original candidates: {stats['total']}")
    print(f"  Unique candidates: {stats['unique']}")
    print(f"  Duplicates filtered: {stats['duplicates']}")
    print(f"  Invalid filtered: {stats['invalid']}")
    
    if stats.get('duplicate_reasons'):
        print("  Duplicate reasons:")
        for reason, count in stats['duplicate_reasons'].items():
            print(f"    {reason}: {count}")

if __name__ == "__main__":
    test_deduplicator()