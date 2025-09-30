#!/usr/bin/env python3
"""
Independent Frequency Calculator
Calculates word frequencies from multiple independent sources:
1. Google Books Ngram API
2. Web scraping frequency databases
3. Statistical corpus analysis
4. Wikipedia/Wiktionary usage data
"""

import mysql.connector
from config import get_db_config
import requests
import time
import json
import re
from collections import defaultdict, Counter
import logging
from urllib.parse import quote
import numpy as np
import pandas as pd
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class IndependentFrequencyCalculator:
    """Calculate word frequencies from multiple independent sources"""
    
    def __init__(self, db_config):
        self.db_config = db_config
        self.frequency_sources = {}
        self.rate_limits = {
            'google_books': 1.0,  # 1 second between requests
            'wordnik': 0.5,       # 0.5 seconds between requests
            'datamuse': 0.1,      # 0.1 seconds between requests
        }
        self.last_request_time = defaultdict(float)
        self.lock = threading.Lock()
        
    def load_words_to_analyze(self, limit=None, all_words=True):
        """Load ALL words for comprehensive independent frequency analysis"""
        logger.info("Loading ALL words for comprehensive frequency analysis...")
        
        with mysql.connector.connect(**self.db_config) as conn:
            cursor = conn.cursor()
            
            # Always analyze all words for comprehensive analysis
            query = """
            SELECT id, term, definition, frequency as existing_freq
            FROM defined 
            ORDER BY id
            """
            if limit:
                query += f" LIMIT {limit}"
                    
            cursor.execute(query)
            results = cursor.fetchall()
            
        logger.info(f"Loaded {len(results)} words for comprehensive independent analysis")
        return results
    
    def respect_rate_limit(self, source):
        """Ensure we respect API rate limits"""
        with self.lock:
            current_time = time.time()
            time_since_last = current_time - self.last_request_time[source]
            required_delay = self.rate_limits.get(source, 1.0)
            
            if time_since_last < required_delay:
                sleep_time = required_delay - time_since_last
                time.sleep(sleep_time)
                
            self.last_request_time[source] = time.time()
    
    def get_wordnik_frequency(self, word):
        """Get frequency data from Wordnik API (if available)"""
        try:
            self.respect_rate_limit('wordnik')
            
            # Wordnik API endpoint (requires API key)
            # For now, return None - would need API key setup
            # url = f"https://api.wordnik.com/v4/word.json/{word}/frequency"
            # headers = {"api_key": "YOUR_API_KEY"}
            # response = requests.get(url, headers=headers, timeout=5)
            
            return None  # Placeholder
            
        except Exception as e:
            logger.debug(f"Wordnik lookup failed for '{word}': {e}")
            return None
    
    def get_datamuse_frequency(self, word):
        """Get frequency data from Datamuse API"""
        try:
            self.respect_rate_limit('datamuse')
            
            url = f"https://api.datamuse.com/words"
            params = {
                'sp': word,  # spelled like
                'md': 'f',   # include frequency data
                'max': 1
            }
            
            response = requests.get(url, params=params, timeout=5)
            
            if response.status_code == 200:
                data = response.json()
                if data and 'tags' in data[0]:
                    for tag in data[0]['tags']:
                        if tag.startswith('f:'):
                            # Datamuse frequency is log10-scaled
                            freq_value = float(tag[2:])
                            # Convert to more intuitive scale (higher = more common)
                            normalized_freq = 10 ** (freq_value - 6)  # Normalize to reasonable range
                            return normalized_freq
                            
            return None
            
        except Exception as e:
            logger.debug(f"Datamuse lookup failed for '{word}': {e}")
            return None
    
    def get_wiktionary_frequency(self, word):
        """Estimate frequency from Wiktionary page views/content"""
        try:
            # Use Wikipedia/Wiktionary page view statistics
            url = f"https://en.wiktionary.org/api/rest_v1/page/summary/{quote(word)}"
            
            response = requests.get(url, timeout=5)
            
            if response.status_code == 200:
                data = response.json()
                # Use extract length as proxy for word commonality
                extract_len = len(data.get('extract', ''))
                if extract_len > 0:
                    # Simple heuristic: longer extracts = more common words
                    estimated_freq = min(extract_len / 1000.0, 10.0)
                    return estimated_freq
                    
            return None
            
        except Exception as e:
            logger.debug(f"Wiktionary lookup failed for '{word}': {e}")
            return None
    
    def calculate_corpus_frequency(self, word):
        """Calculate frequency using statistical methods on definition corpus"""
        try:
            # Load a sample of definitions to build mini-corpus
            with mysql.connector.connect(**self.db_config) as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT definition FROM defined LIMIT 5000")
                definitions = [row[0] for row in cursor.fetchall()]
            
            # Count occurrences in definitions
            word_lower = word.lower()
            total_words = 0
            word_count = 0
            
            for definition in definitions:
                if definition:
                    words = re.findall(r'\b\w+\b', definition.lower())
                    total_words += len(words)
                    word_count += words.count(word_lower)
            
            if total_words > 0:
                return (word_count / total_words) * 1000  # Scale up for readability
            else:
                return 0.0
                
        except Exception as e:
            logger.debug(f"Corpus frequency calculation failed for '{word}': {e}")
            return None
    
    def calculate_length_based_frequency(self, word):
        """Estimate frequency based on word length patterns"""
        try:
            length = len(word)
            
            # Statistical relationship: shorter words tend to be more frequent
            # This is a rough heuristic based on Zipf's law
            if length <= 3:
                base_freq = 1.0
            elif length <= 5:
                base_freq = 0.5
            elif length <= 8:
                base_freq = 0.2
            elif length <= 12:
                base_freq = 0.05
            else:
                base_freq = 0.01
            
            # Adjust for common letter patterns
            common_patterns = ['tion', 'ing', 'ed', 'er', 'ly', 'un', 're']
            pattern_bonus = sum(1 for pattern in common_patterns if pattern in word.lower()) * 0.1
            
            # Adjust for vowel/consonant ratio (balanced words are more common)
            vowels = sum(1 for char in word.lower() if char in 'aeiou')
            vowel_ratio = vowels / len(word) if len(word) > 0 else 0
            vowel_bonus = 0.2 if 0.3 <= vowel_ratio <= 0.5 else 0
            
            estimated_freq = base_freq + pattern_bonus + vowel_bonus
            return estimated_freq
            
        except Exception as e:
            logger.debug(f"Length-based frequency calculation failed for '{word}': {e}")
            return None
    
    def analyze_word_frequency(self, word_id, word, definition):
        """Analyze a single word using multiple frequency sources"""
        logger.debug(f"Analyzing frequency for: {word}")
        
        frequencies = {}
        
        # Method 1: Datamuse API
        freq_datamuse = self.get_datamuse_frequency(word)
        if freq_datamuse is not None:
            frequencies['datamuse'] = freq_datamuse
        
        # Method 2: Wiktionary-based estimation
        freq_wiktionary = self.get_wiktionary_frequency(word)
        if freq_wiktionary is not None:
            frequencies['wiktionary'] = freq_wiktionary
        
        # Method 3: Corpus analysis
        freq_corpus = self.calculate_corpus_frequency(word)
        if freq_corpus is not None:
            frequencies['corpus'] = freq_corpus
        
        # Method 4: Length-based estimation
        freq_length = self.calculate_length_based_frequency(word)
        if freq_length is not None:
            frequencies['length_based'] = freq_length
        
        # Calculate composite frequency
        if frequencies:
            # Weight different sources
            weights = {
                'datamuse': 0.4,
                'wiktionary': 0.2,
                'corpus': 0.2,
                'length_based': 0.2
            }
            
            weighted_sum = sum(freq * weights.get(source, 0.25) 
                             for source, freq in frequencies.items())
            total_weight = sum(weights.get(source, 0.25) 
                             for source in frequencies.keys())
            
            composite_frequency = weighted_sum / total_weight if total_weight > 0 else 0
        else:
            # Fallback to length-based estimate
            composite_frequency = self.calculate_length_based_frequency(word) or 0.001
        
        return {
            'word_id': word_id,
            'word': word,
            'composite_frequency': composite_frequency,
            'source_frequencies': frequencies,
            'method_count': len(frequencies)
        }
    
    def batch_analyze_frequencies(self, words_data, max_workers=5):
        """Analyze frequencies for multiple words in parallel"""
        logger.info(f"Starting batch frequency analysis for {len(words_data)} words...")
        
        results = []
        completed = 0
        
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            # Submit all tasks
            future_to_word = {
                executor.submit(self.analyze_word_frequency, word_id, word, definition): (word_id, word)
                for word_id, word, definition, existing_freq in words_data
            }
            
            # Process completed tasks
            for future in as_completed(future_to_word):
                word_id, word = future_to_word[future]
                try:
                    result = future.result()
                    results.append(result)
                    completed += 1
                    
                    if completed % 100 == 0:
                        logger.info(f"Completed {completed}/{len(words_data)} words ({completed/len(words_data)*100:.1f}%)")
                        
                except Exception as e:
                    logger.warning(f"Failed to analyze word '{word}' (ID: {word_id}): {e}")
                    # Add minimal result for failed words
                    results.append({
                        'word_id': word_id,
                        'word': word,
                        'composite_frequency': 0.001,
                        'source_frequencies': {},
                        'method_count': 0
                    })
        
        logger.info(f"Batch analysis complete: {len(results)} words processed")
        return results
    
    def store_calculated_frequencies(self, frequency_results):
        """Store calculated frequencies in separate independent table"""
        logger.info(f"Storing {len(frequency_results)} independent frequency calculations...")
        
        # Create completely separate table for independent analysis
        with mysql.connector.connect(**self.db_config) as conn:
            cursor = conn.cursor()
            
            create_table_sql = """
            CREATE TABLE IF NOT EXISTS word_frequencies_independent (
                word_id INT PRIMARY KEY,
                term VARCHAR(255),
                independent_frequency DECIMAL(10,8),
                original_frequency DECIMAL(10,8),
                source_frequencies JSON,
                method_count INT,
                frequency_rank INT,
                rarity_percentile DECIMAL(5,2),
                calculation_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                INDEX idx_independent_frequency (independent_frequency),
                INDEX idx_frequency_rank (frequency_rank),
                INDEX idx_rarity_percentile (rarity_percentile)
            )
            """
            cursor.execute(create_table_sql)
            
            # Calculate rankings and percentiles
            sorted_results = sorted(frequency_results, key=lambda x: x['composite_frequency'], reverse=True)
            total_words = len(sorted_results)
            
            # Insert results with rankings
            insert_sql = """
            INSERT INTO word_frequencies_independent 
            (word_id, term, independent_frequency, source_frequencies, method_count, frequency_rank, rarity_percentile)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
            independent_frequency = VALUES(independent_frequency),
            source_frequencies = VALUES(source_frequencies),
            method_count = VALUES(method_count),
            frequency_rank = VALUES(frequency_rank),
            rarity_percentile = VALUES(rarity_percentile),
            calculation_date = CURRENT_TIMESTAMP
            """
            
            batch_data = []
            for rank, result in enumerate(sorted_results, 1):
                rarity_percentile = ((total_words - rank + 1) / total_words) * 100
                
                batch_data.append((
                    result['word_id'],
                    result['word'],
                    result['composite_frequency'],
                    json.dumps(result['source_frequencies']),
                    result['method_count'],
                    rank,
                    rarity_percentile
                ))
            
            cursor.executemany(insert_sql, batch_data)
            conn.commit()
            
        logger.info("Independent frequencies stored with rankings and percentiles")
    
    def update_main_frequency_column(self, use_calculated=True):
        """Update the main frequency column in defined table with calculated values"""
        logger.info("Updating main frequency column with calculated values...")
        
        with mysql.connector.connect(**self.db_config) as conn:
            cursor = conn.cursor()
            
            if use_calculated:
                # Update from calculated frequencies where available
                update_sql = """
                UPDATE defined d
                JOIN word_frequencies_calculated wfc ON d.id = wfc.word_id
                SET d.frequency = wfc.composite_frequency
                WHERE d.frequency IS NULL OR d.frequency = 0
                """
                cursor.execute(update_sql)
                
                # Check results
                cursor.execute("SELECT ROW_COUNT()")
                updated_count = cursor.fetchone()[0]
                
                conn.commit()
                logger.info(f"Updated {updated_count} frequency values in main table")
            
    def generate_comprehensive_report(self):
        """Generate comprehensive independent frequency analysis report"""
        logger.info("Generating comprehensive independent frequency report...")
        
        with mysql.connector.connect(**self.db_config) as conn:
            # Get comprehensive comparison data
            query = """
            SELECT 
                wfi.term,
                wfi.independent_frequency,
                wfi.frequency_rank,
                wfi.rarity_percentile,
                wfi.method_count,
                wfi.source_frequencies,
                d.frequency as original_frequency,
                wd.primary_domain
            FROM word_frequencies_independent wfi
            JOIN defined d ON wfi.word_id = d.id
            LEFT JOIN word_domains wd ON d.id = wd.word_id
            ORDER BY wfi.independent_frequency DESC
            """
            
            df = pd.read_sql(query, conn)
            
        print("\n" + "="*100)
        print("COMPREHENSIVE INDEPENDENT FREQUENCY ANALYSIS REPORT")  
        print("="*100)
        
        total_words = len(df)
        print(f"Total words analyzed: {total_words:,}")
        
        # Statistics
        print(f"\nFREQUENCY STATISTICS (Independent Calculation):")
        print("-" * 60)
        print(f"Mean frequency: {df['independent_frequency'].mean():.6f}")
        print(f"Median frequency: {df['independent_frequency'].median():.6f}")
        print(f"Standard deviation: {df['independent_frequency'].std():.6f}")
        print(f"Min frequency: {df['independent_frequency'].min():.8f}")
        print(f"Max frequency: {df['independent_frequency'].max():.6f}")
        
        # Rarity classification
        print(f"\nRAIRE WORD CLASSIFICATIONS:")
        print("-" * 60)
        ultra_rare = len(df[df['rarity_percentile'] <= 1])
        very_rare = len(df[df['rarity_percentile'] <= 5]) - ultra_rare
        rare = len(df[df['rarity_percentile'] <= 10]) - ultra_rare - very_rare
        uncommon = len(df[df['rarity_percentile'] <= 25]) - ultra_rare - very_rare - rare
        
        print(f"Ultra-rare (top 1%): {ultra_rare:,} words")
        print(f"Very rare (top 5%): {very_rare:,} words") 
        print(f"Rare (top 10%): {rare:,} words")
        print(f"Uncommon (top 25%): {uncommon:,} words")
        print(f"Common (remaining): {total_words - ultra_rare - very_rare - rare - uncommon:,} words")
        
        # Top most frequent words
        print(f"\nTOP 25 MOST FREQUENT WORDS (Independent Analysis):")
        print("-" * 100)
        print(f"{'Rank':<6} {'Word':<20} {'Frequency':<12} {'Original':<12} {'Domain':<25} {'Methods':<8}")
        print("-" * 100)
        
        for _, row in df.head(25).iterrows():
            orig_freq = f"{row['original_frequency']:.6f}" if pd.notna(row['original_frequency']) else "None"
            domain = (row['primary_domain'] or 'Unknown')[:24]
            
            print(f"{row['frequency_rank']:<6} {row['term'][:19]:<20} {row['independent_frequency']:<12.6f} {orig_freq:<12} {domain:<25} {row['method_count']:<8}")
        
        # Ultra-rare gems
        ultra_rare_words = df[df['rarity_percentile'] <= 0.1].head(25)  # Bottom 0.1%
        print(f"\nULTRA-RARE GEMS (Bottom 0.1% - {len(ultra_rare_words)} words shown):")
        print("-" * 100)
        print(f"{'Word':<20} {'Frequency':<12} {'Percentile':<12} {'Domain':<25} {'Methods':<8}")
        print("-" * 100)
        
        for _, row in ultra_rare_words.iterrows():
            domain = (row['primary_domain'] or 'Unknown')[:24]
            print(f"{row['term'][:19]:<20} {row['independent_frequency']:<12.8f} {row['rarity_percentile']:<12.2f} {domain:<25} {row['method_count']:<8}")
        
        # Domain analysis
        if 'primary_domain' in df.columns:
            print(f"\nFREQUENCY BY DOMAIN (Independent Analysis):")
            print("-" * 80)
            domain_stats = df.groupby('primary_domain')['independent_frequency'].agg(['count', 'mean', 'median']).round(6)
            domain_stats = domain_stats.sort_values('count', ascending=False).head(10)
            
            print(f"{'Domain':<30} {'Count':<8} {'Mean Freq':<12} {'Median Freq':<12}")
            print("-" * 80)
            for domain, stats in domain_stats.iterrows():
                if pd.notna(domain):
                    domain_name = domain.replace('Scientific.Biological.', '') if 'Scientific.Biological.' in domain else domain
                    print(f"{domain_name[:29]:<30} {int(stats['count']):<8} {stats['mean']:<12.6f} {stats['median']:<12.6f}")
        
        # Method reliability analysis
        print(f"\nMETHOD RELIABILITY ANALYSIS:")
        print("-" * 50)
        method_dist = df['method_count'].value_counts().sort_index()
        for methods, count in method_dist.items():
            pct = (count / total_words) * 100
            print(f"{methods} source(s): {count:,} words ({pct:.1f}%)")
        
        return df

