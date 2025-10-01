#!/usr/bin/env python3
"""
Build Complete Pronunciation Library
Downloads from Merriam-Webster + synthesizes missing pronunciations
Conservative rate limiting: 3 seconds between requests
"""

import sys
import os
import time
import requests
from pathlib import Path
from typing import Optional, Tuple
import logging
from urllib.parse import urlparse

# Direct imports to avoid dependency issues
import psycopg
from tqdm import tqdm

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Database config
DB_CONFIG = {
    'host': '10.0.0.99',
    'port': 6543,
    'dbname': 'postgres',
    'user': 'postgres.your-tenant-id',
    'password': 'your-super-secret-and-long-postgres-password',
}

# Configuration
PRONUNCIATION_DIR = Path('pronunciation_files')
PRONUNCIATION_DIR.mkdir(exist_ok=True)

RATE_LIMIT_DELAY = 3.0  # Very conservative: 3 seconds between requests
USER_AGENT = 'Mozilla/5.0 (Educational Vocabulary App; Contact: vocabulary@example.com) Python/3.12'

class PronunciationLibraryBuilder:
    """Build comprehensive pronunciation library with respectful scraping"""

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({'User-Agent': USER_AGENT})
        self.stats = {
            'total': 0,
            'downloaded': 0,
            'synthesized': 0,
            'already_local': 0,
            'failed': 0
        }

    def get_db_connection(self):
        """Get database connection"""
        conn = psycopg.connect(**DB_CONFIG)
        with conn.cursor() as cursor:
            cursor.execute('SET search_path TO vocab')
        return conn

    def sanitize_filename(self, filename: str) -> str:
        """Sanitize filename for filesystem safety"""
        # Remove or replace problematic characters
        invalid_chars = '<>:"/\\|?*'
        for char in invalid_chars:
            filename = filename.replace(char, '_')
        return filename

    def download_from_url(self, url: str, word_id: int, term: str) -> Optional[Path]:
        """Download pronunciation file from URL with rate limiting"""
        try:
            # Check if already exists locally
            sanitized_term = self.sanitize_filename(term)
            local_filename = f"{word_id}_{sanitized_term}.wav"
            local_path = PRONUNCIATION_DIR / local_filename

            if local_path.exists() and local_path.stat().st_size > 1000:
                logger.debug(f"File already exists: {local_filename}")
                return local_path

            # Respectful delay
            logger.info(f"Downloading: {term} from Merriam-Webster (waiting {RATE_LIMIT_DELAY}s...)")
            time.sleep(RATE_LIMIT_DELAY)

            # Download
            response = self.session.get(url, timeout=30)
            response.raise_for_status()

            # Validate it's actually audio
            content_type = response.headers.get('Content-Type', '')
            if 'audio' not in content_type.lower() and len(response.content) < 1000:
                logger.warning(f"Invalid audio file for {term}: {content_type}")
                return None

            # Save to file
            with open(local_path, 'wb') as f:
                f.write(response.content)

            logger.info(f"✓ Downloaded: {term} ({len(response.content):,} bytes)")
            return local_path

        except requests.exceptions.RequestException as e:
            logger.error(f"Download failed for {term}: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error downloading {term}: {e}")
            return None

    def synthesize_with_gtts(self, word_id: int, term: str) -> Optional[Path]:
        """Synthesize pronunciation using Google Text-to-Speech"""
        try:
            from gtts import gTTS

            sanitized_term = self.sanitize_filename(term)
            local_filename = f"{word_id}_{sanitized_term}.wav"
            local_path = PRONUNCIATION_DIR / local_filename

            if local_path.exists() and local_path.stat().st_size > 1000:
                logger.debug(f"File already exists: {local_filename}")
                return local_path

            logger.info(f"Synthesizing: {term} with gTTS")

            # Generate speech (slow=False for natural speed)
            tts = gTTS(text=term, lang='en', slow=False)

            # Save to temporary mp3
            temp_path = local_path.with_suffix('.mp3')
            tts.save(str(temp_path))

            # Convert mp3 to wav using ffmpeg if available
            try:
                import subprocess
                result = subprocess.run(
                    ['ffmpeg', '-i', str(temp_path), '-ar', '22050', str(local_path), '-y'],
                    capture_output=True,
                    timeout=10
                )
                temp_path.unlink()  # Remove temp mp3

                if result.returncode == 0 and local_path.exists():
                    logger.info(f"✓ Synthesized: {term}")
                    return local_path
                else:
                    logger.warning(f"ffmpeg conversion failed for {term}, keeping mp3")
                    # Keep the mp3 as fallback
                    return temp_path

            except (FileNotFoundError, subprocess.SubprocessError):
                # ffmpeg not available, use mp3
                logger.debug(f"ffmpeg not available, using mp3 for {term}")
                return temp_path

        except ImportError:
            logger.error("gTTS not installed. Install with: uv pip install gtts")
            return None
        except Exception as e:
            logger.error(f"Synthesis failed for {term}: {e}")
            return None

    def update_database(self, word_id: int, local_path: Path):
        """Update database with local file path"""
        try:
            conn = self.get_db_connection()
            with conn.cursor() as cursor:
                # Store as /pronunciation/filename for web serving
                web_path = f"/pronunciation/{local_path.name}"
                cursor.execute(
                    "UPDATE defined SET wav_url = %s WHERE id = %s",
                    (web_path, word_id)
                )
                conn.commit()
                logger.debug(f"Updated database for word_id {word_id}")
            conn.close()
        except Exception as e:
            logger.error(f"Database update failed for word_id {word_id}: {e}")

    def process_words_with_urls(self, limit: Optional[int] = None):
        """Process words that have Merriam-Webster URLs"""
        logger.info("=" * 60)
        logger.info("PHASE 1: Downloading from Merriam-Webster")
        logger.info("=" * 60)

        conn = self.get_db_connection()
        with conn.cursor() as cursor:
            sql = """
            SELECT id, term, wav_url
            FROM defined
            WHERE wav_url LIKE 'http%'
            ORDER BY id
            """
            if limit:
                sql += f" LIMIT {limit}"

            cursor.execute(sql)
            words = cursor.fetchall()
        conn.close()

        logger.info(f"Found {len(words)} words with Merriam-Webster URLs")

        for word_id, term, url in tqdm(words, desc="Downloading"):
            # Check if already local
            sanitized_term = self.sanitize_filename(term)
            local_path = PRONUNCIATION_DIR / f"{word_id}_{sanitized_term}.wav"

            if local_path.exists() and local_path.stat().st_size > 1000:
                self.stats['already_local'] += 1
                self.update_database(word_id, local_path)
                continue

            # Download
            result_path = self.download_from_url(url, word_id, term)

            if result_path:
                self.stats['downloaded'] += 1
                self.update_database(word_id, result_path)
            else:
                self.stats['failed'] += 1

        logger.info(f"\nPhase 1 Complete: {self.stats['downloaded']} downloaded, "
                   f"{self.stats['already_local']} already local, "
                   f"{self.stats['failed']} failed")

    def process_words_without_urls(self, limit: Optional[int] = None):
        """Process words without URLs - synthesize pronunciations"""
        logger.info("=" * 60)
        logger.info("PHASE 2: Synthesizing missing pronunciations")
        logger.info("=" * 60)

        conn = self.get_db_connection()
        with conn.cursor() as cursor:
            sql = """
            SELECT id, term
            FROM defined
            WHERE (wav_url IS NULL OR wav_url = '')
            ORDER BY id
            """
            if limit:
                sql += f" LIMIT {limit}"

            cursor.execute(sql)
            words = cursor.fetchall()
        conn.close()

        logger.info(f"Found {len(words)} words needing synthesis")

        for word_id, term in tqdm(words, desc="Synthesizing"):
            result_path = self.synthesize_with_gtts(word_id, term)

            if result_path:
                self.stats['synthesized'] += 1
                self.update_database(word_id, result_path)
            else:
                self.stats['failed'] += 1

        logger.info(f"\nPhase 2 Complete: {self.stats['synthesized']} synthesized, "
                   f"{self.stats['failed']} failed")

    def print_final_stats(self):
        """Print final statistics"""
        logger.info("=" * 60)
        logger.info("FINAL STATISTICS")
        logger.info("=" * 60)
        logger.info(f"Already local:    {self.stats['already_local']:,}")
        logger.info(f"Downloaded:       {self.stats['downloaded']:,}")
        logger.info(f"Synthesized:      {self.stats['synthesized']:,}")
        logger.info(f"Failed:           {self.stats['failed']:,}")
        logger.info(f"Total processed:  {sum(self.stats.values()):,}")

        # Count final files
        wav_files = list(PRONUNCIATION_DIR.glob('*.wav'))
        mp3_files = list(PRONUNCIATION_DIR.glob('*.mp3'))
        logger.info(f"\nTotal .wav files: {len(wav_files):,}")
        logger.info(f"Total .mp3 files: {len(mp3_files):,}")
        logger.info(f"Total audio files: {len(wav_files) + len(mp3_files):,}")


