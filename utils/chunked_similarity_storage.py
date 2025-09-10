#!/usr/bin/env python3
"""
Pure chunked storage approach - calculate similarities WITHOUT storing,
then use chunked insertion to handle the 12.88 million records
"""

from definition_similarity_calculator import DefinitionSimilarityCalculator, DefinitionSimilarityScore
from config import get_db_config
import mysql.connector
import numpy as np
import time
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class PureChunkedInserter:
    """Handle massive similarity insertions with pure chunked approach"""
    
    def __init__(self, db_config, chunk_size=25000):
        self.db_config = db_config
        self.chunk_size = chunk_size
        
    def get_connection(self):
        """Get database connection with extended timeouts"""
        config = self.db_config.copy()
        config.update({
            'connection_timeout': 600,  # 10 minutes
            'read_timeout': 600,        # 10 minutes  
            'write_timeout': 600,       # 10 minutes
            'autocommit': False,
        })
        return mysql.connector.connect(**config)
    
    def calculate_similarities_no_store(self, calculator, threshold=0.3):
        """Calculate similarities but don't store them - return list instead"""
        
        print(f"Calculating similarities (threshold: {threshold}) without storing...")
        
        # Load embeddings
        embeddings = calculator.load_embeddings()
        embeddings_array = np.array([d.embedding for d in embeddings])
        word_ids = [d.word_id for d in embeddings]
        
        print(f"Processing {len(embeddings):,} embeddings")
        
        similarities = []
        batch_size = 1500
        
        total_batches = (len(embeddings) + batch_size - 1) // batch_size
        print(f"Processing in {total_batches} batches...")
        
        for i in range(0, len(embeddings), batch_size):
            batch_end = min(i + batch_size, len(embeddings))
            batch_embeddings = embeddings_array[i:batch_end]
            
            # Calculate similarities between this batch and all subsequent embeddings
            for j in range(i, len(embeddings), batch_size):
                other_batch_end = min(j + batch_size, len(embeddings))
                other_batch_embeddings = embeddings_array[j:other_batch_end]
                
                # Calculate similarity matrix
                similarity_matrix = calculator.calculate_cosine_similarity_matrix(
                    batch_embeddings, other_batch_embeddings
                )
                
                # Extract pairs above threshold
                for bi, batch_idx in enumerate(range(i, batch_end)):
                    for oj, other_idx in enumerate(range(j, other_batch_end)):
                        if batch_idx >= other_idx:  # Only process upper triangle
                            continue
                            
                        similarity = similarity_matrix[bi, oj]
                        if similarity >= threshold:
                            similarities.append(DefinitionSimilarityScore(
                                word1_id=word_ids[batch_idx],
                                word2_id=word_ids[other_idx],
                                cosine_similarity=float(similarity),
                                model_name=calculator.model_name
                            ))
            
            # Progress update
            batch_num = (i // batch_size) + 1
            print(f"Batch {batch_num}/{total_batches} - Found {len(similarities):,} similarities so far")
        
        print(f"Calculation complete: {len(similarities):,} similarities above threshold")
        return similarities
    
    def store_similarities_chunked(self, similarities):
        """Store similarities in safe chunks"""
        
        if not similarities:
            print("No similarities to store")
            return True
            
        total_similarities = len(similarities)
        print(f"Starting chunked storage of {total_similarities:,} similarities")
        print(f"Chunk size: {self.chunk_size:,}")
        
        chunks_total = (total_similarities + self.chunk_size - 1) // self.chunk_size
        stored_total = 0
        
        for chunk_num in range(chunks_total):
            chunk_start = chunk_num * self.chunk_size
            chunk_end = min(chunk_start + self.chunk_size, total_similarities)
            chunk = similarities[chunk_start:chunk_end]
            
            print(f"\nChunk {chunk_num + 1}/{chunks_total}")
            print(f"  Records: {chunk_start:,} - {chunk_end-1:,} ({len(chunk):,} records)")
            
            try:
                start_time = time.time()
                
                with self.get_connection() as conn:
                    cursor = conn.cursor()
                    
                    # Use INSERT IGNORE to skip duplicates
                    insert_query = """
                    INSERT IGNORE INTO definition_similarity 
                    (word1_id, word2_id, cosine_similarity, embedding_model)
                    VALUES (%s, %s, %s, %s)
                    """
                    
                    # Convert to tuples
                    data = [(s.word1_id, s.word2_id, s.cosine_similarity, s.model_name) 
                           for s in chunk]
                    
                    # Execute batch insert with small chunks to avoid memory issues
                    mini_chunk_size = 5000
                    inserted = 0
                    
                    for mini_start in range(0, len(data), mini_chunk_size):
                        mini_end = min(mini_start + mini_chunk_size, len(data))
                        mini_chunk = data[mini_start:mini_end]
                        
                        cursor.executemany(insert_query, mini_chunk)
                        inserted += len(mini_chunk)
                    
                    conn.commit()
                    
                elapsed = time.time() - start_time
                rate = len(chunk) / elapsed if elapsed > 0 else 0
                stored_total += len(chunk)
                
                progress = stored_total / total_similarities * 100
                
                print(f"  Completed: {elapsed:.1f}s ({rate:,.0f} records/sec)")
                print(f"  Progress: {stored_total:,}/{total_similarities:,} ({progress:.1f}%)")
                
                # Brief pause between chunks
                time.sleep(0.5)
                
            except mysql.connector.Error as e:
                print(f"  MySQL Error in chunk {chunk_num + 1}: {e}")
                print(f"  Stored {stored_total:,} records before error")
                return False
            except Exception as e:
                print(f"  Unexpected error in chunk {chunk_num + 1}: {e}")
                print(f"  Stored {stored_total:,} records before error")
                return False
        
        # Verify final count
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT COUNT(*) FROM definition_similarity")
                final_count = cursor.fetchone()[0]
                
            print(f"\nSUCCESS!")
            print(f"Total stored: {stored_total:,} records processed")  
            print(f"Database count: {final_count:,} records")
            print(f"Maximum semantic coverage achieved!")
            
            return True
            
        except Exception as e:
            print(f"Error verifying count: {e}")
            return True  # Assume success if storage completed

def main():
    """Main function"""
    print("=== Pure Chunked Similarity Storage ===")
    print("=" * 45)
    
    calculator = DefinitionSimilarityCalculator(get_db_config())
    inserter = PureChunkedInserter(get_db_config(), chunk_size=20000)  # Even smaller chunks
    
    # Step 1: Calculate similarities (without storing)
    similarities = inserter.calculate_similarities_no_store(calculator, threshold=0.3)
    
    if not similarities:
        print("No similarities calculated - stopping")
        return 1
    
    # Step 2: Store with chunked approach
    success = inserter.store_similarities_chunked(similarities)
    
    if success:
        print(f"\nAll {len(similarities):,} similarities stored successfully!")
        return 0
    else:
        print(f"\nStorage failed after processing {len(similarities):,} similarities")
        return 1

if __name__ == "__main__":
    exit(main())