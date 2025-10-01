#!/usr/bin/env python3
"""
Autonomous Vocabulary Spider - No Queries Required
Intelligently spiders academic, literary, and reference sources to discover rare vocabulary
"""

import asyncio
import aiohttp
import random
import re
import json
import hashlib
import logging
import time
import wordfreq
from typing import Dict, List, Optional, Set, Tuple
from datetime import datetime, timedelta, date
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
import sys
import os

# Add parent directory to path for imports
parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

# Add current directory to avoid __init__.py relative import issues
sys.path.insert(0, os.path.dirname(__file__))

from core.secure_config import get_db_config
from core.english_word_validator import validate_english_word
from core.comprehensive_definition_lookup import ComprehensiveDefinitionLookup
from universal_vocabulary_extractor import UniversalVocabularyExtractor, VocabularyCandidate
import mysql.connector
from mysql.connector import Error
import inflect

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class SourceType(Enum):
    """Available source types for autonomous spidering"""
    WIKIPEDIA = "wikipedia"
    ARXIV = "arxiv" 
    GUTENBERG = "gutenberg"
    PUBMED = "pubmed"

@dataclass
class SpiderConfig:
    """Configuration for autonomous spidering session"""
    max_urls_per_source: int = 50
    max_session_duration_minutes: int = 120
    max_total_candidates: int = 500
    zipf_threshold: float = 2.5
    min_word_length: int = 4
    rate_limit_delay: float = 1.0
    max_link_depth: int = 3
    success_rate_update_interval: int = 10  # Update adaptive balancing every N URLs

@dataclass 
class URLVisitRecord:
    """Record of a URL visit"""
    url: str
    url_hash: str
    source_type: SourceType
    first_visited: datetime
    last_visited: datetime
    visit_count: int
    success_count: int
    candidates_found: int
    status: str

@dataclass
class SourcePerformance:
    """Performance metrics for adaptive source balancing"""
    source_type: SourceType
    urls_visited: int = 0
    success_count: int = 0
    total_candidates: int = 0
    total_response_time: float = 0.0
    error_count: int = 0
    
    @property
    def success_rate(self) -> float:
        if self.urls_visited == 0:
            return 0.0
        return self.success_count / self.urls_visited
    
    @property
    def avg_candidates_per_url(self) -> float:
        if self.success_count == 0:
            return 0.0
        return self.total_candidates / self.success_count
    
    @property
    def avg_response_time(self) -> float:
        if self.urls_visited == 0:
            return 0.0
        return self.total_response_time / self.urls_visited
    
    @property
    def composite_score(self) -> float:
        """Weighted composite performance score for adaptive balancing"""
        if self.urls_visited < 3:  # Not enough data
            return 0.5
        
        # Weighted: 40% success rate, 40% candidates/url, 20% response time
        success_weight = 0.4 * self.success_rate
        candidate_weight = 0.4 * min(1.0, self.avg_candidates_per_url / 10.0)  # Normalize to ~10 candidates
        speed_weight = 0.2 * max(0.0, 1.0 - (self.avg_response_time / 5000.0))  # Penalize >5s responses
        
        return success_weight + candidate_weight + speed_weight

