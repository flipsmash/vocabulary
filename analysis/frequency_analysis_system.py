#!/usr/bin/env python3
"""
Advanced Frequency Analysis System - Multi-source frequency collection and composite scoring
"""

import asyncio
import aiohttp
import mysql.connector
from mysql.connector import Error
import json
import logging
from typing import List, Dict, Set, Optional, Tuple
import time
from datetime import datetime, timedelta
import re
import wordfreq
from dataclasses import dataclass
from config import get_db_config

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@dataclass
class FrequencyData:
    """Structured frequency data point"""
    word: str
    source: str
    zipf_score: float
    raw_frequency: float
    confidence: float
    collection_date: datetime
    metadata: Dict

class FrequencyCollectionManager:
    """Collect frequency data from multiple sources and compute composite scores"""
    
    def __init__(self, db_config: Dict):
        self.db_config = db_config
        self.session = None
        
        # Frequency data sources with their reliability weights
        self.frequency_sources = {
            'wordfreq_google': {
                'weight': 0.25,
                'description': 'Google Books corpus via wordfreq',
                'reliability': 0.9
            },
            'wordfreq_twitter': {
                'weight': 0.15,
                'description': 'Twitter corpus via wordfreq',
                'reliability': 0.7
            },
            'wordfreq_subtitles': {
                'weight': 0.2,
                'description': 'OpenSubtitles via wordfreq',
                'reliability': 0.8
            },
            'wordfreq_combined': {
                'weight': 0.4,
                'description': 'Combined wordfreq score',
                'reliability': 0.95
            }
        }
        
        # Cache for already collected frequencies
        self.frequency_cache = {}
        self.cache_expiry_days = 30
    
    async def collect_frequencies(self, words: List[str]) -> Dict[str, List[FrequencyData]]:
        """Collect frequency data for a list of words from all sources"""
        logger.info(f"Collecting frequency data for {len(words)} words")
        
        # Filter out already cached frequencies
        words_to_process = []
        results = {}
        
        for word in words:
            if word in self.frequency_cache:
                cache_entry = self.frequency_cache[word]
                if cache_entry['timestamp'] > datetime.now() - timedelta(days=self.cache_expiry_days):
                    results[word] = cache_entry['data']
                    continue
            words_to_process.append(word)
        
        logger.info(f"Processing {len(words_to_process)} words (found {len(results)} in cache)")
        
        # Collect from all sources
        async with aiohttp.ClientSession() as session:
            self.session = session
            
            # Process in batches to avoid overwhelming APIs
            batch_size = 100
            for i in range(0, len(words_to_process), batch_size):
                batch = words_to_process[i:i+batch_size]
                logger.info(f"Processing batch {i//batch_size + 1}/{(len(words_to_process)-1)//batch_size + 1}")
                
                batch_results = await self._collect_batch_frequencies(batch)
                results.update(batch_results)
                
                # Add to cache
                for word, freq_data in batch_results.items():
                    self.frequency_cache[word] = {
                        'data': freq_data,
                        'timestamp': datetime.now()
                    }
                
                # Rate limiting between batches
                await asyncio.sleep(1.0)
        
        return results
    
    async def _collect_batch_frequencies(self, words: List[str]) -> Dict[str, List[FrequencyData]]:
        """Collect frequencies for a batch of words"""
        results = {}
        
        for word in words:
            word_frequencies = []
            
            # Collect from wordfreq library (multiple corpora)
            try:
                # Google Books corpus
                google_freq = wordfreq.word_frequency(word, 'en', wordlist='large')
                if google_freq > 0:
                    zipf_score = wordfreq.zipf_frequency(word, 'en', wordlist='large')
                    word_frequencies.append(FrequencyData(
                        word=word,
                        source='wordfreq_google',
                        zipf_score=zipf_score,
                        raw_frequency=google_freq,
                        confidence=self.frequency_sources['wordfreq_google']['reliability'],
                        collection_date=datetime.now(),
                        metadata={'corpus': 'google_books', 'wordlist': 'large'}
                    ))
                
                # Twitter corpus
                try:
                    twitter_freq = wordfreq.word_frequency(word, 'en', wordlist='twitter')
                    if twitter_freq > 0:
                        twitter_zipf = -1 * (math.log10(twitter_freq) if twitter_freq > 0 else 0)
                        word_frequencies.append(FrequencyData(
                            word=word,
                            source='wordfreq_twitter', 
                            zipf_score=twitter_zipf,
                            raw_frequency=twitter_freq,
                            confidence=self.frequency_sources['wordfreq_twitter']['reliability'],
                            collection_date=datetime.now(),
                            metadata={'corpus': 'twitter', 'wordlist': 'twitter'}
                        ))
                except:
                    pass  # Twitter corpus might not be available
                
                # OpenSubtitles corpus
                try:
                    sub_freq = wordfreq.word_frequency(word, 'en', wordlist='small')
                    if sub_freq > 0:
                        sub_zipf = wordfreq.zipf_frequency(word, 'en', wordlist='small')
                        word_frequencies.append(FrequencyData(
                            word=word,
                            source='wordfreq_subtitles',
                            zipf_score=sub_zipf,
                            raw_frequency=sub_freq,
                            confidence=self.frequency_sources['wordfreq_subtitles']['reliability'],
                            collection_date=datetime.now(),
                            metadata={'corpus': 'opensubtitles', 'wordlist': 'small'}
                        ))
                except:
                    pass
                
                # Combined/best estimate
                combined_zipf = wordfreq.zipf_frequency(word, 'en')
                combined_freq = wordfreq.word_frequency(word, 'en')
                word_frequencies.append(FrequencyData(
                    word=word,
                    source='wordfreq_combined',
                    zipf_score=combined_zipf,
                    raw_frequency=combined_freq,
                    confidence=self.frequency_sources['wordfreq_combined']['reliability'],
                    collection_date=datetime.now(),
                    metadata={'corpus': 'combined', 'method': 'best_estimate'}
                ))
                
            except Exception as e:
                logger.warning(f"Error collecting frequency for '{word}': {e}")
                # Add a minimal entry so we don't keep trying
                word_frequencies.append(FrequencyData(
                    word=word,
                    source='wordfreq_combined',
                    zipf_score=0.0,  # Unknown frequency
                    raw_frequency=0.0,
                    confidence=0.1,
                    collection_date=datetime.now(),
                    metadata={'error': str(e), 'method': 'fallback'}
                ))
            
            results[word] = word_frequencies
        
        return results
    
    def calculate_composite_zipf(self, frequency_list: List[FrequencyData]) -> Tuple[float, float]:
        """Calculate weighted composite Zipf score and confidence"""
        if not frequency_list:
            return 0.0, 0.0
        
        weighted_scores = []
        total_weight = 0.0
        confidence_scores = []
        
        for freq_data in frequency_list:
            source_config = self.frequency_sources.get(freq_data.source, {'weight': 0.1})
            weight = source_config['weight']
            
            # Only include non-zero scores in the composite
            if freq_data.zipf_score > 0:
                weighted_scores.append(freq_data.zipf_score * weight)
                total_weight += weight
                confidence_scores.append(freq_data.confidence * weight)
        
        if total_weight == 0:
            return 0.0, 0.0
        
        # Weighted average
        composite_zipf = sum(weighted_scores) / total_weight
        composite_confidence = sum(confidence_scores) / total_weight
        
        # Adjust confidence based on agreement between sources
        if len([f for f in frequency_list if f.zipf_score > 0]) > 1:
            # Multiple sources agree - boost confidence
            variance = sum((f.zipf_score - composite_zipf) ** 2 for f in frequency_list if f.zipf_score > 0)
            if variance < 1.0:  # Low variance means good agreement
                composite_confidence = min(1.0, composite_confidence * 1.2)
        
        return composite_zipf, composite_confidence
    
    async def store_frequencies(self, frequency_data: Dict[str, List[FrequencyData]]) -> int:
        """Store frequency data in database"""
        if not frequency_data:
            return 0
        
        try:
            conn = mysql.connector.connect(**self.db_config)
            cursor = conn.cursor()
            
            # Create frequency data table if it doesn't exist
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS word_frequency_data (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    word VARCHAR(100) NOT NULL,
                    source VARCHAR(50) NOT NULL,
                    zipf_score DECIMAL(6,3) DEFAULT 0,
                    raw_frequency DECIMAL(15,10) DEFAULT 0,
                    confidence DECIMAL(4,3) DEFAULT 0,
                    collection_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    metadata JSON,
                    composite_zipf DECIMAL(6,3) DEFAULT 0,
                    composite_confidence DECIMAL(4,3) DEFAULT 0,
                    UNIQUE KEY unique_word_source (word, source),
                    INDEX idx_word (word),
                    INDEX idx_zipf (zipf_score),
                    INDEX idx_composite (composite_zipf)
                )
            """)
            
            stored_count = 0
            
            for word, freq_list in frequency_data.items():
                # Calculate composite scores
                composite_zipf, composite_confidence = self.calculate_composite_zipf(freq_list)
                
                # Store individual frequency data points
                for freq_data in freq_list:
                    try:
                        cursor.execute("""
                            INSERT INTO word_frequency_data 
                            (word, source, zipf_score, raw_frequency, confidence, 
                             metadata, composite_zipf, composite_confidence)
                            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                            ON DUPLICATE KEY UPDATE
                            zipf_score = VALUES(zipf_score),
                            raw_frequency = VALUES(raw_frequency),
                            confidence = VALUES(confidence),
                            metadata = VALUES(metadata),
                            composite_zipf = VALUES(composite_zipf),
                            composite_confidence = VALUES(composite_confidence),
                            collection_date = CURRENT_TIMESTAMP
                        """, (
                            freq_data.word,
                            freq_data.source,
                            freq_data.zipf_score,
                            freq_data.raw_frequency,
                            freq_data.confidence,
                            json.dumps(freq_data.metadata),
                            composite_zipf,
                            composite_confidence
                        ))
                        stored_count += 1
                    except mysql.connector.IntegrityError:
                        continue  # Skip duplicates
            
            conn.commit()
            logger.info(f"Stored frequency data for {len(frequency_data)} words ({stored_count} total entries)")
            return stored_count
            
        except Error as e:
            logger.error(f"Database error storing frequencies: {e}")
            return 0
        finally:
            if 'conn' in locals() and conn.is_connected():
                cursor.close()
                conn.close()
    
    def get_stored_frequencies(self, words: List[str]) -> Dict[str, Tuple[float, float]]:
        """Get stored composite frequencies for words"""
        if not words:
            return {}
        
        try:
            conn = mysql.connector.connect(**self.db_config)
            cursor = conn.cursor()
            
            # Get most recent composite scores for each word
            placeholders = ', '.join(['%s'] * len(words))
            cursor.execute(f"""
                SELECT word, composite_zipf, composite_confidence
                FROM word_frequency_data 
                WHERE word IN ({placeholders}) AND source = 'wordfreq_combined'
                ORDER BY collection_date DESC
            """, words)
            
            results = {}
            for word, zipf, confidence in cursor.fetchall():
                results[word] = (float(zipf), float(confidence))
            
            return results
            
        except Error as e:
            logger.error(f"Database error getting frequencies: {e}")
            return {}
        finally:
            if 'conn' in locals() and conn.is_connected():
                cursor.close()
                conn.close()
    
    def get_frequency_statistics(self) -> Dict:
        """Get statistics about stored frequency data"""
        try:
            conn = mysql.connector.connect(**self.db_config)
            cursor = conn.cursor()
            
            stats = {}
            
            # Total words with frequency data
            cursor.execute("SELECT COUNT(DISTINCT word) FROM word_frequency_data")
            stats['total_words'] = cursor.fetchone()[0]
            
            # Distribution by Zipf score ranges
            cursor.execute("""
                SELECT 
                    CASE 
                        WHEN composite_zipf = 0 THEN 'unknown'
                        WHEN composite_zipf < 2.0 THEN 'very_rare'
                        WHEN composite_zipf < 3.0 THEN 'rare'
                        WHEN composite_zipf < 4.0 THEN 'uncommon'
                        WHEN composite_zipf < 5.0 THEN 'common'
                        ELSE 'very_common'
                    END as frequency_category,
                    COUNT(DISTINCT word) as word_count
                FROM word_frequency_data
                WHERE source = 'wordfreq_combined'
                GROUP BY frequency_category
            """)
            
            stats['frequency_distribution'] = dict(cursor.fetchall())
            
            # Recent collection activity
            cursor.execute("""
                SELECT DATE(collection_date) as date, COUNT(*) as entries
                FROM word_frequency_data
                WHERE collection_date >= DATE_SUB(CURRENT_DATE, INTERVAL 7 DAY)
                GROUP BY DATE(collection_date)
                ORDER BY date DESC
            """)
            
            stats['recent_activity'] = dict(cursor.fetchall())
            
            return stats
            
        except Error as e:
            logger.error(f"Database error getting statistics: {e}")
            return {}
        finally:
            if 'conn' in locals() and conn.is_connected():
                cursor.close()
                conn.close()

class RarityClassifier:
    """Classify words by rarity level using frequency data"""
    
    def __init__(self):
        # Rarity thresholds based on Zipf scores
        self.rarity_thresholds = {
            'extremely_rare': 1.0,     # < 1 in 10 million words
            'very_rare': 2.0,          # < 1 in 1 million words  
            'rare': 3.0,               # < 1 in 100,000 words
            'uncommon': 4.0,           # < 1 in 10,000 words
            'common': 5.0,             # < 1 in 1,000 words
            'very_common': 6.0         # >= 1 in 1,000 words
        }
    
    def classify_rarity(self, zipf_score: float, confidence: float = 1.0) -> Tuple[str, Dict]:
        """Classify word rarity and provide detailed analysis"""
        if zipf_score == 0:
            return 'unknown', {
                'description': 'Frequency unknown - potentially very rare or technical',
                'utility_score': 3.0,
                'confidence': confidence
            }
        
        # Determine rarity category
        category = 'very_common'  # Default
        for rarity, threshold in self.rarity_thresholds.items():
            if zipf_score < threshold:
                category = rarity
                break
        
        # Calculate utility scores based on rarity
        utility_scores = {
            'extremely_rare': 4.0,
            'very_rare': 3.5,
            'rare': 3.0,
            'uncommon': 2.5,
            'common': 1.5,
            'very_common': 0.5,
            'unknown': 2.0
        }
        
        # Descriptions for each category
        descriptions = {
            'extremely_rare': f'Extremely rare word (Zipf {zipf_score:.1f}) - specialist vocabulary',
            'very_rare': f'Very rare word (Zipf {zipf_score:.1f}) - advanced vocabulary',
            'rare': f'Rare word (Zipf {zipf_score:.1f}) - sophisticated vocabulary',
            'uncommon': f'Uncommon word (Zipf {zipf_score:.1f}) - above average vocabulary',
            'common': f'Common word (Zipf {zipf_score:.1f}) - everyday vocabulary',
            'very_common': f'Very common word (Zipf {zipf_score:.1f}) - basic vocabulary',
            'unknown': 'Unknown frequency - potentially rare or specialized'
        }
        
        return category, {
            'description': descriptions[category],
            'utility_score': utility_scores[category],
            'confidence': confidence,
            'zipf_score': zipf_score
        }
    
    def get_vocabulary_level(self, zipf_score: float) -> str:
        """Get vocabulary level description"""
        if zipf_score == 0:
            return 'Graduate/Professional'
        elif zipf_score < 2.0:
            return 'Graduate/Professional'
        elif zipf_score < 3.0:
            return 'Undergraduate/Advanced'
        elif zipf_score < 4.0:
            return 'High School/College'
        elif zipf_score < 5.0:
            return 'Middle School/High School'
        else:
            return 'Elementary/Common'

# Test function
async def test_frequency_system():
    """Test the frequency collection system"""
    freq_manager = FrequencyCollectionManager(get_db_config())
    classifier = RarityClassifier()
    
    # Test words of varying rarity
    test_words = [
        'epistemological',  # Very sophisticated
        'pathophysiology',  # Medical term
        'serendipity',     # Uncommon but known
        'beautiful',       # Common word
        'the',            # Very common
        'quixotic',       # Literary/rare
        'neuroplasticity', # Scientific term
    ]
    
    print(f"Testing frequency system with {len(test_words)} words...")
    
    # Collect frequencies
    frequency_data = await freq_manager.collect_frequencies(test_words)
    
    # Store in database
    stored_count = await freq_manager.store_frequencies(frequency_data)
    print(f"Stored {stored_count} frequency entries")
    
    # Analyze each word
    print("\nWord Analysis:")
    print("-" * 80)
    
    for word in test_words:
        if word in frequency_data:
            composite_zipf, confidence = freq_manager.calculate_composite_zipf(frequency_data[word])
            category, analysis = classifier.classify_rarity(composite_zipf, confidence)
            level = classifier.get_vocabulary_level(composite_zipf)
            
            print(f"{word:20} | {category:15} | {level:20} | {analysis['description']}")
        else:
            print(f"{word:20} | {'ERROR':15} | {'':20} | No frequency data found")
    
    # Show statistics
    stats = freq_manager.get_frequency_statistics()
    print(f"\nFrequency Database Statistics:")
    print(f"Total words: {stats.get('total_words', 0)}")
    print(f"Distribution: {stats.get('frequency_distribution', {})}")

if __name__ == "__main__":
    import math
    asyncio.run(test_frequency_system())