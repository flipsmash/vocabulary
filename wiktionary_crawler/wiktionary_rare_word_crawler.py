#!/usr/bin/env python3
"""
Wiktionary Rare Word Crawler
Downloads and parses English Wiktionary XML dump to extract rare vocabulary candidates
Stores filtered results in PostgreSQL database for manual review
"""

import os
import sys
import re
import bz2
import json
import logging
import requests
from pathlib import Path
from typing import Optional, Set, Dict, List, Tuple
from datetime import datetime
from dataclasses import dataclass
import xml.etree.ElementTree as ET
from urllib.parse import urljoin
import time

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Import database config directly without FastAPI dependencies
try:
    from core.secure_config import get_db_config
except ImportError:
    # Fallback: direct database config
    def get_db_config():
        return {
            'host': '10.0.0.99',
            'port': 6543,
            'dbname': 'postgres',
            'user': 'postgres.your-tenant-id',
            'password': 'your-super-secret-and-long-postgres-password',
        }

import psycopg
from psycopg.rows import dict_row

# ============================================================================
# CONFIGURATION
# ============================================================================

@dataclass
class CrawlerConfig:
    """Configuration for Wiktionary crawler"""

    # Database connection
    db_config: Dict

    # Rarity threshold (0-1 scale, higher = rarer)
    # Default 0.6 captures genuinely rare, interesting words
    final_rarity_threshold: float = 0.6

    # Stoplist size (most common words to exclude)
    stoplist_size: int = 20000

    # Parts of speech to include
    allowed_pos: Set[str] = None

    # Wiktionary dump settings
    wiktionary_dump_url: str = "https://dumps.wikimedia.org/enwiktionary/latest/enwiktionary-latest-pages-articles.xml.bz2"
    dump_dir: Path = Path("wiktionary_crawler/dumps")
    stoplist_path: Path = Path("wiktionary_crawler/stoplist.txt")
    checkpoint_path: Path = Path("wiktionary_crawler/checkpoint.json")

    # Processing settings
    batch_size: int = 500
    max_definition_length: int = 1000
    max_etymology_length: int = 300

    # Progress reporting
    log_interval: int = 1000

    def __post_init__(self):
        if self.allowed_pos is None:
            self.allowed_pos = {
                'noun', 'verb', 'adjective', 'adverb',
                'interjection', 'preposition'
            }

        # Create directories
        self.dump_dir.mkdir(parents=True, exist_ok=True)
        self.checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
        self.stoplist_path.parent.mkdir(parents=True, exist_ok=True)


# ============================================================================
# LOGGING SETUP
# ============================================================================

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


# ============================================================================
# STOPLIST MANAGEMENT
# ============================================================================

class StoplistManager:
    """Download and manage common word stoplist"""

    # Google 10000 English words (commonly used list)
    STOPLIST_URL = "https://raw.githubusercontent.com/first20hours/google-10000-english/master/google-10000-english-usa-no-swears.txt"
    # Alternative: MIT 10k words
    ALTERNATIVE_URL = "https://www.mit.edu/~ecprice/wordlist.10000"

    def __init__(self, config: CrawlerConfig):
        self.config = config
        self.stoplist: Set[str] = set()

    def load_or_download(self) -> Set[str]:
        """Load stoplist from disk or download if missing"""
        if self.config.stoplist_path.exists():
            logger.info(f"Loading stoplist from {self.config.stoplist_path}")
            with open(self.config.stoplist_path, 'r', encoding='utf-8') as f:
                self.stoplist = {line.strip().lower() for line in f if line.strip()}
            logger.info(f"Loaded {len(self.stoplist):,} stoplist words")
            return self.stoplist

        logger.info("Stoplist not found, downloading...")
        return self.download_stoplist()

    def download_stoplist(self) -> Set[str]:
        """Download common words stoplist"""
        try:
            # Try primary source
            logger.info(f"Downloading stoplist from {self.STOPLIST_URL}")
            response = requests.get(self.STOPLIST_URL, timeout=30)
            response.raise_for_status()
            words = {line.strip().lower() for line in response.text.split('\n') if line.strip()}

            # If we need more words, supplement with alternative source
            if len(words) < self.config.stoplist_size:
                logger.info(f"Downloaded {len(words)} words, fetching more from alternative source...")
                response = requests.get(self.ALTERNATIVE_URL, timeout=30)
                response.raise_for_status()
                more_words = {line.strip().lower() for line in response.text.split('\n') if line.strip()}
                words.update(more_words)

            # Limit to configured size
            self.stoplist = set(sorted(words)[:self.config.stoplist_size])

            # Save to disk
            with open(self.config.stoplist_path, 'w', encoding='utf-8') as f:
                for word in sorted(self.stoplist):
                    f.write(f"{word}\n")

            logger.info(f"Downloaded and saved {len(self.stoplist):,} stoplist words")
            return self.stoplist

        except Exception as e:
            logger.error(f"Failed to download stoplist: {e}")
            logger.info("Using minimal built-in stoplist")
            # Minimal fallback
            self.stoplist = {
                'the', 'be', 'to', 'of', 'and', 'a', 'in', 'that', 'have', 'i',
                'it', 'for', 'not', 'on', 'with', 'he', 'as', 'you', 'do', 'at'
            }
            return self.stoplist


