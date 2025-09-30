#!/usr/bin/env python3
"""
Process all 21,724 definitions - Windows-compatible version
"""

from definition_similarity_calculator import DefinitionSimilarityCalculator
from config import get_db_config
import logging
import time

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def main():
    """Process all definitions with maximum coverage"""
    
    print("Processing ALL 21,724 definitions for maximum semantic coverage")
    print("=" * 65)
    
    calculator = DefinitionSimilarityCalculator(get_db_config())
    
    # Get all definitions
    print("Loading all definitions...")
    all_definitions = calculator.get_definitions()  # No limit = all definitions
    print(f"Total definitions to process: {len(all_definitions):,}")
    
    # Check current embeddings
    current_embeddings = calculator.load_embeddings()
    print(f"Current embeddings in database: {len(current_embeddings):,}")
    
    if len(current_embeddings) >= len(all_definitions) - 100:  # Allow some tolerance
        print("Most definitions already processed. Proceeding to similarity calculation...")
    else:
        print(f"Need to process {len(all_definitions) - len(current_embeddings):,} more definitions")
        print("Starting embedding generation (this will take 5-8 minutes)...")
        
        start_time = time.time()
        
        # Generate embeddings with larger batch size for efficiency
        calculator.generate_embeddings_batch(all_definitions, batch_size=64)
        
        # Store embeddings
        calculator.store_embeddings(all_definitions)
        
        elapsed = time.time() - start_time
        print(f"Embedding generation completed in {elapsed/60:.1f} minutes")
    
    # Now calculate similarities
    print("\nCalculating similarities between all definition pairs...")
    
    # Reload embeddings to get current count
    embeddings = calculator.load_embeddings()
    total_pairs = len(embeddings) * (len(embeddings) - 1) // 2
    
    print(f"Definitions: {len(embeddings):,}")
    print(f"Total comparisons: {total_pairs:,}")
    
    # Use threshold of 0.25 for large dataset (good quality matches)
    threshold = 0.25
    print(f"Similarity threshold: {threshold}")
    
    start_time = time.time()
    
    # Calculate similarities
    similarities = calculator.calculate_all_similarities(
        similarity_threshold=threshold,
        batch_size=2000
    )
    
    elapsed = time.time() - start_time
    
    print(f"\nCOMPLETE!")
    print(f"Found {len(similarities):,} high-quality semantic pairs")
    print(f"Processing time: {elapsed/60:.1f} minutes")
    print(f"Match rate: {len(similarities)/total_pairs*100:.3f}% above threshold")
    print("\nYou now have maximum coverage for semantic distractors!")

if __name__ == "__main__":
    main()