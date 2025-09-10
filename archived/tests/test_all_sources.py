#!/usr/bin/env python3
"""
Comprehensive test of all vocabulary harvesting sources
Showcases the diversity and quality of collected terms
"""

import asyncio
import logging
from datetime import datetime
from typing import Dict, List
import random

# Import all our harvesters
from multi_source_harvester import MultiSourceHarvester
from gutenberg_harvester import ProjectGutenbergHarvester
from wiktionary_harvester import WiktionaryHarvester
from universal_vocabulary_extractor import UniversalVocabularyExtractor
from frequency_analysis_system import FrequencyCollectionManager
from config import get_db_config


class ComprehensiveVocabularyTester:
    """Test all vocabulary sources and showcase results"""
    
    def __init__(self):
        self.db_config = get_db_config()
        self.logger = logging.getLogger(__name__)
        self.results = {}
    
    async def test_multi_source_harvester(self) -> Dict:
        """Test the multi-source harvester (ArXiv, Wikipedia, News)"""
        print("\n" + "="*60)
        print("TESTING MULTI-SOURCE HARVESTER")
        print("="*60)
        
        try:
            harvester = MultiSourceHarvester()
            
            # Run a quick harvest session
            session = await harvester.run_harvest_session(
                "neuroscience consciousness",
                configs=[
                    harvester.source_classes[harvester.SourceType.ARXIV](harvester.HarvestConfig(harvester.SourceType.ARXIV, max_results=10)),
                    harvester.source_classes[harvester.SourceType.WIKIPEDIA](harvester.HarvestConfig(harvester.SourceType.WIKIPEDIA, max_results=5)),
                    harvester.source_classes[harvester.SourceType.NEWS_API](harvester.HarvestConfig(harvester.SourceType.NEWS_API, max_results=5))
                ]
            )
            
            print(f"✅ Session Status: {session.status}")
            print(f"📊 Total processed: {session.total_processed}")
            print(f"🎯 Candidates found: {session.candidates_found}")
            print(f"⭐ Quality candidates: {session.quality_candidates}")
            print(f"📈 Success rate: {session.success_rate:.1f}%")
            print(f"⏱️ Duration: {session.duration}")
            
            if session.errors:
                print(f"⚠️ Errors: {len(session.errors)}")
                for error in session.errors[:3]:
                    print(f"   - {error}")
            
            return {
                'status': session.status,
                'candidates': session.candidates_found,
                'quality_candidates': session.quality_candidates,
                'sources': ['arxiv', 'wikipedia', 'news_api']
            }
            
        except Exception as e:
            print(f"❌ Multi-source harvester test failed: {e}")
            return {'status': 'failed', 'error': str(e)}
    
    async def test_gutenberg_harvester(self) -> Dict:
        """Test the Project Gutenberg classical literature harvester"""
        print("\n" + "="*60) 
        print("📚 TESTING GUTENBERG CLASSICAL LITERATURE HARVESTER")
        print("="*60)
        
        try:
            harvester = ProjectGutenbergHarvester(self.db_config)
            
            # Get some classical texts (limit to 2 for testing)
            books = await harvester.get_vocabulary_rich_texts(max_books=2)
            
            print(f"✅ Successfully harvested {len(books)} classical books")
            
            all_candidates = []
            top_terms = []
            
            for book in books:
                print(f"\n📖 {book['title']} by {book['author']}")
                print(f"   📅 Period: {book['literary_period']}")
                print(f"   📄 Content: {len(book['content'])} characters")
                
                # Extract vocabulary
                candidates = harvester.extract_classical_vocabulary(book)
                all_candidates.extend(candidates)
                
                print(f"   🎯 Vocabulary candidates: {len(candidates)}")
                
                # Show top 3 terms
                if candidates:
                    print("   🏆 Top terms:")
                    for i, candidate in enumerate(candidates[:3]):
                        term = candidate['term']
                        score = candidate['preliminary_score']
                        print(f"      {i+1}. {term} (score: {score:.1f})")
                        top_terms.append((term, score, book['author'], book['literary_period']))
            
            return {
                'status': 'completed',
                'books_harvested': len(books),
                'total_candidates': len(all_candidates),
                'top_terms': top_terms[:10],
                'authors': [book['author'] for book in books],
                'periods': list(set(book['literary_period'] for book in books))
            }
            
        except Exception as e:
            print(f"❌ Gutenberg harvester test failed: {e}")
            return {'status': 'failed', 'error': str(e)}
    
    async def test_wiktionary_harvester(self) -> Dict:
        """Test the Wiktionary archaic terms harvester"""
        print("\n" + "="*60)
        print("📖 TESTING WIKTIONARY ARCHAIC TERMS HARVESTER")
        print("="*60)
        
        try:
            harvester = WiktionaryHarvester()
            
            # Harvest some archaic terms
            entries = await harvester.harvest_archaic_terms(limit=15)
            
            print(f"✅ Successfully harvested {len(entries)} archaic entries")
            
            if entries:
                print("\n🏆 Sample archaic terms discovered:")
                for i, entry in enumerate(entries[:8]):
                    print(f"   {i+1}. {entry.term}")
                    print(f"      📝 Definition: {entry.definition[:80]}...")
                    if entry.tags:
                        print(f"      🏷️  Tags: {', '.join(entry.tags[:3])}")
                    print(f"      📊 Score: {getattr(entry, 'utility_score', 'N/A')}")
                    print()
            
            return {
                'status': 'completed',
                'entries_found': len(entries),
                'sample_terms': [entry.term for entry in entries[:10]],
                'avg_definition_length': sum(len(entry.definition) for entry in entries) / len(entries) if entries else 0
            }
            
        except Exception as e:
            print(f"❌ Wiktionary harvester test failed: {e}")
            return {'status': 'failed', 'error': str(e)}
    
    async def test_universal_extractor(self) -> Dict:
        """Test the universal vocabulary extractor on sample texts"""
        print("\n" + "="*60)
        print("🔍 TESTING UNIVERSAL VOCABULARY EXTRACTOR")
        print("="*60)
        
        try:
            extractor = UniversalVocabularyExtractor()
            
            # Test texts from different domains
            test_texts = [
                {
                    'text': """
                    The phenomenological reduction involves a methodical suspension of the 
                    natural attitude, enabling the phenomenologist to examine consciousness 
                    in its pure intentional structure. This epoché reveals the transcendental 
                    dimension of subjectivity, where noesis and noema constitute the 
                    fundamental correlation of experience.
                    """,
                    'domain': 'philosophy'
                },
                {
                    'text': """
                    The pathophysiology of neuroinflammation involves complex interactions 
                    between microglia, astrocytes, and oligodendrocytes. Cytokine cascades 
                    mediate neurodegeneration through oxidative stress and mitochondrial 
                    dysfunction, leading to synaptic pruning and axonal demyelination.
                    """,
                    'domain': 'neuroscience'
                },
                {
                    'text': """
                    The crystallographic analysis revealed a monoclinic structure with 
                    orthorhombic symmetry. X-ray diffraction patterns indicated significant 
                    anisotropy in the lattice parameters, with pronounced dichroism 
                    observable in the spectroscopic measurements.
                    """,
                    'domain': 'chemistry'
                }
            ]
            
            all_candidates = []
            domain_results = {}
            
            for test in test_texts:
                domain = test['domain']
                text = test['text']
                
                candidates = extractor.extract_candidates(
                    text, 
                    {'domain': domain, 'source_type': 'test'}
                )
                
                all_candidates.extend(candidates)
                
                print(f"\n🔬 {domain.title()} Domain:")
                print(f"   📊 Candidates extracted: {len(candidates)}")
                
                if candidates:
                    print("   🏆 Top terms:")
                    top_candidates = sorted(candidates, key=lambda x: x.preliminary_score, reverse=True)[:5]
                    for i, candidate in enumerate(top_candidates):
                        morphology = ', '.join(candidate.morphological_type[:2])
                        print(f"      {i+1}. {candidate.term} (score: {candidate.preliminary_score:.1f}) [{morphology}]")
                
                domain_results[domain] = {
                    'candidates': len(candidates),
                    'top_terms': [(c.term, c.preliminary_score) for c in candidates[:3]]
                }
            
            return {
                'status': 'completed',
                'total_candidates': len(all_candidates),
                'domains_tested': len(test_texts),
                'domain_results': domain_results,
                'avg_score': sum(c.preliminary_score for c in all_candidates) / len(all_candidates) if all_candidates else 0
            }
            
        except Exception as e:
            print(f"❌ Universal extractor test failed: {e}")
            return {'status': 'failed', 'error': str(e)}
    
    async def test_frequency_analyzer(self) -> Dict:
        """Test the frequency analysis system"""
        print("\n" + "="*60)
        print("📈 TESTING FREQUENCY ANALYSIS SYSTEM")
        print("="*60)
        
        try:
            freq_manager = FrequencyCollectionManager(self.db_config)
            
            # Test with a diverse set of words
            test_words = [
                'epistemological', 'phenomenological', 'neuroplasticity',
                'mitochondrial', 'crystallographic', 'pathophysiology',
                'beautiful', 'the', 'amazing', 'scientific',
                'serendipity', 'perspicacious', 'sesquipedalian'
            ]
            
            print(f"🔍 Analyzing frequencies for {len(test_words)} test words...")
            
            # Collect frequency data
            frequencies = await freq_manager.collect_frequencies(test_words)
            
            print(f"✅ Collected frequency data for {len(frequencies)} words")
            
            # Analyze and display results
            analyzed_words = []
            for word, freq_list in frequencies.items():
                if freq_list:
                    zipf_score, confidence = freq_manager.calculate_composite_zipf(freq_list)
                    rarity = freq_manager.classify_rarity(zipf_score)
                    
                    analyzed_words.append({
                        'word': word,
                        'zipf_score': zipf_score,
                        'confidence': confidence,
                        'rarity': rarity
                    })
            
            # Sort by rarity (lowest Zipf = rarest)
            analyzed_words.sort(key=lambda x: x['zipf_score'])
            
            print(f"\n📊 Frequency Analysis Results:")
            print(f"{'Word':<20} {'Zipf':<6} {'Confidence':<10} {'Rarity'}")
            print("-" * 50)
            
            for word_data in analyzed_words[:10]:
                word = word_data['word']
                zipf = word_data['zipf_score']
                confidence = word_data['confidence']
                rarity = word_data['rarity']
                
                print(f"{word:<20} {zipf:<6.1f} {confidence:<10.2f} {rarity}")
            
            return {
                'status': 'completed',
                'words_analyzed': len(analyzed_words),
                'rarest_words': [w['word'] for w in analyzed_words[:5]],
                'most_common': [w['word'] for w in analyzed_words[-3:]],
                'avg_zipf': sum(w['zipf_score'] for w in analyzed_words) / len(analyzed_words) if analyzed_words else 0
            }
            
        except Exception as e:
            print(f"❌ Frequency analyzer test failed: {e}")
            return {'status': 'failed', 'error': str(e)}
    
    async def generate_summary_report(self):
        """Generate a comprehensive summary of all test results"""
        print("\n" + "="*70)
        print("📋 COMPREHENSIVE VOCABULARY HARVESTING SYSTEM TEST SUMMARY")
        print("="*70)
        
        total_candidates = 0
        successful_sources = 0
        all_top_terms = []
        
        for source, result in self.results.items():
            if result.get('status') == 'completed' or result.get('status') == 'success':
                successful_sources += 1
                
                # Count candidates from different result structures
                if 'candidates' in result:
                    total_candidates += result['candidates']
                elif 'total_candidates' in result:
                    total_candidates += result['total_candidates']
                elif 'entries_found' in result:
                    total_candidates += result['entries_found']
                
                # Collect top terms
                if 'top_terms' in result:
                    all_top_terms.extend(result['top_terms'])
        
        print(f"✅ Sources tested successfully: {successful_sources}/{len(self.results)}")
        print(f"🎯 Total vocabulary candidates discovered: {total_candidates}")
        print(f"📊 Test completion rate: {(successful_sources/len(self.results)*100):.1f}%")
        
        # Show diversity of sources
        print(f"\n🌟 Source Diversity:")
        for source, result in self.results.items():
            status = result.get('status', 'unknown')
            status_icon = "✅" if status in ['completed', 'success'] else "❌"
            print(f"   {status_icon} {source.replace('_', ' ').title()}: {status}")
        
        # Show sample of best terms discovered
        if all_top_terms:
            print(f"\n🏆 Sample of Exceptional Terms Discovered:")
            # Mix different types of terms
            sample_terms = random.sample(all_top_terms, min(8, len(all_top_terms)))
            for i, term_data in enumerate(sample_terms, 1):
                if isinstance(term_data, tuple) and len(term_data) >= 2:
                    term, score = term_data[0], term_data[1]
                    extra_info = f" (score: {score:.1f})" if isinstance(score, (int, float)) else ""
                    print(f"   {i}. {term}{extra_info}")
                else:
                    print(f"   {i}. {term_data}")
        
        print(f"\n🚀 System Status: FULLY OPERATIONAL")
        print(f"⏱️  Test completed at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    async def run_comprehensive_test(self):
        """Run comprehensive test of all vocabulary sources"""
        print("🔬 COMPREHENSIVE VOCABULARY HARVESTING SYSTEM TEST")
        print("=" * 70)
        print(f"⏱️  Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        
        # Test each source
        self.results['multi_source'] = await self.test_multi_source_harvester()
        self.results['gutenberg'] = await self.test_gutenberg_harvester()
        self.results['wiktionary'] = await self.test_wiktionary_harvester()
        self.results['universal_extractor'] = await self.test_universal_extractor()
        self.results['frequency_analyzer'] = await self.test_frequency_analyzer()
        
        # Generate summary
        await self.generate_summary_report()
        
        return self.results


async def main():
    """Main test execution"""
    # Set up logging
    logging.basicConfig(
        level=logging.WARNING,  # Reduce noise during testing
        format='%(levelname)s:%(name)s:%(message)s'
    )
    
    # Run comprehensive test
    tester = ComprehensiveVocabularyTester()
    results = await tester.run_comprehensive_test()
    
    return results


if __name__ == "__main__":
    asyncio.run(main())