class AutonomousVocabularySpider:
    """Autonomous vocabulary discovery spider with no query dependencies"""
    
    def __init__(self, config: SpiderConfig = None):
        self.config = config or SpiderConfig()
        self.db_config = get_db_config()
        self.extractor = UniversalVocabularyExtractor()
        self.inflect_engine = inflect.engine()
        self.definition_lookup = None  # Will be initialized in async context
        
        # Session state
        self.session_id = f"spider_{int(time.time())}"
        self.start_time = datetime.now()
        self.visited_urls_cache: Set[str] = set()
        self.performance_metrics: Dict[SourceType, SourcePerformance] = {}
        self.total_candidates_found = 0
        self.total_urls_visited = 0
        
        # Initialize performance tracking
        for source_type in SourceType:
            self.performance_metrics[source_type] = SourcePerformance(source_type)
        
        logger.info(f"Initialized autonomous spider session: {self.session_id}")
    
    def _is_english_word_enhanced(self, word: str) -> bool:
        """Enhanced English word validation with non-Latin script detection"""
        if not word or len(word.strip()) < 2:
            return False
        
        word = word.strip().lower()
        
        # Check for non-Latin scripts (Cyrillic, Arabic, Chinese, etc.)
        for char in word:
            # Cyrillic: U+0400-U+04FF
            # Arabic: U+0600-U+06FF  
            # Chinese/Japanese: U+4E00-U+9FFF, U+3040-U+309F, U+30A0-U+30FF
            # Greek: U+0370-U+03FF
            # Hebrew: U+0590-U+05FF
            if (ord(char) >= 0x0400 and ord(char) <= 0x04FF) or \
               (ord(char) >= 0x0600 and ord(char) <= 0x06FF) or \
               (ord(char) >= 0x4E00 and ord(char) <= 0x9FFF) or \
               (ord(char) >= 0x3040 and ord(char) <= 0x309F) or \
               (ord(char) >= 0x30A0 and ord(char) <= 0x30FF) or \
               (ord(char) >= 0x0370 and ord(char) <= 0x03FF) or \
               (ord(char) >= 0x0590 and ord(char) <= 0x05FF):
                return False
        
        # Check for non-English patterns
        non_english_patterns = [
            # Common non-English letter combinations
            re.compile(r'[ąęłńśźż]'),  # Polish
            re.compile(r'[àáâäèéêëìíîïòóôöùúûü]'),  # Romance languages with heavy accents
            re.compile(r'[şţ]'),  # Romanian
            re.compile(r'[öäüß]'),  # German
            re.compile(r'[æøå]'),  # Scandinavian
            re.compile(r'^[qxz][qxz]'),  # Unlikely English starts
            re.compile(r'[bcdfghjklmnpqrstvwxz]{5,}'),  # Too many consecutive consonants
            re.compile(r'[aeiou]{4,}'),  # Too many consecutive vowels
        ]
        
        for pattern in non_english_patterns:
            if pattern.search(word):
                return False
        
        # Use existing validation if available
        try:
            result = validate_english_word(word)
            if isinstance(result, tuple):
                return result[0]  # (bool, reason) tuple
            return result
        except:
            # Fallback validation
            return len(word) >= 3 and word.replace('-', '').replace("'", '').isalpha()
    
    def _should_exclude_by_pos(self, pos: str, term: str) -> bool:
        """Enhanced POS filtering with PUNCT classification review"""
        if not pos:
            return True  # Exclude words without POS
        
        pos = pos.upper()
        
        # Exclude clearly problematic POS tags
        excluded_pos = {
            'PROPN',  # Proper nouns
            'X',      # Unknown/Other
            'SYM',    # Symbols
            'NUM',    # Numbers
            'SPACE',  # Whitespace
        }
        
        if pos in excluded_pos:
            return True
        
        # Special handling for PUNCT - many are misclassified
        if pos == 'PUNCT':
            # Check if this "PUNCT" term is actually a meaningful word
            if self._is_likely_misclassified_punct(term):
                logger.info(f"Reclassifying '{term}' from PUNCT - appears to be a real word")
                return False  # Don't exclude, it's probably a real word
            else:
                return True   # Exclude actual punctuation
        
        return False  # Include all other POS types
    
    def _is_likely_misclassified_punct(self, term: str) -> bool:
        """Check if a PUNCT-classified term is actually a meaningful word"""
        if not term or len(term) < 3:
            return False
        
        # Remove any actual punctuation
        clean_term = re.sub(r'[^\w\-\']', '', term.lower())
        if len(clean_term) < 3:
            return False
        
        # Check if it looks like a real word
        word_indicators = [
            # Has vowels (most English words do)
            bool(re.search(r'[aeiou]', clean_term)),
            # Reasonable consonant/vowel balance
            len(re.findall(r'[bcdfghjklmnpqrstvwxz]', clean_term)) <= len(clean_term) * 0.8,
            # Common English word patterns
            bool(re.search(r'(ing|tion|ness|ment|able|ible|ous|eous|ious|ary|ery|ory|ful|less|ship|ward|like)$', clean_term)),
            # Common prefixes
            bool(re.search(r'^(un|re|pre|dis|over|under|out|up|in|im|ir|il|non|anti|de|pro|sub|inter|trans|super|auto|semi|multi|extra|ultra|pseudo|quasi|neo|micro|macro|mega|mini)', clean_term)),
            # Not obviously punctuation-like
            not bool(re.search(r'^[^\w]*$', term)),
            # Reasonable length for English words
            3 <= len(clean_term) <= 20,
        ]
        
        # If most indicators suggest it's a word, treat it as misclassified
        return sum(word_indicators) >= 3
    
    async def setup_database_tables(self):
        """Create spider tracking tables if they don't exist"""
        conn = mysql.connector.connect(**self.db_config)
        cursor = conn.cursor()
        
        try:
            # Read and execute the SQL file
            sql_file = Path(__file__).parent.parent / "create_spider_tables.sql"
            if sql_file.exists():
                with open(sql_file, 'r') as f:
                    sql_content = f.read()
                
                # Split by statements and execute
                statements = [stmt.strip() for stmt in sql_content.split(';') if stmt.strip() and not stmt.strip().startswith('--')]
                for statement in statements:
                    if statement:
                        cursor.execute(statement)
                        
            conn.commit()
            logger.info("Spider database tables created/verified")
            
        except Exception as e:
            logger.error(f"Error setting up database tables: {e}")
            conn.rollback()
        finally:
            cursor.close()
            conn.close()
    
    def _hash_url(self, url: str) -> str:
        """Generate SHA-256 hash of URL for fast database lookups"""
        return hashlib.sha256(url.encode('utf-8')).hexdigest()
    
    async def is_url_recently_visited(self, url: str, source_type: SourceType) -> bool:
        """Check if URL was visited within the last 120 days"""
        url_hash = self._hash_url(url)
        
        # Check cache first
        if url_hash in self.visited_urls_cache:
            return True
        
        # Check database
        conn = mysql.connector.connect(**self.db_config)
        cursor = conn.cursor()
        
        try:
            cursor.execute("""
                SELECT id FROM spider_visited_urls 
                WHERE url_hash = %s AND source_type = %s 
                AND last_visited > DATE_SUB(NOW(), INTERVAL 120 DAY)
            """, (url_hash, source_type.value))
            
            result = cursor.fetchone()
            if result:
                self.visited_urls_cache.add(url_hash)
                return True
            return False
            
        except Exception as e:
            logger.error(f"Error checking URL visit history: {e}")
            return False
        finally:
            cursor.close()
            conn.close()
    
    async def record_url_visit(self, url: str, source_type: SourceType, 
                             success: bool, candidates_found: int):
        """Record URL visit in database and cache"""
        url_hash = self._hash_url(url)
        self.visited_urls_cache.add(url_hash)
        
        conn = mysql.connector.connect(**self.db_config)
        cursor = conn.cursor()
        
        try:
            # Insert or update visit record
            cursor.execute("""
                INSERT INTO spider_visited_urls 
                (url, url_hash, source_type, first_visited, last_visited, 
                 visit_count, success_count, candidates_found, status)
                VALUES (%s, %s, %s, NOW(), NOW(), 1, %s, %s, %s)
                ON DUPLICATE KEY UPDATE
                    last_visited = NOW(),
                    visit_count = visit_count + 1,
                    success_count = success_count + %s,
                    candidates_found = candidates_found + %s,
                    status = %s
            """, (
                url[:2000], url_hash, source_type.value, 
                1 if success else 0, candidates_found,
                'success' if success else 'failed',
                1 if success else 0, candidates_found,
                'success' if success else 'failed'
            ))
            
            conn.commit()
            
        except Exception as e:
            logger.error(f"Error recording URL visit: {e}")
        finally:
            cursor.close()
            conn.close()
    
    async def is_word_already_stored(self, term: str) -> bool:
        """Check if word exists in defined or candidate_words tables (case insensitive, singular form)"""
        # Convert to singular form
        singular_term = self.inflect_engine.singular_noun(term.lower()) or term.lower()
        
        conn = mysql.connector.connect(**self.db_config)
        cursor = conn.cursor()
        
        try:
            # Check defined table
            cursor.execute("SELECT id FROM defined WHERE LOWER(term) = %s LIMIT 1", (singular_term,))
            if cursor.fetchone():
                return True
            
            # Check candidate_words table
            cursor.execute("SELECT id FROM candidate_words WHERE LOWER(term) = %s LIMIT 1", (singular_term,))
            if cursor.fetchone():
                return True
            
            return False
            
        except Exception as e:
            logger.error(f"Error checking word existence: {e}")
            return True  # Conservative: assume it exists if we can't check
        finally:
            cursor.close()
            conn.close()
    
    async def filter_candidates_by_frequency(self, candidates: List[VocabularyCandidate], source_url: str = None) -> List[VocabularyCandidate]:
        """Filter candidates by wordfreq zipf score <= 2.5, exclude proper nouns, and add definitions"""
        filtered = []
        
        for candidate in candidates:
            try:
                # ENHANCED POS filtering: Exclude problematic classifications
                if self._should_exclude_by_pos(candidate.part_of_speech, candidate.term):
                    continue
                
                # Check minimum length
                if len(candidate.term) < self.config.min_word_length:
                    continue
                
                # Check word frequency using wordfreq
                zipf_score = wordfreq.zipf_frequency(candidate.term, 'en')
                if zipf_score > self.config.zipf_threshold:
                    continue  # Too common
                
                # Check if already stored (handles singularization and case)
                if await self.is_word_already_stored(candidate.term):
                    continue  # Already exists
                
                # ENHANCED: Validate English word with script detection
                if not self._is_english_word_enhanced(candidate.term):
                    continue
                
                # Look up definition using comprehensive system
                definition_text = await self.lookup_definition_for_candidate(candidate)
                if not definition_text:
                    continue  # Skip if no definition found with matching POS
                
                # Add frequency info and definition to candidate
                candidate.source_metadata['zipf_score'] = zipf_score
                candidate.source_metadata['frequency_filter_passed'] = True
                candidate.source_metadata['definition_text'] = definition_text
                candidate.source_metadata['source_url'] = source_url
                
                filtered.append(candidate)
                
            except Exception as e:
                logger.debug(f"Error filtering candidate '{candidate.term}': {e}")
                continue
        
        return filtered
    
    async def lookup_definition_for_candidate(self, candidate: VocabularyCandidate) -> Optional[str]:
        """Look up definition using comprehensive lookup system with POS matching"""
        try:
            # Convert spider POS tags to standard forms for lookup
            pos_mapping = {
                'NOUN': 'noun',
                'VERB': 'verb', 
                'ADJ': 'adjective',
                'ADV': 'adverb',
                'PROPN': 'noun'  # Though we filter these out
            }
            
            target_pos = pos_mapping.get(candidate.part_of_speech, candidate.part_of_speech.lower())
            
            # Perform lookup - DISABLE CACHE to ensure unique definitions per term
            result = await self.definition_lookup.lookup_term(candidate.term, use_cache=False)
            
            # DEBUG: Log each lookup to verify unique definitions
            logger.debug(f"Definition lookup for '{candidate.term}' (POS: {target_pos}) found {len(result.definitions_by_pos) if result.definitions_by_pos else 0} POS entries")
            
            if not result.definitions_by_pos:
                logger.debug(f"No definitions found for '{candidate.term}'")
                return "Definition not found"
            
            # Look for exact POS match first
            if target_pos in result.definitions_by_pos:
                definitions = result.definitions_by_pos[target_pos]
                if definitions:
                    # Get definitions from most authoritative source (lowest tier number)
                    best_definitions = sorted(definitions, key=lambda d: d.source_tier)
                    
                    # Concatenate all definitions from the best source with same tier
                    best_tier = best_definitions[0].source_tier
                    tier_definitions = [d for d in best_definitions if d.source_tier == best_tier]
                    
                    # Create numbered list
                    definition_parts = []
                    for i, defn in enumerate(tier_definitions, 1):
                        definition_parts.append(f"{i}. {defn.text}")
                    
                    return " ".join(definition_parts)
            
            # If no exact POS match, skip this candidate
            return None
            
        except Exception as e:
            logger.debug(f"Error looking up definition for '{candidate.term}': {e}")
            return "Definition lookup failed"
    
    async def get_random_wikipedia_article(self) -> Optional[str]:
        """Get a random Wikipedia article URL"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get('https://en.wikipedia.org/api/rest_v1/page/random/summary') as response:
                    if response.status == 200:
                        data = await response.json()
                        return data.get('content_urls', {}).get('desktop', {}).get('page')
        except Exception as e:
            logger.error(f"Error getting random Wikipedia article: {e}")
        return None
    
    async def get_wikipedia_links_from_page(self, url: str) -> List[str]:
        """Extract Wikipedia article links from a page"""
        links = []
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as response:
                    if response.status != 200:
                        return links
                    
                    html = await response.text()
                    soup = BeautifulSoup(html, 'html.parser')
                    
                    # Find main content area
                    content = soup.find('div', {'id': 'mw-content-text'})
                    if not content:
                        return links
                    
                    # Extract article links (not external, not files, not special pages)
                    for link in content.find_all('a', href=True):
                        href = link['href']
                        if (href.startswith('/wiki/') and 
                            ':' not in href and
                            '#' not in href and
                            not href.startswith('/wiki/File:')):
                            full_url = urljoin('https://en.wikipedia.org', href)
                            links.append(full_url)
                    
                    # Limit and randomize
                    random.shuffle(links)
                    return links[:20]  # Return up to 20 random links
                    
        except Exception as e:
            logger.error(f"Error extracting Wikipedia links from {url}: {e}")
        
        return links
    
    async def get_arxiv_recent_papers(self) -> List[str]:
        """Get URLs for recent ArXiv papers"""
        papers = []
        try:
            # Get recent papers from various categories
            categories = ['cs.CL', 'cs.AI', 'physics.bio-ph', 'q-bio', 'math.CO']
            category = random.choice(categories)
            
            url = f'http://export.arxiv.org/api/query?search_query=cat:{category}&start=0&max_results=20&sortBy=submittedDate&sortOrder=descending'
            
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as response:
                    if response.status == 200:
                        content = await response.text()
                        # Parse XML to extract paper URLs
                        from xml.etree import ElementTree as ET
                        root = ET.fromstring(content)
                        
                        for entry in root.findall('{http://www.w3.org/2005/Atom}entry'):
                            id_elem = entry.find('{http://www.w3.org/2005/Atom}id')
                            if id_elem is not None:
                                arxiv_id = id_elem.text.split('/')[-1]
                                paper_url = f'https://arxiv.org/abs/{arxiv_id}'
                                papers.append(paper_url)
        
        except Exception as e:
            logger.error(f"Error getting ArXiv papers: {e}")
        
        return papers
    
    async def get_random_gutenberg_works(self) -> List[str]:
        """Get random Project Gutenberg work URLs"""
        works = []
        try:
            # Get from Gutenberg's browse pages
            base_urls = [
                'https://www.gutenberg.org/browse/scores/top',
                'https://www.gutenberg.org/browse/recent/last1',
                f'https://www.gutenberg.org/browse/authors/{random.choice("abcdefghijklmnopqrstuvwxyz")}'
            ]
            
            url = random.choice(base_urls)
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as response:
                    if response.status == 200:
                        html = await response.text()
                        soup = BeautifulSoup(html, 'html.parser')
                        
                        # Find work links
                        for link in soup.find_all('a', href=True):
                            href = link['href']
                            if '/ebooks/' in href and href.endswith(tuple('0123456789')):
                                full_url = urljoin('https://www.gutenberg.org', href)
                                works.append(full_url)
                        
                        random.shuffle(works)
                        return works[:10]  # Return up to 10 works
                        
        except Exception as e:
            logger.error(f"Error getting Gutenberg works: {e}")
        
        return works
    
    async def extract_text_from_url(self, url: str, source_type: SourceType) -> Optional[str]:
        """Extract meaningful text content from a URL"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=30)) as response:
                    if response.status != 200:
                        return None
                    
                    html = await response.text()
                    soup = BeautifulSoup(html, 'html.parser')
                    
                    # Remove script and style elements
                    for script in soup(["script", "style", "nav", "footer", "header"]):
                        script.decompose()
                    
                    # Extract text based on source type
                    if source_type == SourceType.WIKIPEDIA:
                        content = soup.find('div', {'id': 'mw-content-text'})
                        if content:
                            # Remove citation boxes, infoboxes, etc.
                            for unwanted in content.find_all(['table', 'div'], class_=['navbox', 'infobox', 'citation']):
                                unwanted.decompose()
                            text = content.get_text()
                        else:
                            text = soup.get_text()
                    
                    elif source_type == SourceType.ARXIV:
                        # For ArXiv, focus on abstract and main content
                        abstract = soup.find('blockquote', class_='abstract')
                        if abstract:
                            text = abstract.get_text()
                        else:
                            text = soup.get_text()
                    
                    elif source_type == SourceType.GUTENBERG:
                        # For Gutenberg, find the main text content
                        content = soup.find('div', {'id': 'pg-machine-header'})
                        if content and content.find_next('pre'):
                            text = content.find_next('pre').get_text()
                        else:
                            # Try to find main content area
                            main_text = soup.find('pre') or soup.find('div', class_='chapter')
                            if main_text:
                                text = main_text.get_text()
                            else:
                                text = soup.get_text()
                    
                    else:
                        text = soup.get_text()
                    
                    # Clean up text
                    lines = (line.strip() for line in text.splitlines())
                    chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
                    text = ' '.join(chunk for chunk in chunks if chunk)
                    
                    # Limit text length to prevent memory issues
                    if len(text) > 50000:
                        text = text[:50000]
                    
                    return text if len(text) > 100 else None  # Minimum meaningful content
                    
        except Exception as e:
            logger.error(f"Error extracting text from {url}: {e}")
            return None
    
    def select_next_source(self) -> SourceType:
        """Select next source type based on adaptive performance balancing"""
        # If we don't have enough data, use equal probability
        if self.total_urls_visited < 20:
            return random.choice(list(SourceType))
        
        # Calculate selection weights based on composite performance scores
        weights = []
        sources = list(SourceType)
        
        for source_type in sources:
            performance = self.performance_metrics[source_type]
            # Add base weight to ensure all sources get some chance
            weight = 0.1 + performance.composite_score
            weights.append(weight)
        
        # Weighted random selection
        total_weight = sum(weights)
        if total_weight == 0:
            return random.choice(sources)
        
        r = random.uniform(0, total_weight)
        cumsum = 0
        for i, weight in enumerate(weights):
            cumsum += weight
            if r <= cumsum:
                return sources[i]
        
        return sources[-1]  # Fallback
    
    async def spider_source(self, source_type: SourceType, max_urls: int) -> List[VocabularyCandidate]:
        """Spider a specific source type for vocabulary"""
        candidates = []
        urls_processed = 0
        
        logger.info(f"Starting to spider {source_type.value} (max {max_urls} URLs)")
        
        # Get initial URLs
        if source_type == SourceType.WIKIPEDIA:
            initial_url = await self.get_random_wikipedia_article()
            if not initial_url:
                return candidates
            url_queue = [initial_url]
        elif source_type == SourceType.ARXIV:
            url_queue = await self.get_arxiv_recent_papers()
        elif source_type == SourceType.GUTENBERG:
            url_queue = await self.get_random_gutenberg_works()
        else:
            return candidates
        
        if not url_queue:
            logger.warning(f"No initial URLs found for {source_type.value}")
            return candidates
        
        # Process URLs
        while url_queue and urls_processed < max_urls:
            url = url_queue.pop(0)
            
            # Check if recently visited
            if await self.is_url_recently_visited(url, source_type):
                continue
            
            start_time = time.time()
            try:
                # Extract text content
                text_content = await self.extract_text_from_url(url, source_type)
                response_time = (time.time() - start_time) * 1000  # Convert to milliseconds
                
                if text_content:
                    # Extract vocabulary candidates
                    url_candidates = self.extractor.extract_candidates(
                        text_content, 
                        {'source_type': source_type.value, 'url': url}
                    )
                    
                    # Filter candidates
                    filtered_candidates = await self.filter_candidates_by_frequency(url_candidates, url)
                    candidates.extend(filtered_candidates)
                    
                    # Record successful visit
                    await self.record_url_visit(url, source_type, True, len(filtered_candidates))
                    
                    # Update performance metrics
                    perf = self.performance_metrics[source_type]
                    perf.urls_visited += 1
                    perf.success_count += 1
                    perf.total_candidates += len(filtered_candidates)
                    perf.total_response_time += response_time
                    
                    logger.info(f"Processed {url}: {len(filtered_candidates)} candidates found")
                    
                    # Get more URLs from this page (for Wikipedia)
                    if source_type == SourceType.WIKIPEDIA and len(url_queue) < 10:
                        new_links = await self.get_wikipedia_links_from_page(url)
                        # Add unvisited links
                        for link in new_links:
                            if not await self.is_url_recently_visited(link, source_type):
                                url_queue.append(link)
                                if len(url_queue) >= 20:  # Limit queue size
                                    break
                
                else:
                    # Record failed visit
                    await self.record_url_visit(url, source_type, False, 0)
                    perf = self.performance_metrics[source_type]
                    perf.urls_visited += 1
                    perf.total_response_time += response_time
                
            except Exception as e:
                logger.error(f"Error processing {url}: {e}")
                await self.record_url_visit(url, source_type, False, 0)
                perf = self.performance_metrics[source_type]
                perf.urls_visited += 1
                perf.error_count += 1
            
            urls_processed += 1
            self.total_urls_visited += 1
            
            # Rate limiting
            await asyncio.sleep(self.config.rate_limit_delay)
        
        logger.info(f"Completed spidering {source_type.value}: {len(candidates)} candidates from {urls_processed} URLs")
        return candidates
    
    async def store_candidates(self, candidates: List[VocabularyCandidate]):
        """Store filtered candidates in database"""
        if not candidates:
            return
        
        conn = mysql.connector.connect(**self.db_config)
        cursor = conn.cursor()
        
        try:
            insert_query = """
                INSERT INTO candidate_words 
                (term, source_type, source_reference, part_of_speech, utility_score, rarity_indicators,
                 context_snippet, raw_definition, etymology_preview, date_discovered)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """
            
            values = []
            for candidate in candidates:
                source_type = candidate.source_metadata.get('source_type', 'unknown')
                zipf_score = candidate.source_metadata.get('zipf_score', 0.0)
                definition_text = candidate.source_metadata.get('definition_text', 'Definition not available')
                source_url = candidate.source_metadata.get('source_url', '')
                
                rarity_indicators = {
                    'zipf_score': zipf_score,
                    'frequency_rank': 'rare' if zipf_score <= 2.0 else 'uncommon',
                    'source_quality': 'high' if source_type in ['wikipedia', 'arxiv', 'gutenberg'] else 'medium'
                }
                
                values.append((
                    candidate.term,
                    source_type,
                    source_url[:255] if source_url else None,  # Truncate to field length
                    candidate.part_of_speech or 'unknown',
                    candidate.preliminary_score,
                    json.dumps(rarity_indicators),
                    candidate.context[:500] if candidate.context else None,
                    definition_text,
                    json.dumps(candidate.morphological_type)[:500] if candidate.morphological_type else None,
                    datetime.now()
                ))
            
            cursor.executemany(insert_query, values)
            conn.commit()
            
            logger.info(f"Successfully stored {len(candidates)} candidates in database")
            
        except Error as e:
            logger.error(f"Database error storing candidates: {e}")
            conn.rollback()
        finally:
            cursor.close()
            conn.close()
    
    async def run_autonomous_session(self) -> Dict:
        """Run a complete autonomous spidering session"""
        logger.info(f"Starting autonomous spider session {self.session_id}")
        logger.info(f"Config: {self.config.max_urls_per_source} URLs/source, "
                   f"{self.config.max_session_duration_minutes}min max, "
                   f"zipf≤{self.config.zipf_threshold}")
        
        # Setup database
        await self.setup_database_tables()
        
        all_candidates = []
        session_start = datetime.now()
        
        # Initialize definition lookup in async context
        from core.comprehensive_definition_lookup import ComprehensiveDefinitionLookup
        async with ComprehensiveDefinitionLookup() as definition_lookup:
            self.definition_lookup = definition_lookup
            
            try:
                # Continue until limits reached
                while (len(all_candidates) < self.config.max_total_candidates and
                       (datetime.now() - session_start).total_seconds() < self.config.max_session_duration_minutes * 60):
                    
                    # Adaptively select source
                    source_type = self.select_next_source()
                
                    # Calculate dynamic URL limit based on performance
                    performance = self.performance_metrics[source_type]
                    if performance.success_rate > 0.7:
                        urls_to_process = min(self.config.max_urls_per_source, 20)
                    elif performance.success_rate > 0.3:
                        urls_to_process = min(self.config.max_urls_per_source, 10)
                    else:
                        urls_to_process = min(self.config.max_urls_per_source, 5)
                    
                    # Spider the selected source
                    source_candidates = await self.spider_source(source_type, urls_to_process)
                    all_candidates.extend(source_candidates)
                    self.total_candidates_found += len(source_candidates)
                    
                    # Store candidates immediately
                    if source_candidates:
                        await self.store_candidates(source_candidates)
                    
                    logger.info(f"Session progress: {len(all_candidates)} total candidates, "
                               f"{self.total_urls_visited} URLs visited")
            
            except KeyboardInterrupt:
                logger.info("Session interrupted by user")
            except Exception as e:
                logger.error(f"Session error: {e}")
        
        # Final session summary
        duration = datetime.now() - session_start
        
        # Log performance metrics
        logger.info("=== SESSION PERFORMANCE SUMMARY ===")
        for source_type, perf in self.performance_metrics.items():
            if perf.urls_visited > 0:
                logger.info(f"{source_type.value}: {perf.urls_visited} URLs, "
                           f"{perf.success_rate:.2%} success, "
                           f"{perf.avg_candidates_per_url:.1f} candidates/URL, "
                           f"{perf.avg_response_time:.0f}ms avg response")
        
        summary = {
            'session_id': self.session_id,
            'duration': str(duration),
            'total_urls_visited': self.total_urls_visited,
            'total_candidates_found': self.total_candidates_found,
            'unique_candidates_stored': len(all_candidates),
            'performance_metrics': {
                source.value: {
                    'urls_visited': perf.urls_visited,
                    'success_rate': perf.success_rate,
                    'candidates_per_url': perf.avg_candidates_per_url,
                    'composite_score': perf.composite_score
                }
                for source, perf in self.performance_metrics.items()
                if perf.urls_visited > 0
            }
        }
        
        logger.info(f"Session completed: {self.total_candidates_found} candidates found, "
                   f"{len(all_candidates)} stored, {duration}")
        
        return summary

