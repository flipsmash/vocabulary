#!/usr/bin/env python3
"""
Multi-Source Vocabulary Harvester Framework
Orchestrates vocabulary collection from diverse sources
"""

import asyncio
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Set, AsyncGenerator, Tuple
from enum import Enum
import aiohttp
import json
import time
import random

from universal_vocabulary_extractor import UniversalVocabularyExtractor, VocabularyCandidate
from frequency_analysis_system import FrequencyCollectionManager
from config import get_db_config
import mysql.connector
from mysql.connector import Error


class SourceType(Enum):
    """Available source types for vocabulary harvesting"""
    WIKTIONARY = "wiktionary"
    ARXIV = "arxiv"
    PUBMED = "pubmed"
    GUTENBERG = "gutenberg"
    NEWS_API = "news_api"
    WIKIPEDIA = "wikipedia"
    ACADEMIC_JOURNALS = "academic_journals"
    LITERARY_CLASSICS = "literary_classics"
    HISTORICAL_DOCUMENTS = "historical_documents"


@dataclass
class HarvestConfig:
    """Configuration for harvesting operations"""
    source_type: SourceType
    enabled: bool = True
    rate_limit_delay: float = 1.0
    batch_size: int = 50
    max_results: int = 1000
    quality_threshold: float = 7.0
    source_specific_params: Dict = field(default_factory=dict)
    
    # Source priorities (higher = more authoritative)
    priorities = {
        SourceType.WIKTIONARY: 9.0,
        SourceType.ACADEMIC_JOURNALS: 8.5,
        SourceType.ARXIV: 8.0,
        SourceType.PUBMED: 8.0,
        SourceType.WIKIPEDIA: 7.0,
        SourceType.LITERARY_CLASSICS: 7.5,
        SourceType.HISTORICAL_DOCUMENTS: 7.0,
        SourceType.NEWS_API: 6.0,
        SourceType.GUTENBERG: 6.5
    }
    
    @property
    def source_priority(self) -> float:
        return self.priorities.get(self.source_type, 5.0)


@dataclass
class HarvestSession:
    """Tracks a harvesting session"""
    session_id: str
    start_time: datetime
    sources: List[SourceType]
    total_processed: int = 0
    candidates_found: int = 0
    quality_candidates: int = 0
    errors: List[str] = field(default_factory=list)
    status: str = "running"
    end_time: Optional[datetime] = None
    
    @property
    def duration(self) -> Optional[timedelta]:
        if self.end_time:
            return self.end_time - self.start_time
        return datetime.now() - self.start_time
    
    @property
    def success_rate(self) -> float:
        if self.total_processed == 0:
            return 0.0
        return (self.candidates_found / self.total_processed) * 100


class VocabularySource(ABC):
    """Abstract base class for vocabulary sources"""
    
    def __init__(self, config: HarvestConfig):
        self.config = config
        self.session = None
        self.logger = logging.getLogger(f"{self.__class__.__name__}")
    
    @abstractmethod
    async def initialize(self) -> bool:
        """Initialize the source (connect, authenticate, etc.)"""
        pass
    
    @abstractmethod
    async def harvest_batch(self, query: str, limit: int) -> AsyncGenerator[str, None]:
        """Harvest a batch of text content from this source"""
        pass
    
    @abstractmethod
    async def get_metadata(self, content: str) -> Dict:
        """Extract metadata from content (title, author, date, etc.)"""
        pass
    
    async def cleanup(self):
        """Clean up resources"""
        if self.session:
            await self.session.close()
    
    def apply_rate_limiting(self):
        """Apply rate limiting between requests"""
        if self.config.rate_limit_delay > 0:
            time.sleep(self.config.rate_limit_delay)


