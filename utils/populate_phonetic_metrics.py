#!/usr/bin/env python3
"""
Populate missing phonetic metrics in pronunciation_similarity table
Calculates phonetic_distance, stress_similarity, rhyme_score, and syllable_similarity
for existing similarity records that only have overall_similarity
"""

import mysql.connector
import logging
from typing import Tuple, Optional, List
import re
from dataclasses import dataclass

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

@dataclass
class PhoneticData:
    word_id: int
    word: str
    ipa: str
    arpabet: str
    syllables: int
    stress_pattern: str

class PhoneticMetricsCalculator:
    """Calculate detailed phonetic similarity metrics"""
    
    def __init__(self, db_config):
        self.db_config = db_config
        
    def get_connection(self):
        return mysql.connector.connect(**self.db_config)
    
    def calculate_phonetic_distance(self, ipa1: str, ipa2: str) -> float:
        """Calculate phonetic distance between two IPA strings"""
        if not ipa1 or not ipa2:
            return 1.0
            
        # Simple Levenshtein distance normalized by max length
        def levenshtein(s1, s2):
            if len(s1) < len(s2):
                return levenshtein(s2, s1)
            if len(s2) == 0:
                return len(s1)
                
            previous_row = list(range(len(s2) + 1))
            for i, c1 in enumerate(s1):
                current_row = [i + 1]
                for j, c2 in enumerate(s2):
                    insertions = previous_row[j + 1] + 1
                    deletions = current_row[j] + 1
                    substitutions = previous_row[j] + (c1 != c2)
                    current_row.append(min(insertions, deletions, substitutions))
                previous_row = current_row
                
            return previous_row[-1]
        
        distance = levenshtein(ipa1, ipa2)
        max_len = max(len(ipa1), len(ipa2))
        return distance / max_len if max_len > 0 else 0.0
    
    def calculate_stress_similarity(self, stress1: str, stress2: str) -> float:
        """Calculate stress pattern similarity"""
        if not stress1 or not stress2:
            return 0.0
            
        # Convert stress patterns to comparable format
        def normalize_stress(pattern):
            if not pattern:
                return ""
            # Extract stress numbers/patterns
            return re.sub(r'[^012]', '', pattern)
        
        norm1 = normalize_stress(stress1)
        norm2 = normalize_stress(stress2)
        
        if not norm1 or not norm2:
            return 0.0
            
        if norm1 == norm2:
            return 1.0
            
        # Calculate similarity based on matching positions
        min_len = min(len(norm1), len(norm2))
        if min_len == 0:
            return 0.0
            
        matches = sum(1 for i in range(min_len) if norm1[i] == norm2[i])
        return matches / max(len(norm1), len(norm2))
    
    def calculate_rhyme_score(self, ipa1: str, ipa2: str) -> float:
        """Calculate rhyme similarity based on ending sounds"""
        if not ipa1 or not ipa2:
            return 0.0
            
        # Get last 3 phonemes for rhyme comparison
        def get_ending_sounds(ipa, n=3):
            # Simple approach: take last n characters
            return ipa[-n:] if len(ipa) >= n else ipa
        
        ending1 = get_ending_sounds(ipa1)
        ending2 = get_ending_sounds(ipa2)
        
        if ending1 == ending2:
            return 1.0
        
        # Calculate partial rhyme similarity
        matches = sum(1 for i in range(min(len(ending1), len(ending2))) 
                     if ending1[-(i+1)] == ending2[-(i+1)])
        
        return matches / max(len(ending1), len(ending2)) if max(len(ending1), len(ending2)) > 0 else 0.0
    
    def calculate_syllable_similarity(self, syll1: int, syll2: int) -> float:
        """Calculate syllable count similarity"""
        if syll1 <= 0 or syll2 <= 0:
            return 0.0
            
        if syll1 == syll2:
            return 1.0
            
        # Similarity decreases with syllable difference
        diff = abs(syll1 - syll2)
        max_syll = max(syll1, syll2)
        
        return max(0.0, 1.0 - (diff / max_syll))
    
    def get_phonetic_data_batch(self, word_ids: List[int]) -> dict:
        """Get phonetic data for a batch of word IDs"""
        if not word_ids:
            return {}
            
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            placeholders = ','.join(['%s'] * len(word_ids))
            query = f"""
            SELECT word_id, word, ipa_transcription, arpabet_transcription, 
                   syllable_count, stress_pattern
            FROM word_phonetics 
            WHERE word_id IN ({placeholders})
            """
            
            cursor.execute(query, word_ids)
            results = cursor.fetchall()
            
            phonetic_data = {}
            for row in results:
                phonetic_data[row[0]] = PhoneticData(
                    word_id=row[0],
                    word=row[1],
                    ipa=row[2] or "",
                    arpabet=row[3] or "",
                    syllables=row[4] or 0,
                    stress_pattern=row[5] or ""
                )
            
            return phonetic_data
    
    def update_similarity_metrics_batch(self, updates: List[Tuple]):
        """Update similarity records with calculated metrics"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            update_query = """
            UPDATE pronunciation_similarity 
            SET phonetic_distance = %s, stress_similarity = %s, 
                rhyme_score = %s, syllable_similarity = %s
            WHERE word1_id = %s AND word2_id = %s
            """
            
            cursor.executemany(update_query, updates)
            conn.commit()
            
            logger.info(f"Updated {len(updates)} similarity records with phonetic metrics")
    
    def process_similarity_records(self, batch_size=10000, limit=None):
        """Process and update similarity records with missing metrics"""
        logger.info(f"Starting to process similarity records in batches of {batch_size:,}")
        if limit:
            logger.info(f"Processing limit: {limit:,} records")
        
        processed = 0
        
        # Process in batches
        offset = 0
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            while True:
                # Get batch of similarity records
                select_query = """
                SELECT word1_id, word2_id, overall_similarity
                FROM pronunciation_similarity 
                WHERE phonetic_distance = 0 AND stress_similarity = 0 
                AND rhyme_score = 0 AND syllable_similarity = 0
                LIMIT %s OFFSET %s
                """
                
                cursor.execute(select_query, (batch_size, offset))
                similarity_records = cursor.fetchall()
                
                if not similarity_records:
                    break
                
                # Get unique word IDs for this batch
                word_ids = set()
                for word1_id, word2_id, _ in similarity_records:
                    word_ids.add(word1_id)
                    word_ids.add(word2_id)
                
                # Get phonetic data for all words in this batch
                phonetic_data = self.get_phonetic_data_batch(list(word_ids))
                
                # Calculate metrics for each similarity record
                updates = []
                for word1_id, word2_id, overall_sim in similarity_records:
                    if word1_id not in phonetic_data or word2_id not in phonetic_data:
                        logger.warning(f"Missing phonetic data for words {word1_id}, {word2_id}")
                        continue
                    
                    data1 = phonetic_data[word1_id]
                    data2 = phonetic_data[word2_id]
                    
                    # Calculate detailed metrics
                    phonetic_distance = self.calculate_phonetic_distance(data1.ipa, data2.ipa)
                    stress_similarity = self.calculate_stress_similarity(data1.stress_pattern, data2.stress_pattern)
                    rhyme_score = self.calculate_rhyme_score(data1.ipa, data2.ipa)
                    syllable_similarity = self.calculate_syllable_similarity(data1.syllables, data2.syllables)
                    
                    updates.append((
                        phonetic_distance, stress_similarity, rhyme_score, syllable_similarity,
                        word1_id, word2_id
                    ))
                
                # Update database with calculated metrics
                if updates:
                    self.update_similarity_metrics_batch(updates)
                    processed += len(updates)
                    
                    logger.info(f"Processed {processed:,} records")
                
                offset += batch_size
                
                if limit and processed >= limit:
                    break
            
            logger.info(f"Completed processing {processed:,} similarity records")

def main():
    """Main function"""
    from config import get_db_config
    DB_CONFIG = get_db_config()
    
    calculator = PhoneticMetricsCalculator(DB_CONFIG)
    
    import sys
    if len(sys.argv) > 1:
        try:
            limit = int(sys.argv[1])
            logger.info(f"Processing with limit: {limit:,}")
            calculator.process_similarity_records(limit=limit)
        except ValueError:
            logger.error("Invalid limit argument. Please provide a number.")
    else:
        logger.info("Processing all similarity records")
        calculator.process_similarity_records()

if __name__ == "__main__":
    main()