async def main():
    """Main entry point for autonomous spider"""
    import argparse
    
    parser = argparse.ArgumentParser(description="Autonomous Vocabulary Spider")
    parser.add_argument("--max-urls", type=int, default=50, help="Max URLs per source")
    parser.add_argument("--duration", type=int, default=120, help="Max session duration in minutes")
    parser.add_argument("--candidates", type=int, default=500, help="Max total candidates")
    parser.add_argument("--zipf-threshold", type=float, default=2.5, help="Max zipf frequency score")
    
    args = parser.parse_args()
    
    config = SpiderConfig(
        max_urls_per_source=args.max_urls,
        max_session_duration_minutes=args.duration,
        max_total_candidates=args.candidates,
        zipf_threshold=args.zipf_threshold
    )
    
    spider = AutonomousVocabularySpider(config)
    summary = await spider.run_autonomous_session()
    
    print("\n" + "="*60)
    print("AUTONOMOUS SPIDER SESSION COMPLETE")
    print("="*60)
    print(f"Session ID: {summary['session_id']}")
    print(f"Duration: {summary['duration']}")
    print(f"URLs Visited: {summary['total_urls_visited']}")
    print(f"Candidates Found: {summary['total_candidates_found']}")
    print(f"Unique Stored: {summary['unique_candidates_stored']}")
    print()
    print("Source Performance:")
    for source, metrics in summary['performance_metrics'].items():
        print(f"  {source}: {metrics['urls_visited']} URLs, "
              f"{metrics['success_rate']:.1%} success, "
              f"{metrics['candidates_per_url']:.1f} cand/URL")

if __name__ == "__main__":
    asyncio.run(main())