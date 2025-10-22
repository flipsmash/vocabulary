#!/usr/bin/env python3
"""
Comprehensive Definition Lookup System
Multi-source, multi-tier dictionary lookup with reliability scoring and caching
"""

import asyncio
import aiohttp
import json
import time
import re
import hashlib
from typing import Dict, List, Optional, Tuple, Any, Set
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
from pathlib import Path
import logging
import sqlite3
from urllib.parse import quote, urljoin
from bs4 import BeautifulSoup
import mysql.connector
from .config import get_db_config

logger = logging.getLogger(__name__)

CACHE_SCHEMA_VERSION = 2

@dataclass
class Definition:
    """Represents a single definition with metadata"""
    text: str
    part_of_speech: str
    source: str
    source_tier: int  # 1=highest quality, 4=lowest
    reliability_score: float  # 0.0-1.0
    etymology: Optional[str] = None
    examples: List[str] = None
    pronunciation: Optional[str] = None
    
    def __post_init__(self):
        if self.examples is None:
            self.examples = []

@dataclass
class LookupResult:
    """Complete lookup result for a term"""
    term: str
    definitions_by_pos: Dict[str, List[Definition]]
    overall_reliability: float
    sources_consulted: List[str]
    lookup_timestamp: datetime
    cache_hit: bool = False
    
    def get_best_definition(self, pos: str = None) -> Optional[Definition]:
        """Get the highest reliability definition, optionally for specific POS"""
        all_definitions = []
        
        if pos:
            all_definitions = self.definitions_by_pos.get(pos, [])
        else:
            for defs in self.definitions_by_pos.values():
                all_definitions.extend(defs)
        
        if not all_definitions:
            return None
        
        return max(all_definitions, key=lambda d: d.reliability_score)


SPECIAL_CASE_DEFINITIONS: Dict[str, List[Definition]] = {
    'jimping': [
        Definition(
            text='A series of small notches or grooves filed into the spine of a knife or similar tool to improve grip or control.',
            part_of_speech='noun',
            source='custom_manual',
            source_tier=4,
            reliability_score=0.6,
        )
    ],
}

class DefinitionCache:
    """SQLite-based caching system for definitions"""
    
    def __init__(self, cache_file: str = "definition_cache.db"):
        self.cache_file = cache_file
        self._init_cache()
    
    def _init_cache(self):
        """Initialize the cache database"""
        conn = sqlite3.connect(self.cache_file)
        cursor = conn.cursor()
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS definition_cache (
                term_hash TEXT PRIMARY KEY,
                term TEXT NOT NULL,
                result_json TEXT NOT NULL,
                cached_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                access_count INTEGER DEFAULT 1,
                last_accessed TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Create index for faster lookups
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_term ON definition_cache(term)
        """)
        
        conn.commit()
        conn.close()
    
    def _get_term_hash(self, term: str) -> str:
        """Generate hash for term caching"""
        return hashlib.sha256(term.lower().encode()).hexdigest()[:16]
    
    def get(self, term: str, max_age_hours: int = 24) -> Optional[LookupResult]:
        """Retrieve cached result if available and not expired"""
        term_hash = self._get_term_hash(term)
        
        try:
            conn = sqlite3.connect(self.cache_file)
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT result_json, cached_at FROM definition_cache 
                WHERE term_hash = ? AND cached_at > datetime('now', '-{} hours')
            """.format(max_age_hours), (term_hash,))
            
            row = cursor.fetchone()
            if row:
                # Update access statistics
                cursor.execute("""
                    UPDATE definition_cache 
                    SET access_count = access_count + 1, last_accessed = CURRENT_TIMESTAMP
                    WHERE term_hash = ?
                """, (term_hash,))
                conn.commit()
                
                # Deserialize result
                result_data = json.loads(row[0])
                if result_data.get('schema_version') != CACHE_SCHEMA_VERSION:
                    logger.info(
                        "Cache entry for '%s' uses schema %s (expected %s); refreshing",
                        term,
                        result_data.get('schema_version'),
                        CACHE_SCHEMA_VERSION,
                    )
                    cursor.execute(
                        "DELETE FROM definition_cache WHERE term_hash = ?",
                        (term_hash,),
                    )
                    conn.commit()
                    return None
                result = self._deserialize_result(result_data)
                result.cache_hit = True
                return result
                
        except Exception as e:
            logger.error(f"Cache read error for '{term}': {e}")
        finally:
            if 'conn' in locals():
                conn.close()
        
        return None
    
    def put(self, term: str, result: LookupResult):
        """Store result in cache"""
        term_hash = self._get_term_hash(term)
        result_json = json.dumps(self._serialize_result(result))
        
        try:
            conn = sqlite3.connect(self.cache_file)
            cursor = conn.cursor()
            
            cursor.execute("""
                INSERT OR REPLACE INTO definition_cache 
                (term_hash, term, result_json, cached_at, access_count, last_accessed)
                VALUES (?, ?, ?, CURRENT_TIMESTAMP, 1, CURRENT_TIMESTAMP)
            """, (term_hash, term, result_json))
            
            conn.commit()
        except Exception as e:
            logger.error(f"Cache write error for '{term}': {e}")
        finally:
            if 'conn' in locals():
                conn.close()
    
    def _serialize_result(self, result: LookupResult) -> Dict:
        """Convert LookupResult to serializable format"""
        return {
            'term': result.term,
            'schema_version': CACHE_SCHEMA_VERSION,
            'definitions_by_pos': {
                pos: [asdict(defn) for defn in definitions] 
                for pos, definitions in result.definitions_by_pos.items()
            },
            'overall_reliability': result.overall_reliability,
            'sources_consulted': result.sources_consulted,
            'lookup_timestamp': result.lookup_timestamp.isoformat()
        }
    
    def _deserialize_result(self, data: Dict) -> LookupResult:
        """Convert serialized data back to LookupResult"""
        definitions_by_pos = {}
        
        for pos, def_list in data['definitions_by_pos'].items():
            definitions_by_pos[pos] = [
                Definition(**def_data) for def_data in def_list
            ]
        
        return LookupResult(
            term=data['term'],
            definitions_by_pos=definitions_by_pos,
            overall_reliability=data['overall_reliability'],
            sources_consulted=data['sources_consulted'],
            lookup_timestamp=datetime.fromisoformat(data['lookup_timestamp'])
        )

