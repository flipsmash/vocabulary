#!/usr/bin/env python3
"""
Vocabulary Harvesting Orchestrator - Manages all sources with progress tracking
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
from dataclasses import dataclass

from progress_tracker import ProgressTracker, ResumableHarvester
from config import get_db_config

# Import harvesters
from multi_source_harvester import MultiSourceHarvester
from gutenberg_harvester import ProjectGutenbergHarvester
from wiktionary_harvester import WiktionaryHarvester
from universal_vocabulary_extractor import UniversalVocabularyExtractor

logger = logging.getLogger(__name__)

@dataclass
class HarvestGoals:
    """Define harvesting goals for the orchestrator"""
    daily_candidates_target: int = 200
    max_runtime_minutes: int = 60
    min_candidates_per_source: int = 20
    source_priorities: Dict[str, int] = None  # 1=highest priority
    
    def __post_init__(self):
        if self.source_priorities is None:
            self.source_priorities = {
                'gutenberg': 1,      # Highest quality, classical vocab
                'arxiv': 2,          # Academic terms
                'wiktionary': 3,     # Archaic terms  
                'wikipedia': 4,      # General knowledge
                'pubmed': 5,         # Medical terms
                'news_api': 6        # Contemporary usage
            }

class VocabularyOrchestrator:
    """Orchestrates vocabulary harvesting across all sources with intelligent scheduling"""
    
    def __init__(self, goals: HarvestGoals = None):
        self.goals = goals or HarvestGoals()
        self.tracker = ProgressTracker()
        self.db_config = get_db_config()
        
        # Initialize harvesters
        self.harvesters = {
            'multi_source': MultiSourceHarvester(),
            'gutenberg': ProjectGutenbergHarvester(self.db_config),
            'wiktionary': WiktionaryHarvester(),
            'universal_extractor': UniversalVocabularyExtractor()
        }
        
        self.session_start = None
        self.total_candidates_found = 0
        
    async def run_daily_harvest(self, force_run: bool = False) -> Dict[str, Any]:
        """
        Run daily vocabulary harvest with intelligent source prioritization
        """
        self.session_start = datetime.now()
        logger.info(f"Starting daily vocabulary harvest at {self.session_start}")
        
        # Get current status of all sources
        source_status = self.tracker.get_all_source_status()
        
        # Determine which sources to run
        sources_to_run = self._select_sources_to_run(source_status, force_run)
        
        if not sources_to_run:
            logger.info("No sources need to run based on timing and goals")
            return {'status': 'skipped', 'reason': 'no_sources_needed'}
        
        logger.info(f"Selected sources to run: {list(sources_to_run.keys())}")
        
        # Execute harvesting for each source
        results = {}
        remaining_candidates_needed = self.goals.daily_candidates_target
        
        for source_name, source_info in sources_to_run.items():
            if self._should_stop_harvesting():
                logger.info("Stopping harvest due to time or target limits")
                break
                
            logger.info(f"\n=== Harvesting from {source_name.upper()} ===")
            
            try:
                result = await self._harvest_from_source(
                    source_name, 
                    source_info,
                    target_candidates=min(remaining_candidates_needed, self.goals.min_candidates_per_source * 2)
                )
                
                results[source_name] = result
                candidates_found = result.get('candidates_found', 0)
                self.total_candidates_found += candidates_found
                remaining_candidates_needed -= candidates_found
                
                logger.info(f"{source_name}: Found {candidates_found} candidates")
                
                # Check if we've met our daily target
                if self.total_candidates_found >= self.goals.daily_candidates_target:
                    logger.info(f"Reached daily target of {self.goals.daily_candidates_target} candidates")
                    break
                    
            except Exception as e:
                logger.error(f"Error harvesting from {source_name}: {e}")
                results[source_name] = {'status': 'error', 'error': str(e)}
        
        # Generate summary
        summary = self._generate_harvest_summary(results)
        logger.info(f"Daily harvest completed: {summary['total_candidates']} candidates from {summary['sources_run']} sources")
        
        return summary
    
    def _select_sources_to_run(self, source_status: Dict[str, Dict], force_run: bool) -> Dict[str, Dict]:
        """Select which sources should run based on priority, timing, and goals"""
        sources_to_run = {}
        
        # Sort sources by priority
        prioritized_sources = sorted(
            source_status.items(),
            key=lambda x: self.goals.source_priorities.get(x[0], 99)
        )
        
        for source_name, status in prioritized_sources:
            should_run = (
                force_run or 
                status['status'] in ['never_run', 'error'] or
                self.tracker.should_run_source(source_name, min_interval_hours=6)
            )
            
            if should_run:
                sources_to_run[source_name] = status
        
        return sources_to_run
    
    async def _harvest_from_source(self, source_name: str, source_info: Dict, 
                                 target_candidates: int) -> Dict[str, Any]:
        """Harvest from a specific source with progress tracking"""
        
        if source_name == 'gutenberg':
            return await self._harvest_gutenberg(target_candidates)
        elif source_name == 'wiktionary':
            return await self._harvest_wiktionary(target_candidates)
        elif source_name == 'multi_source':
            return await self._harvest_multi_source(target_candidates)
        elif source_name == 'universal_extractor':
            return await self._harvest_universal_extractor(target_candidates)
        else:
            return {'status': 'not_implemented', 'source': source_name}
    
    async def _harvest_gutenberg(self, target_candidates: int) -> Dict[str, Any]:
        """Harvest from Project Gutenberg with resumption"""
        harvester = ResumableHarvester('gutenberg')
        position = harvester.start_harvest_session()
        
        try:
            # Get resumption parameters
            book_index = position.get('book_index', 0)
            author_offset = position.get('author_offset', 0)
            
            # Harvest books
            books = await self.harvesters['gutenberg'].get_vocabulary_rich_texts(
                max_books=min(10, target_candidates // 5)  # Estimate 5 candidates per book
            )
            
            all_candidates = []
            processed = 0
            
            for book in books[book_index:]:
                candidates = self.harvesters['gutenberg'].extract_classical_vocabulary(book)
                all_candidates.extend(candidates)
                processed += 1
                
                # Update progress
                new_position = {
                    'book_index': book_index + processed,
                    'author_offset': author_offset,
                    'last_book_id': book.get('book_id')
                }
                harvester.update_progress(1, len(candidates), 0, new_position)
                harvester.save_position(new_position)
                
                if len(all_candidates) >= target_candidates:
                    break
            
            harvester.end_harvest_session('completed')
            
            return {
                'status': 'completed',
                'candidates_found': len(all_candidates),
                'books_processed': processed,
                'candidates': all_candidates
            }
            
        except Exception as e:
            harvester.end_harvest_session('error', str(e))
            return {'status': 'error', 'error': str(e)}
    
    async def _harvest_wiktionary(self, target_candidates: int) -> Dict[str, Any]:
        """Harvest from Wiktionary with resumption"""
        harvester = ResumableHarvester('wiktionary')
        position = harvester.start_harvest_session()
        
        try:
            # Use the existing harvest_archaic_terms method
            entries = await self.harvesters['wiktionary'].harvest_archaic_terms(
                limit=target_candidates
            )
            
            harvester.update_progress(len(entries), len(entries), 0)
            harvester.end_harvest_session('completed')
            
            return {
                'status': 'completed',
                'candidates_found': len(entries),
                'entries_processed': len(entries),
                'candidates': entries
            }
            
        except Exception as e:
            harvester.end_harvest_session('error', str(e))
            return {'status': 'error', 'error': str(e)}
    
    async def _harvest_multi_source(self, target_candidates: int) -> Dict[str, Any]:
        """Harvest from ArXiv, Wikipedia, News API"""
        harvester = ResumableHarvester('multi_source')
        position = harvester.start_harvest_session()
        
        try:
            # Configure sources
            multi_harvester = self.harvesters['multi_source']
            
            configs = [
                multi_harvester.source_classes[multi_harvester.SourceType.ARXIV](
                    multi_harvester.HarvestConfig(multi_harvester.SourceType.ARXIV, max_results=20)
                ),
                multi_harvester.source_classes[multi_harvester.SourceType.WIKIPEDIA](
                    multi_harvester.HarvestConfig(multi_harvester.SourceType.WIKIPEDIA, max_results=15)
                ),
                multi_harvester.source_classes[multi_harvester.SourceType.NEWS_API](
                    multi_harvester.HarvestConfig(multi_harvester.SourceType.NEWS_API, max_results=10)
                )
            ]
            
            # Run harvest session
            session = await multi_harvester.run_harvest_session(
                "artificial intelligence neuroscience",
                configs=configs
            )
            
            harvester.update_progress(
                session.total_processed,
                session.candidates_found,
                session.quality_candidates
            )
            harvester.end_harvest_session('completed')
            
            return {
                'status': 'completed',
                'candidates_found': session.candidates_found,
                'quality_candidates': session.quality_candidates,
                'session': session
            }
            
        except Exception as e:
            harvester.end_harvest_session('error', str(e))
            return {'status': 'error', 'error': str(e)}
    
    async def _harvest_universal_extractor(self, target_candidates: int) -> Dict[str, Any]:
        """Extract vocabulary from sample academic texts"""
        harvester = ResumableHarvester('universal_extractor')
        harvester.start_harvest_session()
        
        try:
            extractor = self.harvesters['universal_extractor']
            
            # Sample academic texts for extraction
            sample_texts = [
                {
                    'text': """
                    The phenomenological investigation of consciousness reveals fundamental structures
                    of intentionality that transcend empirical psychology. Through epoché and 
                    transcendental reduction, we can examine the noetic-noematic correlation
                    that constitutes the essence of conscious experience.
                    """,
                    'domain': 'philosophy'
                },
                {
                    'text': """
                    Neuroplasticity mechanisms involve synaptic efficacy modulation through
                    long-term potentiation and depression. These processes facilitate 
                    experience-dependent plasticity in cortical networks, enabling
                    adaptive behavioral modifications.
                    """,
                    'domain': 'neuroscience'
                }
            ]
            
            all_candidates = []
            for text_info in sample_texts:
                candidates = extractor.extract_candidates(text_info['text'], text_info)
                all_candidates.extend(candidates)
            
            harvester.update_progress(len(sample_texts), len(all_candidates), 0)
            harvester.end_harvest_session('completed')
            
            return {
                'status': 'completed',
                'candidates_found': len(all_candidates),
                'texts_processed': len(sample_texts),
                'candidates': all_candidates
            }
            
        except Exception as e:
            harvester.end_harvest_session('error', str(e))
            return {'status': 'error', 'error': str(e)}
    
    def _should_stop_harvesting(self) -> bool:
        """Check if we should stop harvesting due to time or target limits"""
        if not self.session_start:
            return False
            
        # Check time limit
        elapsed = datetime.now() - self.session_start
        if elapsed.total_seconds() > self.goals.max_runtime_minutes * 60:
            return True
        
        # Check if we've exceeded our target significantly
        if self.total_candidates_found > self.goals.daily_candidates_target * 1.5:
            return True
            
        return False
    
    def _generate_harvest_summary(self, results: Dict[str, Any]) -> Dict[str, Any]:
        """Generate summary of harvest results"""
        total_candidates = sum(
            result.get('candidates_found', 0) 
            for result in results.values() 
            if isinstance(result, dict)
        )
        
        successful_sources = [
            source for source, result in results.items()
            if isinstance(result, dict) and result.get('status') == 'completed'
        ]
        
        failed_sources = [
            source for source, result in results.items()  
            if isinstance(result, dict) and result.get('status') == 'error'
        ]
        
        return {
            'total_candidates': total_candidates,
            'sources_run': len(results),
            'successful_sources': successful_sources,
            'failed_sources': failed_sources,
            'runtime_minutes': (datetime.now() - self.session_start).total_seconds() / 60,
            'target_met': total_candidates >= self.goals.daily_candidates_target,
            'results': results
        }
    
    async def check_system_status(self) -> Dict[str, Any]:
        """Check status of the entire harvesting system"""
        source_status = self.tracker.get_all_source_status()
        
        # Calculate system health metrics
        sources_healthy = sum(1 for s in source_status.values() if s['status'] not in ['error', 'never_run'])
        total_sources = len(source_status)
        
        # Find sources that need attention
        needs_attention = [
            name for name, status in source_status.items()
            if status['status'] == 'error' or 
            (status['last_run'] and 
             datetime.now() - datetime.fromisoformat(status['last_run']) > timedelta(days=2))
        ]
        
        return {
            'system_health': sources_healthy / total_sources,
            'sources_status': source_status,
            'needs_attention': needs_attention,
            'last_check': datetime.now().isoformat()
        }


# CLI Interface
async def main():
    import argparse
    
    parser = argparse.ArgumentParser(description='Vocabulary Harvesting Orchestrator')
    parser.add_argument('--daily-harvest', action='store_true', 
                       help='Run daily vocabulary harvest')
    parser.add_argument('--force', action='store_true',
                       help='Force run all sources regardless of timing')
    parser.add_argument('--target', type=int, default=200,
                       help='Daily candidates target')
    parser.add_argument('--max-runtime', type=int, default=60,
                       help='Maximum runtime in minutes')
    parser.add_argument('--status', action='store_true',
                       help='Check system status')
    
    args = parser.parse_args()
    
    # Set up logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # Create goals
    goals = HarvestGoals(
        daily_candidates_target=args.target,
        max_runtime_minutes=args.max_runtime
    )
    
    orchestrator = VocabularyOrchestrator(goals)
    
    if args.daily_harvest:
        print("Starting Daily Vocabulary Harvest")
        print("=" * 50)
        
        result = await orchestrator.run_daily_harvest(force_run=args.force)
        
        print(f"\nHarvest Summary:")
        print(f"   Total candidates: {result.get('total_candidates', 0):,}")
        print(f"   Sources run: {result.get('sources_run', 0)}")
        print(f"   Runtime: {result.get('runtime_minutes', 0):.1f} minutes")
        print(f"   Target met: {'YES' if result.get('target_met') else 'NO'}")
        
        if result.get('failed_sources'):
            print(f"   Failed sources: {result['failed_sources']}")
    
    elif args.status:
        print("System Status Check")
        print("=" * 50)
        
        status = await orchestrator.check_system_status()
        print(f"System health: {status['system_health']:.1%}")
        
        if status['needs_attention']:
            print(f"WARNING - Sources needing attention: {status['needs_attention']}")
        else:
            print("SUCCESS - All sources operating normally")


if __name__ == "__main__":
    asyncio.run(main())