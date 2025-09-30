#!/usr/bin/env python3
"""
Circular Definition Detector and Corrector
Identifies definitions that contain the word being defined or its root variations
"""

import mysql.connector
import re
import logging
from typing import List, Tuple, Optional, Dict
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core.config import get_db_config

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class CircularDefinitionDetector:
    def __init__(self):
        self.config = get_db_config()
        
        # Common suffixes to check for root word variations
        self.common_suffixes = [
            'ly', 'ing', 'ed', 'er', 'est', 'ion', 'tion', 'ness', 'ment',
            'ful', 'less', 'able', 'ible', 'ic', 'al', 'ous', 'ive', 'ary',
            'ory', 'y', 's', 'es', 'ize', 'ise', 'ate', 'ify'
        ]
    
    def simple_stem(self, word: str) -> str:
        """Simple stemming algorithm to find root words"""
        word = word.lower().strip()
        
        # Handle common suffix patterns
        suffix_rules = [
            ('ies', 'y'),
            ('ied', 'y'),
            ('ying', 'y'),
            ('ing', ''),
            ('ly', ''),
            ('ed', ''),
            ('ies', 'y'),
            ('ies', 'ie'),
            ('ied', 'ie'),
            ('ies', 'i'),
            ('s', ''),
        ]
        
        for suffix, replacement in suffix_rules:
            if word.endswith(suffix) and len(word) > len(suffix) + 2:
                return word[:-len(suffix)] + replacement
                
        return word
    
    def get_connection(self):
        return mysql.connector.connect(**self.config)
    
    def setup_database_columns(self):
        """Add new columns to the defined table if they don't exist"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        try:
            # Check if columns exist
            cursor.execute("DESCRIBE defined")
            columns = [row[0] for row in cursor.fetchall()]
            
            if 'has_circular_definition' not in columns:
                cursor.execute("""
                    ALTER TABLE defined 
                    ADD COLUMN has_circular_definition BOOLEAN DEFAULT FALSE
                """)
                logger.info("Added has_circular_definition column")
            
            if 'corrected_definition' not in columns:
                cursor.execute("""
                    ALTER TABLE defined 
                    ADD COLUMN corrected_definition TEXT NULL
                """)
                logger.info("Added corrected_definition column")
            
            conn.commit()
            
        except Exception as e:
            logger.error(f"Error setting up database columns: {e}")
            conn.rollback()
        finally:
            cursor.close()
            conn.close()
    
    def get_word_variations(self, word: str) -> List[str]:
        """Generate possible root variations of a word"""
        variations = [word.lower()]
        
        # Add stemmed version
        stemmed = self.simple_stem(word.lower())
        variations.append(stemmed)
        
        # Remove common suffixes to find potential roots
        word_lower = word.lower()
        for suffix in sorted(self.common_suffixes, key=len, reverse=True):
            if word_lower.endswith(suffix) and len(word_lower) > len(suffix) + 2:
                root = word_lower[:-len(suffix)]
                variations.append(root)
                
                # Also try with common suffix replacements
                if suffix in ['ly']:
                    variations.extend([root + 'al', root + 'ic'])
                elif suffix in ['ic']:
                    variations.extend([root + 'y', root + 'ical'])
                elif suffix in ['al']:
                    variations.extend([root + 'ic', root + 'ly'])
        
        # Remove duplicates and very short variations
        variations = list(set([v for v in variations if len(v) >= 3]))
        return variations
    
    def contains_circular_reference(self, word: str, definition: str) -> Tuple[bool, List[str]]:
        """Check if definition contains the word or its variations"""
        if not definition or not word:
            return False, []
        
        # Get all possible variations of the word
        variations = self.get_word_variations(word)
        
        # Clean definition text (remove punctuation for matching)
        clean_definition = re.sub(r'[^\w\s]', ' ', definition.lower())
        definition_words = clean_definition.split()
        
        found_matches = []
        
        for variation in variations:
            # Check for exact word matches (whole words only)
            pattern = r'\b' + re.escape(variation) + r'\b'
            if re.search(pattern, clean_definition):
                found_matches.append(variation)
        
        return len(found_matches) > 0, found_matches
    
    def generate_corrected_definition(self, word: str, original_definition: str, 
                                    circular_matches: List[str]) -> str:
        """Generate a corrected definition by removing circular references"""
        corrected = original_definition
        
        # Simple correction strategies
        for match in circular_matches:
            # Pattern 1: "Of, relating to, or of the nature of [word]"
            pattern1 = re.compile(r'of,?\s+relating\s+to,?\s+or\s+of\s+the\s+nature\s+of\s+\w*' + 
                                re.escape(match) + r'\w*,?\s*', re.IGNORECASE)
            corrected = pattern1.sub('', corrected)
            
            # Pattern 2: Direct references like "a [word]" or "the [word]"
            pattern2 = re.compile(r'\b(a|an|the)\s+\w*' + re.escape(match) + r'\w*\b', re.IGNORECASE)
            corrected = pattern2.sub('', corrected)
            
            # Pattern 3: "in a [word] manner" -> "in a [adjective] manner"
            if word.endswith('ly'):
                base = word[:-2]  # remove 'ly'
                pattern3 = re.compile(r'in\s+a\s+\w*' + re.escape(base) + r'\w*\s+manner', re.IGNORECASE)
                corrected = pattern3.sub('', corrected)
        
        # Clean up the result
        corrected = re.sub(r'\s*[;,]\s*[;,]\s*', '; ', corrected)  # Fix double punctuation
        corrected = re.sub(r'^\s*[;,]\s*', '', corrected)  # Remove leading punctuation
        corrected = re.sub(r'\s*[;,]\s*$', '', corrected)  # Remove trailing punctuation
        corrected = re.sub(r'\s+', ' ', corrected)  # Normalize whitespace
        corrected = corrected.strip()
        
        # Capitalize first letter
        if corrected:
            corrected = corrected[0].upper() + corrected[1:] if len(corrected) > 1 else corrected.upper()
        
        return corrected
    
    def scan_and_flag_definitions(self, limit: Optional[int] = None) -> Dict[str, int]:
        """Scan all definitions and flag circular ones"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        # Get all definitions
        sql = "SELECT id, term, definition FROM defined WHERE definition IS NOT NULL"
        if limit:
            sql += f" LIMIT {limit}"
        
        cursor.execute(sql)
        definitions = cursor.fetchall()
        
        stats = {
            'total_processed': 0,
            'circular_found': 0,
            'corrected': 0,
            'needs_review': 0
        }
        
        for def_id, term, definition in definitions:
            stats['total_processed'] += 1
            
            is_circular, matches = self.contains_circular_reference(term, definition)
            
            if is_circular:
                stats['circular_found'] += 1
                logger.info(f"Circular definition found: '{term}' contains {matches}")
                
                # Generate corrected definition
                corrected = self.generate_corrected_definition(term, definition, matches)
                
                # Update database
                update_sql = """
                    UPDATE defined 
                    SET has_circular_definition = TRUE,
                        corrected_definition = %s
                    WHERE id = %s
                """
                
                cursor.execute(update_sql, (corrected if corrected else None, def_id))
                
                if corrected and len(corrected) > 10:  # Reasonable length check
                    stats['corrected'] += 1
                else:
                    stats['needs_review'] += 1
                    logger.warning(f"Definition needs manual review: '{term}'")
        
        conn.commit()
        cursor.close()
        conn.close()
        
        return stats
    
    def get_flagged_definitions(self, limit: int = 50) -> List[Dict]:
        """Get definitions flagged as circular for review"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT id, term, definition, corrected_definition, part_of_speech
            FROM defined 
            WHERE has_circular_definition = TRUE
            ORDER BY term
            LIMIT %s
        """, (limit,))
        
        results = []
        for row in cursor.fetchall():
            results.append({
                'id': row[0],
                'term': row[1],
                'original_definition': row[2],
                'corrected_definition': row[3],
                'part_of_speech': row[4]
            })
        
        cursor.close()
        conn.close()
        
        return results
    
    def update_corrected_definition(self, def_id: int, corrected_definition: str):
        """Update a corrected definition manually"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            UPDATE defined 
            SET corrected_definition = %s
            WHERE id = %s
        """, (corrected_definition, def_id))
        
        conn.commit()
        cursor.close()
        conn.close()