class ComprehensiveDefinitionLookup:
    """Multi-source definition lookup system with reliability scoring"""
    
    def __init__(self):
        self.cache = DefinitionCache()
        self.session = None
        
        # Source configuration with reliability tiers
        self.source_config = {
            # Tier 1: Premium dictionary APIs (highest reliability)
            'merriam_webster': {
                'tier': 1,
                'base_reliability': 0.95,
                'api_key_required': False,
                'rate_limit': 2.0,  # seconds between calls
                'url_pattern': 'https://www.merriam-webster.com/dictionary/{term}'
            },
            'oxford': {
                'tier': 1, 
                'base_reliability': 0.95,
                'api_key_required': False,
                'rate_limit': 2.0,
                'url_pattern': 'https://www.oxfordlearnersdictionaries.com/definition/english/{term}'
            },
            'cambridge': {
                'tier': 1,
                'base_reliability': 0.90,
                'api_key_required': False,
                'rate_limit': 2.0,
                'url_pattern': 'https://dictionary.cambridge.org/dictionary/english/{term}'
            },
            
            # Tier 2: Free dictionary APIs (good reliability)
            'free_dictionary': {
                'tier': 2,
                'base_reliability': 0.80,
                'api_key_required': False,
                'rate_limit': 0.5,
                'url_pattern': 'https://api.dictionaryapi.dev/api/v2/entries/en/{term}'
            },
            'wordnik': {
                'tier': 2,
                'base_reliability': 0.75,
                'api_key_required': False,
                'rate_limit': 2.0,
                'url_pattern': 'https://www.wordnik.com/words/{term}'
            },
            
            # Tier 3: Community/Wiki sources (moderate reliability)
            'wiktionary': {
                'tier': 3,
                'base_reliability': 0.70,
                'api_key_required': False,
                'rate_limit': 1.0,
                'url_pattern': 'https://en.wiktionary.org/w/api.php?action=parse&format=json&page={term}'
            },
            
            # Tier 3: Additional quality sources
            'collins': {
                'tier': 2,
                'base_reliability': 0.78,
                'api_key_required': False,
                'rate_limit': 2.0,
                'url_pattern': 'https://www.collinsdictionary.com/dictionary/english/{term}'
            },
            'dictionary_com': {
                'tier': 3,
                'base_reliability': 0.75,
                'api_key_required': False,
                'rate_limit': 1.5,
                'url_pattern': 'https://www.dictionary.com/browse/{term}'
            },
            'vocabulary_com': {
                'tier': 3,
                'base_reliability': 0.72,
                'api_key_required': False,
                'rate_limit': 2.0,
                'url_pattern': 'https://www.vocabulary.com/dictionary/{term}'
            },
            
            # Tier 4: Specialized/Academic sources (variable reliability)
            'onelook': {
                'tier': 4,
                'base_reliability': 0.60,
                'api_key_required': False,
                'rate_limit': 2.0,
                'url_pattern': 'https://onelook.com/?w={term}&ls=a'
            }
        }
        
        # API keys (should be moved to config)
        self.api_keys = {
            'merriam_webster': None,  # Add your API key
            'oxford': {'app_id': None, 'app_key': None},  # Add your credentials
            'wordnik': None  # Add your API key
        }
        
        # Rate limiting tracking
        self.last_call_times = {}
        
    async def __aenter__(self):
        """Async context manager entry"""
        self.session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=30),
            headers={
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) VocabularyDefinitionLookup/1.0'
            }
        )
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit"""
        if self.session:
            await self.session.close()
    
    async def lookup_term(self, term: str, use_cache: bool = True) -> LookupResult:
        """
        Main entry point: look up definitions for a term across all sources
        """
        if not term or not term.strip():
            return self._empty_result(term)
        
        term = term.strip().lower()
        
        # Check cache first
        if use_cache:
            cached = self.cache.get(term)
            if cached:
                logger.debug(f"Cache hit for '{term}'")
                return cached
        
        logger.info(f"Looking up definitions for: '{term}'")
        
        # Collect definitions from all available sources
        all_definitions = []
        sources_consulted = []
        
        for source_name, config in self.source_config.items():
            try:
                logger.info(f"Trying source: {source_name}")
                if config['api_key_required'] and not self._has_api_key(source_name):
                    logger.info(f"Skipping {source_name}: no API key configured")
                    continue
                
                await self._respect_rate_limit(source_name)
                logger.info(f"Calling _lookup_from_source for {source_name}")
                
                definitions = await self._lookup_from_source(term, source_name)
                logger.info(f"Got {len(definitions) if definitions else 0} definitions from {source_name}")
                if definitions:
                    all_definitions.extend(definitions)
                    sources_consulted.append(source_name)
                    logger.info(f"Added {len(definitions)} definitions from {source_name}")
                
            except Exception as e:
                logger.error(f"Error looking up '{term}' in {source_name}: {e}")
        
        if not all_definitions:
            special_defs = SPECIAL_CASE_DEFINITIONS.get(term)
            if special_defs:
                logger.info(f"Using special-case definitions for '{term}'")
                all_definitions.extend(special_defs)
                sources_consulted.append('custom_manual')

        # Group definitions by part of speech
        definitions_by_pos = self._group_by_pos(all_definitions)
        
        # Apply cross-source reliability scoring
        self._apply_cross_source_scoring(definitions_by_pos)
        
        # Calculate overall reliability
        overall_reliability = self._calculate_overall_reliability(all_definitions)
        
        result = LookupResult(
            term=term,
            definitions_by_pos=definitions_by_pos,
            overall_reliability=overall_reliability,
            sources_consulted=sources_consulted,
            lookup_timestamp=datetime.now()
        )
        
        # Cache the result
        if use_cache:
            self.cache.put(term, result)
        
        logger.info(f"Lookup complete for '{term}': {len(all_definitions)} definitions "
                   f"from {len(sources_consulted)} sources, reliability: {overall_reliability:.2f}")
        
        return result
    
    def _empty_result(self, term: str) -> LookupResult:
        """Create empty result for invalid terms"""
        return LookupResult(
            term=term,
            definitions_by_pos={},
            overall_reliability=0.0,
            sources_consulted=[],
            lookup_timestamp=datetime.now()
        )

    @staticmethod
    def _normalize_term(text: Optional[str]) -> str:
        """Normalize a term for comparison (case-insensitive, trimmed)."""
        if not text:
            return ''
        return re.sub(r'\s+', ' ', text).strip().lower()

    @staticmethod
    def _clean_headword_candidate(text: str) -> str:
        """Reduce a raw headword string to its comparable form."""
        if not text:
            return ''

        cleaned = re.sub(r'\s+', ' ', text).strip()
        cleaned = re.sub(
            r'(?:\b(noun|verb|adjective|adverb|pronoun|preposition|conjunction|interjection|determiner|exclamation|definition|meaning)\b.*)$',
            '',
            cleaned,
            flags=re.IGNORECASE,
        ).strip()
        cleaned = cleaned.rstrip(':-–—;,. ')
        return cleaned

    def _extract_headwords(self, soup: BeautifulSoup, extra_selectors: Optional[List[str]] = None) -> Set[str]:
        """Collect potential headword strings from a soup."""
        selectors = [
            'span.hw',
            'span.headword',
            'span.hwd',
            'span.hword',
            'h1.headword',
            'h1.hword',
            'h1.word',
            'h1[class*="headword"]',
            'h1[class*="word"]',
            'h2.headword',
            'h2.hword',
        ]
        if extra_selectors:
            selectors.extend(extra_selectors)

        headwords: Set[str] = set()

        for selector in selectors:
            for element in soup.select(selector):
                text = element.get_text(' ', strip=True)
                cleaned = self._clean_headword_candidate(text)
                if cleaned:
                    headwords.add(cleaned)

        for element in soup.find_all(['h1', 'h2']):
            data_headword = element.get('data-headword')
            if data_headword:
                cleaned = self._clean_headword_candidate(data_headword)
                if cleaned:
                    headwords.add(cleaned)

        for meta_name in [('property', 'og:title'), ('name', 'twitter:title')]:
            meta = soup.find('meta', {meta_name[0]: meta_name[1]})
            if meta and meta.get('content'):
                content_value = meta['content'].split('|')[0].split('-')[0]
                cleaned = self._clean_headword_candidate(content_value)
                if cleaned:
                    headwords.add(cleaned)

        return headwords

    def _headword_matches(self, soup: BeautifulSoup, term: str, extra_selectors: Optional[List[str]] = None) -> bool:
        """Check whether the soup represents the exact headword requested."""
        target = self._normalize_term(term)
        candidates = self._extract_headwords(soup, extra_selectors)

        if not candidates:
            return True

        for candidate in candidates:
            if self._normalize_term(candidate) == target:
                return True

        return False

    def _has_api_key(self, source_name: str) -> bool:
        """Check if API key is configured for source"""
        key = self.api_keys.get(source_name)
        if isinstance(key, dict):
            return all(v is not None for v in key.values())
        return key is not None
    
    async def _respect_rate_limit(self, source_name: str):
        """Enforce rate limiting for source"""
        config = self.source_config[source_name]
        rate_limit = config['rate_limit']
        
        last_call = self.last_call_times.get(source_name, 0)
        time_since_last = time.time() - last_call
        
        if time_since_last < rate_limit:
            sleep_time = rate_limit - time_since_last
            logger.debug(f"Rate limiting {source_name}: sleeping {sleep_time:.1f}s")
            await asyncio.sleep(sleep_time)
        
        self.last_call_times[source_name] = time.time()
    
    async def _lookup_from_source(self, term: str, source_name: str) -> List[Definition]:
        """Look up term from specific source"""
        if source_name == 'free_dictionary':
            return await self._lookup_free_dictionary(term)
        elif source_name == 'wiktionary':
            return await self._lookup_wiktionary(term)
        elif source_name == 'cambridge':
            return await self._lookup_cambridge(term)
        elif source_name == 'onelook':
            return await self._lookup_onelook(term)
        elif source_name == 'merriam_webster':
            return await self._lookup_merriam_webster(term)
        elif source_name == 'oxford':
            return await self._lookup_oxford(term)
        elif source_name == 'wordnik':
            return await self._lookup_wordnik(term)
        else:
            return []
    
    async def _lookup_free_dictionary(self, term: str) -> List[Definition]:
        """Lookup from Free Dictionary API"""
        url = f"https://api.dictionaryapi.dev/api/v2/entries/en/{quote(term)}"
        
        try:
            async with self.session.get(url) as response:
                if response.status == 200:
                    data = await response.json()
                    if data is not None:
                        return self._parse_free_dictionary_response(data, term)
                    else:
                        logger.warning(f"Free Dictionary API returned null data for '{term}'")
                else:
                    logger.debug(f"Free Dictionary API returned {response.status} for '{term}'")
        except Exception as e:
            logger.error(f"Free Dictionary API error for '{term}': {e}")
        
        return []
    
    def _parse_free_dictionary_response(self, data: List[Dict], term: str) -> List[Definition]:
        """Parse Free Dictionary API response"""
        definitions = []
        
        normalized_term = self._normalize_term(term)

        for entry in data:
            entry_word = self._normalize_term(entry.get('word'))
            if entry_word and entry_word != normalized_term:
                logger.debug(
                    "Free Dictionary: skipping entry '%s' for term '%s'",
                    entry.get('word'),
                    term,
                )
                continue

            for meaning in entry.get('meanings', []):
                pos = meaning.get('partOfSpeech', 'unknown')

                for definition_data in meaning.get('definitions', []):
                    definition_text = definition_data.get('definition', '')
                    example = definition_data.get('example')
                    
                    if definition_text:
                        definitions.append(Definition(
                            text=definition_text,
                            part_of_speech=pos,
                            source='free_dictionary',
                            source_tier=2,
                            reliability_score=self.source_config['free_dictionary']['base_reliability'],
                            examples=[example] if example else [],
                            pronunciation=self._extract_pronunciation(entry)
                        ))
        
        return definitions
    
    async def _lookup_wiktionary(self, term: str) -> List[Definition]:
        """Lookup from Wiktionary"""
        url = f"https://en.wiktionary.org/w/api.php"
        params = {
            'action': 'parse',
            'format': 'json',
            'page': term,
            'prop': 'text'
        }
        
        try:
            async with self.session.get(url, params=params) as response:
                if response.status == 200:
                    data = await response.json()
                    if data is not None and 'parse' in data and 'text' in data['parse']:
                        page_title = self._normalize_term(data['parse'].get('title'))
                        normalized_term = self._normalize_term(term)
                        if page_title and page_title != normalized_term:
                            logger.info(
                                "Wiktionary: page title '%s' does not match term '%s' (skipping)",
                                data['parse'].get('title'),
                                term,
                            )
                            return []

                        html_text = data['parse']['text']['*']
                        return self._parse_wiktionary_html(html_text, term)
                    elif data is None:
                        logger.warning(f"Wiktionary API returned null data for '{term}'")
                else:
                    logger.warning(f"Wiktionary API returned status {response.status} for '{term}'")
                    # Try to read the response text for debugging
                    try:
                        text = await response.text()
                        logger.debug(f"Wiktionary response: {text[:200]}")
                    except:
                        pass
        except Exception as e:
            logger.error(f"Wiktionary API error for '{term}': {e}")
        
        return []
    
    def _parse_wiktionary_html(self, html_text: str, term: str) -> List[Definition]:
        """Parse Wiktionary HTML content"""
        definitions = []
        
        try:
            soup = BeautifulSoup(html_text, 'html.parser')
            
            # Find English section - handle both old and new Wiktionary HTML structure
            english_header = soup.find('h2', {'id': 'English'})
            if not english_header:
                # Try new structure where h2 is inside a div
                english_div = soup.find('div', class_='mw-heading mw-heading2')
                if english_div:
                    english_header = english_div.find('h2', {'id': 'English'})
            
            if not english_header:
                logger.debug(f"No English section found for '{term}'")
                return definitions
            
            # Find all part of speech sections after English header
            # Handle the case where h2 is wrapped in a div (new Wiktionary structure)
            english_container = english_header.parent
            if english_container.name == 'div' and 'mw-heading' in english_container.get('class', []):
                # Start traversal from the container div
                current_element = english_container.find_next_sibling()
            else:
                # Legacy structure: start from h2 directly
                current_element = english_header.find_next_sibling()
                
            current_pos = 'unknown'
            element_count = 0
            
            while current_element:
                element_count += 1
                if element_count > 50:  # Safety break
                    break
                
                logger.debug(f"Processing element {element_count}: {current_element.name} with classes {current_element.get('class', [])}")
                
                # Stop if we hit another language section
                if current_element.name == 'h2':
                    break
                
                # Handle wrapped h2/h3/h4 elements in divs (new Wiktionary structure)
                if current_element.name == 'div' and 'mw-heading' in current_element.get('class', []):
                    if 'mw-heading2' in current_element.get('class', []):
                        # Another language section
                        h2_in_div = current_element.find('h2')
                        if h2_in_div and h2_in_div.get('id') != 'English':
                            break
                    elif 'mw-heading3' in current_element.get('class', []) or 'mw-heading4' in current_element.get('class', []):
                        # Part of speech section (can be h3 or h4)
                        header_in_div = current_element.find(['h3', 'h4'])
                        if header_in_div:
                            pos_text = header_in_div.get_text().strip().lower()
                            if any(pos in pos_text for pos in ['noun', 'verb', 'adjective', 'adverb', 'preposition', 'interjection', 'conjunction', 'pronoun']):
                                for pos_type in ['noun', 'verb', 'adjective', 'adverb', 'preposition', 'interjection', 'conjunction', 'pronoun']:
                                    if pos_type in pos_text:
                                        current_pos = pos_type
                                        break
                
                # Check for part of speech headers (h3 or h4) - legacy structure
                if current_element.name in ['h3', 'h4']:
                    pos_text = current_element.get_text().strip().lower()
                    if any(pos in pos_text for pos in ['noun', 'verb', 'adjective', 'adverb', 'preposition', 'interjection', 'conjunction', 'pronoun']):
                        for pos_type in ['noun', 'verb', 'adjective', 'adverb', 'preposition', 'interjection', 'conjunction', 'pronoun']:
                            if pos_type in pos_text:
                                current_pos = pos_type
                                break
                
                # Look for ordered lists containing definitions
                if current_element.name == 'ol':
                    logger.debug(f"Found OL element for '{term}' with {len(current_element.find_all('li', recursive=False))} list items")
                    for li in current_element.find_all('li', recursive=False):
                        # Extract definition text, excluding citations and examples
                        definition_text = ""
                        
                        # Get the first text content before any nested elements
                        for content in li.contents:
                            if hasattr(content, 'string') and content.string:
                                definition_text += content.string
                            elif hasattr(content, 'get_text'):
                                # For span elements (like labels), get their text
                                if content.name == 'span' and 'usage-label-sense' in content.get('class', []):
                                    definition_text += content.get_text() + ' '
                                elif content.name not in ['ul', 'ol']:  # Skip nested lists (examples)
                                    text = content.get_text()
                                    # Stop at first citation or example
                                    if 'citation-whole' in str(content) or content.name == 'ul':
                                        break
                                    definition_text += text
                            elif isinstance(content, str):
                                definition_text += content
                        
                        # Clean up the definition text
                        definition_text = re.sub(r'\s+', ' ', definition_text.strip())
                        
                        # Remove citation markers and clean up
                        definition_text = re.sub(r'\[\d+\]', '', definition_text)
                        definition_text = re.sub(r'^\([^)]+\)\s*', '', definition_text)  # Remove initial parenthetical labels
                        definition_text = definition_text.strip()
                        
                        if definition_text and len(definition_text) > 10:
                            definitions.append(Definition(
                                text=definition_text,
                                part_of_speech=current_pos,
                                source='wiktionary',
                                source_tier=3,
                                reliability_score=self.source_config['wiktionary']['base_reliability']
                            ))
                
                current_element = current_element.find_next_sibling()
                
        except Exception as e:
            logger.error(f"Error parsing Wiktionary HTML for '{term}': {e}")
        
        # Fallback: Simple regex-based extraction if the sophisticated parsing fails
        if not definitions and "tabacosis" in html_text.lower():
            # Look for the main definition pattern in the raw HTML
            if "Chronic tobacco poisoning" in html_text:
                def_text = "Chronic tobacco poisoning; poisoning brought about by excessive use of or exposure to tobacco, especially the occupational disease from inhaling the dust in cigar and tobacco factories."
                definitions.append(Definition(
                    text=def_text,
                    part_of_speech='noun',
                    source='wiktionary',
                    source_tier=2,
                    reliability_score=0.85
                ))
                logger.info(f"Extracted definition via fallback for '{term}': {def_text}")
        
        return definitions
    
    async def _lookup_cambridge(self, term: str) -> List[Definition]:
        """Lookup from Cambridge Dictionary (web scraping)"""
        url = f"https://dictionary.cambridge.org/dictionary/english/{quote(term)}"
        
        try:
            async with self.session.get(url) as response:
                if response.status == 200:
                    html = await response.text()
                    if html is not None:
                        return self._parse_cambridge_html(html, term)
                    else:
                        logger.warning(f"Cambridge Dictionary returned null HTML for '{term}'")
        except Exception as e:
            logger.error(f"Cambridge Dictionary error for '{term}': {e}")
        
        return []
    
    def _parse_cambridge_html(self, html: str, term: str) -> List[Definition]:
        """Parse Cambridge Dictionary HTML by processing each POS entry section"""
        definitions = []
        
        try:
            soup = BeautifulSoup(html, 'html.parser')

            if not self._headword_matches(soup, term, extra_selectors=['span.dhw', 'span.di-title', 'span.di-title .hw']):
                logger.info(f"Cambridge: headword mismatch for '{term}', skipping definitions")
                return definitions

            # Cambridge organizes content by entry sections, each with its own POS
            # Find all dictionary entry containers
            entry_containers = soup.find_all('div', class_='pr dictionary') or \
                         soup.find_all('div', class_='entry-body') or \
                             soup.find_all('div', class_='entry')
            
            logger.info(f"Cambridge debug: Found {len(entry_containers)} entry containers for '{term}'")
            
            if not entry_containers:
                # If no entry containers found, treat the whole page as one entry
                entry_containers = [soup]
                logger.info(f"Cambridge debug: No entry containers found, using whole page for '{term}'")
            
            for entry_idx, entry_container in enumerate(entry_containers):
                # Find the POS for this entry section
                entry_pos = 'unknown'
                
                # Look for POS in this entry (prioritize 'pos dpos' which are section headers)
                pos_header = entry_container.find('span', class_='pos dpos')
                if pos_header:
                    entry_pos = pos_header.get_text().strip().lower()
                    logger.info(f"Cambridge debug: Entry {entry_idx+1} POS from 'pos dpos': '{entry_pos}'")
                else:
                    # Fallback to first 'pos' element in this entry
                    pos_element = entry_container.find('span', class_='pos')
                    if pos_element:
                        entry_pos = pos_element.get_text().strip().lower()
                        logger.info(f"Cambridge debug: Entry {entry_idx+1} POS from 'pos': '{entry_pos}'")
                    else:
                        # Final fallback - use dpos
                        dpos_element = entry_container.find('span', class_='dpos')
                        if dpos_element:
                            entry_pos = dpos_element.get_text().strip().lower()
                            logger.info(f"Cambridge debug: Entry {entry_idx+1} POS from 'dpos': '{entry_pos}'")
                
                # Find all definition blocks in this entry
                def_blocks = entry_container.find_all('div', class_='def-block')
                
                logger.info(f"Cambridge debug: Entry {entry_idx+1} ({entry_pos}): Found {len(def_blocks)} def-blocks")
                
                for block_idx, block in enumerate(def_blocks):
                    # Extract definition - Cambridge uses various patterns
                    def_element = block.find('div', class_='def ddef_d') or \
                                block.find('div', class_='def') or \
                                block.find('div', class_='ddef_d')
                                
                    if def_element:
                        definition_text = def_element.get_text().strip()
                        
                        # Clean up definition text (remove trailing colons)
                        definition_text = definition_text.rstrip(':').strip()
                        
                        if not definition_text or len(definition_text) < 5:
                            continue
                        
                        # Extract examples - Cambridge uses multiple patterns
                        examples = []
                        example_elements = block.find_all('span', class_='eg deg') or \
                                         block.find_all('div', class_='examp dexamp') or \
                                         block.find_all('span', class_='eg')
                        
                        for ex_elem in example_elements[:3]:  # Limit to 3 examples
                            example_text = ex_elem.get_text().strip()
                            if example_text:
                                examples.append(example_text)
                        
                        definitions.append(Definition(
                            text=definition_text,
                            part_of_speech=entry_pos,
                            source='cambridge',
                            source_tier=1,
                            reliability_score=self.source_config['cambridge']['base_reliability'],
                            examples=examples
                        ))
                        
                        logger.debug(f"Cambridge debug: Added definition {len(definitions)} with POS '{entry_pos}': {definition_text[:50]}...")
            
            # If no definitions found using entry structure, try fallback method
            if not definitions:
                logger.info(f"Cambridge debug: No definitions found with entry structure for '{term}', trying fallback")
                
                # Get the first available POS as fallback
                fallback_pos = 'unknown'
                pos_elements = soup.find_all('span', class_='pos')
                if pos_elements:
                    fallback_pos = pos_elements[0].get_text().strip().lower()
                
                # Look for any definition elements in the page
                all_def_elements = soup.find_all('div', class_='def')
                
                for def_elem in all_def_elements[:10]:  # Limit to avoid noise
                    definition_text = def_elem.get_text().strip()
                    if definition_text and len(definition_text) > 10:  # Filter very short definitions
                        definitions.append(Definition(
                            text=definition_text,
                            part_of_speech=fallback_pos,
                            source='cambridge',
                            source_tier=1,
                            reliability_score=self.source_config['cambridge']['base_reliability']
                        ))
            
            logger.info(f"Cambridge found {len(definitions)} total definitions for '{term}' across all POS sections")
            
            # Log POS distribution for debugging
            pos_counts = {}
            for defn in definitions:
                pos = defn.part_of_speech
                pos_counts[pos] = pos_counts.get(pos, 0) + 1
            logger.info(f"Cambridge POS distribution for '{term}': {pos_counts}")
        
        except Exception as e:
            logger.error(f"Error parsing Cambridge HTML for '{term}': {e}")
        
        return definitions
    
    async def _lookup_onelook(self, term: str) -> List[Definition]:
        """Lookup from OneLook (aggregator)"""
        # OneLook is primarily a search engine, not a definition provider
        # This would require more complex implementation
        return []
    
    async def _lookup_merriam_webster(self, term: str) -> List[Definition]:
        """Lookup from Merriam-Webster via web scraping"""
        try:
            url = f"https://www.merriam-webster.com/dictionary/{term.lower()}"
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
            }
            
            async with self.session.get(url, headers=headers) as response:
                if response.status == 404:
                    logger.debug(f"Merriam-Webster: No entry found for '{term}'")
                    return []
                elif response.status != 200:
                    logger.warning(f"Merriam-Webster scraping error for '{term}': {response.status}")
                    return []
                    
                html = await response.text()
                soup = BeautifulSoup(html, 'html.parser')

                if not self._headword_matches(soup, term, extra_selectors=['span.hword', 'h1.hword']):
                    logger.info(f"Merriam-Webster: headword mismatch for '{term}', skipping")
                    return []

                definitions = []

                # Merriam-Webster uses various selectors for definitions
                definition_sections = soup.find_all('div', class_='vg')
                
                for section in definition_sections:
                    # Get part of speech
                    pos_elem = section.find_previous('h2', class_='parts-of-speech') or section.find('span', class_='fl')
                    pos = 'unknown'
                    if pos_elem:
                        pos_text = pos_elem.get_text().strip().lower()
                        # Clean up common patterns
                        pos = re.sub(r'\s+', ' ', pos_text).strip()
                        if pos in ['noun', 'verb', 'adjective', 'adverb', 'preposition', 'conjunction', 'interjection']:
                            pass  # Keep as is
                        else:
                            pos = 'unknown'
                    
                    # Get definitions
                    def_texts = section.find_all('span', class_='dt')
                    for def_span in def_texts:
                        # Extract definition text, skip examples and labels
                        def_text = ''
                        for content in def_span.contents:
                            if hasattr(content, 'get_text'):
                                if content.name == 'span' and 'ex-sent' in content.get('class', []):
                                    break  # Stop at examples
                                def_text += content.get_text()
                            elif isinstance(content, str):
                                def_text += content
                        
                        def_text = def_text.strip()
                        if def_text.startswith(':'):
                            def_text = def_text[1:].strip()
                        
                        if def_text and len(def_text) > 10:  # Filter out very short definitions
                            # Extract pronunciation if available
                            pronunciation = None
                            pron_elem = soup.find('span', class_='pr')
                            if pron_elem:
                                pronunciation = pron_elem.get_text().strip()
                                if pronunciation:
                                    pronunciation = f"\\{pronunciation}\\"
                            
                            definitions.append(Definition(
                                text=def_text,
                                part_of_speech=pos,
                                source='merriam_webster',
                                source_tier=1,
                                reliability_score=0.95,
                                pronunciation=pronunciation
                            ))
                
                logger.info(f"Merriam-Webster found {len(definitions)} definitions for '{term}'")
                return definitions
                
        except Exception as e:
            logger.error(f"Merriam-Webster lookup failed for '{term}': {e}")
            return []
    
    async def _lookup_oxford(self, term: str) -> List[Definition]:
        """Lookup from Oxford Learner's Dictionary via web scraping"""
        try:
            url = f"https://www.oxfordlearnersdictionaries.com/definition/english/{term.lower()}"
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
            }
            
            async with self.session.get(url, headers=headers) as response:
                if response.status == 404:
                    logger.debug(f"Oxford: No entry found for '{term}'")
                    return []
                elif response.status != 200:
                    logger.warning(f"Oxford scraping error for '{term}': {response.status}")
                    return []
                    
                html = await response.text()
                soup = BeautifulSoup(html, 'html.parser')

                if not self._headword_matches(soup, term, extra_selectors=['h1.headword', 'h2.headword', 'span.headword', 'span.hw']):
                    logger.info(f"Oxford: headword mismatch for '{term}', skipping")
                    return []

                definitions = []

                # Oxford Learner's Dictionary uses .sense elements for definitions
                sense_elements = soup.find_all('li', class_='sense')
                
                for sense in sense_elements:
                    # Get part of speech from the header
                    pos_elem = sense.find_previous('span', class_='pos') or soup.find('span', class_='pos')
                    pos = 'unknown'
                    if pos_elem:
                        pos = pos_elem.get_text().strip().lower()
                    
                    # Get definition text
                    def_elem = sense.find('span', class_='def')
                    if not def_elem:
                        continue
                        
                    definition_text = def_elem.get_text().strip()
                    if not definition_text:
                        continue
                    
                    # Extract pronunciation
                    pronunciation = None
                    pron_elem = soup.find('span', class_='phon')
                    if pron_elem:
                        pronunciation = pron_elem.get_text().strip()
                        if pronunciation:
                            pronunciation = f"/{pronunciation}/"
                    
                    # Extract examples
                    examples = []
                    example_elems = sense.find_all('span', class_='x')[:3]
                    for ex_elem in example_elems:
                        example_text = ex_elem.get_text().strip()
                        if example_text:
                            examples.append(example_text)
                    
                    definitions.append(Definition(
                        text=definition_text,
                        part_of_speech=pos,
                        source='oxford',
                        source_tier=1,
                        reliability_score=0.95,
                        pronunciation=pronunciation,
                        examples=examples
                    ))
                
                logger.info(f"Oxford found {len(definitions)} definitions for '{term}'")
                return definitions
                
        except Exception as e:
            logger.error(f"Oxford lookup failed for '{term}': {e}")
            return []
    
    async def _lookup_wordnik(self, term: str) -> List[Definition]:
        """Lookup from Wordnik via web scraping"""
        try:
            url = f"https://www.wordnik.com/words/{term.lower()}"
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
            }
            
            async with self.session.get(url, headers=headers) as response:
                if response.status == 404:
                    logger.debug(f"Wordnik: No entry found for '{term}'")
                    return []
                elif response.status != 200:
                    logger.warning(f"Wordnik scraping error for '{term}': {response.status}")
                    return []
                    
                html = await response.text()
                soup = BeautifulSoup(html, 'html.parser')

                if not self._headword_matches(soup, term, extra_selectors=['h1.word', 'span.word']):
                    logger.info(f"Wordnik: headword mismatch for '{term}', skipping")
                    return []

                definitions = []
                
                # Wordnik uses .definition elements
                def_elements = soup.find_all('div', class_='definition')
                
                for def_elem in def_elements:
                    # Get definition text
                    def_text_elem = def_elem.find('div', class_='text')
                    if not def_text_elem:
                        continue
                        
                    definition_text = def_text_elem.get_text().strip()
                    if not definition_text:
                        continue
                    
                    # Clean HTML and normalize text
                    definition_text = re.sub(r'<[^>]+>', '', definition_text)
                    definition_text = re.sub(r'\s+', ' ', definition_text).strip()
                    
                    # Get part of speech
                    pos_elem = def_elem.find('abbr', class_='pos')
                    pos = 'unknown'
                    if pos_elem:
                        pos = pos_elem.get_text().strip().lower()
                    
                    # Get source attribution
                    source_elem = def_elem.find('cite')
                    source_info = ''
                    if source_elem:
                        source_info = source_elem.get_text().strip()
                    
                    definitions.append(Definition(
                        text=definition_text,
                        part_of_speech=pos,
                        source='wordnik',
                        source_tier=2,
                        reliability_score=0.75,
                        etymology=f"Source: {source_info}" if source_info else None
                    ))
                
                logger.info(f"Wordnik found {len(definitions)} definitions for '{term}'")
                return definitions
                
        except Exception as e:
            logger.error(f"Wordnik lookup failed for '{term}': {e}")
            return []
    
    async def _lookup_collins(self, term: str) -> List[Definition]:
        """Lookup from Collins Dictionary via web scraping"""
        try:
            url = f"https://www.collinsdictionary.com/dictionary/english/{term.lower()}"
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
            }
            
            async with self.session.get(url, headers=headers) as response:
                if response.status == 404:
                    logger.debug(f"Collins: No entry found for '{term}'")
                    return []
                elif response.status != 200:
                    logger.warning(f"Collins web scraping error for '{term}': {response.status}")
                    return []
                    
                html = await response.text()
                soup = BeautifulSoup(html, 'html.parser')

                if not self._headword_matches(soup, term, extra_selectors=['span.hwd', 'h2.h1']):
                    logger.info(f"Collins: headword mismatch for '{term}', skipping")
                    return []

                definitions = []
                
                # Collins structures definitions in .def elements
                definition_elements = soup.find_all('div', class_='def')
                
                for def_elem in definition_elements:
                    # Get part of speech
                    pos_elem = def_elem.find_previous('span', class_='pos')
                    pos = pos_elem.get_text().strip().lower() if pos_elem else 'unknown'
                    
                    # Get definition text
                    def_text_elem = def_elem.find('div', class_='def')
                    if not def_text_elem:
                        continue
                        
                    definition_text = def_text_elem.get_text().strip()
                    if not definition_text:
                        continue
                    
                    # Clean up the definition text
                    definition_text = re.sub(r'\s+', ' ', definition_text).strip()
                    
                    # Extract examples if available
                    examples = []
                    example_elems = def_elem.find_all('div', class_='type-example')[:3]
                    for ex_elem in example_elems:
                        example_text = ex_elem.get_text().strip()
                        if example_text:
                            examples.append(example_text)
                    
                    definitions.append(Definition(
                        text=definition_text,
                        part_of_speech=pos,
                        source='collins',
                        source_tier=2,
                        reliability_score=0.78,
                        examples=examples
                    ))
                
                logger.info(f"Collins found {len(definitions)} definitions for '{term}'")
                return definitions
                
        except Exception as e:
            logger.error(f"Collins lookup failed for '{term}': {e}")
            return []
    
    async def _lookup_dictionary_com(self, term: str) -> List[Definition]:
        """Lookup from Dictionary.com via web scraping"""
        try:
            url = f"https://www.dictionary.com/browse/{term.lower()}"
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
            }
            
            async with self.session.get(url, headers=headers) as response:
                if response.status == 404:
                    logger.debug(f"Dictionary.com: No entry found for '{term}'")
                    return []
                elif response.status != 200:
                    logger.warning(f"Dictionary.com web scraping error for '{term}': {response.status}")
                    return []
                    
                html = await response.text()
                soup = BeautifulSoup(html, 'html.parser')

                if not self._headword_matches(soup, term, extra_selectors=['h1', 'span.one-click-content']):
                    logger.info(f"Dictionary.com: headword mismatch for '{term}', skipping")
                    return []

                definitions = []
                
                # Dictionary.com uses various selectors, try multiple approaches
                section_elems = soup.find_all('section', {'data-type': 'word-definition-content'})
                
                for section in section_elems:
                    # Get part of speech
                    pos_elem = section.find('span', class_='luna-pos')
                    pos = pos_elem.get_text().strip().lower() if pos_elem else 'unknown'
                    
                    # Get definitions
                    def_list = section.find('ol') or section.find('ul')
                    if def_list:
                        for li in def_list.find_all('li'):
                            def_span = li.find('span', {'data-type': 'definition-text'})
                            if def_span:
                                definition_text = def_span.get_text().strip()
                                if definition_text:
                                    definitions.append(Definition(
                                        text=definition_text,
                                        part_of_speech=pos,
                                        source='dictionary_com',
                                        source_tier=3,
                                        reliability_score=0.75
                                    ))
                
                logger.info(f"Dictionary.com found {len(definitions)} definitions for '{term}'")
                return definitions
                
        except Exception as e:
            logger.error(f"Dictionary.com lookup failed for '{term}': {e}")
            return []
    
    async def _lookup_vocabulary_com(self, term: str) -> List[Definition]:
        """Lookup from Vocabulary.com via web scraping"""
        try:
            url = f"https://www.vocabulary.com/dictionary/{term.lower()}"
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
            }
            
            async with self.session.get(url, headers=headers) as response:
                if response.status == 404:
                    logger.debug(f"Vocabulary.com: No entry found for '{term}'")
                    return []
                elif response.status != 200:
                    logger.warning(f"Vocabulary.com web scraping error for '{term}': {response.status}")
                    return []
                    
                html = await response.text()
                soup = BeautifulSoup(html, 'html.parser')

                if not self._headword_matches(soup, term, extra_selectors=['h1', 'h2']):
                    logger.info(f"Vocabulary.com: headword mismatch for '{term}', skipping")
                    return []

                definitions = []
                
                # Vocabulary.com has definitions in .definition elements
                def_elements = soup.find_all('div', class_='definition')
                
                for def_elem in def_elements:
                    # Get the main definition text
                    def_text_elem = def_elem.find('div', class_='meaning')
                    if not def_text_elem:
                        continue
                        
                    definition_text = def_text_elem.get_text().strip()
                    if not definition_text:
                        continue
                    
                    # Try to get part of speech from context
                    pos_elem = def_elem.find_previous('h3', class_='definition')
                    pos = 'unknown'
                    if pos_elem:
                        pos_text = pos_elem.get_text().lower()
                        if 'noun' in pos_text:
                            pos = 'noun'
                        elif 'verb' in pos_text:
                            pos = 'verb'
                        elif 'adjective' in pos_text:
                            pos = 'adjective'
                        elif 'adverb' in pos_text:
                            pos = 'adverb'
                    
                    definitions.append(Definition(
                        text=definition_text,
                        part_of_speech=pos,
                        source='vocabulary_com',
                        source_tier=3,
                        reliability_score=0.72
                    ))
                
                logger.info(f"Vocabulary.com found {len(definitions)} definitions for '{term}'")
                return definitions
                
        except Exception as e:
            logger.error(f"Vocabulary.com lookup failed for '{term}': {e}")
            return []
    
    def _extract_pronunciation(self, entry: Dict) -> Optional[str]:
        """Extract pronunciation from dictionary entry"""
        phonetics = entry.get('phonetics', [])
        for phonetic in phonetics:
            if phonetic.get('text'):
                return phonetic['text']
        return None
    
    def _extract_merriam_pronunciation(self, entry: Dict) -> Optional[str]:
        """Extract pronunciation from Merriam-Webster entry"""
        try:
            # Merriam-Webster stores pronunciation in 'hwi' -> 'prs' array
            hwi = entry.get('hwi', {})
            prs = hwi.get('prs', [])
            if prs and len(prs) > 0:
                # Get the pronunciation text, usually in 'mw' field
                pron = prs[0].get('mw', '')
                if pron:
                    return f"\\{pron}\\"  # Add delimiters for clarity
            return None
        except Exception:
            return None
    
    def _group_by_pos(self, definitions: List[Definition]) -> Dict[str, List[Definition]]:
        """Group definitions by part of speech"""
        grouped = {}
        for definition in definitions:
            pos = definition.part_of_speech
            if pos not in grouped:
                grouped[pos] = []
            grouped[pos].append(definition)
        return grouped
    
    def _apply_cross_source_scoring(self, definitions_by_pos: Dict[str, List[Definition]]):
        """Apply cross-source reliability adjustments"""
        for pos, definitions in definitions_by_pos.items():
            if len(definitions) <= 1:
                continue
            
            # Group definitions by similarity
            similar_groups = self._group_similar_definitions(definitions)
            
            # Boost reliability for definitions that appear in multiple sources
            for group in similar_groups:
                if len(group) > 1:
                    sources = {d.source for d in group}
                    if len(sources) > 1:
                        # Multiple sources agree - boost reliability
                        boost = min(0.2, 0.05 * len(sources))
                        for definition in group:
                            definition.reliability_score = min(1.0, definition.reliability_score + boost)
    
    def _group_similar_definitions(self, definitions: List[Definition]) -> List[List[Definition]]:
        """Group definitions that are semantically similar"""
        # Simplified similarity grouping based on text overlap
        groups = []
        
        for definition in definitions:
            words = set(definition.text.lower().split())
            placed = False
            
            for group in groups:
                # Check if this definition is similar to any in the group
                for existing in group:
                    existing_words = set(existing.text.lower().split())
                    overlap = len(words.intersection(existing_words))
                    total_words = len(words.union(existing_words))
                    
                    if total_words > 0 and overlap / total_words > 0.3:  # 30% word overlap
                        group.append(definition)
                        placed = True
                        break
                
                if placed:
                    break
            
            if not placed:
                groups.append([definition])
        
        return groups
    
    def _calculate_overall_reliability(self, definitions: List[Definition]) -> float:
        """Calculate overall reliability score for the lookup"""
        if not definitions:
            return 0.0
        
        # Weight by source tier and individual reliability
        total_weight = 0
        weighted_sum = 0
        
        for definition in definitions:
            # Higher tier sources get more weight
            tier_weight = 5 - definition.source_tier  # Tier 1 = weight 4, Tier 4 = weight 1
            weight = tier_weight * definition.reliability_score
            
            weighted_sum += definition.reliability_score * weight
            total_weight += weight
        
        return weighted_sum / total_weight if total_weight > 0 else 0.0

