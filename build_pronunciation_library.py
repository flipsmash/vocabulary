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
            'merriam_webster': 0,
            'free_dictionary': 0,
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

    def get_merriam_webster_audio_url(self, term: str) -> Optional[str]:
        """
        Fetch pronunciation URL from Merriam-Webster API
        Uses their collegiate dictionary API (free for non-commercial use)
        """
        try:
            # Merriam-Webster API endpoint (requires API key for production, but can scrape page)
            # For now, we'll construct the expected URL pattern based on their convention
            # Format: https://media.merriam-webster.com/soundc11/{first_letter}/{filename}.wav

            # Their filename convention is complex, so let's try the Free Dictionary API first
            # and only use existing M-W URLs from database
            return None

        except Exception as e:
            logger.debug(f"Could not get M-W URL for {term}: {e}")
            return None

    def get_free_dictionary_audio_url(self, term: str) -> Optional[str]:
        """
        Fetch pronunciation URL from Free Dictionary API
        Returns URL if available, None otherwise
        """
        try:
            url = f"https://api.dictionaryapi.dev/api/v2/entries/en/{term.lower()}"

            # Respectful delay
            time.sleep(RATE_LIMIT_DELAY)

            response = self.session.get(url, timeout=10)

            if response.status_code == 200:
                data = response.json()
                if isinstance(data, list) and len(data) > 0:
                    entry = data[0]

                    # Check phonetics for audio
                    if 'phonetics' in entry:
                        for phonetic in entry['phonetics']:
                            if 'audio' in phonetic and phonetic['audio']:
                                audio_url = phonetic['audio']
                                # Prefer US pronunciation, then UK, then any
                                if '-us.mp3' in audio_url or '-uk.mp3' in audio_url:
                                    logger.info(f"Found Free Dictionary audio for {term}: {audio_url}")
                                    return audio_url

                        # Return first available audio if no US/UK found
                        for phonetic in entry['phonetics']:
                            if 'audio' in phonetic and phonetic['audio']:
                                logger.info(f"Found Free Dictionary audio for {term}: {phonetic['audio']}")
                                return phonetic['audio']

            return None

        except Exception as e:
            logger.debug(f"Free Dictionary API failed for {term}: {e}")
            return None

    def download_from_url(self, url: str, word_id: int, term: str, source: str = 'unknown') -> Optional[Path]:
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
            logger.info(f"Downloading: {term} from {source} (waiting {RATE_LIMIT_DELAY}s...)")
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

    def process_all_words(self, limit: Optional[int] = None):
        """
        Process ALL words with intelligent source selection:
        1. Check if local file exists (skip)
        2. Try Merriam-Webster URL from database
        3. Try Free Dictionary API
        4. Synthesize with gTTS
        """
        logger.info("=" * 60)
        logger.info("COMPREHENSIVE PRONUNCIATION LIBRARY BUILD")
        logger.info("=" * 60)

        conn = self.get_db_connection()
        with conn.cursor() as cursor:
            # Get ALL words, regardless of wav_url status
            sql = """
            SELECT id, term, wav_url
            FROM defined
            ORDER BY id
            """
            if limit:
                sql += f" LIMIT {limit}"

            cursor.execute(sql)
            words = cursor.fetchall()
        conn.close()

        logger.info(f"Processing {len(words)} total words")
        logger.info(f"Strategy: Merriam-Webster → Free Dictionary → gTTS Synthesis")
        logger.info("")

        for word_id, term, existing_wav_url in tqdm(words, desc="Processing"):
            # Check if already local
            sanitized_term = self.sanitize_filename(term)
            local_path = PRONUNCIATION_DIR / f"{word_id}_{sanitized_term}.wav"
            mp3_path = PRONUNCIATION_DIR / f"{word_id}_{sanitized_term}.mp3"

            if (local_path.exists() and local_path.stat().st_size > 1000) or \
               (mp3_path.exists() and mp3_path.stat().st_size > 1000):
                self.stats['already_local'] += 1
                existing_file = local_path if local_path.exists() else mp3_path
                self.update_database(word_id, existing_file)
                continue

            result_path = None

            # Strategy 1: Try Merriam-Webster (if URL exists in database)
            if existing_wav_url and existing_wav_url.startswith('http'):
                logger.debug(f"Trying Merriam-Webster for {term}")
                result_path = self.download_from_url(existing_wav_url, word_id, term, source='Merriam-Webster')
                if result_path:
                    self.stats['merriam_webster'] += 1
                    self.update_database(word_id, result_path)
                    continue

            # Strategy 2: Try Free Dictionary API
            logger.debug(f"Trying Free Dictionary API for {term}")
            free_dict_url = self.get_free_dictionary_audio_url(term)
            if free_dict_url:
                result_path = self.download_from_url(free_dict_url, word_id, term, source='Free Dictionary')
                if result_path:
                    self.stats['free_dictionary'] += 1
                    self.update_database(word_id, result_path)
                    continue

            # Strategy 3: Synthesize with gTTS
            logger.debug(f"Synthesizing {term} with gTTS")
            result_path = self.synthesize_with_gtts(word_id, term)
            if result_path:
                self.stats['synthesized'] += 1
                self.update_database(word_id, result_path)
            else:
                self.stats['failed'] += 1

        self.print_phase_stats()

    def print_phase_stats(self):
        """Print statistics after processing"""
        logger.info("\n" + "=" * 60)
        logger.info("PROCESSING COMPLETE")
        logger.info("=" * 60)
        logger.info(f"Already local:       {self.stats['already_local']:6,}")
        logger.info(f"Merriam-Webster:     {self.stats['merriam_webster']:6,}")
        logger.info(f"Free Dictionary:     {self.stats['free_dictionary']:6,}")
        logger.info(f"gTTS Synthesized:    {self.stats['synthesized']:6,}")
        logger.info(f"Failed:              {self.stats['failed']:6,}")
        logger.info(f"Total processed:     {sum(self.stats.values()):6,}")

    def print_final_stats(self):
        """Print final statistics"""
        logger.info("\n" + "=" * 60)
        logger.info("FINAL LIBRARY STATISTICS")
        logger.info("=" * 60)

        # Count final files
        wav_files = list(PRONUNCIATION_DIR.glob('*.wav'))
        mp3_files = list(PRONUNCIATION_DIR.glob('*.mp3'))

        logger.info(f"\nAudio Files by Format:")
        logger.info(f"  WAV files:  {len(wav_files):6,}")
        logger.info(f"  MP3 files:  {len(mp3_files):6,}")
        logger.info(f"  Total:      {len(wav_files) + len(mp3_files):6,}")

        logger.info(f"\nSources Breakdown:")
        logger.info(f"  Merriam-Webster:  {self.stats['merriam_webster']:6,}")
        logger.info(f"  Free Dictionary:  {self.stats['free_dictionary']:6,}")
        logger.info(f"  gTTS Synthesis:   {self.stats['synthesized']:6,}")
        logger.info(f"  Already local:    {self.stats['already_local']:6,}")
        logger.info(f"  Failed:           {self.stats['failed']:6,}")


def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="Build comprehensive pronunciation library with multi-source fallback"
    )
    parser.add_argument(
        '--limit',
        type=int,
        help='Limit number of words to process (for testing)'
    )

    args = parser.parse_args()

    builder = PronunciationLibraryBuilder()

    logger.info("=" * 60)
    logger.info("PRONUNCIATION LIBRARY BUILDER")
    logger.info("=" * 60)
    logger.info(f"Rate limit: {RATE_LIMIT_DELAY} seconds between requests")
    logger.info(f"Output directory: {PRONUNCIATION_DIR.absolute()}")
    logger.info(f"\nSource Priority:")
    logger.info(f"  1. Local file (skip if exists)")
    logger.info(f"  2. Merriam-Webster (from database URLs)")
    logger.info(f"  3. Free Dictionary API")
    logger.info(f"  4. gTTS Synthesis")
    logger.info("")

    # Process all words with intelligent fallback
    builder.process_all_words(limit=args.limit)

    # Final stats
    builder.print_final_stats()

    logger.info("\n✓ Pronunciation library build complete!")
    logger.info("Next step: Test pronunciation playback in web app")


if __name__ == '__main__':
    main()
