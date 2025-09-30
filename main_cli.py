#!/usr/bin/env python3
"""
Main CLI Entry Point - Fixed Version
Uses the existing working cuda_enhanced_cli directly
"""

import argparse
import sys
import logging
from pathlib import Path
from datetime import datetime

# Add the package to path
sys.path.insert(0, str(Path(__file__).parent))

def main():
    """Main entry point - simplified to use cuda_enhanced_cli directly"""
    
    # Show help if no arguments provided
    if len(sys.argv) == 1:
        print("Vocabulary Pronunciation Similarity System")
        print("=" * 55)
        print("Use cuda_enhanced_cli.py for pronunciation similarity operations:")
        print("  python cuda_enhanced_cli.py --help")
        print()
        print("For definition similarity:")
        print("  python definition_similarity_calculator.py")
        print()
        print("Or use direct commands:")
        return 0
    
    # Parse basic arguments for definition similarity and ingestion
    parser = argparse.ArgumentParser(description='Vocabulary System CLI')
    parser.add_argument('--find-semantic-distractors', type=int, metavar='WORD_ID',
                       help='Find semantic distractors for a word')
    parser.add_argument('--process-definitions', action='store_true',
                       help='Process definitions and create embeddings')
    parser.add_argument('--calculate-definition-similarities', action='store_true',
                       help='Calculate definition similarities')
    parser.add_argument('--similarity-threshold', type=float, default=0.3,
                       help='Similarity threshold for definition similarities')
    parser.add_argument('--fill-missing-definitions', action='store_true',
                       help='Fill NULL/empty definitions using the lookup system')
    parser.add_argument('--fill-limit', type=int, default=None,
                       help='Limit the number of rows scanned when filling definitions')
    parser.add_argument('--fill-dry-run', action='store_true',
                       help='Preview definition fixes without modifying the database')
    # Legacy ingestion options (experimental system was moved to abandoned/)
    # Use the current harvesting system instead: gutenberg_harvester.py, wiktionary_harvester.py, etc.
    
    args = parser.parse_args()
    
    try:
        if args.process_definitions:
            from analysis.definition_similarity_calculator import DefinitionSimilarityCalculator
            from core.config import get_db_config
            
            print("[INFO] Processing word definitions...")
            calculator = DefinitionSimilarityCalculator(get_db_config())
            calculator.create_definition_tables()
            definitions = calculator.get_definitions()
            print(f"Processing {len(definitions)} definitions")
            calculator.generate_embeddings_batch(definitions)
            calculator.store_embeddings(definitions)
            print("[OK] Definition processing complete")
            
        elif args.calculate_definition_similarities:
            from analysis.definition_similarity_calculator import DefinitionSimilarityCalculator
            from core.config import get_db_config

            print(f"[INFO] Calculating definition similarities (threshold: {args.similarity_threshold})")
            calculator = DefinitionSimilarityCalculator(get_db_config())
            similarities = calculator.calculate_all_similarities(args.similarity_threshold)
            print(f"[OK] Found {len(similarities)} semantic similarity pairs")

        elif args.fill_missing_definitions:
            import logging
            from core.definition_filler import fill_missing_definitions

            logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

            print("[INFO] Filling missing definitions ...")
            summary = fill_missing_definitions(
                limit=args.fill_limit,
                dry_run=args.fill_dry_run,
            )
            print(
                f"[OK] Looked up {summary.looked_up} terms | "
                f"Updated {summary.updated} | Inserted {summary.inserted} | "
                f"Skipped {summary.skipped}"
            )

        # Removed experimental ingestion system - moved to abandoned/experimental_ingestion/
        # Use current harvesting system instead: gutenberg_harvester.py, wiktionary_harvester.py, etc.

        elif args.find_semantic_distractors:
            from core.config import get_db_config
            import mysql.connector
            
            word_id = args.find_semantic_distractors
            print(f"[INFO] Finding semantic distractors for word ID {word_id}")
            
            conn = mysql.connector.connect(**get_db_config())
            cursor = conn.cursor()
            
            # Get word name
            cursor.execute("SELECT term FROM defined WHERE id = %s", (word_id,))
            result = cursor.fetchone()
            if not result:
                print("Word not found")
                return 1
            
            word = result[0]
            print(f"Target word: '{word}'")
            
            # Find semantic similarities
            cursor.execute("""
            SELECT d.term, ds.cosine_similarity, d.definition
            FROM definition_similarity ds
            JOIN defined d ON (
                (ds.word1_id = %s AND ds.word2_id = d.id) OR
                (ds.word2_id = %s AND ds.word1_id = d.id)
            )
            WHERE d.id != %s
            ORDER BY ds.cosine_similarity DESC
            LIMIT 5
            """, (word_id, word_id, word_id))
            
            distractors = cursor.fetchall()
            conn.close()
            
            if distractors:
                print(f"\nSemantic distractors:")
                for i, (d_word, similarity, definition) in enumerate(distractors, 1):
                    print(f"{i}. {d_word} (similarity: {similarity:.3f})")
                    print(f"   {definition[:80]}...")
                    print()
            else:
                print("No semantic distractors found")
        
        else:
            print("For pronunciation similarity operations, use:")
            print("  python cuda_enhanced_cli.py --help")
            print("\nIngestion examples:")
            print("  python main_cli.py --ingest-run rss --ingest-limit 200")
            print("  python main_cli.py --ingest-run arxiv --ingest-limit 200")
            print("  python main_cli.py --ingest-run github --ingest-limit 50")
            
        return 0
        
    except Exception as e:
        print(f"[ERROR] {e}")
        return 1

if __name__ == "__main__":
    sys.exit(main())