# ============================================================================
# WIKTIONARY DUMP DOWNLOADER
# ============================================================================

class WiktionaryDumpDownloader:
    """Download Wiktionary XML dump"""

    def __init__(self, config: CrawlerConfig):
        self.config = config

    def get_dump_path(self) -> Path:
        """Get local path for dump file"""
        filename = self.config.wiktionary_dump_url.split('/')[-1]
        return self.config.dump_dir / filename

    def download_if_missing(self) -> Path:
        """Download dump file if not present"""
        dump_path = self.get_dump_path()

        if dump_path.exists():
            size_mb = dump_path.stat().st_size / (1024 * 1024)
            logger.info(f"Wiktionary dump already exists: {dump_path} ({size_mb:.1f} MB)")
            return dump_path

        logger.info(f"Downloading Wiktionary dump from {self.config.wiktionary_dump_url}")
        logger.info("This may take 10-30 minutes depending on your connection...")

        response = requests.get(self.config.wiktionary_dump_url, stream=True, timeout=120)
        response.raise_for_status()

        total_size = int(response.headers.get('content-length', 0))
        downloaded = 0

        with open(dump_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)
                    downloaded += len(chunk)
                    if total_size:
                        progress = (downloaded / total_size) * 100
                        if downloaded % (10 * 1024 * 1024) == 0:  # Log every 10MB
                            logger.info(f"Downloaded {downloaded / (1024*1024):.1f} MB / {total_size / (1024*1024):.1f} MB ({progress:.1f}%)")

        size_mb = dump_path.stat().st_size / (1024 * 1024)
        logger.info(f"Download complete: {dump_path} ({size_mb:.1f} MB)")
        return dump_path


# ============================================================================
# WIKTIONARY MARKUP PARSER
# ============================================================================

@dataclass
class WiktionaryEntry:
    """Parsed Wiktionary entry"""
    term: str
    definitions: List[str]
    part_of_speech: str
    etymology: Optional[str] = None
    is_archaic: bool = False
    is_obsolete: bool = False


