#!/usr/bin/env python3
"""
Vocabulary List Harvester
Harvests vocabulary terms from pre-existing vocabulary lists on web pages
Checks against 'defined' table and adds new terms to 'candidate_words'
"""

import re
import logging
import hashlib
from typing import List, Tuple, Optional, Dict, Set
from datetime import datetime
from urllib.parse import urlparse
import requests
from bs4 import BeautifulSoup, Tag
import mysql.connector
from mysql.connector import Error
import json
import time

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class VocabularyListHarvester:
    """Flexible harvester for ingesting vocabulary lists from web pages"""

    def __init__(self, db_config: Optional[Dict] = None):
        """
        Initialize the harvester

        Args:
            db_config: Database configuration dictionary
        """
        if db_config is None:
            # Import from config if not provided
            import sys
            import os
            parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            if parent_dir not in sys.path:
                sys.path.insert(0, parent_dir)
            from core.config import get_db_config
            db_config = get_db_config()

        self.db_config = db_config
        self.session_id = None
        self.stats = {
            'total_processed': 0,
            'candidates_found': 0,
            'candidates_accepted': 0,
            'already_defined': 0,
            'errors': 0
        }

        # Pattern detection strategies
        self.pattern_detectors = [
            self._detect_definition_list,
            self._detect_table_pattern,
            self._detect_list_pattern,
            self._detect_div_pattern,
            self._detect_text_pattern
        ]

        # Common vocabulary list indicators
        self.vocabulary_indicators = [
            'vocabulary', 'glossary', 'dictionary', 'terms', 'definitions',
            'word list', 'vocab', 'lexicon', 'terminology', 'words to know'
        ]

    def _get_connection(self):
        """Get database connection"""
        return mysql.connector.connect(**self.db_config)

    def _start_session(self, url: str):
        """Start a harvesting session"""
        conn = self._get_connection()
        cursor = conn.cursor()

        try:
            session_id = f"vocab_list_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{hashlib.md5(url.encode()).hexdigest()[:8]}"

            cursor.execute("""
                INSERT INTO harvesting_sessions
                (source_type, session_start, status, notes)
                VALUES (%s, %s, %s, %s)
            """, ('vocabulary_list_harvester', datetime.now(), 'running', f'URL: {url}'))

            conn.commit()
            self.session_id = cursor.lastrowid
            logger.info(f"Started harvesting session {session_id}")

        except Error as e:
            logger.warning(f"Could not start session tracking: {e}")
        finally:
            cursor.close()
            conn.close()

    def _end_session(self):
        """End the harvesting session"""
        if not self.session_id:
            return

        conn = self._get_connection()
        cursor = conn.cursor()

        try:
            cursor.execute("""
                UPDATE harvesting_sessions
                SET session_end = %s,
                    total_processed = %s,
                    candidates_found = %s,
                    candidates_accepted = %s,
                    status = %s
                WHERE id = %s
            """, (
                datetime.now(),
                self.stats['total_processed'],
                self.stats['candidates_found'],
                self.stats['candidates_accepted'],
                'completed',
                self.session_id
            ))

            conn.commit()
            logger.info(f"Ended harvesting session")

        except Error as e:
            logger.warning(f"Could not end session tracking: {e}")
        finally:
            cursor.close()
            conn.close()

    def harvest_from_url(self, url: str, domain: Optional[str] = None,
                         max_terms: int = 1000) -> Dict:
        """
        Main entry point to harvest vocabulary from a URL

        Args:
            url: The URL to harvest from
            domain: Optional domain/category for the terms
            max_terms: Maximum number of terms to process

        Returns:
            Dictionary with harvest statistics
        """
        logger.info(f"Starting harvest from {url}")
        self._start_session(url)

        try:
            # Fetch page content
            response = requests.get(url, headers={
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            }, timeout=30)
            response.raise_for_status()

            soup = BeautifulSoup(response.text, 'html.parser')

            # Detect vocabulary pattern
            pattern_type, elements = self._detect_vocabulary_pattern(soup)

            if not pattern_type:
                logger.warning("No vocabulary list pattern detected")
                return self.stats

            logger.info(f"Detected pattern: {pattern_type}")

            # Extract terms based on pattern
            terms = self._extract_terms(pattern_type, elements)

            if not terms:
                logger.warning("No terms extracted")
                return self.stats

            logger.info(f"Extracted {len(terms)} terms")
            self.stats['total_processed'] = len(terms)

            # Check existing terms
            new_terms = self._check_existing_terms(terms)
            logger.info(f"Found {len(new_terms)} new terms not in 'defined' table")

            # Store candidates
            if new_terms:
                stored = self._store_candidates(new_terms, url, domain)
                logger.info(f"Stored {stored} candidates")

        except Exception as e:
            logger.error(f"Error harvesting from {url}: {e}")
            self.stats['errors'] += 1

        finally:
            self._end_session()

        return self.stats

    def _detect_vocabulary_pattern(self, soup: BeautifulSoup) -> Tuple[Optional[str], Optional[List]]:
        """
        Detect the vocabulary list pattern in the page

        Returns:
            Tuple of (pattern_type, elements_to_process)
        """
        # First check if page seems to contain vocabulary
        page_text = soup.get_text().lower()
        has_vocab_indicator = any(indicator in page_text for indicator in self.vocabulary_indicators)

        if not has_vocab_indicator:
            logger.debug("No vocabulary indicators found in page")

        # Try each detection strategy
        for detector in self.pattern_detectors:
            pattern_type, elements = detector(soup)
            if pattern_type:
                return pattern_type, elements

        return None, None

    def _detect_definition_list(self, soup: BeautifulSoup) -> Tuple[Optional[str], Optional[List]]:
        """Detect HTML definition list pattern (<dl>, <dt>, <dd>)"""
        dl_elements = soup.find_all('dl')

        for dl in dl_elements:
            terms = dl.find_all('dt')
            definitions = dl.find_all('dd')

            # Check if this looks like a vocabulary list
            if len(terms) >= 3 and len(definitions) >= 3:
                # Verify it's actually vocabulary (not navigation, etc.)
                sample_term = terms[0].get_text().strip()
                if len(sample_term) > 2 and len(sample_term) < 50:
                    return 'definition_list', [dl]

        return None, None

    def _detect_table_pattern(self, soup: BeautifulSoup) -> Tuple[Optional[str], Optional[List]]:
        """Detect table-based vocabulary lists"""
        tables = soup.find_all('table')

        for table in tables:
            rows = table.find_all('tr')
            if len(rows) < 3:
                continue

            # Check header row for vocabulary indicators
            header = rows[0]
            header_text = header.get_text().lower()

            if any(word in header_text for word in ['term', 'word', 'vocabulary', 'definition', 'meaning']):
                return 'table', [table]

            # Check first data row structure
            if len(rows) > 1:
                first_row = rows[1]
                cells = first_row.find_all(['td', 'th'])
                if len(cells) >= 2:
                    # Check if it looks like term-definition pairs
                    term_candidate = cells[0].get_text().strip()
                    def_candidate = cells[1].get_text().strip()

                    if (3 <= len(term_candidate) <= 50 and
                        10 <= len(def_candidate) <= 1000):
                        return 'table', [table]

        return None, None

    def _detect_list_pattern(self, soup: BeautifulSoup) -> Tuple[Optional[str], Optional[List]]:
        """Detect list-based patterns (ul/ol with consistent structure)"""
        lists = soup.find_all(['ul', 'ol'])

        for lst in lists:
            items = lst.find_all('li')
            if len(items) < 5:
                continue

            # Check if items have consistent structure
            consistent_pattern = True
            has_definitions = True

            for item in items[:5]:  # Check first 5 items
                text = item.get_text().strip()
                # Common patterns: "term - definition", "term: definition", "term. definition"
                if not any(delimiter in text for delimiter in [' - ', ': ', '. ']):
                    has_definitions = False
                    break

                # Check for bold/strong terms
                strong_term = item.find(['strong', 'b'])
                if strong_term:
                    continue

            if has_definitions:
                return 'list', [lst]

        return None, None

    def _detect_div_pattern(self, soup: BeautifulSoup) -> Tuple[Optional[str], Optional[List]]:
        """Detect div-based patterns with classes"""
        # Common class patterns for vocabulary lists
        vocab_classes = ['vocabulary', 'vocab', 'glossary', 'terms', 'definition', 'word-list']

        for class_name in vocab_classes:
            elements = soup.find_all(class_=re.compile(class_name, re.I))
            if elements:
                # Verify these contain actual vocabulary
                for elem in elements:
                    text = elem.get_text()
                    # Simple heuristic: should have multiple short "words" and longer "definitions"
                    words = text.split()
                    if len(words) > 20:  # Reasonable amount of content
                        return 'div', elements

        # Look for repeated div structures
        divs_with_terms = []
        for div in soup.find_all('div'):
            # Check if div contains term-like structure
            term_elem = div.find(['h3', 'h4', 'h5', 'strong', 'b'])
            if term_elem:
                text_content = div.get_text().strip()
                if 20 <= len(text_content) <= 500:  # Reasonable definition length
                    divs_with_terms.append(div)

        if len(divs_with_terms) >= 5:
            return 'div', divs_with_terms

        return None, None

    def _detect_text_pattern(self, soup: BeautifulSoup) -> Tuple[Optional[str], Optional[List]]:
        """Detect plain text patterns with consistent delimiters"""
        # Look for paragraphs or divs with consistent patterns
        text_blocks = soup.find_all(['p', 'div'])

        vocab_blocks = []
        for block in text_blocks:
            text = block.get_text().strip()
            lines = text.split('\n')

            # Check if multiple lines follow a pattern
            if len(lines) >= 5:
                pattern_count = 0
                for line in lines:
                    if any(delimiter in line for delimiter in [' - ', ': ', '. ']):
                        pattern_count += 1

                if pattern_count >= 3:
                    vocab_blocks.append(block)

        if vocab_blocks:
            return 'text', vocab_blocks

        return None, None

    def _extract_terms(self, pattern_type: str, elements: List) -> List[Tuple[str, str, Optional[str]]]:
        """
        Extract terms based on detected pattern

        Returns:
            List of (term, definition, part_of_speech) tuples
        """
        terms = []

        if pattern_type == 'definition_list':
            terms = self._extract_from_definition_list(elements[0])
        elif pattern_type == 'table':
            terms = self._extract_from_table(elements[0])
        elif pattern_type == 'list':
            terms = self._extract_from_list(elements[0])
        elif pattern_type == 'div':
            terms = self._extract_from_divs(elements)
        elif pattern_type == 'text':
            terms = self._extract_from_text(elements)

        # Clean and validate terms
        cleaned_terms = []
        for term_data in terms:
            if len(term_data) >= 2:
                term = self._clean_term(term_data[0])
                definition = self._clean_definition(term_data[1])
                pos = term_data[2] if len(term_data) > 2 else None

                if term and definition and len(term) <= 100 and len(definition) >= 10:
                    cleaned_terms.append((term, definition, pos))

        return cleaned_terms

    def _extract_from_definition_list(self, dl_element) -> List[Tuple[str, str, Optional[str]]]:
        """Extract terms from definition list"""
        terms = []
        dt_elements = dl_element.find_all('dt')
        dd_elements = dl_element.find_all('dd')

        for i, dt in enumerate(dt_elements):
            if i < len(dd_elements):
                term = dt.get_text().strip()
                definition = dd_elements[i].get_text().strip()
                pos = self._extract_pos(definition)
                terms.append((term, definition, pos))

        return terms

    def _extract_from_table(self, table_element) -> List[Tuple[str, str, Optional[str]]]:
        """Extract terms from table"""
        terms = []
        rows = table_element.find_all('tr')

        # Skip header row
        for row in rows[1:]:
            cells = row.find_all(['td', 'th'])
            if len(cells) >= 2:
                term = cells[0].get_text().strip()
                definition = cells[1].get_text().strip()

                # Check if there's a POS column
                pos = None
                if len(cells) >= 3:
                    pos = cells[2].get_text().strip()
                else:
                    pos = self._extract_pos(definition)

                terms.append((term, definition, pos))

        return terms

    def _extract_from_list(self, list_element) -> List[Tuple[str, str, Optional[str]]]:
        """Extract terms from list"""
        terms = []
        items = list_element.find_all('li')

        for item in items:
            text = item.get_text().strip()

            # Try different delimiters
            for delimiter in [' - ', ': ', '. ']:
                if delimiter in text:
                    parts = text.split(delimiter, 1)
                    if len(parts) == 2:
                        term = parts[0].strip()
                        definition = parts[1].strip()
                        pos = self._extract_pos(definition)
                        terms.append((term, definition, pos))
                        break

            # Check for bold/strong term
            strong = item.find(['strong', 'b'])
            if strong:
                term = strong.get_text().strip()
                # Get remaining text as definition
                strong.extract()
                definition = item.get_text().strip()
                if definition.startswith('-') or definition.startswith(':'):
                    definition = definition[1:].strip()
                pos = self._extract_pos(definition)
                terms.append((term, definition, pos))

        return terms

    def _extract_from_divs(self, div_elements) -> List[Tuple[str, str, Optional[str]]]:
        """Extract terms from div elements"""
        terms = []

        for div in div_elements:
            # Look for term in heading or bold
            term_elem = div.find(['h3', 'h4', 'h5', 'strong', 'b'])
            if term_elem:
                term = term_elem.get_text().strip()

                # Get definition from remaining text
                term_elem.extract()
                definition = div.get_text().strip()

                if definition:
                    pos = self._extract_pos(definition)
                    terms.append((term, definition, pos))

        return terms

    def _extract_from_text(self, text_elements) -> List[Tuple[str, str, Optional[str]]]:
        """Extract terms from plain text"""
        terms = []

        for element in text_elements:
            text = element.get_text().strip()
            lines = text.split('\n')

            for line in lines:
                line = line.strip()
                if not line:
                    continue

                # Try different delimiters
                for delimiter in [' - ', ': ', '. ']:
                    if delimiter in line:
                        parts = line.split(delimiter, 1)
                        if len(parts) == 2:
                            term = parts[0].strip()
                            definition = parts[1].strip()

                            # Basic validation
                            if 3 <= len(term) <= 50 and len(definition) >= 10:
                                pos = self._extract_pos(definition)
                                terms.append((term, definition, pos))
                                break

        return terms

    def _extract_pos(self, text: str) -> Optional[str]:
        """Extract part of speech from definition text"""
        text_lower = text.lower()

        # Common POS indicators at start of definition
        pos_patterns = {
            'noun': r'^(\()?n\.?(\))?[\s,:]',
            'verb': r'^(\()?v\.?(\))?[\s,:]',
            'adjective': r'^(\()?adj\.?(\))?[\s,:]',
            'adverb': r'^(\()?adv\.?(\))?[\s,:]',
        }

        for pos, pattern in pos_patterns.items():
            if re.match(pattern, text_lower):
                return pos.upper()

        # Check for POS words in parentheses
        if '(' in text:
            paren_match = re.search(r'\((noun|verb|adjective|adverb)\)', text_lower)
            if paren_match:
                return paren_match.group(1).upper()

        return None

    def _clean_term(self, term: str) -> str:
        """Clean and normalize a term"""
        # Remove extra whitespace
        term = ' '.join(term.split())

        # Remove common artifacts
        term = term.strip('.,;:!?"\'')

        # Remove numbering
        term = re.sub(r'^\d+[\.\)]\s*', '', term)

        return term.strip()

    def _clean_definition(self, definition: str) -> str:
        """Clean and normalize a definition"""
        # Remove extra whitespace
        definition = ' '.join(definition.split())

        # Remove citations like [1], [2]
        definition = re.sub(r'\[\d+\]', '', definition)

        # Remove "see also" and similar
        definition = re.sub(r'(See also|Compare|Cf\.):.*$', '', definition, flags=re.I)

        return definition.strip()

    def _check_existing_terms(self, terms: List[Tuple[str, str, Optional[str]]]) -> List[Tuple[str, str, Optional[str]]]:
        """
        Check which terms already exist in the 'defined' table

        Returns:
            List of terms that are NOT in the defined table
        """
        if not terms:
            return []

        conn = self._get_connection()
        cursor = conn.cursor()

        try:
            # Get all term strings for batch checking
            term_strings = [term[0].lower() for term in terms]

            # Create placeholders for SQL IN clause
            placeholders = ','.join(['%s'] * len(term_strings))

            # Check which terms already exist
            cursor.execute(f"""
                SELECT LOWER(term)
                FROM vocab.defined
                WHERE LOWER(term) IN ({placeholders})
            """, term_strings)

            existing_terms = set(row[0] for row in cursor.fetchall())

            # Filter out existing terms
            new_terms = []
            for term_data in terms:
                if term_data[0].lower() not in existing_terms:
                    new_terms.append(term_data)
                else:
                    self.stats['already_defined'] += 1

            return new_terms

        except Error as e:
            logger.error(f"Error checking existing terms: {e}")
            return terms  # Return all terms if check fails

        finally:
            cursor.close()
            conn.close()

    def _store_candidates(self, terms: List[Tuple[str, str, Optional[str]]],
                         url: str, domain: Optional[str]) -> int:
        """
        Store candidate terms in the database

        Returns:
            Number of successfully stored candidates
        """
        if not terms:
            return 0

        conn = self._get_connection()
        cursor = conn.cursor()
        stored_count = 0

        try:
            # Parse domain from URL if not provided
            if not domain:
                parsed_url = urlparse(url)
                domain = parsed_url.netloc.replace('www.', '')

            # Prepare batch insert
            insert_data = []
            for term, definition, pos in terms:
                # Calculate utility score (simple heuristic)
                utility_score = self._calculate_utility_score(term, definition)

                # Prepare data for insertion
                insert_data.append((
                    term,
                    'other',  # Use 'other' since 'vocabulary_list' is not in ENUM
                    url,
                    definition[:500] if len(definition) > 500 else definition,  # Truncate for snippet
                    definition,
                    None,  # etymology_preview
                    pos,
                    utility_score,
                    json.dumps({
                        'source_type_detailed': 'vocabulary_list',  # Store actual source type here
                        'domain': domain,
                        'harvest_date': datetime.now().isoformat()
                    }),
                    datetime.now().date(),
                    'pending'
                ))

            # Batch insert with ON DUPLICATE KEY UPDATE
            cursor.executemany("""
                INSERT INTO vocab.candidate_words
                (term, source_type, source_reference, context_snippet, raw_definition,
                 etymology_preview, part_of_speech, utility_score, rarity_indicators,
                 date_discovered, review_status)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE
                    raw_definition = VALUES(raw_definition),
                    utility_score = VALUES(utility_score),
                    updated_at = CURRENT_TIMESTAMP
            """, insert_data)

            stored_count = cursor.rowcount
            conn.commit()

            self.stats['candidates_found'] = len(terms)
            self.stats['candidates_accepted'] = stored_count

            logger.info(f"Stored {stored_count} candidates to database")

        except Error as e:
            logger.error(f"Error storing candidates: {e}")
            conn.rollback()

        finally:
            cursor.close()
            conn.close()

        return stored_count

    def _calculate_utility_score(self, term: str, definition: str) -> float:
        """
        Calculate a utility score for the term

        Simple heuristic based on:
        - Term length (moderate length preferred)
        - Definition quality (length, completeness)
        - Term complexity
        """
        score = 5.0  # Base score

        # Term length scoring
        term_len = len(term)
        if 5 <= term_len <= 12:
            score += 1.0
        elif term_len > 20:
            score -= 1.0

        # Definition quality
        def_len = len(definition)
        if def_len >= 50:
            score += 1.0
        if def_len >= 100:
            score += 0.5
        if def_len < 20:
            score -= 2.0

        # Check for complete sentences
        if '.' in definition:
            score += 0.5

        # Penalize very common words (basic heuristic)
        common_words = {'the', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for'}
        if term.lower() in common_words:
            score -= 3.0

        # Bonus for multi-word terms (phrases)
        if ' ' in term:
            score += 0.5

        # Ensure score is within bounds
        return max(0.0, min(10.0, score))

    def harvest_multiple_urls(self, urls: List[str], domain: Optional[str] = None) -> Dict:
        """
        Harvest from multiple URLs

        Args:
            urls: List of URLs to harvest from
            domain: Optional domain/category for all terms

        Returns:
            Combined statistics dictionary
        """
        combined_stats = {
            'total_processed': 0,
            'candidates_found': 0,
            'candidates_accepted': 0,
            'already_defined': 0,
            'errors': 0,
            'urls_processed': 0
        }

        for url in urls:
            logger.info(f"Processing URL {combined_stats['urls_processed'] + 1}/{len(urls)}: {url}")

            # Reset instance stats for this URL
            self.stats = {
                'total_processed': 0,
                'candidates_found': 0,
                'candidates_accepted': 0,
                'already_defined': 0,
                'errors': 0
            }

            # Harvest from URL
            url_stats = self.harvest_from_url(url, domain)

            # Combine statistics
            for key in combined_stats:
                if key != 'urls_processed':
                    combined_stats[key] += url_stats.get(key, 0)

            combined_stats['urls_processed'] += 1

            # Brief delay between URLs to be respectful
            time.sleep(2)

        logger.info(f"""
        Harvest Complete:
        - URLs processed: {combined_stats['urls_processed']}
        - Total terms processed: {combined_stats['total_processed']}
        - New candidates found: {combined_stats['candidates_found']}
        - Candidates stored: {combined_stats['candidates_accepted']}
        - Already defined: {combined_stats['already_defined']}
        - Errors: {combined_stats['errors']}
        """)

        return combined_stats


def main():
    """Main entry point for testing"""
    import argparse

    parser = argparse.ArgumentParser(description='Harvest vocabulary lists from web pages')
    parser.add_argument('url', help='URL to harvest vocabulary from')
    parser.add_argument('--domain', help='Domain/category for the terms')
    parser.add_argument('--max-terms', type=int, default=1000, help='Maximum terms to process')

    args = parser.parse_args()

    harvester = VocabularyListHarvester()
    stats = harvester.harvest_from_url(args.url, args.domain, args.max_terms)

    print(f"\nHarvest Statistics:")
    for key, value in stats.items():
        print(f"  {key}: {value}")


if __name__ == "__main__":
    main()