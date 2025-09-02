#!/usr/bin/env python3
"""
Recalculate Independent Frequencies with New Weights
No new API calls - just reweight existing source data
New weights: Datamuse 70%, Wiktionary 20%, Length-based 10%
Corpus method omitted entirely
"""

import mysql.connector
import json
import logging
from config import get_db_config

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def recalculate_frequencies():
    """Recalculate independent frequencies with new weights"""
    logger.info("Starting frequency recalculation with new weights...")
    logger.info("New weights: Datamuse 70%, Wiktionary 20%, Length-based 10%, Corpus 0%")
    
    config = get_db_config()
    conn = mysql.connector.connect(**config)
    cursor = conn.cursor()
    
    # Get all existing frequency records
    cursor.execute("""
        SELECT word_id, term, source_frequencies 
        FROM word_frequencies_independent
        ORDER BY word_id
    """)
    
    records = cursor.fetchall()
    logger.info(f"Found {len(records)} frequency records to recalculate")
    
    updated_count = 0
    batch_size = 1000
    updates = []
    
    # New weight scheme
    new_weights = {
        'datamuse': 0.70,
        'wiktionary': 0.20,
        'length_based': 0.10,
        'corpus': 0.0  # Completely omit corpus
    }
    
    for word_id, term, source_frequencies_json in records:
        try:
            # Parse the stored source frequencies
            source_frequencies = json.loads(source_frequencies_json)
            
            # Calculate new weighted frequency (omitting corpus)
            weighted_sum = 0.0
            total_weight = 0.0
            used_sources = []
            
            for source, frequency in source_frequencies.items():
                if source in new_weights and frequency is not None and frequency > 0:
                    weight = new_weights[source]
                    if weight > 0:  # Skip corpus (weight = 0)
                        weighted_sum += frequency * weight
                        total_weight += weight
                        used_sources.append(source)
            
            if total_weight > 0:
                new_independent_frequency = weighted_sum / total_weight
                
                # Store the update
                updates.append((new_independent_frequency, word_id))
                updated_count += 1
                
                if updated_count % 1000 == 0:
                    logger.info(f"Processed {updated_count}/{len(records)} records...")
            else:
                # No valid sources - keep existing frequency
                logger.warning(f"No valid sources for word: {term}")
                
        except Exception as e:
            logger.error(f"Error processing word {term} (ID: {word_id}): {e}")
            continue
    
    logger.info(f"Prepared {len(updates)} frequency updates")
    
    # Batch update the database
    logger.info("Updating database with new frequencies...")
    
    update_sql = """
        UPDATE word_frequencies_independent 
        SET independent_frequency = %s 
        WHERE word_id = %s
    """
    
    # Process in batches
    for i in range(0, len(updates), batch_size):
        batch = updates[i:i+batch_size]
        cursor.executemany(update_sql, batch)
        conn.commit()
        
        batch_num = (i // batch_size) + 1
        total_batches = (len(updates) + batch_size - 1) // batch_size
        logger.info(f"Updated batch {batch_num}/{total_batches} ({len(batch)} records)")
    
    # Recalculate rankings based on new frequencies
    logger.info("Recalculating frequency rankings...")
    
    # Get total count first
    cursor.execute("SELECT COUNT(*) FROM word_frequencies_independent")
    total_words = cursor.fetchone()[0]
    
    # Use a different approach for ranking
    cursor.execute("""
        SELECT word_id, independent_frequency 
        FROM word_frequencies_independent 
        ORDER BY independent_frequency DESC, word_id ASC
    """)
    
    ranked_words = cursor.fetchall()
    
    # Update rankings in batches
    rank_updates = [(rank + 1, word_id) for rank, (word_id, _) in enumerate(ranked_words)]
    
    cursor.executemany("""
        UPDATE word_frequencies_independent 
        SET frequency_rank = %s 
        WHERE word_id = %s
    """, rank_updates)
    
    # Recalculate rarity percentiles
    logger.info("Recalculating rarity percentiles...")
    
    cursor.execute("""
        UPDATE word_frequencies_independent 
        SET rarity_percentile = ROUND((frequency_rank / %s) * 100, 1)
    """, (total_words,))
    
    conn.commit()
    
    logger.info(f"Successfully recalculated frequencies for {updated_count} words")
    logger.info(f"New weights applied: {new_weights}")
    
    # Generate summary statistics
    cursor.execute("""
        SELECT 
            COUNT(*) as total_words,
            AVG(independent_frequency) as mean_freq,
            MIN(independent_frequency) as min_freq,
            MAX(independent_frequency) as max_freq,
            COUNT(*) - COUNT(CASE WHEN independent_frequency > 0 THEN 1 END) as zero_freq_count
        FROM word_frequencies_independent
    """)
    
    stats = cursor.fetchone()
    logger.info(f"SUMMARY STATISTICS:")
    logger.info(f"  Total words: {stats[0]:,}")
    logger.info(f"  Mean frequency: {stats[1]:.6f}")
    logger.info(f"  Min frequency: {stats[2]:.6f}")
    logger.info(f"  Max frequency: {stats[3]:.6f}")
    logger.info(f"  Words with zero frequency: {stats[4]:,}")
    
    cursor.close()
    conn.close()
    
    logger.info("Frequency recalculation complete!")

if __name__ == "__main__":
    recalculate_frequencies()