#!/usr/bin/env python3
"""
Wiktionary Harvester - Extract rare and archaic vocabulary from Wiktionary
"""

import requests
import json
import time
import re
import mysql.connector
from typing import Dict, List, Optional, Tuple, Set
from dataclasses import dataclass
from datetime import datetime, date
from urllib.parse import quote, unquote
import logging
import sys
import os
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
sys.path.insert(0, parent_dir)
from core.secure_config import get_db_config
from core.english_word_validator import validate_english_word
from core.vocabulary_deduplicator import filter_duplicate_candidates, get_existing_terms
from core.comprehensive_definition_lookup import enhance_candidate_with_definitions
import asyncio

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@dataclass
class WiktionaryEntry:
    term: str
    part_of_speech: str
    definition: str
    etymology: Optional[str]
    tags: List[str]  # archaic, obsolete, etc.
    context: Optional[str]
    source_url: str

class WiktionaryHarvester:
    """Client for fetching data from Wiktionary APIs"""
    
    def __init__(self, delay: float = 0.1):
        self.api_url = "https://en.wiktionary.org/w/api.php"
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'VocabularyHarvester/1.0 (Educational/Personal Use)'
        })
        self.delay = delay  # Rate limiting
        self.parser = WiktionaryParser()
        
    def get_category_members(self, category: str, limit: int = 500) -> List[str]:
        """Get list of page titles in a specific category"""
        logger.info(f"Fetching members of category: {category}")
        
        params = {
            'action': 'query',
            'list': 'categorymembers',
            'cmtitle': f'Category:{category}',
            'cmlimit': min(limit, 500),  # API maximum
            'format': 'json',
            'continue': ''
        }
        
        titles = []
        
        while True:
            try:
                time.sleep(self.delay)
                response = self.session.get(self.api_url, params=params, timeout=10)
                response.raise_for_status()
                
                data = response.json()
                
                # Extract page titles
                if 'query' in data and 'categorymembers' in data['query']:
                    batch_titles = [page['title'] for page in data['query']['categorymembers']]
                    titles.extend(batch_titles)
                    logger.info(f"Retrieved {len(batch_titles)} titles from {category}")
                
                # Check if there are more results
                if 'continue' not in data or len(titles) >= limit:
                    break
                    
                # Update continuation parameters
                params.update(data['continue'])
                
            except Exception as e:
                logger.error(f"Error fetching category {category}: {e}")
                break
        
        return titles[:limit]
    
    def get_page_content(self, title: str) -> Optional[str]:
        """Fetch raw wikitext content for a page"""
        params = {
            'action': 'query',
            'titles': title,
            'prop': 'revisions',
            'rvprop': 'content',
            'format': 'json'
        }
        
        try:
            time.sleep(self.delay)
            response = self.session.get(self.api_url, params=params, timeout=10)
            response.raise_for_status()
            
            data = response.json()
            
            if 'query' in data and 'pages' in data['query']:
                pages = data['query']['pages']
                for page_id, page_data in pages.items():
                    if 'revisions' in page_data and page_data['revisions']:
                        return page_data['revisions'][0]['*']
            
            return None
            
        except Exception as e:
            logger.error(f"Error fetching page {title}: {e}")
            return None
    
    async def harvest_archaic_terms(self, limit: int = 15) -> List[WiktionaryEntry]:
        """Harvest archaic terms from Wiktionary for testing"""
        try:
            # Get archaic terms from category
            categories = ['English archaic terms', 'English obsolete terms']
            all_entries = []
            
            for category in categories:
                # Get a few page titles
                titles = self.get_category_members(category, limit=max(5, limit//2))
                
                for title in titles[:limit]:
                    # Get page content
                    content = self.get_page_content(title)
                    if content:
                        # Parse entries
                        entries = self.parser.parse_entry(title, content)
                        all_entries.extend(entries)
                        
                        # Stop if we have enough entries
                        if len(all_entries) >= limit:
                            break
                
                if len(all_entries) >= limit:
                    break
            
            return all_entries[:limit]
            
        except Exception as e:
            logger.error(f"Error harvesting archaic terms: {e}")
            return []

class WiktionaryParser:
    """Parse Wiktionary wikitext to extract structured data"""
    
    def __init__(self):
        # Regex patterns for parsing wikitext
        self.etymology_pattern = re.compile(r'===\s*Etymology\s*===\s*\n(.*?)(?=\n===|\n==|\Z)', re.DOTALL | re.IGNORECASE)
        self.pos_pattern = re.compile(r'===\s*(Noun|Verb|Adjective|Adverb|Preposition|Conjunction|Interjection|Phrase|Expression|Determiner|Particle|Exclamation)\s*===', re.IGNORECASE)
        self.definition_pattern = re.compile(r'^#\s*(.+?)$', re.MULTILINE)
        
        # Patterns for archaic/obsolete tags
        self.tag_patterns = {
            'direct': re.compile(r'\{\{\s*(archaic|obsolete|dated|historical)\s*\}\}', re.IGNORECASE),
            'label': re.compile(r'\{\{\s*label\s*\|\s*en\s*\|[^}]*?(archaic|obsolete|dated|historical)', re.IGNORECASE),
            'lb': re.compile(r'\{\{\s*lb\s*\|\s*en\s*\|[^}]*?(archaic|obsolete|dated|historical)', re.IGNORECASE),
            'context': re.compile(r'\{\{\s*context\s*\|\s*en\s*\|[^}]*?(archaic|obsolete|dated|historical)', re.IGNORECASE),
            'term-label': re.compile(r'\{\{\s*term-label\s*\|\s*en\s*\|[^}]*?(archaic|obsolete|dated|historical)', re.IGNORECASE),
            'qualifier': re.compile(r'\{\{\s*qualifier\s*\|[^}]*?(archaic|obsolete|dated|historical)', re.IGNORECASE)
        }
        
    def parse_entry(self, title: str, wikitext: str) -> List[WiktionaryEntry]:
        """Parse Wikitext and extract structured entries"""
        if not wikitext:
            return []
            
        entries = []
        
        # Find English section
        english_section = self._extract_english_section(wikitext)
        if not english_section:
            return []
        
        # Extract etymology
        etymology = self._extract_etymology(english_section)
        
        # Find all part-of-speech sections
        pos_sections = self._split_by_pos(english_section)
        
        for pos, content in pos_sections:
            definitions = self._extract_definitions(content)
            
            # Extract tags from the entire POS section (not just individual definitions)
            section_tags = self._extract_tags(content)
            
            for definition in definitions:
                # Check for target tags in both definition and section
                definition_tags = self._extract_tags(definition)
                all_tags = list(set(section_tags + definition_tags))
                
                if self._is_target_word(definition, all_tags) or section_tags:  # Accept if section has archaic tags
                    entry = WiktionaryEntry(
                        term=title.lower(),
                        part_of_speech=pos.lower(),
                        definition=self._clean_definition(definition),
                        etymology=etymology,
                        tags=all_tags,
                        context=self._extract_context(definition),
                        source_url=f"https://en.wiktionary.org/wiki/{quote(title)}"
                    )
                    entries.append(entry)
        
        return entries
    
    def _extract_english_section(self, wikitext: str) -> Optional[str]:
        """Extract the English language section from wikitext"""
        english_match = re.search(r'==\s*English\s*==\s*\n(.*?)(?=\n==\s*[^=]|\Z)', wikitext, re.DOTALL | re.IGNORECASE)
        if english_match:
            return english_match.group(1)
        return None
    
    def _extract_etymology(self, english_text: str) -> Optional[str]:
        """Extract etymology information"""
        match = self.etymology_pattern.search(english_text)
        if match:
            etymology = match.group(1).strip()
            # Clean up basic wikitext
            etymology = re.sub(r'\[\[([^|]+\|)?([^\]]+)\]\]', r'\2', etymology)
            etymology = re.sub(r'\{\{[^}]+\}\}', '', etymology)
            return etymology[:500]  # Truncate for storage
        return None
    
    def _split_by_pos(self, english_text: str) -> List[Tuple[str, str]]:
        """Split text by part-of-speech sections"""
        sections = []
        pos_matches = list(self.pos_pattern.finditer(english_text))
        
        for i, match in enumerate(pos_matches):
            pos = match.group(1)
            start = match.end()
            
            # Find end of this section
            if i + 1 < len(pos_matches):
                end = pos_matches[i + 1].start()
            else:
                end = len(english_text)
            
            content = english_text[start:end]
            sections.append((pos, content))
        
        return sections
    
    def _extract_definitions(self, pos_content: str) -> List[str]:
        """Extract numbered definitions from a part-of-speech section"""
        definitions = []
        
        for match in self.definition_pattern.finditer(pos_content):
            definition = match.group(1).strip()
            if definition and not definition.startswith('#'):  # Skip sub-definitions for now
                definitions.append(definition)
        
        return definitions
    
    def _extract_tags(self, definition_text: str) -> List[str]:
        """Extract archaic, obsolete, etc. tags from definition"""
        tags = []
        
        for tag_type, pattern in self.tag_patterns.items():
            matches = pattern.findall(definition_text)
            for match in matches:
                if isinstance(match, tuple):
                    match = match[-1]  # Get last group from tuple
                elif isinstance(match, list):
                    match = match[-1]  # Get last item from list
                    
                match = match.lower().strip()
                if match and match not in tags:
                    tags.append(match)
        
        return tags
    
    def _extract_context(self, definition_text: str) -> Optional[str]:
        """Extract usage context or examples"""
        # Look for quoted examples
        example_match = re.search(r"''([^']+)''", definition_text)
        if example_match:
            return example_match.group(1)
        
        # Look for parenthetical context
        context_match = re.search(r'\(([^)]+)\)', definition_text)
        if context_match:
            context = context_match.group(1)
            if len(context) < 100:  # Reasonable context length
                return context
        
        return None
    
    def _is_target_word(self, definition: str, tags: List[str]) -> bool:
        """Determine if this word meets harvesting criteria"""
        target_tags = {'archaic', 'obsolete', 'dated', 'historical'}
        return bool(set(tags).intersection(target_tags))
    
    def _clean_definition(self, definition: str) -> str:
        """Clean wikitext markup from definition"""
        # Remove wikilinks but keep text
        cleaned = re.sub(r'\[\[([^|]+\|)?([^\]]+)\]\]', r'\2', definition)
        
        # Remove templates
        cleaned = re.sub(r'\{\{[^}]+\}\}', '', cleaned)
        
        # Remove HTML tags
        cleaned = re.sub(r'<[^>]+>', '', cleaned)
        
        # Clean up whitespace
        cleaned = re.sub(r'\s+', ' ', cleaned).strip()
        
        return cleaned

class UtilityScorer:
    """Score words for utility/interest in vocabulary building"""
    
    def __init__(self, existing_words: Set[str]):
        self.existing_words = existing_words
        self.common_prefixes = {
            'un-', 're-', 'pre-', 'dis-', 'over-', 'under-', 'anti-', 'co-', 'de-', 'ex-'
        }
        self.common_suffixes = {
            '-tion', '-sion', '-ness', '-ment', '-able', '-ible', '-ful', '-less', 
            '-ous', '-ious', '-ly', '-er', '-est', '-ing', '-ed'
        }
    
    def score_word(self, entry: WiktionaryEntry) -> float:
        """Score word utility from 0-10"""
        score = 5.0  # Base score
        
        # Already exists penalty
        if entry.term in self.existing_words:
            return 0.0  # Skip completely
        
        # Length preferences (sweet spot 6-12 characters)
        length = len(entry.term)
        if 6 <= length <= 12:
            score += 1.0
        elif length < 4:
            score -= 2.0  # Too short
        elif length > 15:
            score -= 1.5  # Too long
        
        # Etymology richness bonus
        if entry.etymology and len(entry.etymology) > 50:
            score += 1.0
        
        # Part of speech preferences
        preferred_pos = {'noun', 'verb', 'adjective', 'adverb'}
        if entry.part_of_speech in preferred_pos:
            score += 1.0
        
        # Context availability
        if entry.context:
            score += 0.5
        
        # Morphological accessibility (recognizable roots)
        if self._has_recognizable_morphology(entry.term):
            score += 1.0
        
        # Tag-based scoring
        tag_scores = {
            'archaic': 1.5,    # Sweet spot for practical rarity
            'dated': 1.2,      # Less rare but still interesting
            'historical': 1.0,  # Context-dependent usefulness
            'obsolete': 0.3,   # Often too obscure for practical use
        }
        
        for tag in entry.tags:
            score += tag_scores.get(tag, 0)
        
        # Definition quality
        if entry.definition and len(entry.definition) > 30:
            score += 0.5
        
        # Penalize very technical or specialized terms
        technical_indicators = ['chemistry', 'physics', 'biology', 'anatomy', 'botany', 'medicine']
        if any(indicator in entry.definition.lower() for indicator in technical_indicators):
            score -= 0.5
        
        return min(10.0, max(0.0, score))
    
    def _has_recognizable_morphology(self, word: str) -> bool:
        """Check if word has recognizable prefixes/suffixes"""
        word_lower = word.lower()
        
        has_prefix = any(word_lower.startswith(prefix[:-1]) for prefix in self.common_prefixes)
        has_suffix = any(word_lower.endswith(suffix[1:]) for suffix in self.common_suffixes)
        
        return has_prefix or has_suffix

class HarvesterDatabase:
    """Database interface for harvester operations"""
    
    def __init__(self):
        self.db_config = get_db_config()
    
    def get_existing_terms(self) -> Set[str]:
        """Get all existing terms to avoid duplicates"""
        try:
            conn = mysql.connector.connect(**self.db_config)
            cursor = conn.cursor()
            
            # Get from main vocabulary
            cursor.execute("SELECT LOWER(term) FROM defined")
            existing = {row[0] for row in cursor.fetchall()}
            
            # Get from candidates
            cursor.execute("SELECT LOWER(term) FROM candidate_words")
            candidates = {row[0] for row in cursor.fetchall()}
            
            return existing.union(candidates)
            
        except Exception as e:
            logger.error(f"Database error getting existing terms: {e}")
            return set()
        finally:
            if 'conn' in locals() and conn.is_connected():
                cursor.close()
                conn.close()
    
    async def insert_candidates(self, entries: List[WiktionaryEntry], scores: List[float]) -> int:
        """Insert candidate words into review queue"""
        if not entries:
            return 0
            
        try:
            conn = mysql.connector.connect(**self.db_config)
            cursor = conn.cursor()
            
            insert_query = """
            INSERT INTO candidate_words 
            (term, source_type, source_reference, context_snippet, raw_definition, 
             etymology_preview, part_of_speech, utility_score, rarity_indicators, date_discovered)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
            utility_score = GREATEST(utility_score, VALUES(utility_score)),
            updated_at = CURRENT_TIMESTAMP
            """
            
            inserted_count = 0
            rejected_count = 0
            
            for entry, score in zip(entries, scores):
                # Validate English word before storing
                is_english, reason = validate_english_word(entry.term)
                
                if not is_english:
                    logger.debug(f"Rejected non-English word '{entry.term}': {reason}")
                    rejected_count += 1
                    continue
                
                # Convert WiktionaryEntry to candidate format for enhancement
                candidate = {
                    'term': entry.term,
                    'part_of_speech': entry.part_of_speech,
                    'context': entry.context,
                    'source_metadata': {
                        'source_url': entry.source_url,
                        'tags': entry.tags
                    }
                }
                
                # Enhance candidate with comprehensive definitions
                enhanced_candidate = await enhance_candidate_with_definitions(candidate)
                
                # Create enhanced rarity data including definitions
                rarity_data = json.dumps({
                    'tags': entry.tags,
                    'source': 'wiktionary',
                    'has_etymology': bool(entry.etymology),
                    'has_context': bool(entry.context),
                    'validation_reason': reason,
                    'definitions': enhanced_candidate.get('definitions', {}),
                    'definition_reliability': enhanced_candidate.get('definition_reliability', 0.0)
                })
                
                # Use enhanced definitions in raw_definition field if available
                enhanced_definitions = enhanced_candidate.get('definitions', {})
                if enhanced_definitions:
                    definition_text = []
                    for pos, defs in enhanced_definitions.items():
                        if defs:
                            definition_text.append(f"{pos}: {defs[0].get('definition', '')}")
                    raw_definition = "; ".join(definition_text) if definition_text else entry.definition
                else:
                    raw_definition = entry.definition
                
                try:
                    cursor.execute(insert_query, (
                        entry.term,
                        'wiktionary',
                        entry.source_url,
                        entry.context,
                        raw_definition,
                        entry.etymology,
                        entry.part_of_speech,
                        score,
                        rarity_data,
                        date.today()
                    ))
                    inserted_count += 1
                except mysql.connector.IntegrityError:
                    # Duplicate entry, skip
                    continue
            
            conn.commit()
            logger.info(f"Successfully inserted {inserted_count} candidate words (rejected {rejected_count} non-English words)")
            return inserted_count
            
        except Exception as e:
            logger.error(f"Database error inserting candidates: {e}")
            return 0
        finally:
            if 'conn' in locals() and conn.is_connected():
                cursor.close()
                conn.close()
    
    def log_session(self, source_type: str, categories: List[str], 
                   processed: int, found: int, accepted: int) -> None:
        """Log harvesting session results"""
        try:
            conn = mysql.connector.connect(**self.db_config)
            cursor = conn.cursor()
            
            cursor.execute("""
                INSERT INTO harvesting_sessions 
                (source_type, session_end, total_processed, candidates_found, 
                 candidates_accepted, categories_processed, status)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
            """, (
                source_type, datetime.now(), processed, found, accepted,
                json.dumps(categories), 'completed'
            ))
            
            conn.commit()
            
        except Exception as e:
            logger.error(f"Error logging session: {e}")
        finally:
            if 'conn' in locals() and conn.is_connected():
                cursor.close()
                conn.close()

class VocabularyHarvester:
    """Main orchestrator for vocabulary harvesting"""
    
    def __init__(self):
        self.wiktionary = WiktionaryHarvester()
        self.parser = WiktionaryParser()
        self.database = HarvesterDatabase()
        
        # Load existing words for deduplication (use centralized system)
        existing_words = get_existing_terms()
        self.scorer = UtilityScorer(existing_words)
        logger.info(f"Loaded {len(existing_words)} existing terms for deduplication")
    
    async def harvest_wiktionary_batch(self, categories: List[str], batch_size: int = 100,
                                     min_score: float = 3.0) -> Dict[str, int]:
        """Main harvesting workflow"""
        logger.info(f"Starting harvest of categories: {categories}")
        
        all_candidates = []
        total_processed = 0
        
        for category in categories:
            logger.info(f"Processing category: {category}")
            page_titles = self.wiktionary.get_category_members(category, batch_size)
            
            for i, title in enumerate(page_titles):
                if i % 10 == 0:
                    logger.info(f"Processing {i+1}/{len(page_titles)}: {title}")
                
                # Get page content
                content = self.wiktionary.get_page_content(title)
                if not content:
                    continue
                
                # Parse entries
                entries = self.parser.parse_entry(title, content)
                total_processed += 1
                
                # Score and filter entries
                for entry in entries:
                    score = self.scorer.score_word(entry)
                    if score >= min_score:
                        all_candidates.append((entry, score))
        
        # Sort by score and filter duplicates before inserting to database
        all_candidates.sort(key=lambda x: x[1], reverse=True)
        entries, scores = zip(*all_candidates) if all_candidates else ([], [])
        
        candidates_found = len(entries)
        candidates_accepted = 0
        
        if entries:
            # Filter duplicates using centralized system
            # Convert WiktionaryEntry objects to dict format for deduplicator
            candidate_dicts = []
            for entry in entries:
                candidate_dicts.append({
                    'term': entry.term,
                    'part_of_speech': entry.part_of_speech,
                    'definition': entry.definition,
                    'etymology': entry.etymology,
                    'tags': entry.tags,
                    'context': entry.context,
                    'source_url': entry.source_url
                })
            
            filtered_dicts, dedup_stats = filter_duplicate_candidates(candidate_dicts)
            logger.info(f"Deduplication: {dedup_stats['unique']}/{dedup_stats['total']} candidates are unique "
                       f"(filtered {dedup_stats['duplicates']} duplicates)")
            
            # Convert back to WiktionaryEntry objects and matching scores
            filtered_entries = []
            filtered_scores = []
            
            filtered_terms = {d['term'] for d in filtered_dicts}
            for entry, score in zip(entries, scores):
                if entry.term in filtered_terms:
                    filtered_entries.append(entry)
                    filtered_scores.append(score)
            
            if filtered_entries:
                candidates_accepted = await self.database.insert_candidates(filtered_entries, filtered_scores)
            else:
                logger.info("No candidates remaining after deduplication")
        
        # Log session
        self.database.log_session(
            'wiktionary', categories, total_processed, 
            candidates_found, candidates_accepted
        )
        
        logger.info(f"Harvest complete: {total_processed} processed, "
                   f"{candidates_found} candidates, {candidates_accepted} accepted")
        
        return {
            'processed': total_processed,
            'candidates_found': candidates_found,
            'candidates_accepted': candidates_accepted
        }

# CLI Interface
async def main():
    """Command line interface for the harvester"""
    import argparse
    
    parser = argparse.ArgumentParser(description='Wiktionary Vocabulary Harvester')
    parser.add_argument('--categories', nargs='+', 
                       default=['English archaic terms', 'English obsolete terms'],
                       help='Wiktionary categories to harvest')
    parser.add_argument('--batch-size', type=int, default=50,
                       help='Number of pages to process per category')
    parser.add_argument('--min-score', type=float, default=3.0,
                       help='Minimum utility score to accept candidates')
    parser.add_argument('--delay', type=float, default=0.1,
                       help='Delay between API calls (seconds)')
    
    args = parser.parse_args()
    
    # Initialize harvester
    harvester = VocabularyHarvester()
    harvester.wiktionary.delay = args.delay
    
    # Run harvest
    results = await harvester.harvest_wiktionary_batch(
        categories=args.categories,
        batch_size=args.batch_size,
        min_score=args.min_score
    )
    
    print(f"\nHarvesting Results:")
    print(f"Pages processed: {results['processed']}")
    print(f"Candidates found: {results['candidates_found']}")
    print(f"Candidates accepted: {results['candidates_accepted']}")
    
    if results['candidates_accepted'] > 0:
        print(f"\nTo review candidates, run:")
        print(f"python wiktionary_reviewer.py")

if __name__ == "__main__":
    asyncio.run(main())