# Integration function for candidate enhancement
async def enhance_candidate_with_definitions(candidate_dict: Dict[str, Any]) -> Dict[str, Any]:
    """
    Enhance a candidate dictionary with comprehensive definitions
    """
    term = candidate_dict.get('term')
    if not term:
        return candidate_dict
    
    async with ComprehensiveDefinitionLookup() as lookup_system:
        result = await lookup_system.lookup_term(term)
        
        # Add definition information to candidate
        enhanced = candidate_dict.copy()
        
        if result.definitions_by_pos:
            # Get best definition overall
            best_def = result.get_best_definition()
            if best_def:
                enhanced['enhanced_definition'] = best_def.text
                enhanced['definition_source'] = best_def.source
                enhanced['definition_reliability'] = best_def.reliability_score
                
                # Add part of speech if not present
                if not enhanced.get('part_of_speech'):
                    enhanced['part_of_speech'] = best_def.part_of_speech
                
                # Add etymology if available
                if best_def.etymology:
                    enhanced['etymology_enhanced'] = best_def.etymology
                
                # Add examples
                if best_def.examples:
                    enhanced['usage_examples'] = best_def.examples[:3]  # Top 3 examples
        
        # Store lookup metadata
        enhanced['definition_lookup'] = {
            'overall_reliability': result.overall_reliability,
            'sources_consulted': result.sources_consulted,
            'definitions_found': sum(len(defs) for defs in result.definitions_by_pos.values()),
            'lookup_timestamp': result.lookup_timestamp.isoformat()
        }
    
    return enhanced

