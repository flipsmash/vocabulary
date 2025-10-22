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
            'not_found': 0,
            'errors': 0,
            'no_match': 0
        }

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

    async def update_word(
        self,
        word_id: int,
        term: str,
        pos: str,
        http_client: httpx.AsyncClient
    ) -> bool:
        """
        Update a single word's definition from API.

        Returns True if updated, False otherwise.
        """
        logger.info(f"Processing: {term} ({pos})")

        # Fetch from API
        api_data = await self.fetch_from_api(term, http_client)

        if not api_data:
            self.stats['not_found'] += 1
            logger.warning(f"  No API data found for: {term}")
            return False

        # Extract definition matching POS
        definition = self.extract_definition_for_pos(api_data, pos)

        if not definition:
            self.stats['no_match'] += 1
            logger.warning(f"  No matching POS '{pos}' found in API data for: {term}")
            return False

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

    async def process_all(self, batch_size: int = 10, delay: float = 0.5):
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
        logger.info(f"Total processed:    {self.stats['found']}")
        logger.info(f"Successfully updated: {self.stats['updated']}")
        logger.info(f"Not found in API:    {self.stats['not_found']}")
        logger.info(f"No POS match:        {self.stats['no_match']}")
        logger.info(f"Errors:              {self.stats['errors']}")
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
        default=10,
        help='Number of words to process concurrently (default: 10)'
    )
    parser.add_argument(
        '--delay',
        type=float,
        default=0.5,
        help='Delay in seconds between batches (default: 0.5)'
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
