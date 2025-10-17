#!/usr/bin/env python3
"""
URL-Specific Vocabulary Harvester
Harvests vocabulary from a specified URL with configurable depth and frequency filtering
"""

import asyncio
import aiohttp
import argparse
import sys
import os
import logging
from urllib.parse import urljoin, urlparse
from typing import List, Optional, Set
from dataclasses import dataclass
import time
from datetime import datetime
import mysql.connector
from mysql.connector import Error

# Add parent directory to path for imports
parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

from core.secure_config import get_db_config
from core.comprehensive_definition_lookup import ComprehensiveDefinitionLookup
from harvesters.universal_vocabulary_extractor import UniversalVocabularyExtractor, VocabularyCandidate
from harvesters.respectful_scraper import RespectfulScraper
import wordfreq
import spacy

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@dataclass
class HarvestStats:
    """Statistics for the harvest session"""
    start_time: datetime
    urls_processed: int = 0
    urls_successful: int = 0
    candidates_found: int = 0
    candidates_stored: int = 0
    max_depth_reached: int = 0

class URLVocabularyHarvester:
    """Harvests vocabulary from specified URLs with depth traversal and frequency filtering"""
    
    def __init__(self, zipf_threshold: float = 3.0, max_depth: int = 1, max_urls: int = 50):
        self.zipf_threshold = zipf_threshold
        self.max_depth = max_depth
        self.max_urls = max_urls
        self.db_config = get_db_config()
        
        # Initialize components
        self.extractor = UniversalVocabularyExtractor()
        self.scraper = RespectfulScraper()
        
        # Load spaCy model for POS tagging
        try:
            self.nlp = spacy.load("en_core_web_sm")
        except OSError:
            logger.warning("spaCy model 'en_core_web_sm' not found. Install with: python -m spacy download en_core_web_sm")
            self.nlp = None
        
        # Tracking
        self.visited_urls: Set[str] = set()
        self.url_queue: List[tuple] = []  # (url, depth)
        self.stats = HarvestStats(start_time=datetime.now())
    
    def normalize_url(self, url: str, base_url: str = None) -> Optional[str]:
        """Normalize and validate URL"""
        try:
            if base_url:
                url = urljoin(base_url, url)
            
            parsed = urlparse(url)
            if not parsed.scheme:
                return None
            if not parsed.netloc:
                return None
                
            return url
        except Exception as e:
            logger.debug(f"Error normalizing URL '{url}': {e}")
            return None
    
    def should_follow_link(self, url: str, base_domain: str) -> bool:
        """Check if we should follow this link based on domain and other criteria"""
        try:
            parsed = urlparse(url)
            
            # Stay within the same domain
            if parsed.netloc != base_domain:
                return False
                
            # Skip common non-content URLs
            skip_patterns = [
                '/admin', '/login', '/register', '/cart', '/checkout',
                '/api/', '/.', '/css/', '/js/', '/images/', '/img/',
                '.pdf', '.doc', '.zip', '.jpg', '.png', '.gif',
                '#', '?search=', '?sort=', '?filter='
            ]
            
            url_lower = url.lower()
            for pattern in skip_patterns:
                if pattern in url_lower:
                    return False
            
            return True
            
        except Exception:
            return False
    
    async def extract_links_from_content(self, html_content: str, base_url: str) -> List[str]:
        """Extract valid links from HTML content"""
        try:
            from bs4 import BeautifulSoup
            
            soup = BeautifulSoup(html_content, 'html.parser')
            links = []
            base_domain = urlparse(base_url).netloc
            
            # Extract from anchor tags
            for link in soup.find_all('a', href=True):
                href = link['href']
                normalized_url = self.normalize_url(href, base_url)
                
                if normalized_url and self.should_follow_link(normalized_url, base_domain):
                    links.append(normalized_url)
            
            # Remove duplicates while preserving order
            seen = set()
            unique_links = []
            for link in links:
                if link not in seen:
                    seen.add(link)
                    unique_links.append(link)
            
            return unique_links[:20]  # Limit to prevent explosion
            
        except Exception as e:
            logger.debug(f"Error extracting links: {e}")
            return []
    
    async def filter_candidates_by_frequency(self, candidates: List[VocabularyCandidate], source_url: str) -> List[VocabularyCandidate]:
        """Filter candidates by frequency (zipf score) and POS"""
        filtered = []
        
        for candidate in candidates:
            try:
                # Skip proper nouns if we have spaCy
                if self.nlp:
                    doc = self.nlp(candidate.term)
                    if doc and doc[0].pos_ == 'PROPN':
                        continue
                
                # Check frequency using wordfreq
                zipf_score = wordfreq.zipf_frequency(candidate.term.lower(), 'en')
                
                # Filter by zipf threshold (lower = rarer)
                if zipf_score > self.zipf_threshold:
                    continue  # Too common
                
                if zipf_score == 0:
                    # Very rare or OOV - be more selective
                    if len(candidate.term) < 4 or not candidate.term.isalpha():
                        continue
                
                # Check if already exists in database
                if await self.is_word_already_stored(candidate.term):
                    continue
                
                # Look up definition
                definition_text = await self.lookup_definition_for_candidate(candidate)
                if not definition_text:
                    continue
                
                # Add metadata
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
        """Look up definition using comprehensive lookup system"""
        try:
            # Convert POS tags to standard forms
            pos_mapping = {
                'NOUN': 'noun', 'VERB': 'verb', 'ADJ': 'adjective', 'ADV': 'adverb'
            }
            
            target_pos = pos_mapping.get(candidate.part_of_speech, candidate.part_of_speech.lower())
            
            # Perform lookup
            result = await self.definition_lookup.lookup_term(candidate.term, use_cache=True)
            
            if not result.definitions_by_pos:
                return "Definition not found"
            
            # Look for exact POS match first
            if target_pos in result.definitions_by_pos:
                definitions = result.definitions_by_pos[target_pos]
                if definitions:
                    # Get definitions from most authoritative source
                    best_definitions = sorted(definitions, key=lambda d: d.source_tier)
                    best_tier = best_definitions[0].source_tier
                    tier_definitions = [d for d in best_definitions if d.source_tier == best_tier]
                    
                    # Create numbered list
                    definition_parts = []
                    for i, defn in enumerate(tier_definitions, 1):
                        definition_parts.append(f"{i}. {defn.text}")
                    
                    return " ".join(definition_parts)
            
            # No exact POS match
            return None
            
        except Exception as e:
            logger.debug(f"Error looking up definition for '{candidate.term}': {e}")
            return "Definition lookup failed"
    
    async def is_word_already_stored(self, term: str) -> bool:
        """Check if word exists in defined or candidate_words tables"""
        try:
            conn = mysql.connector.connect(**self.db_config)
            cursor = conn.cursor()
            
            # Check both tables
            cursor.execute("SELECT 1 FROM vocab.defined WHERE word = %s LIMIT 1", (term.lower(),))
            if cursor.fetchone():
                return True
            
            cursor.execute("SELECT 1 FROM vocab.candidate_words WHERE word = %s LIMIT 1", (term.lower(),))
            if cursor.fetchone():
                return True
            
            return False
            
        except Exception as e:
            logger.debug(f"Error checking word existence: {e}")
            return True  # Conservative: assume it exists if we can't check
        finally:
            if cursor:
                cursor.close()
            if conn:
                conn.close()
    
    async def store_candidates(self, candidates: List[VocabularyCandidate]) -> int:
        """Store candidates in database"""
        if not candidates:
            return 0
        
        try:
            conn = mysql.connector.connect(**self.db_config)
            cursor = conn.cursor()
            
            insert_query = """
                INSERT IGNORE INTO vocab.candidate_words 
                (word, part_of_speech, confidence, context_sentence, source_type, raw_definition, source_reference)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
            """
            
            values = []
            for candidate in candidates:
                values.append((
                    candidate.term.lower(),
                    candidate.part_of_speech,
                    candidate.confidence,
                    candidate.context_sentence or '',
                    'url_harvest',
                    candidate.source_metadata.get('definition_text', ''),
                    candidate.source_metadata.get('source_url', '')
                ))
            
            cursor.executemany(insert_query, values)
            conn.commit()
            
            stored_count = cursor.rowcount
            logger.info(f"Successfully stored {stored_count} candidates in database")
            return stored_count
            
        except Error as e:
            logger.error(f"Database error storing candidates: {e}")
            return 0
        finally:
            if cursor:
                cursor.close()
            if conn:
                conn.close()
    
    async def process_url(self, url: str, current_depth: int) -> List[VocabularyCandidate]:
        """Process a single URL and return vocabulary candidates"""
        logger.info(f"Processing URL (depth {current_depth}): {url}")
        
        try:
            # Fetch content
            content = await self.scraper.fetch_article_content(url, "url_harvest")
            if not content:
                logger.warning(f"No content retrieved from {url}")
                return []
            
            self.stats.urls_successful += 1
            
            # Extract vocabulary candidates
            candidates = self.extractor.extract_candidates(
                content, 
                {'source_type': 'url_harvest', 'url': url, 'depth': current_depth}
            )
            
            if not candidates:
                logger.info(f"No candidates found in {url}")
                return []
            
            # Filter by frequency
            filtered_candidates = await self.filter_candidates_by_frequency(candidates, url)
            
            logger.info(f"Found {len(filtered_candidates)} valid candidates from {url}")
            self.stats.candidates_found += len(filtered_candidates)
            
            # Add links for next depth level if we haven't reached max depth
            if current_depth < self.max_depth and len(self.visited_urls) < self.max_urls:
                links = await self.extract_links_from_content(content, url)
                for link in links[:10]:  # Limit links per page
                    if link not in self.visited_urls and len(self.url_queue) < self.max_urls:
                        self.url_queue.append((link, current_depth + 1))
            
            return filtered_candidates
            
        except Exception as e:
            logger.error(f"Error processing URL {url}: {e}")
            return []
    
    async def harvest_from_url(self, start_url: str) -> dict:
        """Main harvest method"""
        logger.info(f"Starting URL harvest from: {start_url}")
        logger.info(f"Parameters: max_depth={self.max_depth}, max_urls={self.max_urls}, zipf_threshold={self.zipf_threshold}")
        
        # Initialize definition lookup in async context
        async with ComprehensiveDefinitionLookup() as definition_lookup:
            self.definition_lookup = definition_lookup
            
            # Initialize queue with starting URL
            self.url_queue.append((start_url, 0))
            all_candidates = []
            
            while self.url_queue and len(self.visited_urls) < self.max_urls:
                current_url, current_depth = self.url_queue.pop(0)
                
                # Skip if already visited
                if current_url in self.visited_urls:
                    continue
                
                self.visited_urls.add(current_url)
                self.stats.urls_processed += 1
                self.stats.max_depth_reached = max(self.stats.max_depth_reached, current_depth)
                
                # Process this URL
                candidates = await self.process_url(current_url, current_depth)
                
                if candidates:
                    all_candidates.extend(candidates)
                    
                    # Store candidates immediately
                    stored_count = await self.store_candidates(candidates)
                    self.stats.candidates_stored += stored_count
                
                # Rate limiting
                await asyncio.sleep(1)
        
        # Generate summary
        duration = datetime.now() - self.stats.start_time
        
        summary = {
            'start_url': start_url,
            'duration': str(duration),
            'urls_processed': self.stats.urls_processed,
            'urls_successful': self.stats.urls_successful,
            'max_depth_reached': self.stats.max_depth_reached,
            'candidates_found': self.stats.candidates_found,
            'candidates_stored': self.stats.candidates_stored,
            'zipf_threshold': self.zipf_threshold,
            'success_rate': f"{(self.stats.urls_successful/max(1, self.stats.urls_processed))*100:.1f}%"
        }
        
        return summary