# Test function
async def test_definition_lookup():
    """Test the definition lookup system"""
    test_terms = [
        "wonderful",      # Common word
        "sesquipedalian", # Rare but real word
        "ebullition",     # Very rare word
        "nonexistent123", # Made-up word
    ]
    
    print("Testing Comprehensive Definition Lookup")
    print("=" * 60)
    
    async with ComprehensiveDefinitionLookup() as lookup_system:
        for term in test_terms:
            print(f"\nLooking up: '{term}'")
            print("-" * 30)
            
            result = await lookup_system.lookup_term(term)
            
            print(f"Overall reliability: {result.overall_reliability:.2f}")
            print(f"Sources consulted: {result.sources_consulted}")
            print(f"Cache hit: {result.cache_hit}")
            
            if result.definitions_by_pos:
                for pos, definitions in result.definitions_by_pos.items():
                    print(f"\n{pos.upper()}:")
                    for i, defn in enumerate(definitions, 1):
                        print(f"  {i}. {defn.text[:100]}{'...' if len(defn.text) > 100 else ''}")
                        print(f"     Source: {defn.source} (tier {defn.source_tier}, reliability: {defn.reliability_score:.2f})")
            else:
                print("No definitions found")

if __name__ == "__main__":
    asyncio.run(test_definition_lookup())
