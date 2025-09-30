#!/usr/bin/env python3
"""
Process all definitions in manageable chunks to avoid MySQL limits
"""

from definition_similarity_calculator import DefinitionSimilarityCalculator
from config import get_db_config
import logging
import time

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def process_definitions_in_chunks():
    """Process all definitions in chunks to avoid MySQL limits"""
    
    calculator = DefinitionSimilarityCalculator(get_db_config())
    
    # Get all definitions
    all_definitions = calculator.get_definitions()
    current_embeddings = calculator.load_embeddings()
    
    print(f"Total definitions: {len(all_definitions):,}")
    print(f"Current embeddings: {len(current_embeddings):,}")
    
    if len(current_embeddings) >= len(all_definitions) - 100:
        print("Embeddings are mostly complete. Proceeding to similarity calculation...")
        return calculate_similarities(calculator)
    
    print(f"Processing {len(all_definitions):,} definitions in chunks...")
    
    # Process in chunks of 2000 definitions
    chunk_size = 2000
    total_processed = len(current_embeddings)
    
    start_idx = total_processed  # Resume from where we left off
    
    for i in range(start_idx, len(all_definitions), chunk_size):
        chunk_end = min(i + chunk_size, len(all_definitions))
        chunk = all_definitions[i:chunk_end]
        
        print(f"\nProcessing chunk {i//chunk_size + 1}: definitions {i:,}-{chunk_end-1:,}")
        print(f"Chunk size: {len(chunk)} definitions")
        
        try:
            start_time = time.time()
            
            # Generate embeddings for this chunk
            calculator.generate_embeddings_batch(chunk, batch_size=64)
            
            # Store embeddings for this chunk
            calculator.store_embeddings(chunk)
            
            elapsed = time.time() - start_time
            total_processed += len(chunk)
            
            print(f"Chunk completed in {elapsed:.1f}s")
            print(f"Total progress: {total_processed:,}/{len(all_definitions):,} ({total_processed/len(all_definitions)*100:.1f}%)")
            
        except Exception as e:
            print(f"Error processing chunk {i//chunk_size + 1}: {e}")
            print("You can restart this script - it will resume from where it left off")
            return False
    
    print(f"\nEmbedding generation complete! Processed {total_processed:,} definitions")
    
    # Now calculate similarities
    return calculate_similarities(calculator)

def calculate_similarities(calculator):
    """Calculate similarities with optimized settings"""
    
    print("\nCalculating similarities...")
    
    embeddings = calculator.load_embeddings()
    total_pairs = len(embeddings) * (len(embeddings) - 1) // 2
    
    print(f"Definitions with embeddings: {len(embeddings):,}")
    print(f"Total comparisons needed: {total_pairs:,}")
    
    # Use higher threshold for very large datasets
    threshold = 0.3 if len(embeddings) > 15000 else 0.25
    print(f"Using similarity threshold: {threshold}")
    
    try:
        start_time = time.time()
        
        similarities = calculator.calculate_all_similarities(
            similarity_threshold=threshold,
            batch_size=1500  # Smaller batches to be safe
        )
        
        elapsed = time.time() - start_time
        
        print(f"\nSimilarity calculation complete!")
        print(f"Found: {len(similarities):,} high-quality semantic pairs")
        print(f"Processing time: {elapsed/60:.1f} minutes")
        print(f"Match rate: {len(similarities)/total_pairs*100:.4f}% above threshold")
        
        return True
        
    except Exception as e:
        print(f"Error during similarity calculation: {e}")
        return False

def main():
    """Main function"""
    print("Processing all definitions with chunked approach")
    print("=" * 55)
    
    success = process_definitions_in_chunks()
    
    if success:
        print("\n=== COMPLETE ===")
        print("All definitions processed with maximum semantic coverage!")
        print("Test with: python main_cli.py --find-semantic-distractors [WORD_ID]")
    else:
        print("\n=== FAILED ===")
        print("Process failed but can be restarted to resume")
    
    return 0 if success else 1

if __name__ == "__main__":
    exit(main())