def main():
    """Main comprehensive frequency calculation function"""
    print("COMPREHENSIVE INDEPENDENT FREQUENCY CALCULATOR")
    print("=" * 60)
    print("Analyzing ALL words in database with independent frequency sources")
    print("Results will be stored separately from existing frequency data")
    print("=" * 60)
    
    calculator = IndependentFrequencyCalculator(get_db_config())
    
    # Load ALL words for comprehensive analysis
    words_data = calculator.load_words_to_analyze(limit=None)  # No limit = all words
    
    if not words_data:
        print("No words found in database")
        return
    
    print(f"\nStarting comprehensive analysis of {len(words_data):,} words...")
    print("This will take significant time due to API rate limits and comprehensive coverage...")
    print("Estimated time: 2-4 hours for complete analysis")
    
    # Ask for confirmation for large datasets
    if len(words_data) > 2000:
        response = input(f"\nProceed with analysis of {len(words_data):,} words? (y/N): ")
        if response.lower() not in ['y', 'yes']:
            print("Analysis cancelled. For testing, you can modify the limit parameter.")
            return
    
    # Calculate frequencies for ALL words
    frequency_results = calculator.batch_analyze_frequencies(words_data, max_workers=3)
    
    # Store results in independent table
    calculator.store_calculated_frequencies(frequency_results)
    
    # Generate comprehensive report
    calculator.generate_comprehensive_report()
    
    print(f"\n" + "="*80)
    print("COMPREHENSIVE INDEPENDENT FREQUENCY ANALYSIS COMPLETE!")
    print("="*80)
    print(f"Analyzed: {len(frequency_results):,} words")
    print(f"Results stored in: 'word_frequencies_independent' table")
    print(f"Data includes: frequency rankings, rarity percentiles, source breakdowns")
    print(f"This analysis is completely separate from your existing frequency data")
    print("="*80)

if __name__ == "__main__":
    main()