class WiktionaryParser:
    """Parse Wiktionary XML dump and wiki markup"""

    # XML namespace
    NS = {'mw': 'http://www.mediawiki.org/xml/export-0.10/'}

    # POS section headers in Wiktionary
    POS_HEADERS = {
        'noun': 'noun',
        'verb': 'verb',
        'adjective': 'adjective',
        'adverb': 'adverb',
        'interjection': 'interjection',
        'preposition': 'preposition',
        'pronoun': 'pronoun',
        'conjunction': 'conjunction'
    }

    def __init__(self, config: CrawlerConfig):
        self.config = config

    def is_valid_term(self, term: str) -> bool:
        """Check if term is valid (no multi-word phrases except hyphenated/apostrophes)"""
        # Allow hyphens and apostrophes within word
        # Reject if contains spaces or other special characters
        if ' ' in term:
            return False
        if not re.match(r"^[a-zA-Z][a-zA-Z\-']*[a-zA-Z]$", term) and not re.match(r"^[a-zA-Z]$", term):
            return False
        return True

    def extract_pos_section(self, text: str, pos: str) -> Optional[str]:
        """Extract a specific POS section from Wiktionary markup"""
        # Match ===Noun===, ===Verb===, etc.
        # Look for heading with the POS name (case-insensitive)
        pattern = rf'===\s*{re.escape(pos)}\s*===(.+?)(?:===|$)'
        match = re.search(pattern, text, re.IGNORECASE | re.DOTALL)
        return match.group(1) if match else None

    def extract_definitions(self, pos_section: str, max_length: int) -> List[str]:
        """Extract definitions from POS section"""
        definitions = []

        # Find numbered/bulleted definitions: # definition
        for line in pos_section.split('\n'):
            line = line.strip()
            if line.startswith('#') and not line.startswith('##'):
                # Remove wiki markup
                definition = line.lstrip('#').strip()
                definition = self.clean_wiki_markup(definition)
                if definition and len(definition) > 10:  # Skip very short entries
                    definitions.append(definition)

        # Concatenate and limit length
        combined = ' | '.join(definitions)
        if len(combined) > max_length:
            combined = combined[:max_length] + '...'

        return [combined] if combined else []

    def extract_etymology(self, text: str, max_length: int) -> Optional[str]:
        """Extract etymology section (immediate origin only)"""
        # Match ===Etymology=== or ===Etymology 1===
        pattern = r'===\s*Etymology[^=]*===(.+?)(?====|$)'
        match = re.search(pattern, text, re.IGNORECASE | re.DOTALL)

        if not match:
            return None

        etym_text = match.group(1).strip()

        # Extract first paragraph or first sentence
        lines = [l.strip() for l in etym_text.split('\n') if l.strip() and not l.startswith('=')]
        if not lines:
            return None

        # Get first non-empty line
        first_line = lines[0]
        first_line = self.clean_wiki_markup(first_line)

        # Limit length
        if len(first_line) > max_length:
            first_line = first_line[:max_length] + '...'

        return first_line if first_line else None

    def check_archaic_obsolete(self, text: str) -> Tuple[bool, bool]:
        """Check if word is marked as archaic or obsolete"""
        text_lower = text.lower()
        is_archaic = 'archaic' in text_lower or '{{archaic' in text_lower
        is_obsolete = 'obsolete' in text_lower or '{{obsolete' in text_lower
        return is_archaic, is_obsolete

    def clean_wiki_markup(self, text: str) -> str:
        """Remove Wiktionary wiki markup"""
        # Remove templates {{template}}
        text = re.sub(r'\{\{[^}]+\}\}', '', text)
        # Remove links [[link|display]] -> display
        text = re.sub(r'\[\[([^\]|]+\|)?([^\]]+)\]\]', r'\2', text)
        # Remove HTML tags
        text = re.sub(r'<[^>]+>', '', text)
        # Remove multiple spaces
        text = re.sub(r'\s+', ' ', text)
        return text.strip()

    def parse_page(self, title: str, text: str) -> List[WiktionaryEntry]:
        """Parse a Wiktionary page and extract entries"""
        entries = []

        # Check if valid term
        if not self.is_valid_term(title):
            return entries

        # Skip if it's not an English entry (look for ==English==)
        if '==English==' not in text:
            return entries

        # Extract English section
        english_match = re.search(r'==English==(.+?)(?:^==\w|$)', text, re.MULTILINE | re.DOTALL)
        if not english_match:
            return entries

        english_section = english_match.group(1)

        # Check for proper noun (exclude)
        if '===Proper noun===' in english_section or '{{proper noun' in english_section.lower():
            return entries

        # Check archaic/obsolete
        is_archaic, is_obsolete = self.check_archaic_obsolete(english_section)

        # Extract etymology
        etymology = self.extract_etymology(english_section, self.config.max_etymology_length)

        # Try to extract each POS
        for pos_key, pos_name in self.POS_HEADERS.items():
            if pos_name not in self.config.allowed_pos:
                continue

            pos_section = self.extract_pos_section(english_section, pos_key)
            if not pos_section:
                continue

            definitions = self.extract_definitions(pos_section, self.config.max_definition_length)
            if not definitions or not definitions[0]:
                continue

            entry = WiktionaryEntry(
                term=title.lower(),
                definitions=definitions,
                part_of_speech=pos_name,
                etymology=etymology,
                is_archaic=is_archaic,
                is_obsolete=is_obsolete
            )
            entries.append(entry)

        return entries

    def parse_dump(self, dump_path: Path, callback, checkpoint_callback=None):
        """Parse XML dump file and yield entries"""
        logger.info(f"Parsing Wiktionary dump: {dump_path}")

        # Open bz2 file
        with bz2.open(dump_path, 'rt', encoding='utf-8') as f:
            context = ET.iterparse(f, events=('end',))

            page_count = 0
            for event, elem in context:
                if elem.tag == '{http://www.mediawiki.org/xml/export-0.10/}page':
                    page_count += 1

                    # Extract title and text
                    title_elem = elem.find('mw:title', self.NS)
                    text_elem = elem.find('.//mw:text', self.NS)

                    if title_elem is not None and text_elem is not None:
                        title = title_elem.text
                        text = text_elem.text

                        if title and text:
                            entries = self.parse_page(title, text)
                            for entry in entries:
                                callback(entry)

                    # Clear element to free memory
                    elem.clear()

                    # Checkpoint callback
                    if checkpoint_callback and page_count % 10000 == 0:
                        checkpoint_callback(page_count)

                    # Progress logging
                    if page_count % 50000 == 0:
                        logger.info(f"Processed {page_count:,} pages...")


