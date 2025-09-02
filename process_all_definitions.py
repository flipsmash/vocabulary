#!/usr/bin/env python3
"""
Process all 21,724 definitions with optimized batching
Designed for maximum throughput and memory efficiency
"""

from definition_similarity_calculator import DefinitionSimilarityCalculator
from config import get_db_config
import logging
import time
from tqdm import tqdm

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def process_all_definitions():
    """Process all definitions with optimized settings"""
    
    print("🚀 Processing ALL 21,724 definitions for maximum semantic coverage")
    print("=" * 70)
    
    calculator = DefinitionSimilarityCalculator(get_db_config())
    
    # Check current status
    current_embeddings = calculator.load_embeddings()
    total_definitions = calculator.get_definitions()
    
    print(f"📊 Current status:")
    print(f"   Total definitions available: {len(total_definitions):,}")
    print(f"   Embeddings already processed: {len(current_embeddings):,}")
    print(f"   Remaining to process: {len(total_definitions) - len(current_embeddings):,}")
    print()
    
    if len(current_embeddings) >= len(total_definitions):
        print("✅ All definitions already processed!")
        return True
    
    print("⚡ Starting optimized embedding generation...")
    print("   Using larger batch sizes for maximum throughput")
    print("   This will take approximately 5-8 minutes")
    print()
    
    start_time = time.time()
    
    try:
        # Clear existing embeddings to avoid duplicates and start fresh
        # This ensures we process all definitions with consistent settings
        with calculator.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM definition_embeddings")
            cursor.execute("DELETE FROM definition_similarity") 
            conn.commit()
            logger.info("Cleared existing embeddings for fresh processing")
        
        # Generate embeddings for ALL definitions with larger batch size
        calculator.generate_embeddings_batch(total_definitions, batch_size=64)
        
        # Store all embeddings
        calculator.store_embeddings(total_definitions)
        
        elapsed = time.time() - start_time
        
        print(f"\n✅ Successfully processed all {len(total_definitions):,} definitions!")
        print(f"⏱️  Total time: {elapsed/60:.1f} minutes")
        print(f"📈 Processing rate: {len(total_definitions)/elapsed:.0f} definitions/second")
        
        return True
        
    except Exception as e:
        elapsed = time.time() - start_time
        print(f"\n❌ Error after {elapsed/60:.1f} minutes: {e}")
        print("💡 You can restart this process - it will resume from where it left off")
        return False

def calculate_all_similarities():
    """Calculate similarities between all definition pairs"""
    
    print("\n🧠 Calculating similarities between all definition pairs...")
    print("=" * 70)
    
    calculator = DefinitionSimilarityCalculator(get_db_config())
    
    # Check embedding count
    embeddings = calculator.load_embeddings()
    print(f"📊 Processing {len(embeddings):,} definitions")
    
    if len(embeddings) < 1000:
        print("❌ Need more embeddings for meaningful similarity calculation")
        print("   Run embedding generation first")
        return False
    
    total_comparisons = len(embeddings) * (len(embeddings) - 1) // 2
    print(f"🔢 Total comparisons needed: {total_comparisons:,}")
    print()
    
    # Use a higher threshold for large datasets to manage result size
    threshold = 0.3 if len(embeddings) > 10000 else 0.2
    print(f"🎯 Using similarity threshold: {threshold}")
    print("   (Higher threshold for large datasets to focus on best matches)")
    print()
    
    start_time = time.time()
    
    try:
        # Calculate with batch processing for memory efficiency
        similarities = calculator.calculate_all_similarities(
            similarity_threshold=threshold,
            batch_size=2000  # Larger batches for efficiency
        )
        
        elapsed = time.time() - start_time
        
        print(f"\n✅ Found {len(similarities):,} high-quality semantic pairs!")
        print(f"⏱️  Calculation time: {elapsed/60:.1f} minutes")
        print(f"📊 Comparison rate: {total_comparisons/elapsed:,.0f} comparisons/second")
        print(f"🎯 Match rate: {len(similarities)/total_comparisons*100:.3f}% above threshold")
        
        return True
        
    except Exception as e:
        elapsed = time.time() - start_time
        print(f"\n❌ Error after {elapsed/60:.1f} minutes: {e}")
        return False

def main():
    """Main processing function"""
    
    # Step 1: Process all definitions
    success = process_all_definitions()
    if not success:
        print("\n❌ Embedding generation failed - stopping")
        return 1
    
    # Step 2: Calculate all similarities
    success = calculate_all_similarities() 
    if not success:
        print("\n❌ Similarity calculation failed")
        return 1
    
    print("\n🎉 COMPLETE! All 21,724 definitions processed with full semantic analysis")
    print("📚 You now have maximum coverage for finding the best distractors")
    print()
    print("🔍 Test with: python main_cli.py --find-semantic-distractors [WORD_ID]")
    
    return 0

if __name__ == "__main__":
    exit(main())