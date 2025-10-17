#!/usr/bin/env python3
"""
Revised Vocabulary List Harvester
Simplified, robust approach focused on finding ALL terms in vocabulary lists
"""

import re
import logging
import hashlib
from typing import List, Tuple, Optional, Dict, Set, Any
from datetime import datetime
from urllib.parse import urlparse, urljoin
import requests
from bs4 import BeautifulSoup, Tag, NavigableString
import mysql.connector
from mysql.connector import Error
import json
import time

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class RevisedVocabularyHarvester:
    """Simplified, robust vocabulary list harvester"""

    def __init__(self, db_config: Optional[Dict] = None):
        """Initialize the revised harvester"""
        if db_config is None:
            import sys
            import os
            current_dir = os.path.dirname(os.path.abspath(__file__))
            parent_dir = os.path.dirname(current_dir)
            sys.path.insert(0, parent_dir)
            from core.config import get_db_config
            db_config = get_db_config()

        self.db_config = db_config
        self.stats = {
            'total_processed': 0,
            'candidates_found': 0,
            'candidates_accepted': 0,
            'already_defined': 0,
            'errors': 0
        }

    def _get_connection(self):
        """Get database connection"""
        return mysql.connector.connect(**self.db_config)

    def harvest_from_url(self, url: str, domain: Optional[str] = None) -> Dict:
        """
        Harvest vocabulary from a URL using simplified approach

        Args:
            url: The URL to harvest from
            domain: Optional domain/category for the terms

        Returns:
            Harvest statistics
        """
        logger.info(f"Harvesting from {url}")

        try:
            # Fetch page content
            response = requests.get(url, headers={
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            }, timeout=30)
            response.raise_for_status()

            soup = BeautifulSoup(response.text, 'html.parser')

            # Extract ALL vocabulary terms using multiple strategies
            all_terms = self._extract_vocabulary_comprehensive(soup)

            if not all_terms:
                logger.warning("No vocabulary terms found")
                return self.stats

            logger.info(f"Found {len(all_terms)} potential terms")
            self.stats['total_processed'] = len(all_terms)

            # Clean and validate terms (minimal filtering)
            valid_terms = self._clean_and_validate(all_terms)
            logger.info(f"After basic validation: {len(valid_terms)} terms")

            # Filter existing terms
            new_terms = self._filter_existing_terms(valid_terms)
            logger.info(f"New terms not in database: {len(new_terms)}")

            # Store all new terms
            if new_terms:
                stored = self._store_candidates(new_terms, url, domain)
                logger.info(f"Stored {stored} candidates")

        except Exception as e:
            logger.error(f"Error harvesting from {url}: {e}")
            self.stats['errors'] += 1

        return self.stats

    def _extract_vocabulary_comprehensive(self, soup: BeautifulSoup) -> List[Tuple[str, str]]:
        """
        Extract vocabulary using multiple comprehensive strategies

        Returns:
            List of (term, definition) tuples
        """
        all_terms = []

        # Strategy 1: Definition Lists (most structured)
        dl_terms = self._extract_from_definition_lists(soup)
        all_terms.extend(dl_terms)
        logger.debug(f"Definition lists: {len(dl_terms)} terms")

        # Strategy 2: Tables (common for vocabulary)
        table_terms = self._extract_from_tables(soup)
        all_terms.extend(table_terms)
        logger.debug(f"Tables: {len(table_terms)} terms")

        # Strategy 3: Lists with patterns
        list_terms = self._extract_from_lists(soup)
        all_terms.extend(list_terms)
        logger.debug(f"Lists: {len(list_terms)} terms")

        # Strategy 4: Structured text patterns
        text_terms = self._extract_from_structured_text(soup)
        all_terms.extend(text_terms)
        logger.debug(f"Structured text: {len(text_terms)} terms")

        # Strategy 5: Bold/strong patterns
        bold_terms = self._extract_from_bold_patterns(soup)
        all_terms.extend(bold_terms)
        logger.debug(f"Bold patterns: {len(bold_terms)} terms")

        # Strategy 6: Generic text mining (fallback)
        mined_terms = self._extract_from_text_mining(soup)
        all_terms.extend(mined_terms)
        logger.debug(f"Text mining: {len(mined_terms)} terms")

        # Remove duplicates while preserving order
        seen = set()
        unique_terms = []
        for term, definition in all_terms:
            term_key = term.lower().strip()
            if term_key and term_key not in seen and len(term_key) > 1:
                seen.add(term_key)
                unique_terms.append((term, definition))

        logger.info(f"Total unique terms extracted: {len(unique_terms)}")
        return unique_terms

    def _extract_from_definition_lists(self, soup: BeautifulSoup) -> List[Tuple[str, str]]:
        """Extract from HTML definition lists (dl, dt, dd)"""
        terms = []

        for dl in soup.find_all('dl'):
            dt_elements = dl.find_all('dt')
            dd_elements = dl.find_all('dd')

            # Match dt with dd elements
            for i, dt in enumerate(dt_elements):
                if i < len(dd_elements):
                    term = self._clean_text(dt.get_text())
                    definition = self._clean_text(dd_elements[i].get_text())

                    if term and definition:
                        terms.append((term, definition))

        return terms

    def _extract_from_tables(self, soup: BeautifulSoup) -> List[Tuple[str, str]]:
        """Extract from table structures"""
        terms = []

        for table in soup.find_all('table'):
            rows = table.find_all('tr')

            for row in rows:
                cells = row.find_all(['td', 'th'])

                # Skip if not at least 2 columns
                if len(cells) < 2:
                    continue

                # Skip obvious header rows
                if row.find('th') and not row.find('td'):
                    continue

                term = self._clean_text(cells[0].get_text())
                definition = self._clean_text(cells[1].get_text())

                # Basic validation
                if (term and definition and
                    len(term) < 100 and len(definition) > 5 and
                    not self._looks_like_header(term, definition)):
                    terms.append((term, definition))

        return terms

    def _extract_from_lists(self, soup: BeautifulSoup) -> List[Tuple[str, str]]:
        """Extract from ul/ol lists with various patterns"""
        terms = []

        for list_elem in soup.find_all(['ul', 'ol']):
            items = list_elem.find_all('li')

            for item in items:
                item_text = item.get_text().strip()

                # Try various separators
                separators = [' - ', ': ', ' – ', ' — ', ' | ', '. ']

                for sep in separators:
                    if sep in item_text:
                        parts = item_text.split(sep, 1)
                        if len(parts) == 2:
                            term = self._clean_text(parts[0])
                            definition = self._clean_text(parts[1])

                            if term and definition and len(term) < 100:
                                terms.append((term, definition))
                                break

                # Also check for bold/strong term followed by definition
                strong_elem = item.find(['strong', 'b'])
                if strong_elem:
                    term = self._clean_text(strong_elem.get_text())

                    # Get remaining text after removing the strong element
                    strong_elem_copy = strong_elem.extract()
                    definition = self._clean_text(item.get_text())

                    # Clean up definition (remove leading punctuation)
                    definition = re.sub(r'^[:\-–—\s]+', '', definition).strip()

                    if term and definition and len(term) < 100:
                        terms.append((term, definition))

        return terms

    def _extract_from_structured_text(self, soup: BeautifulSoup) -> List[Tuple[str, str]]:
        """Extract from structured text patterns"""
        terms = []

        # Get all text and look for patterns
        text_blocks = soup.find_all(['p', 'div', 'section', 'article'])

        for block in text_blocks:
            text = block.get_text()

            # Pattern: WORD: definition
            pattern1 = r'^([A-Z][a-zA-Z\'\-\s]{2,49})\s*:\s*(.{10,500})$'
            matches = re.findall(pattern1, text, re.MULTILINE)
            terms.extend(matches)

            # Pattern: WORD - definition
            pattern2 = r'^([A-Z][a-zA-Z\'\-\s]{2,49})\s*[-–—]\s*(.{10,500})$'
            matches = re.findall(pattern2, text, re.MULTILINE)
            terms.extend(matches)

            # Pattern: Word (possibly lowercase): definition
            pattern3 = r'^([A-Za-z][a-zA-Z\'\-\s]{2,49})\s*:\s*(.{10,500})$'
            matches = re.findall(pattern3, text, re.MULTILINE)
            terms.extend(matches)

        return [(self._clean_text(t), self._clean_text(d)) for t, d in terms]

    def _extract_from_bold_patterns(self, soup: BeautifulSoup) -> List[Tuple[str, str]]:
        """Extract from bold/strong elements followed by definitions"""
        terms = []

        for bold_elem in soup.find_all(['strong', 'b']):
            term = self._clean_text(bold_elem.get_text())

            if not term or len(term) > 50:
                continue

            # Look for definition in various places
            definition = None

            # 1. Next sibling text
            next_sibling = bold_elem.next_sibling
            if isinstance(next_sibling, NavigableString):
                definition = self._clean_text(str(next_sibling))

            # 2. Parent's remaining text
            if not definition or len(definition) < 10:
                parent = bold_elem.parent
                if parent:
                    parent_text = parent.get_text()
                    if term in parent_text:
                        idx = parent_text.index(term) + len(term)
                        remaining = parent_text[idx:].strip()
                        # Clean up leading punctuation
                        remaining = re.sub(r'^[:\-–—\s]+', '', remaining).strip()
                        if len(remaining) > 10:
                            definition = remaining[:500]  # Limit length

            if definition and len(definition) > 10:
                terms.append((term, definition))

        return terms

    def _extract_from_text_mining(self, soup: BeautifulSoup) -> List[Tuple[str, str]]:
        """Fallback text mining approach"""
        terms = []

        # Get all text content
        all_text = soup.get_text()
        lines = all_text.split('\n')

        current_term = None
        current_definition = []

        for line in lines:
            line = line.strip()
            if not line:
                continue

            # If line looks like a term (short, starts with capital, no punctuation at end)
            if (len(line) < 50 and
                line[0].isupper() and
                not line.endswith(('.', '!', '?')) and
                ':' not in line and
                len(line.split()) <= 5):

                # Save previous term
                if current_term and current_definition:
                    definition = ' '.join(current_definition)
                    if len(definition) > 10:
                        terms.append((current_term, definition))

                # Start new term
                current_term = line
                current_definition = []

            elif current_term and len(line) > 10:
                # Add to current definition
                current_definition.append(line)

                # Limit definition length
                if len(' '.join(current_definition)) > 1000:
                    break

        # Don't forget the last term
        if current_term and current_definition:
            definition = ' '.join(current_definition)
            if len(definition) > 10:
                terms.append((current_term, definition))

        return terms

    def _clean_text(self, text: str) -> str:
        """Clean and normalize text"""
        if not text:
            return ""

        # Remove extra whitespace
        text = ' '.join(text.split())

        # Remove common artifacts
        text = re.sub(r'\[[0-9]+\]', '', text)  # Citations
        text = re.sub(r'\s+', ' ', text)  # Multiple spaces

        return text.strip()

    def _looks_like_header(self, term: str, definition: str) -> bool:
        """Check if this looks like a table header rather than vocabulary"""
        headers = ['word', 'term', 'definition', 'meaning', 'vocabulary', 'name', 'description']

        term_lower = term.lower()
        def_lower = definition.lower()

        return (term_lower in headers or def_lower in headers or
                (len(term) < 6 and len(definition) < 15))

    def _clean_and_validate(self, terms: List[Tuple[str, str]]) -> List[Tuple[str, str]]:
        """Clean and do minimal validation - accept almost everything"""
        valid_terms = []

        for term, definition in terms:
            # Clean
            clean_term = self._clean_text(term)
            clean_definition = self._clean_text(definition)

            # Minimal validation only
            if (clean_term and clean_definition and
                2 <= len(clean_term) <= 100 and  # Reasonable term length
                len(clean_definition) >= 5 and    # Has some definition
                len(clean_definition) <= 2000):   # Not too long

                valid_terms.append((clean_term, clean_definition))

        return valid_terms

    def _filter_existing_terms(self, terms: List[Tuple[str, str]]) -> List[Tuple[str, str]]:
        """Filter out terms that already exist in 'defined' table"""
        if not terms:
            return []

        conn = self._get_connection()
        cursor = conn.cursor()

        try:
            # Get all term strings
            term_strings = [term.lower() for term, _ in terms]

            # Batch check
            placeholders = ','.join(['%s'] * len(term_strings))
            cursor.execute(f"""
                SELECT LOWER(term)
                FROM vocab.defined
                WHERE LOWER(term) IN ({placeholders})
            """, term_strings)

            existing = set(row[0] for row in cursor.fetchall())

            # Filter
            new_terms = []
            for term, definition in terms:
                if term.lower() not in existing:
                    new_terms.append((term, definition))
                    self.stats['candidates_found'] += 1
                else:
                    self.stats['already_defined'] += 1

            return new_terms

        except Error as e:
            logger.error(f"Error filtering existing terms: {e}")
            return terms

        finally:
            cursor.close()
            conn.close()

    def _store_candidates(self, terms: List[Tuple[str, str]], source_url: str, domain: Optional[str]) -> int:
        """Store candidate terms in database"""
        if not terms:
            return 0

        conn = self._get_connection()
        cursor = conn.cursor()
        stored = 0

        try:
            # Parse domain from URL if not provided
            if not domain:
                parsed_url = urlparse(source_url)
                domain = parsed_url.netloc.replace('www.', '')

            insert_data = []
            for term, definition in terms:
                # Prepare metadata
                metadata = {
                    'source_type_detailed': 'vocabulary_list',
                    'domain': domain,
                    'harvest_date': datetime.now().isoformat(),
                    'harvester_version': 'revised_v1.0'
                }

                insert_data.append((
                    term,
                    'other',  # Use 'other' for ENUM constraint
                    source_url,
                    definition[:500] if len(definition) > 500 else definition,  # context_snippet
                    definition,  # raw_definition
                    None,  # etymology_preview
                    None,  # part_of_speech (not determined here)
                    5.0,   # utility_score (default for all terms)
                    json.dumps(metadata),
                    datetime.now().date(),
                    'pending'
                ))

            # Batch insert
            cursor.executemany("""
                INSERT INTO vocab.candidate_words
                (term, source_type, source_reference, context_snippet, raw_definition,
                 etymology_preview, part_of_speech, utility_score, rarity_indicators,
                 date_discovered, review_status)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE
                    raw_definition = IF(LENGTH(VALUES(raw_definition)) > LENGTH(raw_definition),
                                       VALUES(raw_definition), raw_definition),
                    updated_at = CURRENT_TIMESTAMP
            """, insert_data)

            stored = cursor.rowcount
            conn.commit()

            self.stats['candidates_accepted'] = stored
            logger.info(f"Stored {stored} candidates")

        except Error as e:
            logger.error(f"Error storing candidates: {e}")
            conn.rollback()

        finally:
            cursor.close()
            conn.close()

        return stored

    def harvest_site(self, base_url: str, crawl_alphabetical: bool = True, max_pages: int = 50) -> Dict:
        """
        Harvest an entire site, looking for alphabetical divisions

        Args:
            base_url: Base URL of the vocabulary site
            crawl_alphabetical: Whether to look for A-Z divisions
            max_pages: Maximum pages to crawl

        Returns:
            Combined harvest statistics
        """
        logger.info(f"Starting site harvest from {base_url}")

        urls_to_process = [base_url]
        processed_urls = set()

        if crawl_alphabetical:
            alpha_urls = self._find_alphabetical_urls(base_url)
            if alpha_urls:
                logger.info(f"Found {len(alpha_urls)} alphabetical pages")
                urls_to_process = alpha_urls[:max_pages]

        # Combined stats
        combined_stats = {
            'total_processed': 0,
            'candidates_found': 0,
            'candidates_accepted': 0,
            'already_defined': 0,
            'errors': 0,
            'urls_processed': 0
        }

        for url in urls_to_process:
            if url in processed_urls:
                continue

            logger.info(f"Processing: {url}")

            # Reset stats for this URL
            self.stats = {
                'total_processed': 0,
                'candidates_found': 0,
                'candidates_accepted': 0,
                'already_defined': 0,
                'errors': 0
            }

            # Harvest this URL
            self.harvest_from_url(url)

            # Add to combined stats
            for key in combined_stats:
                if key != 'urls_processed':
                    combined_stats[key] += self.stats.get(key, 0)

            combined_stats['urls_processed'] += 1
            processed_urls.add(url)

            # Respectful delay
            time.sleep(2)

        return combined_stats

    def _find_alphabetical_urls(self, base_url: str) -> List[str]:
        """Find alphabetical division URLs (A-Z pages)"""
        try:
            response = requests.get(base_url, timeout=30)
            soup = BeautifulSoup(response.text, 'html.parser')

            alpha_urls = []

            # Look for A-Z navigation
            for link in soup.find_all('a', href=True):
                text = link.get_text().strip()
                href = link.get('href')

                # Single letter links
                if text and len(text) == 1 and text.isalpha() and text.isupper():
                    full_url = urljoin(base_url, href)
                    alpha_urls.append(full_url)

                # "Letter A", "Words starting with A" etc
                elif re.match(r'(letter\s+[a-z]|[a-z]\s+words|\w*\s*[a-z]\s*\w*)', text.lower()):
                    full_url = urljoin(base_url, href)
                    alpha_urls.append(full_url)

            # Remove duplicates
            return list(set(alpha_urls))

        except Exception as e:
            logger.error(f"Error finding alphabetical URLs: {e}")
            return []


def main():
    """Main entry point"""
    import argparse

    parser = argparse.ArgumentParser(description='Revised Vocabulary List Harvester')
    parser.add_argument('url', help='URL to harvest')
    parser.add_argument('--site', action='store_true', help='Harvest entire site with alphabetical crawling')
    parser.add_argument('--domain', help='Domain/category for terms')

    args = parser.parse_args()

    harvester = RevisedVocabularyHarvester()

    if args.site:
        stats = harvester.harvest_site(args.url, crawl_alphabetical=True)
    else:
        stats = harvester.harvest_from_url(args.url, args.domain)

    print("\nHarvest Results:")
    for key, value in stats.items():
        print(f"  {key}: {value}")


if __name__ == "__main__":
    main()