class WikipediaSource(VocabularySource):
    """Wikipedia article harvester"""
    
    async def initialize(self) -> bool:
        self.session = aiohttp.ClientSession(
            headers={'User-Agent': 'VocabularyHarvester/1.0 (Educational)'}
        )
        return True
    
    async def harvest_batch(self, query: str, limit: int) -> AsyncGenerator[str, None]:
        """Harvest Wikipedia articles related to query"""
        search_url = "https://en.wikipedia.org/api/rest_v1/page/search"
        
        try:
            params = {
                'q': query,
                'limit': min(limit, 50)
            }
            
            async with self.session.get(search_url, params=params) as response:
                if response.status == 200:
                    data = await response.json()
                    
                    for page in data.get('pages', []):
                        content_url = f"https://en.wikipedia.org/api/rest_v1/page/summary/{page['key']}"
                        
                        try:
                            async with self.session.get(content_url) as content_response:
                                if content_response.status == 200:
                                    content_data = await content_response.json()
                                    extract = content_data.get('extract', '')
                                    
                                    if len(extract) > 100:  # Meaningful content
                                        yield extract
                                        
                                        self.apply_rate_limiting()
                                        
                        except Exception as e:
                            self.logger.warning(f"Error fetching Wikipedia content: {e}")
                            continue
                            
        except Exception as e:
            self.logger.error(f"Wikipedia search error: {e}")
    
    async def get_metadata(self, content: str) -> Dict:
        return {
            'source': 'wikipedia',
            'source_type': 'wikipedia',
            'domain': 'encyclopedia',
            'reliability': 7.0
        }


class ArxivSource(VocabularySource):
    """ArXiv academic paper harvester"""
    
    async def initialize(self) -> bool:
        self.session = aiohttp.ClientSession(
            headers={'User-Agent': 'VocabularyHarvester/1.0 (Educational)'}
        )
        return True
    
    async def harvest_batch(self, query: str, limit: int) -> AsyncGenerator[str, None]:
        """Harvest ArXiv paper abstracts"""
        search_url = "http://export.arxiv.org/api/query"
        
        try:
            params = {
                'search_query': f'all:{query}',
                'start': 0,
                'max_results': min(limit, 100),
                'sortBy': 'relevance',
                'sortOrder': 'descending'
            }
            
            async with self.session.get(search_url, params=params) as response:
                if response.status == 200:
                    xml_content = await response.text()
                    
                    # Simple XML parsing for abstracts
                    import xml.etree.ElementTree as ET
                    try:
                        root = ET.fromstring(xml_content)
                        
                        for entry in root.findall('.//{http://www.w3.org/2005/Atom}entry'):
                            summary = entry.find('.//{http://www.w3.org/2005/Atom}summary')
                            if summary is not None and summary.text:
                                abstract_text = summary.text.strip()
                                if len(abstract_text) > 200:  # Meaningful abstract
                                    yield abstract_text
                                    
                                    self.apply_rate_limiting()
                    
                    except ET.ParseError as e:
                        self.logger.error(f"ArXiv XML parsing error: {e}")
                        
        except Exception as e:
            self.logger.error(f"ArXiv search error: {e}")
    
    async def get_metadata(self, content: str) -> Dict:
        return {
            'source': 'arxiv',
            'source_type': 'arxiv',
            'domain': 'academic',
            'reliability': 8.0
        }


class NewsSource(VocabularySource):
    """News article harvester (requires API key)"""
    
    async def initialize(self) -> bool:
        # For demo purposes, we'll simulate news content
        self.session = aiohttp.ClientSession()
        return True
    
    async def harvest_batch(self, query: str, limit: int) -> AsyncGenerator[str, None]:
        """Simulate news article harvesting"""
        # In real implementation, this would use News API or similar
        sample_articles = [
            "Recent advancements in quantum computing have demonstrated unprecedented computational capabilities, with researchers achieving quantum supremacy in specific algorithmic domains.",
            "The efficacy of novel pharmaceutical interventions continues to be evaluated through rigorous clinical trials, with particular emphasis on bioavailability and therapeutic windows.",
            "Contemporary geopolitical developments have elucidated the complexities inherent in international diplomatic negotiations and multilateral treaty frameworks."
        ]
        
        for i, article in enumerate(sample_articles):
            if i >= limit:
                break
            yield article
            self.apply_rate_limiting()
    
    async def get_metadata(self, content: str) -> Dict:
        return {
            'source': 'news',
            'source_type': 'news_api',
            'domain': 'journalism',
            'reliability': 6.0
        }


