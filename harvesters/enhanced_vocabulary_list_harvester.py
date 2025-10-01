#!/usr/bin/env python3
"""
Enhanced Vocabulary List Harvester
Harvests vocabulary terms from web pages with advanced features:
- Flexible pattern detection for any vocabulary list structure
- Definition lookup for terms without definitions
- POS imputation and multi-sense combining
- Site crawling for alphabetical divisions
- Quality filtering and metadata extraction
"""

import re
import logging
import hashlib
from typing import List, Tuple, Optional, Dict, Set, Any
from datetime import datetime
from urllib.parse import urlparse, urljoin
import requests
from bs4 import BeautifulSoup, Tag
import mysql.connector
from mysql.connector import Error
import json
import time
import asyncio
from dataclasses import dataclass

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@dataclass
class VocabularyTerm:
    """Structured vocabulary term with all metadata"""
    term: str
    definitions: Dict[str, List[str]]  # POS -> list of definitions/senses
    primary_definition: str
    part_of_speech: Optional[str]
    etymology: Optional[str]
    pronunciation: Optional[str]
    examples: List[str]
    synonyms: List[str]
    source_url: str
    quality_score: float
    metadata: Dict[str, Any]


class EnhancedVocabularyListHarvester:
    """Advanced harvester with comprehensive features"""

    def __init__(self, db_config: Optional[Dict] = None):
        """Initialize the enhanced harvester"""
        if db_config is None:
            import sys
            import os
            parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            if parent_dir not in sys.path:
                sys.path.insert(0, parent_dir)
            from core.config import get_db_config
            db_config = get_db_config()

        self.db_config = db_config
        self.definition_lookup = None
        self._init_definition_lookup()

        self.session_id = None
        self.stats = {
            'total_processed': 0,
            'candidates_found': 0,
            'candidates_accepted': 0,
            'already_defined': 0,
            'definitions_looked_up': 0,
            'undefined_candidates': 0,
            'errors': 0
        }

        # Enhanced pattern detectors - more flexible
        self.pattern_detectors = [
            self._detect_any_structured_list,
            self._detect_definition_blocks,
            self._detect_card_based_layout,
            self._detect_accordion_pattern,
            self._detect_glossary_pattern,
            self._detect_mixed_content
        ]

        # POS patterns and indicators
        self.pos_patterns = {
            'NOUN': ['n.', 'noun', 'n', '(n)', '[n]', 'substantive'],
            'VERB': ['v.', 'verb', 'v', '(v)', '[v]', 'vb', 'v.t.', 'v.i.'],
            'ADJECTIVE': ['adj.', 'adjective', 'adj', '(adj)', '[adj]', 'a.'],
            'ADVERB': ['adv.', 'adverb', 'adv', '(adv)', '[adv]'],
            'PREPOSITION': ['prep.', 'preposition', 'prep', '(prep)'],
            'CONJUNCTION': ['conj.', 'conjunction', 'conj', '(conj)'],
            'INTERJECTION': ['interj.', 'interjection', 'int', '(int)'],
            'PRONOUN': ['pron.', 'pronoun', 'pron', '(pron)']
        }

    def _init_definition_lookup(self):
        """Initialize the definition lookup system"""
        try:
            # Try to import the definition lookup
            import sys
            import os
            current_dir = os.path.dirname(os.path.abspath(__file__))
            parent_dir = os.path.dirname(current_dir)
            sys.path.insert(0, parent_dir)

            # Try multiple import paths
            try:
                from core.comprehensive_definition_lookup import ComprehensiveDefinitionLookup
            except ImportError:
                # Fallback import
                import importlib.util
                spec = importlib.util.spec_from_file_location(
                    "comprehensive_definition_lookup",
                    os.path.join(parent_dir, "core", "comprehensive_definition_lookup.py")
                )
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
                ComprehensiveDefinitionLookup = module.ComprehensiveDefinitionLookup

            self.definition_lookup = ComprehensiveDefinitionLookup()
            logger.info("Definition lookup system initialized")
        except Exception as e:
            logger.warning(f"Could not import definition lookup: {e}")
            self.definition_lookup = None

    def _get_connection(self):
        """Get database connection"""
        return mysql.connector.connect(**self.db_config)

    def harvest_site(self, base_url: str, crawl_alphabetical: bool = True,
                     max_pages: int = 100) -> Dict:
        """
        Harvest an entire site, optionally crawling alphabetical divisions

        Args:
            base_url: The base URL of the vocabulary site
            crawl_alphabetical: Whether to look for and crawl A-Z divisions
            max_pages: Maximum number of pages to crawl

        Returns:
            Harvest statistics
        """
        logger.info(f"Starting site harvest from {base_url}")

        urls_to_process = [base_url]
        processed_urls = set()

        if crawl_alphabetical:
            # Look for alphabetical navigation
            alpha_urls = self._find_alphabetical_urls(base_url)
            if alpha_urls:
                logger.info(f"Found {len(alpha_urls)} alphabetical divisions")
                urls_to_process = alpha_urls
            else:
                # Look for pagination
                paginated_urls = self._find_paginated_urls(base_url)
                if paginated_urls:
                    logger.info(f"Found {len(paginated_urls)} paginated pages")
                    urls_to_process.extend(paginated_urls[:max_pages])

        # Process each URL
        for url in urls_to_process[:max_pages]:
            if url in processed_urls:
                continue

            logger.info(f"Processing: {url}")
            self.harvest_from_url(url)
            processed_urls.add(url)

            # Respectful delay
            time.sleep(2)

        return self.stats

    def _find_alphabetical_urls(self, base_url: str) -> List[str]:
        """Find URLs for alphabetical divisions (A-Z pages)"""
        try:
            response = requests.get(base_url, timeout=30)
            soup = BeautifulSoup(response.text, 'html.parser')

            alpha_urls = []

            # Look for A-Z navigation links
            for link in soup.find_all('a'):
                href = link.get('href')
                text = link.get_text().strip()

                # Check if it's a single letter link
                if text and len(text) == 1 and text.isalpha():
                    full_url = urljoin(base_url, href)
                    alpha_urls.append(full_url)

                # Check for "Letter A", "A words", etc.
                elif re.match(r'^(letter\s+)?[a-z](\s+words)?$', text.lower()):
                    full_url = urljoin(base_url, href)
                    alpha_urls.append(full_url)

            # Remove duplicates while preserving order
            seen = set()
            unique_urls = []
            for url in alpha_urls:
                if url not in seen:
                    seen.add(url)
                    unique_urls.append(url)

            return unique_urls

        except Exception as e:
            logger.error(f"Error finding alphabetical URLs: {e}")
            return []

    def _find_paginated_urls(self, base_url: str) -> List[str]:
        """Find paginated URLs (page 1, 2, 3, etc.)"""
        try:
            response = requests.get(base_url, timeout=30)
            soup = BeautifulSoup(response.text, 'html.parser')

            paginated_urls = []

            # Look for pagination patterns
            for link in soup.find_all('a'):
                href = link.get('href')
                text = link.get_text().strip()

                # Check for page numbers
                if re.match(r'^\d+$', text) or 'page' in text.lower():
                    full_url = urljoin(base_url, href)
                    paginated_urls.append(full_url)

            return list(set(paginated_urls))

        except Exception as e:
            logger.error(f"Error finding paginated URLs: {e}")
            return []

    def harvest_from_url(self, url: str, domain: Optional[str] = None) -> Dict:
        """
        Harvest vocabulary from a URL with enhanced processing

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

            # Extract all potential vocabulary terms
            raw_terms = self._extract_all_vocabulary(soup)

            if not raw_terms:
                logger.warning("No vocabulary terms found")
                return self.stats

            logger.info(f"Found {len(raw_terms)} potential terms")

            # Process and enrich terms
            processed_terms = self._process_terms(raw_terms, url)

            # Filter existing terms
            new_terms = self._filter_existing_terms(processed_terms)

            # Store candidates
            if new_terms:
                self._store_enhanced_candidates(new_terms, url, domain)

        except Exception as e:
            logger.error(f"Error harvesting from {url}: {e}")
            self.stats['errors'] += 1

        return self.stats

    def _extract_all_vocabulary(self, soup: BeautifulSoup) -> List[Dict]:
        """
        Extract vocabulary using multiple flexible strategies

        Returns:
            List of raw term dictionaries
        """
        all_terms = []

        # Try each pattern detector
        for detector in self.pattern_detectors:
            try:
                terms = detector(soup)
                if terms:
                    all_terms.extend(terms)
                    logger.debug(f"Detector {detector.__name__} found {len(terms)} terms")
            except Exception as e:
                logger.debug(f"Detector {detector.__name__} failed: {e}")

        # Deduplicate by term
        seen_terms = set()
        unique_terms = []
        for term_data in all_terms:
            term_lower = term_data.get('term', '').lower()
            if term_lower and term_lower not in seen_terms:
                seen_terms.add(term_lower)
                unique_terms.append(term_data)

        return unique_terms

    def _detect_any_structured_list(self, soup: BeautifulSoup) -> List[Dict]:
        """Detect any structured list format flexibly"""
        terms = []

        # Find any element that looks like it contains multiple terms
        potential_containers = soup.find_all(['dl', 'ul', 'ol', 'div', 'section', 'article'])

        for container in potential_containers:
            text_blocks = container.find_all(text=True)
            text_content = ' '.join(text_blocks)

            # Look for patterns like "word - definition" or "word: definition"
            patterns = [
                r'([A-Za-z\s\-\']+?)\s*[-–—:]\s*([^.!?]+[.!?])',
                r'([A-Za-z\s\-\']+?)\s*\n\s*([^.!?]+[.!?])',
                r'\b([A-Z][a-z]+(?:\s+[A-Za-z]+)*)\s*[:-]\s*([^.!?]+)',
            ]

            for pattern in patterns:
                matches = re.findall(pattern, text_content)
                for match in matches:
                    if len(match) >= 2:
                        term = match[0].strip()
                        definition = match[1].strip()

                        # Basic validation
                        if 2 < len(term) < 50 and len(definition) > 10:
                            terms.append({
                                'term': term,
                                'definition': definition,
                                'source_element': 'structured_list'
                            })

        return terms

    def _detect_definition_blocks(self, soup: BeautifulSoup) -> List[Dict]:
        """Detect definition blocks with headers and content"""
        terms = []

        # Look for heading + content patterns
        headings = soup.find_all(['h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'strong', 'b'])

        for heading in headings:
            term = heading.get_text().strip()

            # Skip if too long or too short
            if len(term) < 2 or len(term) > 50:
                continue

            # Look for definition in next sibling or parent's text
            definition = None

            # Check next sibling
            next_elem = heading.find_next_sibling()
            if next_elem:
                definition = next_elem.get_text().strip()

            # Check parent's remaining text
            if not definition or len(definition) < 10:
                parent = heading.parent
                if parent:
                    # Get text after the heading
                    heading_text = heading.get_text()
                    parent_text = parent.get_text()
                    if heading_text in parent_text:
                        idx = parent_text.index(heading_text) + len(heading_text)
                        definition = parent_text[idx:].strip()

            if definition and len(definition) > 10:
                terms.append({
                    'term': term,
                    'definition': definition[:500],  # Limit length
                    'source_element': 'definition_block'
                })

        return terms

    def _detect_card_based_layout(self, soup: BeautifulSoup) -> List[Dict]:
        """Detect card-based or tile-based layouts"""
        terms = []

        # Common card class patterns
        card_patterns = ['card', 'tile', 'vocab', 'term', 'word', 'entry', 'item']

        for pattern in card_patterns:
            cards = soup.find_all(class_=re.compile(pattern, re.I))

            for card in cards:
                # Look for term and definition within card
                term = None
                definition = None

                # Try to find term in heading or bold
                term_elem = card.find(['h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'strong', 'b'])
                if term_elem:
                    term = term_elem.get_text().strip()

                # Find definition in remaining text
                if term:
                    card_text = card.get_text().strip()
                    if term in card_text:
                        idx = card_text.index(term) + len(term)
                        definition = card_text[idx:].strip()

                if term and definition and len(term) < 50 and len(definition) > 10:
                    terms.append({
                        'term': term,
                        'definition': definition[:500],
                        'source_element': 'card'
                    })

        return terms

    def _detect_accordion_pattern(self, soup: BeautifulSoup) -> List[Dict]:
        """Detect accordion or collapsible patterns"""
        terms = []

        # Look for accordion patterns
        accordions = soup.find_all(class_=re.compile('accordion|collapse|expand', re.I))

        for accordion in accordions:
            # Find toggle/header and content pairs
            headers = accordion.find_all(class_=re.compile('header|toggle|title', re.I))
            contents = accordion.find_all(class_=re.compile('content|body|description', re.I))

            for i, header in enumerate(headers):
                if i < len(contents):
                    term = header.get_text().strip()
                    definition = contents[i].get_text().strip()

                    if 2 < len(term) < 50 and len(definition) > 10:
                        terms.append({
                            'term': term,
                            'definition': definition[:500],
                            'source_element': 'accordion'
                        })

        return terms

    def _detect_glossary_pattern(self, soup: BeautifulSoup) -> List[Dict]:
        """Detect glossary-specific patterns"""
        terms = []

        # Look for glossary indicators
        glossary_sections = soup.find_all(text=re.compile('glossary|dictionary|vocabulary|lexicon', re.I))

        for text_node in glossary_sections:
            parent = text_node.parent
            if parent:
                # Find the container with terms
                container = parent.find_parent(['div', 'section', 'article'])
                if container:
                    # Extract all potential term-definition pairs
                    text = container.get_text()

                    # Try various patterns
                    patterns = [
                        r'([A-Z][a-z]+(?:\s+[a-z]+)*)\s*:\s*([^.!?]+[.!?])',
                        r'([A-Z][a-z]+(?:\s+[a-z]+)*)\s*—\s*([^.!?]+[.!?])',
                        r'\*\*([^*]+)\*\*\s*:?\s*([^*\n]+)',
                    ]

                    for pattern in patterns:
                        matches = re.findall(pattern, text)
                        for match in matches:
                            if len(match) >= 2:
                                term = match[0].strip()
                                definition = match[1].strip()

                                if 2 < len(term) < 50 and len(definition) > 10:
                                    terms.append({
                                        'term': term,
                                        'definition': definition,
                                        'source_element': 'glossary'
                                    })

        return terms

    def _detect_mixed_content(self, soup: BeautifulSoup) -> List[Dict]:
        """Catch-all for mixed content patterns"""
        terms = []

        # Find all text that looks like term-definition pairs
        all_text = soup.get_text()

        # Split into lines or sentences
        lines = all_text.split('\n')

        current_term = None
        current_definition = []

        for line in lines:
            line = line.strip()
            if not line:
                continue

            # Check if line looks like a term (short, capitalized, etc.)
            if len(line) < 50 and line[0].isupper() and ':' not in line and '.' not in line:
                # Save previous term if exists
                if current_term and current_definition:
                    definition = ' '.join(current_definition)
                    if len(definition) > 10:
                        terms.append({
                            'term': current_term,
                            'definition': definition[:500],
                            'source_element': 'mixed'
                        })

                # Start new term
                current_term = line
                current_definition = []

            elif current_term and len(line) > 10:
                # Add to current definition
                current_definition.append(line)

        # Don't forget the last term
        if current_term and current_definition:
            definition = ' '.join(current_definition)
            if len(definition) > 10:
                terms.append({
                    'term': current_term,
                    'definition': definition[:500],
                    'source_element': 'mixed'
                })

        return terms

    def _process_terms(self, raw_terms: List[Dict], source_url: str) -> List[VocabularyTerm]:
        """
        Process raw terms: lookup missing definitions, impute POS, combine senses

        Args:
            raw_terms: List of raw term dictionaries
            source_url: Source URL for the terms

        Returns:
            List of processed VocabularyTerm objects
        """
        processed = []

        for raw_term in raw_terms:
            term_str = raw_term.get('term', '').strip()
            definition = raw_term.get('definition', '').strip()

            if not term_str:
                continue

            # Clean the term
            term_str = self._clean_term(term_str)

            # If no definition, look it up
            if not definition or len(definition) < 10:
                logger.info(f"Looking up definition for: {term_str}")
                definition = self._lookup_definition(term_str)

                if definition:
                    self.stats['definitions_looked_up'] += 1
                else:
                    # Add as undefined candidate
                    logger.info(f"No definition found for: {term_str}")
                    self.stats['undefined_candidates'] += 1
                    definition = "No definition available - marked for manual review"

            # Extract or impute POS
            pos = self._extract_or_impute_pos(term_str, definition)

            # Extract metadata
            etymology = self._extract_etymology(definition)
            examples = self._extract_examples(definition)
            pronunciation = raw_term.get('pronunciation')

            # Combine multiple senses if present
            definitions_by_pos = self._organize_definitions(definition, pos)

            # Create primary definition (numbered if multiple senses)
            primary_def = self._create_primary_definition(definitions_by_pos)

            # Calculate quality score
            quality_score = self._calculate_quality_score(
                term_str, primary_def, bool(etymology), bool(examples)
            )

            # Create VocabularyTerm
            vocab_term = VocabularyTerm(
                term=term_str,
                definitions=definitions_by_pos,
                primary_definition=primary_def,
                part_of_speech=pos,
                etymology=etymology,
                pronunciation=pronunciation,
                examples=examples,
                synonyms=[],
                source_url=source_url,
                quality_score=quality_score,
                metadata={
                    'source_element': raw_term.get('source_element', 'unknown'),
                    'has_lookup': not raw_term.get('definition')
                }
            )

            processed.append(vocab_term)

        return processed

    def _lookup_definition(self, term: str) -> Optional[str]:
        """Look up definition using comprehensive lookup system"""
        if not self.definition_lookup:
            return None

        try:
            # Use async lookup
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            result = loop.run_until_complete(
                self.definition_lookup.lookup_term(term)
            )
            loop.close()

            if result and result.definitions_by_pos:
                # Combine all definitions
                all_defs = []
                for pos, defs in result.definitions_by_pos.items():
                    for def_obj in defs:
                        all_defs.append(f"({pos}) {def_obj.text}")

                return " | ".join(all_defs)

        except Exception as e:
            logger.error(f"Error looking up definition for {term}: {e}")

        return None

    def _extract_or_impute_pos(self, term: str, definition: str) -> Optional[str]:
        """Extract POS from definition or impute based on patterns"""
        if not definition:
            return None

        definition_lower = definition.lower()

        # Check for explicit POS indicators
        for pos, indicators in self.pos_patterns.items():
            for indicator in indicators:
                if indicator in definition_lower[:20]:  # Check start of definition
                    return pos

        # Impute based on definition patterns
        if any(phrase in definition_lower for phrase in ['to ', 'action of', 'act of']):
            return 'VERB'
        elif any(phrase in definition_lower for phrase in ['person who', 'one who', 'place where']):
            return 'NOUN'
        elif any(phrase in definition_lower for phrase in ['having', 'characterized by', 'relating to']):
            return 'ADJECTIVE'
        elif any(phrase in definition_lower for phrase in ['in a', 'manner', 'way']):
            return 'ADVERB'

        # Default based on term ending
        if term.endswith('ly'):
            return 'ADVERB'
        elif term.endswith(('ing', 'ed')):
            return 'VERB'
        elif term.endswith(('tion', 'sion', 'ment', 'ness', 'ity')):
            return 'NOUN'
        elif term.endswith(('ous', 'ive', 'ful', 'less')):
            return 'ADJECTIVE'

        return 'NOUN'  # Default

    def _organize_definitions(self, definition: str, pos: Optional[str]) -> Dict[str, List[str]]:
        """Organize definitions by POS and combine multiple senses"""
        definitions_by_pos = {}

        if not definition:
            return definitions_by_pos

        # Split on common sense separators
        senses = re.split(r'[;|]|\d+\.', definition)

        current_pos = pos or 'NOUN'
        definitions_by_pos[current_pos] = []

        for sense in senses:
            sense = sense.strip()
            if not sense:
                continue

            # Check if this sense indicates a different POS
            for check_pos, indicators in self.pos_patterns.items():
                if any(ind in sense.lower()[:10] for ind in indicators):
                    current_pos = check_pos
                    if current_pos not in definitions_by_pos:
                        definitions_by_pos[current_pos] = []
                    # Remove POS indicator from sense
                    for ind in indicators:
                        sense = re.sub(re.escape(ind), '', sense, flags=re.I).strip()
                    break

            if sense and len(sense) > 5:
                definitions_by_pos[current_pos].append(sense)

        return definitions_by_pos

    def _create_primary_definition(self, definitions_by_pos: Dict[str, List[str]]) -> str:
        """Create a single primary definition combining all senses"""
        all_definitions = []

        for pos, senses in definitions_by_pos.items():
            if not senses:
                continue

            if len(senses) == 1:
                all_definitions.append(f"({pos}) {senses[0]}")
            else:
                # Number multiple senses
                numbered_senses = [f"{i+1}. {sense}" for i, sense in enumerate(senses)]
                combined = f"({pos}) " + " ".join(numbered_senses)
                all_definitions.append(combined)

        return " | ".join(all_definitions) if all_definitions else "No definition available"

    def _extract_etymology(self, text: str) -> Optional[str]:
        """Extract etymology information from text"""
        if not text:
            return None

        # Look for etymology patterns
        etym_patterns = [
            r'etymology:?\s*([^.]+)',
            r'from\s+(?:Latin|Greek|French|German|Old English)\s+([^.]+)',
            r'derived from\s+([^.]+)',
            r'origin:?\s*([^.]+)'
        ]

        for pattern in etym_patterns:
            match = re.search(pattern, text, re.I)
            if match:
                return match.group(1).strip()

        return None

    def _extract_examples(self, text: str) -> List[str]:
        """Extract example sentences from text"""
        examples = []

        if not text:
            return examples

        # Look for example patterns
        example_patterns = [
            r'(?:example|e\.g\.|for example):?\s*"([^"]+)"',
            r'(?:example|e\.g\.|for example):?\s*([^.]+\.)',
            r'"([^"]+)"',  # Any quoted text might be an example
        ]

        for pattern in example_patterns:
            matches = re.findall(pattern, text, re.I)
            examples.extend(matches[:3])  # Limit to 3 examples

        return examples

    def _calculate_quality_score(self, term: str, definition: str,
                                has_etymology: bool, has_examples: bool) -> float:
        """Calculate quality score for a term"""
        score = 5.0  # Base score

        # Term quality
        if 4 <= len(term) <= 15:
            score += 1.0
        if not term.replace('-', '').replace("'", '').isalpha():
            score -= 1.0

        # Definition quality
        def_len = len(definition)
        if def_len >= 30:
            score += 1.0
        if def_len >= 100:
            score += 1.0
        if def_len < 15:
            score -= 2.0

        # Metadata bonuses
        if has_etymology:
            score += 1.0
        if has_examples:
            score += 1.0

        # Check for completeness
        if '.' in definition:
            score += 0.5

        return max(0.0, min(10.0, score))

    def _clean_term(self, term: str) -> str:
        """Clean and normalize a term"""
        # Remove extra whitespace
        term = ' '.join(term.split())

        # Remove numbering and special characters
        term = re.sub(r'^\d+[\.\)]\s*', '', term)
        term = re.sub(r'[^\w\s\'-]', '', term)

        return term.strip()

    def _filter_existing_terms(self, terms: List[VocabularyTerm]) -> List[VocabularyTerm]:
        """Filter out terms that already exist in 'defined' table"""
        if not terms:
            return []

        conn = self._get_connection()
        cursor = conn.cursor()

        try:
            # Get all term strings
            term_strings = [t.term.lower() for t in terms]

            # Batch check
            placeholders = ','.join(['%s'] * len(term_strings))
            cursor.execute(f"""
                SELECT LOWER(term)
                FROM defined
                WHERE LOWER(term) IN ({placeholders})
            """, term_strings)

            existing = set(row[0] for row in cursor.fetchall())

            # Filter
            new_terms = []
            for term in terms:
                if term.term.lower() not in existing:
                    new_terms.append(term)
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

    def _store_enhanced_candidates(self, terms: List[VocabularyTerm],
                                  source_url: str, domain: Optional[str]) -> int:
        """Store enhanced candidate terms with all metadata"""
        if not terms:
            return 0

        conn = self._get_connection()
        cursor = conn.cursor()
        stored = 0

        try:
            insert_data = []
            for term in terms:
                # Prepare metadata JSON
                metadata = {
                    'source_type_detailed': 'vocabulary_list',  # Store actual source type here
                    'domain': domain or urlparse(source_url).netloc,
                    'harvest_date': datetime.now().isoformat(),
                    'has_etymology': bool(term.etymology),
                    'has_examples': bool(term.examples),
                    'was_looked_up': term.metadata.get('has_lookup', False),
                    'source_element': term.metadata.get('source_element', 'unknown')
                }

                insert_data.append((
                    term.term,
                    'other',  # Use 'other' since 'vocabulary_list' is not in ENUM
                    source_url,
                    term.primary_definition[:500],  # context_snippet
                    term.primary_definition,  # raw_definition
                    term.etymology,
                    term.part_of_speech,
                    term.quality_score,
                    json.dumps(metadata),
                    datetime.now().date(),
                    'pending'
                ))

            # Batch insert
            cursor.executemany("""
                INSERT INTO candidate_words
                (term, source_type, source_reference, context_snippet, raw_definition,
                 etymology_preview, part_of_speech, utility_score, rarity_indicators,
                 date_discovered, review_status)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE
                    raw_definition = IF(LENGTH(VALUES(raw_definition)) > LENGTH(raw_definition),
                                       VALUES(raw_definition), raw_definition),
                    utility_score = VALUES(utility_score),
                    updated_at = CURRENT_TIMESTAMP
            """, insert_data)

            stored = cursor.rowcount
            conn.commit()

            self.stats['candidates_accepted'] = stored
            logger.info(f"Stored {stored} enhanced candidates")

        except Error as e:
            logger.error(f"Error storing candidates: {e}")
            conn.rollback()

        finally:
            cursor.close()
            conn.close()

        return stored


def main():
    """Main entry point"""
    import argparse

    parser = argparse.ArgumentParser(description='Enhanced Vocabulary List Harvester')
    parser.add_argument('url', help='URL or site to harvest')
    parser.add_argument('--site', action='store_true', help='Harvest entire site with alphabetical crawling')
    parser.add_argument('--domain', help='Domain/category for terms')
    parser.add_argument('--max-pages', type=int, default=100, help='Max pages to crawl for site harvest')

    args = parser.parse_args()

    harvester = EnhancedVocabularyListHarvester()

    if args.site:
        stats = harvester.harvest_site(args.url, crawl_alphabetical=True, max_pages=args.max_pages)
    else:
        stats = harvester.harvest_from_url(args.url, args.domain)

    print("\nHarvest Complete:")
    for key, value in stats.items():
        print(f"  {key}: {value}")


if __name__ == "__main__":
    main()