# ============================================================================
# DATABASE MANAGER
# ============================================================================

class CandidateDatabase:
    """Manage vocabulary_candidates database"""

    def __init__(self, config: CrawlerConfig):
        self.config = config
        self.existing_terms: Set[str] = set()
        self.batch: List[Dict] = []

    def get_connection(self):
        """Get database connection"""
        conn = psycopg.connect(**self.config.db_config)
        with conn.cursor() as cursor:
            cursor.execute('SET search_path TO vocab')
        return conn

    def load_existing_terms(self):
        """Load existing terms from both defined and vocabulary_candidates tables"""
        logger.info("Loading existing terms from database...")

        conn = self.get_connection()
        try:
            with conn.cursor() as cursor:
                # Load from defined table
                cursor.execute("SELECT LOWER(term) FROM defined")
                defined_terms = {row[0] for row in cursor.fetchall()}

                # Load from vocabulary_candidates table
                cursor.execute("SELECT LOWER(term) FROM vocabulary_candidates")
                candidate_terms = {row[0] for row in cursor.fetchall()}

                self.existing_terms = defined_terms | candidate_terms

            logger.info(f"Loaded {len(defined_terms):,} terms from defined table")
            logger.info(f"Loaded {len(candidate_terms):,} terms from vocabulary_candidates table")
            logger.info(f"Total existing terms: {len(self.existing_terms):,}")
        finally:
            conn.close()

    def get_rarity_scores(self, terms: List[str]) -> Dict[str, float]:
        """Batch query rarity scores from word_rarity_metrics"""
        if not terms:
            return {}

        conn = self.get_connection()
        try:
            with conn.cursor(row_factory=dict_row) as cursor:
                # Use ANY() for efficient batch query
                cursor.execute(
                    """
                    SELECT LOWER(term) as term, final_rarity
                    FROM word_rarity_metrics
                    WHERE LOWER(term) = ANY(%s)
                    """,
                    (terms,)
                )
                return {row['term']: row['final_rarity'] for row in cursor.fetchall()}
        finally:
            conn.close()

    def add_to_batch(self, entry: WiktionaryEntry, final_rarity: float, source_dump_date: str):
        """Add candidate to batch"""
        self.batch.append({
            'term': entry.term,
            'final_rarity': final_rarity,
            'definition': entry.definitions[0] if entry.definitions else '',
            'part_of_speech': entry.part_of_speech,
            'etymology': entry.etymology,
            'obsolete_or_archaic': entry.is_archaic or entry.is_obsolete,
            'source_dump_date': source_dump_date
        })

    def flush_batch(self) -> int:
        """Insert batch to database"""
        if not self.batch:
            return 0

        conn = self.get_connection()
        try:
            with conn.cursor() as cursor:
                # Use execute_batch for efficiency
                insert_sql = """
                INSERT INTO vocabulary_candidates
                    (term, final_rarity, definition, part_of_speech, etymology,
                     obsolete_or_archaic, source_dump_date)
                VALUES (%(term)s, %(final_rarity)s, %(definition)s, %(part_of_speech)s,
                        %(etymology)s, %(obsolete_or_archaic)s, %(source_dump_date)s)
                ON CONFLICT (term) DO NOTHING
                """

                from psycopg import sql
                for record in self.batch:
                    try:
                        cursor.execute(insert_sql, record)
                    except Exception as e:
                        logger.warning(f"Failed to insert {record['term']}: {e}")

                conn.commit()
                inserted = len(self.batch)
                self.batch.clear()
                return inserted
        finally:
            conn.close()


# ============================================================================
# CHECKPOINT MANAGER
# ============================================================================