class MultiSourceHarvester:
    """Main orchestrator for multi-source vocabulary harvesting"""
    
    def __init__(self):
        self.db_config = get_db_config()
        self.extractor = UniversalVocabularyExtractor()
        self.frequency_analyzer = FrequencyCollectionManager(self.db_config)
        self.sources: Dict[SourceType, VocabularySource] = {}
        self.logger = logging.getLogger(__name__)
        
        # Register available sources
        self.source_classes = {
            SourceType.WIKIPEDIA: WikipediaSource,
            SourceType.ARXIV: ArxivSource,
            SourceType.NEWS_API: NewsSource,
        }
    
    def register_source(self, source_type: SourceType, source_class: type):
        """Register a new source type"""
        self.source_classes[source_type] = source_class
    
    async def initialize_sources(self, configs: List[HarvestConfig]) -> List[SourceType]:
        """Initialize all configured sources"""
        initialized_sources = []
        
        for config in configs:
            if config.enabled and config.source_type in self.source_classes:
                try:
                    source_class = self.source_classes[config.source_type]
                    source = source_class(config)
                    
                    if await source.initialize():
                        self.sources[config.source_type] = source
                        initialized_sources.append(config.source_type)
                        self.logger.info(f"Initialized source: {config.source_type.value}")
                    else:
                        self.logger.warning(f"Failed to initialize: {config.source_type.value}")
                        
                except Exception as e:
                    self.logger.error(f"Error initializing {config.source_type.value}: {e}")
        
        return initialized_sources
    
    async def harvest_from_sources(
        self, 
        query: str, 
        session: HarvestSession,
        max_per_source: int = 20
    ) -> List[VocabularyCandidate]:
        """Harvest vocabulary candidates from all sources"""
        all_candidates = []
        
        # Collect content from all sources
        source_content = {}
        
        for source_type, source in self.sources.items():
            try:
                self.logger.info(f"Harvesting from {source_type.value}...")
                content_list = []
                
                async for content in source.harvest_batch(query, max_per_source):
                    content_list.append(content)
                    session.total_processed += 1
                
                source_content[source_type] = content_list
                self.logger.info(f"Collected {len(content_list)} items from {source_type.value}")
                
            except Exception as e:
                error_msg = f"Error harvesting from {source_type.value}: {e}"
                self.logger.error(error_msg)
                session.errors.append(error_msg)
        
        # Extract candidates from collected content
        for source_type, contents in source_content.items():
            source_config = self.sources[source_type].config
            
            for content in contents:
                try:
                    # Extract vocabulary from content
                    extracted_candidates = self.extractor.extract_candidates(content)
                    
                    # Add source metadata
                    metadata = await self.sources[source_type].get_metadata(content)
                    
                    for candidate in extracted_candidates:
                        # Enhance candidate with source information
                        candidate.source_metadata.update(metadata)
                        candidate.source_metadata['source_type'] = source_type.value
                        
                        # Adjust score based on source reliability
                        reliability_factor = metadata.get('reliability', 5.0) / 10.0
                        adjusted_score = candidate.preliminary_score * reliability_factor
                        candidate.preliminary_score = adjusted_score
                        
                        # Apply quality threshold
                        if adjusted_score >= 7.0:  # Quality threshold
                            all_candidates.append(candidate)
                            session.candidates_found += 1
                            
                            if adjusted_score >= 9.0:
                                session.quality_candidates += 1
                
                except Exception as e:
                    error_msg = f"Error extracting from {source_type.value} content: {e}"
                    self.logger.warning(error_msg)
                    session.errors.append(error_msg)
        
        # Remove duplicates and sort by quality
        unique_candidates = self._deduplicate_candidates(all_candidates)
        unique_candidates.sort(key=lambda x: x.preliminary_score, reverse=True)
        
        return unique_candidates
    
    def _deduplicate_candidates(self, candidates: List[VocabularyCandidate]) -> List[VocabularyCandidate]:
        """Remove duplicate candidates, keeping the highest scored version"""
        seen = {}
        
        for candidate in candidates:
            key = candidate.term.lower()
            
            if key not in seen or candidate.preliminary_score > seen[key].preliminary_score:
                seen[key] = candidate
        
        return list(seen.values())
    
    async def store_candidates(self, candidates: List[VocabularyCandidate], session_id: str):
        """Store candidates in the database"""
        if not candidates:
            return
        
        try:
            conn = mysql.connector.connect(**self.db_config)
            cursor = conn.cursor()
            
            # Prepare batch insert  
            insert_query = """
                INSERT INTO candidate_words 
                (term, source_type, part_of_speech, utility_score, rarity_indicators,
                 context_snippet, raw_definition, etymology_preview, date_discovered)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """
            
            values = []
            for candidate in candidates:
                source_type = candidate.source_metadata.get('source_type', 'other')
                values.append((
                    candidate.term,
                    source_type,
                    candidate.part_of_speech,
                    candidate.preliminary_score,
                    json.dumps(candidate.linguistic_features) if candidate.linguistic_features else "{}",
                    candidate.context[:500] if candidate.context else None,
                    f"{candidate.part_of_speech} term from {source_type}",  # placeholder definition
                    json.dumps(candidate.morphological_type)[:500] if candidate.morphological_type else None,
                    datetime.now()
                ))
            
            cursor.executemany(insert_query, values)
            conn.commit()
            
            self.logger.info(f"Stored {len(candidates)} candidates in database")
            
        except Error as e:
            self.logger.error(f"Database error storing candidates: {e}")
            raise
        finally:
            if 'conn' in locals() and conn.is_connected():
                cursor.close()
                conn.close()
    
    async def run_harvest_session(
        self, 
        query: str, 
        configs: List[HarvestConfig],
        session_id: Optional[str] = None
    ) -> HarvestSession:
        """Run a complete harvesting session"""
        
        if not session_id:
            session_id = f"harvest_{int(time.time())}"
        
        session = HarvestSession(
            session_id=session_id,
            start_time=datetime.now(),
            sources=[config.source_type for config in configs if config.enabled]
        )
        
        try:
            # Initialize sources
            initialized = await self.initialize_sources(configs)
            
            if not initialized:
                session.status = "failed"
                session.errors.append("No sources could be initialized")
                return session
            
            # Harvest from all sources
            candidates = await self.harvest_from_sources(query, session)
            
            # Analyze frequency data for top candidates
            if candidates:
                top_candidates = candidates[:50]  # Analyze top 50
                terms = [c.term for c in top_candidates]
                
                self.logger.info(f"Analyzing frequencies for {len(terms)} candidates...")
                await self.frequency_analyzer.collect_frequencies(terms)
            
            # Store candidates
            await self.store_candidates(candidates, session_id)
            
            session.status = "completed"
            
        except Exception as e:
            session.status = "failed"
            session.errors.append(f"Session error: {e}")
            self.logger.error(f"Harvest session failed: {e}")
            
        finally:
            session.end_time = datetime.now()
            
            # Cleanup sources
            for source in self.sources.values():
                try:
                    await source.cleanup()
                except Exception as e:
                    self.logger.warning(f"Error cleaning up source: {e}")
        
        return session
    
    async def get_harvest_recommendations(self) -> List[str]:
        """Get recommended harvest queries based on existing vocabulary gaps"""
        # This could analyze existing vocabulary to find gaps
        # For now, return some sophisticated academic domains
        return [
            "epistemology philosophy",
            "neuroplasticity cognitive science",
            "quantum mechanics physics", 
            "molecular biology genetics",
            "sustainable development economics",
            "computational linguistics",
            "Byzantine history medieval",
            "phenomenology existentialism"
        ]


