#!/usr/bin/env python3
"""
Update vocab.defined table entries with missing definitions.

Fetches definitions from dictionaryapi.dev API for words that have:
- NULL definitions
- Empty string definitions

Matches both term AND part_of_speech when updating from API data.
"""

import sys
import logging
import argparse
import asyncio
from pathlib import Path
from typing import List, Dict, Optional, Tuple
from datetime import datetime

import httpx

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from core.database_manager import db_manager

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class DefinitionUpdater:
    """Updates missing definitions from dictionaryapi.dev API."""

    def __init__(self, dry_run: bool = False):
        self.dry_run = dry_run
        self.stats = {
            'found': 0,
            'updated': 0,
            'moved_to_no_definition': 0,
            'errors': 0,
            'skipped_already_processed': 0
        }
        self._ensure_no_definition_table()

    def _ensure_no_definition_table(self):
        """Ensure the no_definition table exists."""
        create_table_sql = """
            CREATE TABLE IF NOT EXISTS vocab.no_definition (
                id SERIAL PRIMARY KEY,
                term VARCHAR(255) NOT NULL,
                part_of_speech VARCHAR(50) NOT NULL,
                reason TEXT NOT NULL,
                date_moved TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(term, part_of_speech)
            );
            CREATE INDEX IF NOT EXISTS idx_no_definition_term ON vocab.no_definition(term);
        """
        try:
            with db_manager.get_connection() as conn:
                conn.execute(create_table_sql)
            logger.debug("Ensured vocab.no_definition table exists")
        except Exception as e:
            logger.warning(f"Could not ensure no_definition table: {e}")

    def is_already_processed(self, term: str, pos: str) -> bool:
        """Check if term+POS already exists in no_definition table (idempotency)."""
        query = """
            SELECT COUNT(*) FROM vocab.no_definition
            WHERE term = %s AND part_of_speech = %s
        """
        with db_manager.get_cursor() as cursor:
            cursor.execute(query, (term, pos))
            count = cursor.fetchone()[0]
            return count > 0

    def get_words_missing_definitions(self) -> List[Dict]:
        """Find all words with NULL or empty definitions."""
        query = """
            SELECT id, term, part_of_speech, definition
            FROM vocab.defined
            WHERE definition IS NULL OR definition = ''
            ORDER BY term
        """

        with db_manager.get_cursor(dictionary=True) as cursor:
            cursor.execute(query)
            results = cursor.fetchall()

        logger.info(f"Found {len(results)} words with missing definitions")
        return results

    async def fetch_from_api(self, term: str, http_client: httpx.AsyncClient) -> Optional[List[Dict]]:
        """Fetch word data from dictionaryapi.dev API."""
        url = f"https://api.dictionaryapi.dev/api/v2/entries/en/{term}"

        try:
            response = await http_client.get(url, timeout=20.0)
            response.raise_for_status()
            data = response.json()
            return data
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                logger.debug(f"Word not found in API: {term}")
                return None
            logger.error(f"HTTP error for {term}: {e}")
            return None
        except Exception as e:
            logger.error(f"Error fetching {term}: {e}")
            return None

    def extract_definition_for_pos(self, api_data: List[Dict], target_pos: str) -> Optional[str]:
        """
        Extract definition matching the target part of speech.

        Returns the first definition that matches the POS, or None if no match.
        """
        # Normalize POS for comparison
        target_pos_lower = target_pos.lower().strip()

        # Common POS mappings
        pos_mappings = {
            'n': 'noun',
            'v': 'verb',
            'adj': 'adjective',
            'adv': 'adverb',
            'prep': 'preposition',
            'conj': 'conjunction',
            'pron': 'pronoun',
            'interj': 'interjection'
        }

        # Expand target POS if abbreviated
        normalized_target = pos_mappings.get(target_pos_lower, target_pos_lower)

        for entry in api_data:
            meanings = entry.get('meanings', [])
            for meaning in meanings:
                api_pos = meaning.get('partOfSpeech', '').lower().strip()

                # Check for exact match or if target matches the full form
                if api_pos == normalized_target or api_pos == target_pos_lower:
                    definitions = meaning.get('definitions', [])
                    if definitions:
                        # Return the first definition
                        return definitions[0].get('definition', '').strip()

        return None

    def move_to_no_definition(self, word_id: int, term: str, pos: str, reason: str) -> bool:
        """
        Move a word from vocab.defined to vocab.no_definition.

        Uses a transaction to ensure atomicity - either both operations succeed or neither does.
        """
        if self.dry_run:
            logger.info(f"  DRY RUN - Would move '{term}' ({pos}) to no_definition: {reason}")
            self.stats['moved_to_no_definition'] += 1
            return True

        try:
            # Use a single transaction for both operations
            with db_manager.get_connection() as conn:
                with conn.cursor() as cursor:
                    # Insert into no_definition
                    cursor.execute(
                        """
                        INSERT INTO vocab.no_definition (term, part_of_speech, reason)
                        VALUES (%s, %s, %s)
                        ON CONFLICT (term, part_of_speech) DO NOTHING
                        """,
                        (term, pos, reason)
                    )

                    # Delete from defined (with CASCADE to handle foreign keys)
                    cursor.execute(
                        """
                        DELETE FROM vocab.defined
                        WHERE id = %s
                        """,
                        (word_id,)
                    )
                # Transaction commits automatically when connection context exits

            self.stats['moved_to_no_definition'] += 1
            logger.info(f"  ✓ Moved to no_definition: {reason}")
            return True

        except Exception as e:
            self.stats['errors'] += 1
            logger.error(f"  Error moving {term} to no_definition: {e}")
            return False

    async def update_word(
        self,
        word_id: int,
        term: str,
        pos: str,
        http_client: httpx.AsyncClient
    ) -> bool:
        """
        Update a single word's definition from API, or move to no_definition if not found.

        Returns True if processed (updated or moved), False if error.
        """
        logger.info(f"Processing: {term} ({pos})")

        # Check if already processed (idempotency)
        if self.is_already_processed(term, pos):
            self.stats['skipped_already_processed'] += 1
            logger.debug(f"  Skipping: already in no_definition table")
            return True

        # Fetch from API
        api_data = await self.fetch_from_api(term, http_client)

        if not api_data:
            # No API data - move to no_definition
            logger.warning(f"  No API data found for: {term}")
            return self.move_to_no_definition(word_id, term, pos, "not_found_in_api")

        # Extract definition matching POS
        definition = self.extract_definition_for_pos(api_data, pos)

        if not definition:
            # API has data but not for this POS - move to no_definition
            logger.warning(f"  No matching POS '{pos}' found in API data for: {term}")
            return self.move_to_no_definition(word_id, term, pos, "no_matching_pos")

        # Update database
        if self.dry_run:
            logger.info(f"  DRY RUN - Would update '{term}' ({pos}): {definition[:100]}...")
            self.stats['updated'] += 1
            return True

        try:
            update_query = """
                UPDATE vocab.defined
                SET definition = %s,
                    definition_updated = CURRENT_TIMESTAMP
                WHERE id = %s
            """

            with db_manager.get_cursor() as cursor:
                cursor.execute(update_query, (definition, word_id))

            self.stats['updated'] += 1
            logger.info(f"  ✓ Updated: {definition[:100]}...")
            return True

        except Exception as e:
            self.stats['errors'] += 1
            logger.error(f"  Error updating {term}: {e}")
            return False

    async def process_all(self, batch_size: int = 5, delay: float = 2.0):
        """Process all words with missing definitions."""
        words = self.get_words_missing_definitions()

        if not words:
            logger.info("No words with missing definitions found")
            return

        logger.info(f"Processing {len(words)} words...")
        if self.dry_run:
            logger.info("DRY RUN MODE - No changes will be made")

        async with httpx.AsyncClient() as client:
            # Process in batches to avoid overwhelming the API
            for i in range(0, len(words), batch_size):
                batch = words[i:i + batch_size]

                # Process batch
                tasks = []
                for word in batch:
                    task = self.update_word(
                        word['id'],
                        word['term'],
                        word['part_of_speech'],
                        client
                    )
                    tasks.append(task)

                await asyncio.gather(*tasks)

                # Delay between batches
                if i + batch_size < len(words):
                    logger.debug(f"Batch complete. Waiting {delay}s before next batch...")
                    await asyncio.sleep(delay)

        # Print summary
        self._print_summary()

    def _print_summary(self):
        """Print processing summary."""
        logger.info("")
        logger.info("=" * 60)
        logger.info("SUMMARY")
        logger.info("=" * 60)
        logger.info(f"Successfully updated:          {self.stats['updated']}")
        logger.info(f"Moved to no_definition:        {self.stats['moved_to_no_definition']}")
        logger.info(f"Skipped (already processed):   {self.stats['skipped_already_processed']}")
        logger.info(f"Errors:                        {self.stats['errors']}")
        logger.info("=" * 60)


def main():
    parser = argparse.ArgumentParser(
        description='Update vocab.defined entries with missing definitions from API'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Show what would be done without making changes'
    )
    parser.add_argument(
        '--batch-size',
        type=int,
        default=5,
        help='Number of words to process concurrently (default: 5)'
    )
    parser.add_argument(
        '--delay',
        type=float,
        default=2.0,
        help='Delay in seconds between batches (default: 2.0)'
    )
    parser.add_argument(
        '--verbose',
        action='store_true',
        help='Enable verbose logging'
    )

    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    # Create updater and run
    updater = DefinitionUpdater(dry_run=args.dry_run)

    try:
        asyncio.run(updater.process_all(
            batch_size=args.batch_size,
            delay=args.delay
        ))

        return 0

    except KeyboardInterrupt:
        logger.info("\nInterrupted by user")
        return 1
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())
