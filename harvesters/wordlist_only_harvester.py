#!/usr/bin/env python3
"""
Wordlist-Only Harvester
ONLY extracts terms from actual vocabulary/word lists, nothing else.
Accepts ALL terms found in wordlists without any filtering.
"""

import re
import logging
import requests
from bs4 import BeautifulSoup
from core.database_manager import db_manager, database_cursor
import mysql.connector
from mysql.connector import Error
import json
from datetime import datetime
from urllib.parse import urlparse
from typing import List, Tuple, Optional, Dict

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class WordlistOnlyHarvester:
    """Harvester that ONLY processes actual vocabulary lists"""

    def __init__(self, db_config: Optional[Dict] = None):
        """Initialize harvester"""
        if db_config is None:
            import sys
            import os
            current_dir = os.path.dirname(os.path.abspath(__file__))
            parent_dir = os.path.dirname(current_dir)
            sys.path.insert(0, parent_dir)
            from core.secure_config import get_db_config
            db_config = get_db_config()

        self.db_config = db_config
        self.stats = {
            'wordlist_sections_found': 0,
            'terms_extracted': 0,
            'terms_stored': 0,
            'already_defined': 0
        }

    def harvest_from_url(self, url: str, domain: Optional[str] = None) -> Dict:
        """
        Harvest ONLY from vocabulary lists on the page

        Args:
            url: URL to harvest from
            domain: Optional domain category

        Returns:
            Harvest statistics
        """
        logger.info(f"Harvesting vocabulary lists from: {url}")

        try:
            # Fetch page
            response = requests.get(url, headers={
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            }, timeout=30)
            response.raise_for_status()

            soup = BeautifulSoup(response.text, 'html.parser')

            # Find ONLY vocabulary list sections
            wordlist_sections = self._identify_vocabulary_lists(soup)

            if not wordlist_sections:
                logger.warning("No vocabulary list sections found")
                return self.stats

            logger.info(f"Found {len(wordlist_sections)} vocabulary list sections")
            self.stats['wordlist_sections_found'] = len(wordlist_sections)

            # Extract terms ONLY from these sections
            all_terms = []
            for section in wordlist_sections:
                terms = self._extract_terms_from_wordlist(section)
                all_terms.extend(terms)
                logger.debug(f"Section extracted {len(terms)} terms")

            logger.info(f"Total terms extracted from wordlists: {len(all_terms)}")
            self.stats['terms_extracted'] = len(all_terms)

            if not all_terms:
                logger.warning("No terms extracted from wordlist sections")
                return self.stats

            # Remove duplicates
            unique_terms = self._deduplicate_terms(all_terms)
            logger.info(f"Unique terms: {len(unique_terms)}")

            # Filter existing terms
            new_terms = self._filter_existing_terms(unique_terms)
            logger.info(f"New terms not in database: {len(new_terms)}")

            # Store ALL new terms (no filtering)
            if new_terms:
                stored = self._store_all_terms(new_terms, url, domain)
                self.stats['terms_stored'] = stored
                logger.info(f"Stored {stored} terms")

        except Exception as e:
            logger.error(f"Error harvesting from {url}: {e}")
            import traceback
            traceback.print_exc()

        return self.stats

    def _identify_vocabulary_lists(self, soup: BeautifulSoup) -> List:
        """
        Identify sections that are ACTUALLY vocabulary lists

        Returns:
            List of BeautifulSoup elements that contain vocabulary lists
        """
        wordlist_sections = []

        # Strategy 1: Look for explicit vocabulary list indicators
        vocab_indicators = [
            'vocabulary', 'glossary', 'dictionary', 'word list', 'wordlist',
            'terms', 'lexicon', 'vocab', 'definitions'
        ]

        # Find sections with vocabulary indicators in headings or classes
        for indicator in vocab_indicators:
            # Headings containing vocabulary indicators
            headings = soup.find_all(['h1', 'h2', 'h3', 'h4', 'h5', 'h6'],
                                   string=re.compile(indicator, re.I))

            for heading in headings:
                # Find the container that likely holds the vocabulary
                container = self._find_vocabulary_container(heading)
                if container and container not in wordlist_sections:
                    wordlist_sections.append(container)

            # Elements with vocabulary-related classes or IDs
            elements = soup.find_all(class_=re.compile(indicator, re.I))
            elements.extend(soup.find_all(id=re.compile(indicator, re.I)))

            for element in elements:
                if element not in wordlist_sections and self._looks_like_wordlist(element):
                    wordlist_sections.append(element)

        # Strategy 2: Look for structured lists that look like vocabulary
        # Definition lists (dl) - these are almost always vocabulary when they exist
        for dl in soup.find_all('dl'):
            if self._is_vocabulary_definition_list(dl):
                wordlist_sections.append(dl)

        # Tables that look like vocabulary
        for table in soup.find_all('table'):
            if self._is_vocabulary_table(table):
                wordlist_sections.append(table)

        # Lists that clearly contain vocabulary
        for list_elem in soup.find_all(['ul', 'ol']):
            if self._is_vocabulary_list(list_elem):
                wordlist_sections.append(list_elem)

        return wordlist_sections

    def _find_vocabulary_container(self, heading) -> Optional:
        """Find the container that holds vocabulary after a vocabulary heading"""
        # Look for next sibling that contains structured content
        current = heading.next_sibling

        while current:
            if hasattr(current, 'name') and current.name:
                # Check if this element contains structured vocabulary
                if current.name in ['dl', 'table', 'ul', 'ol', 'div', 'section']:
                    if self._looks_like_wordlist(current):
                        return current
            current = current.next_sibling

        # If no sibling found, check parent's next elements
        parent = heading.parent
        if parent:
            # Look for structured elements after this heading within same parent
            all_elements = parent.find_all(['dl', 'table', 'ul', 'ol', 'div'])
            for elem in all_elements:
                if self._looks_like_wordlist(elem):
                    return elem

        return None

    def _looks_like_wordlist(self, element) -> bool:
        """Check if an element looks like it contains a vocabulary list"""
        if not element or not hasattr(element, 'get_text'):
            return False

        text = element.get_text()

        # Must have reasonable amount of content
        if len(text) < 50:
            return False

        # Check for vocabulary-like patterns
        # Look for multiple term-definition patterns
        patterns = [
            r'[A-Z][a-zA-Z]+\s*:\s*[A-Z]',  # Term: Definition
            r'[A-Z][a-zA-Z]+\s*[-–—]\s*[A-Z]',  # Term - Definition
            r'[A-Z][a-zA-Z]+.*?\n.*?[a-z]',  # Term on one line, definition next
        ]

        pattern_count = 0
        for pattern in patterns:
            matches = re.findall(pattern, text)
            pattern_count += len(matches)

        # Should have at least 3 term-definition patterns to be considered a wordlist
        return pattern_count >= 3

    def _is_vocabulary_definition_list(self, dl) -> bool:
        """Check if definition list contains vocabulary"""
        dt_elements = dl.find_all('dt')
        dd_elements = dl.find_all('dd')

        # Must have at least 2 term-definition pairs (was too strict before)
        if len(dt_elements) < 2 or len(dd_elements) < 2:
            return False

        # Check if terms look like vocabulary words
        vocabulary_like = 0
        for dt in dt_elements[:5]:  # Check first 5
            term = dt.get_text().strip()
            # Should be reasonable word length and alphabetic
            if 2 <= len(term) <= 50 and re.match(r'^[A-Za-z\s\'-]+$', term):
                vocabulary_like += 1

        return vocabulary_like >= 2  # At least 2 valid terms

    def _is_vocabulary_table(self, table) -> bool:
        """Check if table contains vocabulary"""
        rows = table.find_all('tr')
        if len(rows) < 4:  # At least header + 3 data rows
            return False

        # Check if looks like term-definition table
        vocabulary_rows = 0
        for row in rows[1:6]:  # Skip header, check first 5 data rows
            cells = row.find_all(['td', 'th'])
            if len(cells) >= 2:
                term = cells[0].get_text().strip()
                definition = cells[1].get_text().strip()

                # Check if looks like vocabulary
                if (2 <= len(term) <= 50 and len(definition) >= 10 and
                    re.match(r'^[A-Za-z\s\'-]+$', term)):
                    vocabulary_rows += 1

        return vocabulary_rows >= 3

    def _is_vocabulary_list(self, list_elem) -> bool:
        """Check if list contains vocabulary"""
        items = list_elem.find_all('li')
        if len(items) < 3:
            return False

        vocabulary_items = 0
        for item in items[:5]:  # Check first 5 items
            text = item.get_text().strip()

            # Look for term-definition patterns
            if any(sep in text for sep in [': ', ' - ', ' – ', ' — ']):
                # Split and check if looks like term-definition
                for sep in [': ', ' - ', ' – ', ' — ']:
                    if sep in text:
                        parts = text.split(sep, 1)
                        if len(parts) == 2:
                            term = parts[0].strip()
                            definition = parts[1].strip()
                            if (2 <= len(term) <= 50 and len(definition) >= 5 and
                                re.match(r'^[A-Za-z\s\'-]+$', term)):
                                vocabulary_items += 1
                                break

        return vocabulary_items >= 3

    def _extract_terms_from_wordlist(self, section) -> List[Tuple[str, str]]:
        """
        Extract terms from a confirmed vocabulary list section

        Args:
            section: BeautifulSoup element containing vocabulary

        Returns:
            List of (term, definition) tuples
        """
        terms = []

        # Extract based on element type
        if section.name == 'dl':
            terms = self._extract_from_dl(section)
        elif section.name == 'table':
            terms = self._extract_from_table(section)
        elif section.name in ['ul', 'ol']:
            terms = self._extract_from_list(section)
        else:
            # Generic extraction for div/section
            terms = self._extract_from_generic(section)

        return terms

    def _extract_from_dl(self, dl) -> List[Tuple[str, str]]:
        """Extract from definition list"""
        terms = []
        dt_elements = dl.find_all('dt')
        dd_elements = dl.find_all('dd')

        for i, dt in enumerate(dt_elements):
            if i < len(dd_elements):
                term = self._clean_term(dt.get_text())
                definition = self._clean_definition(dd_elements[i].get_text())

                if term and definition:
                    terms.append((term, definition))

        return terms

    def _extract_from_table(self, table) -> List[Tuple[str, str]]:
        """Extract from vocabulary table"""
        terms = []
        rows = table.find_all('tr')

        # Skip header row
        for row in rows[1:]:
            cells = row.find_all(['td', 'th'])
            if len(cells) >= 2:
                term = self._clean_term(cells[0].get_text())
                definition = self._clean_definition(cells[1].get_text())

                if term and definition:
                    terms.append((term, definition))

        return terms

    def _extract_from_list(self, list_elem) -> List[Tuple[str, str]]:
        """Extract from vocabulary list"""
        terms = []
        items = list_elem.find_all('li')

        for item in items:
            text = item.get_text().strip()

            # Try different separators
            for separator in [': ', ' - ', ' – ', ' — ', '. ']:
                if separator in text:
                    parts = text.split(separator, 1)
                    if len(parts) == 2:
                        term = self._clean_term(parts[0])
                        definition = self._clean_definition(parts[1])

                        if term and definition:
                            terms.append((term, definition))
                            break

            # Also check for bold terms
            strong = item.find(['strong', 'b'])
            if strong:
                term = self._clean_term(strong.get_text())
                strong.extract()
                definition = self._clean_definition(item.get_text())

                if term and definition:
                    terms.append((term, definition))

        return terms

    def _extract_from_generic(self, element) -> List[Tuple[str, str]]:
        """Extract from generic container"""
        terms = []
        text = element.get_text()

        # Look for term: definition patterns
        patterns = [
            r'^([A-Z][A-Za-z\s\'-]{1,49})\s*:\s*(.{5,500})$',
            r'^([A-Z][A-Za-z\s\'-]{1,49})\s*[-–—]\s*(.{5,500})$'
        ]

        for pattern in patterns:
            matches = re.findall(pattern, text, re.MULTILINE)
            for term, definition in matches:
                clean_term = self._clean_term(term)
                clean_def = self._clean_definition(definition)
                if clean_term and clean_def:
                    terms.append((clean_term, clean_def))

        return terms

    def _clean_term(self, term: str) -> str:
        """Clean term text"""
        if not term:
            return ""

        # Remove extra whitespace
        term = ' '.join(term.split())

        # Remove numbering
        term = re.sub(r'^\d+[\.\)]\s*', '', term)

        # Keep only letters, spaces, hyphens, apostrophes
        term = re.sub(r'[^A-Za-z\s\'-]', '', term)

        return term.strip()

    def _clean_definition(self, definition: str) -> str:
        """Clean definition text"""
        if not definition:
            return ""

        # Remove extra whitespace
        definition = ' '.join(definition.split())

        # Remove citations
        definition = re.sub(r'\[[0-9]+\]', '', definition)

        return definition.strip()

    def _deduplicate_terms(self, terms: List[Tuple[str, str]]) -> List[Tuple[str, str]]:
        """Remove duplicate terms"""
        seen = set()
        unique = []

        for term, definition in terms:
            term_key = term.lower()
            if term_key not in seen:
                seen.add(term_key)
                unique.append((term, definition))

        return unique

    def _filter_existing_terms(self, terms: List[Tuple[str, str]]) -> List[Tuple[str, str]]:
        """Filter out terms already in defined table"""
        if not terms:
            return []

        try:
            term_strings = [term.lower() for term, _ in terms]
            placeholders = ','.join(['%s'] * len(term_strings))

            with database_cursor() as cursor:
                cursor.execute(f"""
                    SELECT LOWER(term) FROM vocab.defined
                    WHERE LOWER(term) IN ({placeholders})
                """, term_strings)

                existing = set(row[0] for row in cursor.fetchall())

                new_terms = []
                for term, definition in terms:
                    if term.lower() not in existing:
                        new_terms.append((term, definition))
                    else:
                        self.stats['already_defined'] += 1

                return new_terms

        except Exception as e:
            logger.error(f"Error filtering existing terms: {e}")
            return terms

    def _store_all_terms(self, terms: List[Tuple[str, str]], source_url: str, domain: Optional[str]) -> int:
        """Store ALL terms without any filtering"""
        if not terms:
            return 0

        try:
            if not domain:
                domain = urlparse(source_url).netloc.replace('www.', '')

            insert_data = []
            for term, definition in terms:
                metadata = {
                    'source_type_detailed': 'vocabulary_list',
                    'domain': domain,
                    'harvest_date': datetime.now().isoformat(),
                    'harvester': 'wordlist_only_v1.0'
                }

                insert_data.append((
                    term,
                    'other',  # ENUM constraint
                    source_url,
                    definition[:500],  # context_snippet
                    definition,  # raw_definition
                    None,  # etymology_preview
                    None,  # part_of_speech
                    5.0,   # utility_score
                    json.dumps(metadata),
                    datetime.now().date(),
                    'pending'
                ))

            stored = db_manager.execute_many("""
                INSERT INTO vocab.candidate_words
                (term, source_type, source_reference, context_snippet, raw_definition,
                 etymology_preview, part_of_speech, utility_score, rarity_indicators,
                 date_discovered, review_status)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE
                    raw_definition = VALUES(raw_definition),
                    updated_at = CURRENT_TIMESTAMP
            """, insert_data)

            logger.info(f"Stored {stored} wordlist terms")
            return stored

        except Exception as e:
            logger.error(f"Error storing terms: {e}")
            return 0


def main():
    """Command line interface"""
    import argparse

    parser = argparse.ArgumentParser(description='Wordlist-Only Vocabulary Harvester')
    parser.add_argument('url', help='URL containing vocabulary lists')
    parser.add_argument('--domain', help='Domain/category for terms')

    args = parser.parse_args()

    harvester = WordlistOnlyHarvester()
    stats = harvester.harvest_from_url(args.url, args.domain)

    print(f"\nHarvest Results:")
    print(f"  Wordlist sections found: {stats['wordlist_sections_found']}")
    print(f"  Terms extracted: {stats['terms_extracted']}")
    print(f"  Terms stored: {stats['terms_stored']}")
    print(f"  Already defined: {stats['already_defined']}")


if __name__ == "__main__":
    main()