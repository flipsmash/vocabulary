#!/usr/bin/env python3
"""
Comprehensive similarity maintenance script.

Ensures all words have semantic similarity embeddings and pairwise similarities calculated.
Designed to be run regularly via cron to keep similarity data current.
"""

import sys
import argparse
import logging
from pathlib import Path
from datetime import datetime

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from analysis.definition_similarity_calculator import DefinitionSimilarityCalculator

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def main():
    parser = argparse.ArgumentParser(
        description='Maintain word similarity embeddings and calculations'
    )
    parser.add_argument(
        '--model',
        default='sentence-transformers/all-mpnet-base-v2',
        help='Embedding model to use (default: mpnet for higher quality)'
    )
    parser.add_argument(
        '--threshold',
        type=float,
        default=0.4,
        help='Minimum similarity threshold to store (default: 0.4)'
    )
    parser.add_argument(
        '--batch-size',
        type=int,
        default=5000,
        help='Batch size for similarity calculations (default: 5000, GPU efficient at >=5000)'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Show what would be done without making changes'
    )
    parser.add_argument(
        '--skip-embeddings',
        action='store_true',
        help='Skip embedding generation (only calculate similarities)'
    )
    parser.add_argument(
        '--skip-similarities',
        action='store_true',
        help='Skip similarity calculation (only generate embeddings)'
    )
    parser.add_argument(
        '--silent',
        action='store_true',
        help='Minimal output (for cron jobs)'
    )

    args = parser.parse_args()

    # Adjust logging for silent mode
    if args.silent:
        logging.getLogger().setLevel(logging.WARNING)

    start_time = datetime.now()

    if not args.silent:
        logger.info("=" * 80)
        logger.info("SIMILARITY MAINTENANCE")
        logger.info("=" * 80)
        logger.info(f"Model: {args.model}")
        logger.info(f"Threshold: {args.threshold}")
        logger.info(f"Batch size: {args.batch_size}")
        if args.dry_run:
            logger.info("DRY RUN MODE - No changes will be made")
        logger.info("")

    try:
        # Initialize calculator
        if not args.silent:
            logger.info("Initializing similarity calculator...")
        calculator = DefinitionSimilarityCalculator(model_name=args.model)

        # Ensure tables exist
        calculator.create_definition_tables()

        # Step 1: Get all definitions
        if not args.silent:
            logger.info("\nStep 1: Loading definitions from database...")
        definitions = calculator.get_definitions()
        total_words = len(definitions)

        if not args.silent:
            logger.info(f"Found {total_words:,} definitions")

        if total_words == 0:
            logger.error("No definitions found in database!")
            return 1

        # Step 2: Generate embeddings (if not skipped)
        if not args.skip_embeddings:
            if not args.silent:
                logger.info("\nStep 2: Checking for words missing embeddings...")

            # Find words without embeddings for this model
            words_without_embeddings = [
                d for d in definitions
                if d.embedding is None or len(d.embedding) == 0
            ]

            if words_without_embeddings:
                if args.dry_run:
                    logger.info(f"DRY RUN: Would generate embeddings for {len(words_without_embeddings):,} words")
                else:
                    if not args.silent:
                        logger.info(f"Generating embeddings for {len(words_without_embeddings):,} words...")
                        logger.info("This may take several minutes...")

                    calculator.generate_embeddings_batch(words_without_embeddings, batch_size=32)

                    if not args.silent:
                        logger.info("Storing embeddings in database...")
                    calculator.store_embeddings(words_without_embeddings)

                    if not args.silent:
                        logger.info(f"✓ Generated and stored embeddings for {len(words_without_embeddings):,} words")
            else:
                if not args.silent:
                    logger.info("✓ All words already have embeddings for this model")
        else:
            if not args.silent:
                logger.info("\nStep 2: Skipped (--skip-embeddings)")

        # Step 3: Calculate similarities (if not skipped)
        if not args.skip_similarities:
            if not args.silent:
                logger.info("\nStep 3: Calculating pairwise similarities...")
                logger.info(f"Threshold: {args.threshold} (only similarities >= {args.threshold} will be stored)")

            if args.dry_run:
                logger.info(f"DRY RUN: Would calculate similarities for {total_words:,} words")
                logger.info(f"         Estimated pairs: ~{total_words * (total_words - 1) // 2:,}")
            else:
                if not args.silent:
                    logger.info("This may take significant time for large vocabularies...")

                num_similarities = calculator.calculate_all_similarities(
                    similarity_threshold=args.threshold,
                    batch_size=args.batch_size
                )

                if not args.silent:
                    if num_similarities is not None:
                        logger.info(f"✓ Calculated and stored {num_similarities:,} similarity pairs")
                    else:
                        logger.warning("No embeddings found - unable to calculate similarities")
        else:
            if not args.silent:
                logger.info("\nStep 3: Skipped (--skip-similarities)")

        # Summary
        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()

        if not args.silent:
            logger.info("\n" + "=" * 80)
            logger.info("COMPLETE!")
            logger.info("=" * 80)
            logger.info(f"Duration: {duration:.1f} seconds")
            logger.info(f"Model: {args.model}")
            logger.info(f"Definitions processed: {total_words:,}")
            if not args.skip_embeddings:
                logger.info(f"Embeddings: {'(dry run)' if args.dry_run else 'Updated'}")
            if not args.skip_similarities:
                logger.info(f"Similarities: {'(dry run)' if args.dry_run else 'Updated'}")
            logger.info("")
        else:
            # Minimal output for cron
            if args.dry_run:
                print(f"DRY RUN: {total_words:,} words checked")
            else:
                print(f"✓ Similarity maintenance complete: {total_words:,} words, {duration:.1f}s")

        return 0

    except Exception as e:
        logger.error(f"Error during similarity maintenance: {e}", exc_info=not args.silent)
        return 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        logger.info("\nInterrupted by user")
        sys.exit(1)