def main():
    """Main function to run the circular definition detection"""
    detector = CircularDefinitionDetector()
    
    # Setup database
    logger.info("Setting up database columns...")
    detector.setup_database_columns()
    
    # Scan definitions (limit to 1000 for testing)
    logger.info("Scanning definitions for circular references...")
    stats = detector.scan_and_flag_definitions()  # Process ALL definitions
    
    print("\nCIRCULAR DEFINITION DETECTION RESULTS")
    print("=" * 50)
    print(f"Total definitions processed: {stats['total_processed']:,}")
    print(f"Circular definitions found: {stats['circular_found']:,}")
    print(f"Successfully corrected: {stats['corrected']:,}")
    print(f"Need manual review: {stats['needs_review']:,}")
    
    # Show some examples
    if stats['circular_found'] > 0:
        print("\nEXAMPLES OF FLAGGED DEFINITIONS:")
        print("-" * 40)
        examples = detector.get_flagged_definitions(limit=5)
        for example in examples:
            print(f"\nTerm: {example['term']}")
            print(f"Original: {example['original_definition'][:100]}...")
            if example['corrected_definition']:
                print(f"Corrected: {example['corrected_definition'][:100]}...")
            else:
                print("Corrected: [NEEDS MANUAL REVIEW]")

if __name__ == "__main__":
    main()