async def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(description="URL-Specific Vocabulary Harvester")
    parser.add_argument("url", help="Starting URL to harvest from")
    parser.add_argument("--depth", type=int, default=1, help="Maximum crawl depth (default: 1)")
    parser.add_argument("--max-urls", type=int, default=50, help="Maximum URLs to process (default: 50)")
    parser.add_argument("--zipf-threshold", type=float, default=3.0, help="Maximum zipf frequency score (default: 3.0)")
    parser.add_argument("--verbose", "-v", action="store_true", help="Enable verbose logging")
    
    args = parser.parse_args()
    
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    # Validate URL
    if not args.url.startswith(('http://', 'https://')):
        print("Error: URL must start with http:// or https://")
        sys.exit(1)
    
    # Create harvester
    harvester = URLVocabularyHarvester(
        zipf_threshold=args.zipf_threshold,
        max_depth=args.depth,
        max_urls=args.max_urls
    )
    
    try:
        # Run harvest
        summary = await harvester.harvest_from_url(args.url)
        
        # Display results
        print("\n" + "="*60)
        print("URL VOCABULARY HARVEST COMPLETE")
        print("="*60)
        print(f"Start URL: {summary['start_url']}")
        print(f"Duration: {summary['duration']}")
        print(f"URLs Processed: {summary['urls_processed']}")
        print(f"URLs Successful: {summary['urls_successful']} ({summary['success_rate']})")
        print(f"Max Depth Reached: {summary['max_depth_reached']}")
        print(f"Candidates Found: {summary['candidates_found']}")
        print(f"Candidates Stored: {summary['candidates_stored']}")
        print(f"Zipf Threshold: ≤{summary['zipf_threshold']} (lower = rarer words)")
        
    except KeyboardInterrupt:
        print("\nHarvest interrupted by user")
    except Exception as e:
        print(f"Error during harvest: {e}")
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())