class CheckpointManager:
    """Manage processing checkpoints for resumability"""

    def __init__(self, config: CrawlerConfig):
        self.config = config
        self.checkpoint = {
            'pages_processed': 0,
            'candidates_added': 0,
            'last_updated': None
        }

    def load(self) -> Dict:
        """Load checkpoint from disk"""
        if self.config.checkpoint_path.exists():
            with open(self.config.checkpoint_path, 'r') as f:
                self.checkpoint = json.load(f)
            logger.info(f"Loaded checkpoint: {self.checkpoint['pages_processed']:,} pages processed, "
                       f"{self.checkpoint['candidates_added']:,} candidates added")
        return self.checkpoint

    def save(self, pages_processed: int, candidates_added: int):
        """Save checkpoint to disk"""
        self.checkpoint['pages_processed'] = pages_processed
        self.checkpoint['candidates_added'] = candidates_added
        self.checkpoint['last_updated'] = datetime.now().isoformat()

        with open(self.config.checkpoint_path, 'w') as f:
            json.dump(self.checkpoint, f, indent=2)

    def clear(self):
        """Clear checkpoint file"""
        if self.config.checkpoint_path.exists():
            self.config.checkpoint_path.unlink()


# ============================================================================
# MAIN CRAWLER
# ============================================================================

class WiktionaryRareWordCrawler:
    """Main crawler orchestrator"""

    def __init__(self, config: CrawlerConfig):
        self.config = config
        self.stoplist_manager = StoplistManager(config)
        self.downloader = WiktionaryDumpDownloader(config)
        self.parser = WiktionaryParser(config)
        self.database = CandidateDatabase(config)
        self.checkpoint_manager = CheckpointManager(config)

        self.stats = {
            'pages_processed': 0,
            'entries_extracted': 0,
            'in_stoplist': 0,
            'already_exists': 0,
            'no_rarity_score': 0,
            'above_threshold': 0,
            'candidates_added': 0
        }

        self.pending_entries: List[WiktionaryEntry] = []
        self.source_dump_date = datetime.now().strftime('%Y%m%d')

    def run(self):
        """Run the complete crawling pipeline"""
        logger.info("=" * 70)
        logger.info("WIKTIONARY RARE WORD CRAWLER")
        logger.info("=" * 70)
        logger.info(f"Final rarity threshold: {self.config.final_rarity_threshold}")
        logger.info(f"Stoplist size: {self.config.stoplist_size:,}")
        logger.info(f"Allowed POS: {', '.join(sorted(self.config.allowed_pos))}")
        logger.info("")

        # Step 1: Load stoplist
        stoplist = self.stoplist_manager.load_or_download()
        logger.info("")

        # Step 2: Download Wiktionary dump
        dump_path = self.downloader.download_if_missing()
        logger.info("")

        # Extract dump date from filename
        date_match = re.search(r'(\d{8})', dump_path.name)
        if date_match:
            self.source_dump_date = date_match.group(1)

        # Step 3: Load existing terms
        self.database.load_existing_terms()
        logger.info("")

        # Step 4: Load checkpoint (if resuming)
        checkpoint = self.checkpoint_manager.load()
        if checkpoint['pages_processed'] > 0:
            logger.info(f"Resuming from checkpoint...")
            self.stats['pages_processed'] = checkpoint['pages_processed']
            self.stats['candidates_added'] = checkpoint['candidates_added']
        logger.info("")

        # Step 5: Parse dump
        logger.info("Starting Wiktionary dump parsing...")
        logger.info("This will take 1-3 hours depending on your system...")
        logger.info("")

        def entry_callback(entry: WiktionaryEntry):
            """Process each extracted entry"""
            self.stats['entries_extracted'] += 1

            # Filter: stoplist
            if entry.term in stoplist:
                self.stats['in_stoplist'] += 1
                return

            # Filter: already exists
            if entry.term in self.database.existing_terms:
                self.stats['already_exists'] += 1
                return

            # Add to pending batch
            self.pending_entries.append(entry)

            # Process batch when full
            if len(self.pending_entries) >= self.config.batch_size:
                self.process_pending_batch()

            # Log progress
            if self.stats['entries_extracted'] % self.config.log_interval == 0:
                self.log_progress()

        def checkpoint_callback(pages_processed: int):
            """Save checkpoint periodically"""
            self.stats['pages_processed'] = pages_processed
            self.checkpoint_manager.save(pages_processed, self.stats['candidates_added'])

        # Parse the dump
        self.parser.parse_dump(dump_path, entry_callback, checkpoint_callback)

        # Process remaining entries
        if self.pending_entries:
            self.process_pending_batch()

        # Final batch flush
        if self.database.batch:
            inserted = self.database.flush_batch()
            self.stats['candidates_added'] += inserted

        # Clear checkpoint on successful completion
        self.checkpoint_manager.clear()

        # Print final summary
        self.print_summary()

    def process_pending_batch(self):
        """Process pending entries batch"""
        if not self.pending_entries:
            return

        # Get rarity scores for all terms in batch
        terms = [entry.term for entry in self.pending_entries]
        rarity_scores = self.database.get_rarity_scores(terms)

        # Filter and add candidates
        for entry in self.pending_entries:
            if entry.term not in rarity_scores:
                self.stats['no_rarity_score'] += 1
                continue

            final_rarity = rarity_scores[entry.term]

            # Check threshold
            if final_rarity < self.config.final_rarity_threshold:
                self.stats['above_threshold'] += 1
                continue

            # Add to database batch
            self.database.add_to_batch(entry, final_rarity, self.source_dump_date)

        # Flush database batch if large enough
        if len(self.database.batch) >= self.config.batch_size:
            inserted = self.database.flush_batch()
            self.stats['candidates_added'] += inserted

        # Clear pending
        self.pending_entries.clear()

    def log_progress(self):
        """Log current progress"""
        logger.info(f"Processed {self.stats['entries_extracted']:,} entries | "
                   f"Added {self.stats['candidates_added']:,} candidates | "
                   f"Filtered: stoplist={self.stats['in_stoplist']:,}, "
                   f"exists={self.stats['already_exists']:,}, "
                   f"no_rarity={self.stats['no_rarity_score']:,}, "
                   f"common={self.stats['above_threshold']:,}")

    def print_summary(self):
        """Print final summary statistics"""
        logger.info("")
        logger.info("=" * 70)
        logger.info("CRAWLING COMPLETE")
        logger.info("=" * 70)
        logger.info(f"Pages processed:       {self.stats['pages_processed']:>10,}")
        logger.info(f"Entries extracted:     {self.stats['entries_extracted']:>10,}")
        logger.info("")
        logger.info("Filtering Results:")
        logger.info(f"  In stoplist:         {self.stats['in_stoplist']:>10,}")
        logger.info(f"  Already exists:      {self.stats['already_exists']:>10,}")
        logger.info(f"  No rarity score:     {self.stats['no_rarity_score']:>10,}")
        logger.info(f"  Too common:          {self.stats['above_threshold']:>10,}")
        logger.info("")
        logger.info(f"Candidates added:      {self.stats['candidates_added']:>10,}")
        logger.info("=" * 70)
        logger.info("")
        logger.info("Review candidates in vocabulary_candidates table:")
        logger.info("  SELECT * FROM vocabulary_candidates ORDER BY final_rarity DESC LIMIT 20;")