def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="Build comprehensive pronunciation library with respectful scraping"
    )
    parser.add_argument(
        '--download-limit',
        type=int,
        help='Limit number of downloads (for testing)'
    )
    parser.add_argument(
        '--synthesis-limit',
        type=int,
        help='Limit number of syntheses (for testing)'
    )
    parser.add_argument(
        '--skip-download',
        action='store_true',
        help='Skip download phase (synthesis only)'
    )
    parser.add_argument(
        '--skip-synthesis',
        action='store_true',
        help='Skip synthesis phase (download only)'
    )

    args = parser.parse_args()

    builder = PronunciationLibraryBuilder()

    logger.info("Starting Pronunciation Library Builder")
    logger.info(f"Rate limit: {RATE_LIMIT_DELAY} seconds between requests")
    logger.info(f"Output directory: {PRONUNCIATION_DIR.absolute()}")

    # Phase 1: Download from Merriam-Webster
    if not args.skip_download:
        builder.process_words_with_urls(limit=args.download_limit)

    # Phase 2: Synthesize missing
    if not args.skip_synthesis:
        builder.process_words_without_urls(limit=args.synthesis_limit)

    # Final stats
    builder.print_final_stats()

    logger.info("\n✓ Pronunciation library build complete!")
    logger.info("Next step: Update web app to serve these files")


if __name__ == '__main__':
    main()
