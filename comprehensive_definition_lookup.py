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
from config import get_db_config

logger = logging.getLogger(__name__)

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
                'api_key_required': True,
                'rate_limit': 1.0,  # seconds between calls
                'url_pattern': 'https://www.dictionaryapi.com/api/v3/references/collegiate/json/{term}?key={api_key}'
            },
            'oxford': {
                'tier': 1, 
                'base_reliability': 0.95,
                'api_key_required': True,
                'rate_limit': 1.0,
                'url_pattern': 'https://od-api.oxforddictionaries.com/api/v2/entries/en-us/{term}'
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
                'api_key_required': True,
                'rate_limit': 1.0,
                'url_pattern': 'https://api.wordnik.com/v4/word.json/{term}/definitions?limit=20&api_key={api_key}'
            },
            
            # Tier 3: Community/Wiki sources (moderate reliability)
            'wiktionary': {
                'tier': 3,
                'base_reliability': 0.70,
                'api_key_required': False,
                'rate_limit': 1.0,
                'url_pattern': 'https://en.wiktionary.org/w/api.php?action=parse&format=json&page={term}'
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
                'User-Agent': 'VocabularyDefinitionLookup/1.0 (Educational Research)'
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
                if config['api_key_required'] and not self._has_api_key(source_name):
                    logger.debug(f"Skipping {source_name}: no API key configured")
                    continue
                
                await self._respect_rate_limit(source_name)
                
                definitions = await self._lookup_from_source(term, source_name)
                if definitions:
                    all_definitions.extend(definitions)
                    sources_consulted.append(source_name)
                    logger.debug(f"Found {len(definitions)} definitions from {source_name}")
                
            except Exception as e:
                logger.error(f"Error looking up '{term}' in {source_name}: {e}")
        
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
        elif source_name == 'merriam_webster' and self._has_api_key(source_name):
            return await self._lookup_merriam_webster(term)
        elif source_name == 'oxford' and self._has_api_key(source_name):
            return await self._lookup_oxford(term)
        elif source_name == 'wordnik' and self._has_api_key(source_name):
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
                    return self._parse_free_dictionary_response(data, term)
                else:
                    logger.debug(f"Free Dictionary API returned {response.status} for '{term}'")
        except Exception as e:
            logger.error(f"Free Dictionary API error for '{term}': {e}")
        
        return []
    
    def _parse_free_dictionary_response(self, data: List[Dict], term: str) -> List[Definition]:
        """Parse Free Dictionary API response"""
        definitions = []
        
        for entry in data:
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
        # This is a simplified implementation - Wiktionary parsing is complex
        url = f"https://en.wiktionary.org/w/api.php"
        params = {
            'action': 'parse',
            'format': 'json',
            'page': term,
            'prop': 'wikitext'
        }
        
        try:
            async with self.session.get(url, params=params) as response:
                if response.status == 200:
                    data = await response.json()
                    if 'parse' in data and 'wikitext' in data['parse']:
                        wikitext = data['parse']['wikitext']['*']
                        return self._parse_wiktionary_wikitext(wikitext, term)
        except Exception as e:
            logger.error(f"Wiktionary API error for '{term}': {e}")
        
        return []
    
    def _parse_wiktionary_wikitext(self, wikitext: str, term: str) -> List[Definition]:
        """Parse Wiktionary wikitext (simplified)"""
        definitions = []
        
        # This is a very simplified parser - Wiktionary has complex formatting
        # Look for English section and definition patterns
        if '==English==' in wikitext:
            english_section = wikitext.split('==English==')[1].split('==')[0]
            
            # Extract definitions (very basic pattern matching)
            definition_pattern = r'^#\s*(.+?)(?:\n|$)'
            pos_pattern = r'===\s*(Noun|Verb|Adjective|Adverb)\s*==='
            
            current_pos = 'unknown'
            for line in english_section.split('\n'):
                pos_match = re.search(pos_pattern, line, re.IGNORECASE)
                if pos_match:
                    current_pos = pos_match.group(1).lower()
                
                def_match = re.search(definition_pattern, line)
                if def_match:
                    definition_text = def_match.group(1).strip()
                    # Clean up wikitext markup
                    definition_text = re.sub(r'\[\[([^|]+)\|([^\]]+)\]\]', r'\2', definition_text)
                    definition_text = re.sub(r'\[\[([^\]]+)\]\]', r'\1', definition_text)
                    definition_text = re.sub(r'\{\{[^}]+\}\}', '', definition_text)
                    
                    if definition_text and len(definition_text) > 10:
                        definitions.append(Definition(
                            text=definition_text,
                            part_of_speech=current_pos,
                            source='wiktionary',
                            source_tier=3,
                            reliability_score=self.source_config['wiktionary']['base_reliability']
                        ))
        
        return definitions
    
    async def _lookup_cambridge(self, term: str) -> List[Definition]:
        """Lookup from Cambridge Dictionary (web scraping)"""
        url = f"https://dictionary.cambridge.org/dictionary/english/{quote(term)}"
        
        try:
            async with self.session.get(url) as response:
                if response.status == 200:
                    html = await response.text()
                    return self._parse_cambridge_html(html, term)
        except Exception as e:
            logger.error(f"Cambridge Dictionary error for '{term}': {e}")
        
        return []
    
    def _parse_cambridge_html(self, html: str, term: str) -> List[Definition]:
        """Parse Cambridge Dictionary HTML"""
        definitions = []
        
        try:
            soup = BeautifulSoup(html, 'html.parser')
            
            # Find definition blocks
            def_blocks = soup.find_all('div', class_='def-block')
            
            for block in def_blocks:
                # Extract part of speech
                pos_element = block.find('span', class_='pos')
                pos = pos_element.text.strip() if pos_element else 'unknown'
                
                # Extract definition
                def_element = block.find('div', class_='def')
                if def_element:
                    definition_text = def_element.get_text().strip()
                    
                    # Extract examples
                    examples = []
                    example_elements = block.find_all('span', class_='eg')
                    for ex_elem in example_elements:
                        examples.append(ex_elem.get_text().strip())
                    
                    definitions.append(Definition(
                        text=definition_text,
                        part_of_speech=pos,
                        source='cambridge',
                        source_tier=1,
                        reliability_score=self.source_config['cambridge']['base_reliability'],
                        examples=examples
                    ))
        
        except Exception as e:
            logger.error(f"Error parsing Cambridge HTML for '{term}': {e}")
        
        return definitions
    
    async def _lookup_onelook(self, term: str) -> List[Definition]:
        """Lookup from OneLook (aggregator)"""
        # OneLook is primarily a search engine, not a definition provider
        # This would require more complex implementation
        return []
    
    async def _lookup_merriam_webster(self, term: str) -> List[Definition]:
        """Lookup from Merriam-Webster API (if API key available)"""
        # Placeholder for premium API
        return []
    
    async def _lookup_oxford(self, term: str) -> List[Definition]:
        """Lookup from Oxford API (if API key available)"""
        # Placeholder for premium API
        return []
    
    async def _lookup_wordnik(self, term: str) -> List[Definition]:
        """Lookup from Wordnik API (if API key available)"""
        # Placeholder for API implementation
        return []
    
    def _extract_pronunciation(self, entry: Dict) -> Optional[str]:
        """Extract pronunciation from dictionary entry"""
        phonetics = entry.get('phonetics', [])
        for phonetic in phonetics:
            if phonetic.get('text'):
                return phonetic['text']
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