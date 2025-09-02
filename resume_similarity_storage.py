#!/usr/bin/env python3
"""
Resume similarity calculation and storage with chunked database inserts
Handles the 12.88 million similarity pairs with connection timeout protection
"""

from definition_similarity_calculator import DefinitionSimilarityCalculator
from config import get_db_config
import mysql.connector
import time
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class ChunkedSimilarityInserter:
    """Handle massive similarity insertions with chunked approach"""
    
    def __init__(self, db_config, chunk_size=50000):
        self.db_config = db_config
        self.chunk_size = chunk_size
        
    def get_connection(self):
        """Get database connection with extended timeouts"""
        config = self.db_config.copy()
        config.update({
            'connection_timeout': 300,  # 5 minutes
            'autocommit': False,
        })
        return mysql.connector.connect(**config)
    
    def get_stored_similarity_count(self):
        """Check how many similarities are already stored"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM definition_similarity")
            return cursor.fetchone()[0]
    
    def store_similarities_chunked(self, similarities, start_idx=0):
        """Store similarities in chunks to avoid timeout"""
        
        total_similarities = len(similarities)
        stored_count = self.get_stored_similarity_count()
        
        print(f"Total similarities to store: {total_similarities:,}")
        print(f"Already stored: {stored_count:,}")
        print(f"Starting from index: {start_idx:,}")
        print(f"Chunk size: {self.chunk_size:,}")
        
        chunks_total = (total_similarities - start_idx + self.chunk_size - 1) // self.chunk_size
        
        for chunk_num in range(chunks_total):
            chunk_start = start_idx + (chunk_num * self.chunk_size)
            chunk_end = min(chunk_start + self.chunk_size, total_similarities)
            
            if chunk_start >= total_similarities:
                break
            
            chunk = similarities[chunk_start:chunk_end]
            
            print(f"\nProcessing chunk {chunk_num + 1}/{chunks_total}")
            print(f"  Range: {chunk_start:,} - {chunk_end-1:,}")
            print(f"  Size: {len(chunk):,} records")
            
            try:
                start_time = time.time()
                
                with self.get_connection() as conn:
                    cursor = conn.cursor()
                    
                    # Prepare insert query
                    insert_query = """
                    INSERT IGNORE INTO definition_similarity 
                    (word1_id, word2_id, cosine_similarity, embedding_model)
                    VALUES (%s, %s, %s, %s)
                    """
                    
                    # Convert to tuples for insertion
                    data = [(s.word1_id, s.word2_id, s.cosine_similarity, s.model_name) 
                           for s in chunk]
                    
                    # Execute batch insert
                    cursor.executemany(insert_query, data)
                    conn.commit()
                    
                elapsed = time.time() - start_time
                rate = len(chunk) / elapsed
                
                # Update progress
                total_stored = stored_count + ((chunk_num + 1) * self.chunk_size)
                progress = min(total_stored / total_similarities * 100, 100)
                
                print(f"  Completed in {elapsed:.1f}s ({rate:,.0f} records/sec)")
                print(f"  Progress: {total_stored:,}/{total_similarities:,} ({progress:.1f}%)")
                
                # Brief pause to prevent overwhelming the database
                time.sleep(0.5)
                
            except mysql.connector.Error as e:
                print(f"  Error in chunk {chunk_num + 1}: {e}")
                print(f"  You can restart from chunk {chunk_num + 1} (index {chunk_start})")
                return False
            except Exception as e:
                print(f"  Unexpected error in chunk {chunk_num + 1}: {e}")
                return False
        
        final_count = self.get_stored_similarity_count()
        print(f"\nStorage completed!")
        print(f"Total similarities now in database: {final_count:,}")
        return True

def resume_similarity_calculation():
    """Resume the similarity calculation and storage process"""
    
    print("=== Resuming Similarity Storage with Chunked Approach ===")
    print("=" * 65)
    
    calculator = DefinitionSimilarityCalculator(get_db_config())
    
    # Check current status
    embeddings = calculator.load_embeddings()
    stored_count = ChunkedSimilarityInserter(get_db_config()).get_stored_similarity_count()
    
    print(f"Definitions with embeddings: {len(embeddings):,}")
    print(f"Similarities already stored: {stored_count:,}")
    
    if len(embeddings) < 21000:
        print("ERROR: Not enough embeddings. Run embedding generation first.")
        return False
    
    print(f"\nRecalculating similarities (this will find ~12.88 million pairs)...")
    
    # Recalculate similarities (this is fast since embeddings are loaded)
    start_time = time.time()
    
    similarities = calculator.calculate_all_similarities(
        similarity_threshold=0.3,
        batch_size=1500  # Conservative batch size
    )
    
    calc_time = time.time() - start_time
    
    print(f"Similarity calculation completed in {calc_time/60:.1f} minutes")
    print(f"Found {len(similarities):,} high-quality pairs")
    
    if not similarities:
        print("No similarities found - something went wrong")
        return False
    
    # Now store with chunked approach
    print(f"\nStarting chunked storage process...")
    
    inserter = ChunkedSimilarityInserter(get_db_config(), chunk_size=25000)  # Smaller chunks for safety
    success = inserter.store_similarities_chunked(similarities)
    
    if success:
        final_count = inserter.get_stored_similarity_count()
        total_possible = len(embeddings) * (len(embeddings) - 1) // 2
        
        print(f"\n🎉 SUCCESS!")
        print(f"Stored: {final_count:,} similarity pairs")
        print(f"Total possible: {total_possible:,}")
        print(f"Coverage: {final_count/total_possible*100:.4f}% above threshold")
        print(f"\nYou now have maximum semantic coverage!")
        
        return True
    else:
        print(f"\n❌ Storage failed - but can be resumed")
        return False

def main():
    """Main function"""
    success = resume_similarity_calculation()
    return 0 if success else 1

if __name__ == "__main__":
    exit(main())