# CLI Interface
async def main():
    """Main CLI interface for multi-source harvesting"""
    logging.basicConfig(level=logging.INFO)
    
    harvester = MultiSourceHarvester()
    
    # Configure sources
    configs = [
        HarvestConfig(
            source_type=SourceType.WIKIPEDIA,
            rate_limit_delay=0.5,
            max_results=20
        ),
        HarvestConfig(
            source_type=SourceType.ARXIV,
            rate_limit_delay=1.0,
            max_results=15
        ),
        HarvestConfig(
            source_type=SourceType.NEWS_API,
            rate_limit_delay=0.3,
            max_results=10
        )
    ]
    
    print("Multi-Source Vocabulary Harvester")
    print("=" * 50)
    
    # Get recommendations
    recommendations = await harvester.get_harvest_recommendations()
    print(f"\nRecommended queries: {', '.join(recommendations[:3])}")
    
    # Use first recommendation for demo
    query = recommendations[0]
    print(f"\nRunning harvest session for: '{query}'")
    
    session = await harvester.run_harvest_session(query, configs)
    
    print(f"\nSession Results:")
    print(f"Status: {session.status}")
    print(f"Duration: {session.duration}")
    print(f"Sources: {[s.value for s in session.sources]}")
    print(f"Total processed: {session.total_processed}")
    print(f"Candidates found: {session.candidates_found}")
    print(f"Quality candidates: {session.quality_candidates}")
    print(f"Success rate: {session.success_rate:.1f}%")
    
    if session.errors:
        print(f"\nErrors ({len(session.errors)}):")
        for error in session.errors[:3]:  # Show first 3 errors
            print(f"  - {error}")


if __name__ == "__main__":
    asyncio.run(main())