# ============================================================================
# MAIN ENTRY POINT
# ============================================================================

def main():
    """Main entry point"""
    import argparse

    parser = argparse.ArgumentParser(
        description="Wiktionary Rare Word Crawler - Extract rare vocabulary candidates"
    )
    parser.add_argument(
        '--threshold',
        type=float,
        default=0.6,
        help='Final rarity threshold (0-1, higher=rarer, default: 0.6)'
    )
    parser.add_argument(
        '--stoplist-size',
        type=int,
        default=20000,
        help='Number of common words to exclude (default: 20000)'
    )
    parser.add_argument(
        '--batch-size',
        type=int,
        default=500,
        help='Batch size for database operations (default: 500)'
    )
    parser.add_argument(
        '--reset',
        action='store_true',
        help='Clear checkpoint and start fresh'
    )

    args = parser.parse_args()

    # Get database config
    db_config = get_db_config()

    # Create configuration
    config = CrawlerConfig(
        db_config=db_config,
        final_rarity_threshold=args.threshold,
        stoplist_size=args.stoplist_size,
        batch_size=args.batch_size
    )

    # Clear checkpoint if requested
    if args.reset:
        checkpoint_path = Path("wiktionary_crawler/checkpoint.json")
        if checkpoint_path.exists():
            checkpoint_path.unlink()
            logger.info("Checkpoint cleared")

    # Run crawler
    try:
        crawler = WiktionaryRareWordCrawler(config)
        crawler.run()
    except KeyboardInterrupt:
        logger.info("\nCrawling interrupted by user")
        logger.info("Progress has been saved - rerun to resume from checkpoint")
    except Exception as e:
        logger.error(f"Crawler failed: {e}", exc_info=True)
        sys.exit(1)


if __name__ == '__main__':
    main()
