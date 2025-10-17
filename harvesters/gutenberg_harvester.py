#!/usr/bin/env python3
"""
Project Gutenberg Classical Literature Harvester
Respectful extraction of sophisticated vocabulary from classic texts
"""

import asyncio
import aiohttp
import random
import re
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timedelta
import json
import logging
from pathlib import Path
from bs4 import BeautifulSoup
import hashlib

from .respectful_scraper import RespectfulWebScraper
from .universal_vocabulary_extractor import UniversalVocabularyExtractor, VocabularyCandidate
import sys
import os
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
sys.path.insert(0, parent_dir)
from core.secure_config import get_db_config
from core.english_word_validator import validate_english_word
from core.vocabulary_deduplicator import filter_duplicate_candidates
from wordfreq import zipf_frequency
import mysql.connector
from mysql.connector import Error


# Quick stoplist to avoid work on extremely common vocabulary
COMMON_WORDS = {
    'the', 'and', 'that', 'have', 'with', 'this', 'from', 'would', 'there',
    'about', 'could', 'should', 'other', 'which', 'their', 'every', 'because',
    'between', 'people', 'through', 'never', 'always', 'where', 'while', 'those',
    'being', 'after', 'before', 'against', 'under', 'among', 'again', 'even',
    'first', 'little', 'great', 'world', 'might', 'house', 'another', 'something',
    'nothing', 'woman', 'father', 'mother', 'brother', 'child', 'children',
    'friend', 'heart', 'hands', 'eyes', 'once'
}


class ProjectGutenbergHarvester:
    """Harvest classic literature with full text access"""
    
    def __init__(self, db_config: Dict):
        self.db_config = db_config
        self.scraper = RespectfulWebScraper()
        self.extractor = UniversalVocabularyExtractor()
        self.base_url = "https://www.gutenberg.org"
        self.logger = logging.getLogger(__name__)
        
        # Target works known for sophisticated vocabulary
        self.priority_authors = [
            'shakespeare', 'milton', 'chaucer', 'spenser', 'donne',
            'bacon', 'burton', 'browne', 'johnson', 'gibbon',
            'hume', 'locke', 'berkeley', 'hobbes', 'spinoza',
            'swift', 'pope', 'dryden', 'addison', 'steele',
            'defoe', 'richardson', 'fielding', 'sterne', 'austen',
            'coleridge', 'wordsworth', 'byron', 'shelley', 'keats'
        ]
        
        # Literary periods for context
        self.author_periods = {
            'shakespeare': 'elizabethan',
            'milton': 'restoration', 
            'chaucer': 'medieval',
            'spenser': 'elizabethan',
            'donne': 'metaphysical',
            'bacon': 'renaissance',
            'burton': 'jacobean',
            'browne': 'baroque',
            'johnson': 'neoclassical',
            'gibbon': 'enlightenment',
            'swift': 'augustan',
            'pope': 'augustan',
            'austen': 'regency',
            'coleridge': 'romantic',
            'wordsworth': 'romantic',
            'byron': 'romantic',
            'shelley': 'romantic',
            'keats': 'romantic'
        }
        
        self.daily_limit = 25
        self.books_processed_today = self._get_books_processed_today()
        
        # Cache processed books to avoid re-downloading
        self.processed_books_cache = self._load_processed_books_cache()
        
    def _get_books_processed_today(self) -> int:
        """Get count of books processed today"""
        today = datetime.now().strftime("%Y-%m-%d")
        cache_file = Path("gutenberg_daily_count.json")
        
        try:
            if cache_file.exists():
                with open(cache_file, 'r') as f:
                    data = json.load(f)
                return data.get(today, 0)
            else:
                return 0
        except Exception:
            return 0
    
    def _increment_daily_count(self):
        """Increment daily book count"""
        today = datetime.now().strftime("%Y-%m-%d")
        cache_file = Path("gutenberg_daily_count.json")
        
        try:
            data = {}
            if cache_file.exists():
                with open(cache_file, 'r') as f:
                    data = json.load(f)
            
            data[today] = data.get(today, 0) + 1
            
            # Keep only last 7 days
            cutoff_date = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")
            data = {k: v for k, v in data.items() if k >= cutoff_date}
            
            with open(cache_file, 'w') as f:
                json.dump(data, f, indent=2)
                
            self.books_processed_today = data[today]
            
        except Exception as e:
            self.logger.warning(f"Failed to update daily count: {e}")
    
    def _load_processed_books_cache(self) -> Dict[str, str]:
        """Load cache of already processed books"""
        cache_file = Path("gutenberg_processed_cache.json")
        
        try:
            if cache_file.exists():
                with open(cache_file, 'r') as f:
                    return json.load(f)
            else:
                return {}
        except Exception:
            return {}
    
    def _save_processed_books_cache(self):
        """Save processed books cache"""
        cache_file = Path("gutenberg_processed_cache.json")
        
        try:
            with open(cache_file, 'w') as f:
                json.dump(self.processed_books_cache, f, indent=2)
        except Exception as e:
            self.logger.warning(f"Failed to save processed books cache: {e}")
    
    async def get_vocabulary_rich_texts(self, max_books: int = None) -> List[Dict]:
        """Get classic texts known for rich vocabulary"""
        max_books = max_books or min(self.daily_limit - self.books_processed_today, 15)
        
        if max_books <= 0:
            self.logger.info("Daily limit reached for Gutenberg harvesting")
            return []
        
        self.logger.info(f"Harvesting up to {max_books} books from Project Gutenberg")
        
        books_with_content = []
        
        # Shuffle authors to get variety
        authors_to_process = self.priority_authors.copy()
        random.shuffle(authors_to_process)
        
        for author in authors_to_process:
            if len(books_with_content) >= max_books:
                break
                
            try:
                self.logger.info(f"Processing works by {author}")
                
                # Get books for this author
                author_books = await self._get_author_books(author)
                
                # Process up to 2 books per author per session
                books_processed = 0
                for book_info in author_books:
                    if (len(books_with_content) >= max_books or 
                        books_processed >= 2):
                        break
                    
                    book_id = book_info['id']
                    
                    # Skip if already processed recently
                    if book_id in self.processed_books_cache:
                        continue
                    
                    book_content = await self._get_book_text(book_id)
                    if book_content and book_content['text']:
                        book_data = {
                            'book_id': book_id,
                            'author': author,
                            'title': book_content['title'],
                            'content': book_content['text'][:15000],  # First 15k chars for vocab extraction
                            'url': f"https://www.gutenberg.org/ebooks/{book_id}",
                            'literary_period': self.author_periods.get(author, 'classical'),
                            'word_count': len(book_content['text'].split())
                        }
                        
                        books_with_content.append(book_data)
                        books_processed += 1
                        
                        # Add to processed cache
                        self.processed_books_cache[book_id] = datetime.now().strftime("%Y-%m-%d")
                        
                        self._increment_daily_count()
                        
                        self.logger.info(f"Successfully processed: {book_content['title']} by {author}")
                        
                        # Human-like delay between books
                        await asyncio.sleep(random.uniform(4, 12))
                        
            except Exception as e:
                self.logger.error(f"Error processing author {author}: {e}")
                continue
        
        # Save cache
        self._save_processed_books_cache()
        
        self.logger.info(f"Successfully harvested {len(books_with_content)} books from Gutenberg")
        return books_with_content
    
    async def _get_author_books(self, author: str) -> List[Dict[str, str]]:
        """Get list of books by author from Gutenberg search"""
        search_url = f"https://www.gutenberg.org/ebooks/search/?query={author}&submit_search=Go%21"
        
        try:
            search_html = await self.scraper.fetch_article_content(search_url, 'gutenberg')
            if not search_html:
                return []
            
            book_ids = self._extract_book_ids_from_search(search_html)
            
            # Return book info with IDs
            return [{'id': book_id, 'author': author} for book_id in book_ids[:5]]  # Max 5 per author
            
        except Exception as e:
            self.logger.error(f"Error searching for {author}: {e}")
            return []
    
    def _extract_book_ids_from_search(self, search_html: str) -> List[str]:
        """Extract Gutenberg book IDs from search results"""
        try:
            soup = BeautifulSoup(search_html, 'html.parser')
            book_ids = []
            
            # Find links to ebooks
            for link in soup.find_all('a', href=True):
                href = link['href']
                if '/ebooks/' in href:
                    # Extract book ID
                    match = re.search(r'/ebooks/(\d+)', href)
                    if match:
                        book_ids.append(match.group(1))
            
            # Remove duplicates and return
            return list(set(book_ids))
            
        except Exception as e:
            self.logger.error(f"Error extracting book IDs: {e}")
            return []
    
    async def _get_book_text(self, book_id: str) -> Optional[Dict]:
        """Download full text of a Gutenberg book"""
        # Try different text formats in order of preference
        text_urls = [
            f"https://www.gutenberg.org/files/{book_id}/{book_id}-0.txt",  # UTF-8
            f"https://www.gutenberg.org/files/{book_id}/{book_id}.txt",    # ASCII
            f"https://www.gutenberg.org/cache/epub/{book_id}/pg{book_id}.txt"  # Alternative
        ]
        
        for url in text_urls:
            try:
                # Use direct aiohttp for text files (more efficient than full scraper)
                async with aiohttp.ClientSession() as session:
                    headers = {
                        'User-Agent': 'VocabularyResearchBot/1.0 (Educational Research; Contact: researcher@example.com)'
                    }
                    
                    async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=60)) as response:
                        if response.status == 200:
                            text = await response.text(encoding='utf-8', errors='ignore')
                            
                            if len(text) > 1000:  # Ensure we got actual content
                                # Extract title and clean text
                                title = self._extract_title(text)
                                cleaned_text = self._clean_gutenberg_text(text)
                                
                                if len(cleaned_text) > 5000:  # Ensure substantial content
                                    return {
                                        'title': title,
                                        'text': cleaned_text
                                    }
                        
                        # Small delay between URL attempts
                        await asyncio.sleep(random.uniform(2, 5))
                        
            except Exception as e:
                self.logger.debug(f"Failed to fetch {url}: {e}")
                continue
        
        self.logger.warning(f"Could not fetch text for book {book_id}")
        return None
    
    def _extract_title(self, text: str) -> str:
        """Extract book title from Gutenberg text"""
        lines = text.split('\n')[:100]  # Check first 100 lines
        
        for line in lines:
            line = line.strip()
            if line.startswith('Title:'):
                title = line.split('Title:')[1].strip()
                # Clean up title
                title = re.sub(r'\s+', ' ', title)
                return title[:200]  # Reasonable length limit
        
        # Fallback: look for common title patterns
        for line in lines:
            line = line.strip()
            if len(line) > 10 and len(line) < 100:
                # Look for lines that might be titles (all caps, centered, etc.)
                if (line.isupper() and not line.startswith('*') and 
                    not re.search(r'\d', line) and len(line.split()) <= 8):
                    return line.title()
        
        return "Unknown Title"
    
    def _clean_gutenberg_text(self, text: str) -> str:
        """Clean Project Gutenberg text formatting"""
        # Remove Gutenberg header/footer
        start_markers = [
            "*** START OF THE PROJECT GUTENBERG EBOOK",
            "*** START OF THIS PROJECT GUTENBERG EBOOK",
            "***START OF THE PROJECT GUTENBERG EBOOK",
            "START OF THE PROJECT GUTENBERG",
            "*** START OF"
        ]
        
        end_markers = [
            "*** END OF THE PROJECT GUTENBERG EBOOK",
            "*** END OF THIS PROJECT GUTENBERG EBOOK", 
            "***END OF THE PROJECT GUTENBERG EBOOK",
            "END OF THE PROJECT GUTENBERG",
            "*** END OF"
        ]
        
        # Find actual content start
        start_idx = 0
        for marker in start_markers:
            idx = text.find(marker)
            if idx != -1:
                # Find end of this line and skip a few more lines
                start_idx = text.find('\n', idx)
                if start_idx != -1:
                    # Skip a few more lines to get past the header
                    for _ in range(3):
                        next_line = text.find('\n', start_idx + 1)
                        if next_line != -1:
                            start_idx = next_line
                        else:
                            break
                break
        
        # Find content end
        end_idx = len(text)
        for marker in end_markers:
            idx = text.find(marker)
            if idx != -1:
                end_idx = idx
                break
        
        # Extract main content
        content = text[start_idx:end_idx]
        
        # Clean up formatting
        content = re.sub(r'\r\n', '\n', content)  # Normalize line endings
        content = re.sub(r'\n\s*\n\s*\n+', '\n\n', content)  # Reduce excessive newlines
        content = re.sub(r'[ \t]+', ' ', content)  # Normalize spaces
        content = re.sub(r'_{5,}', '', content)  # Remove underscore dividers
        content = re.sub(r'-{5,}', '', content)  # Remove dash dividers
        
        # Remove page numbers and chapter markers that might interfere
        content = re.sub(r'\n\s*\d+\s*\n', '\n\n', content)  # Standalone numbers (page numbers)
        content = re.sub(r'\n\s*CHAPTER\s+[IVXLCDM]+\s*\n', '\n\nCHAPTER\n', content, flags=re.IGNORECASE)
        
        return content.strip()
    
    def extract_classical_vocabulary(self, book: Dict) -> List[Dict]:
        """Extract sophisticated vocabulary from classical literature"""
        content = book['content']
        author = book['author']
        title = book['title']
        period = book.get('literary_period', 'classical')
        
        # Use the universal extractor as the primary source of candidates
        base_candidates = self.extractor.extract_candidates(
            content,
            {
                'source_type': 'gutenberg',
                'author': author,
                'title': title,
                'literary_period': period
            }
        )

        # Deduplicate and score without specialising on archaic-only patterns
        unique_candidates = self._deduplicate_by_term(base_candidates)

        scored_candidates = self._score_classical_candidates(unique_candidates, period)

        # Return all scored candidates so downstream filters decide what to keep
        return scored_candidates
    
    def _deduplicate_by_term(self, candidates: List) -> List[Dict]:
        """Remove duplicate terms, keeping the best instance"""
        term_to_best = {}
        
        for candidate in candidates:
            # Handle both dict and VocabularyCandidate objects
            if hasattr(candidate, 'term'):
                # VocabularyCandidate object
                term = candidate.term
                score = candidate.preliminary_score
                # Convert to dict for consistent handling
                candidate_dict = {
                    'term': candidate.term,
                    'original_form': getattr(candidate, 'original_form', candidate.term),
                    'part_of_speech': candidate.part_of_speech,
                    'fine_pos': candidate.fine_pos,
                    'lemma': candidate.lemma,
                    'context': candidate.context,
                    'linguistic_features': candidate.linguistic_features,
                    'morphological_type': candidate.morphological_type,
                    'source_metadata': candidate.source_metadata,
                    'preliminary_score': candidate.preliminary_score
                }
            else:
                # Dict object
                term = candidate['term']
                score = candidate.get('preliminary_score', 0)
                candidate_dict = candidate
            
            if term not in term_to_best:
                term_to_best[term] = candidate_dict
            else:
                # Keep candidate with higher score
                best_score = term_to_best[term].get('preliminary_score', 0)
                
                if score > best_score:
                    term_to_best[term] = candidate_dict
        
        return list(term_to_best.values())
    
    def _score_classical_candidates(self, candidates: List[Dict], period: str) -> List[Dict]:
        """Score candidates with lightweight heuristics."""

        period_bonuses = {
            'medieval': 0.8,
            'elizabethan': 0.7,
            'jacobean': 0.6,
            'restoration': 0.5,
            'augustan': 0.5,
            'romantic': 0.4,
            'classical': 0.4,
        }

        period_bonus = period_bonuses.get(period, 0.3)

        for candidate in candidates:
            score = candidate.get('preliminary_score', 5.0)

            # Period context provides a small bump to keep metadata valuable
            score += period_bonus

            term = candidate['term']
            term_length = len(term)

            # Prefer medium-length or longer words; penalise very short single tokens
            if ' ' not in term and term_length < 4:
                score -= 1.0
            elif 6 <= term_length <= 12:
                score += 0.8
            elif term_length > 12:
                score += 0.4

            # Multi-word expressions and hyphenated forms tend to be more specialised
            if ' ' in term:
                score += 0.6
            if '-' in term:
                score += 0.3

            # POS and morphological hints from the extractor
            pos_hint = candidate.get('part_of_speech') or ''
            if pos_hint.upper() in {'NOUN', 'ADJECTIVE'}:
                score += 0.2

            morph_types = candidate.get('morphological_type', [])
            if morph_types:
                score += min(0.2 * len(morph_types), 0.6)

            # Reward richer contexts
            context_length = len(candidate.get('context', ''))
            if context_length > 80:
                score += 0.3

            candidate['preliminary_score'] = min(12.0, max(0.0, score))

        candidates.sort(key=lambda x: x['preliminary_score'], reverse=True)
        return candidates
    
    async def store_candidates(self, candidates: List[Dict], batch_id: str):
        """Store classical vocabulary candidates in database"""
        if not candidates:
            return
        
        try:
            conn = mysql.connector.connect(**self.db_config)
            cursor = conn.cursor()
            
            insert_query = """
                INSERT INTO vocab.candidate_words 
                (term, source_type, part_of_speech, utility_score, rarity_indicators,
                 context_snippet, raw_definition, etymology_preview, date_discovered)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """
            
            # First, filter out duplicate candidates
            filtered_candidates, dedup_stats = filter_duplicate_candidates(candidates)
            self.logger.info(f"Deduplication: {dedup_stats['unique']}/{dedup_stats['total']} candidates are unique "
                           f"(filtered {dedup_stats['duplicates']} duplicates)")
            
            values = []
            validated_candidates = []
            precheck_rejected = 0
            non_english_rejected = 0
            frequency_rejected = 0

            for candidate in filtered_candidates:
                term = candidate['term']
                normalized_term = term.lower()

                # Quick heuristics to skip obviously common or short tokens
                if (' ' not in normalized_term and len(normalized_term) < 4) or normalized_term in COMMON_WORDS:
                    precheck_rejected += 1
                    continue
                if any(char.isdigit() for char in normalized_term):
                    precheck_rejected += 1
                    continue

                # Validate English word before storing
                is_english, reason = validate_english_word(term)

                if not is_english:
                    non_english_rejected += 1
                    self.logger.debug(f"Rejected non-English word '{term}': {reason}")
                    continue

                # Require the term to be rare according to wordfreq
                zipf_score = zipf_frequency(term, 'en')
                if zipf_score is not None and zipf_score >= 1.75:
                    frequency_rejected += 1
                    self.logger.debug(
                        "Skipped common word '%s' (Zipf frequency %.2f)",
                        term,
                        zipf_score,
                    )
                    continue

                source_metadata = candidate.get('source_metadata', {})
                linguistic_features = candidate.get('linguistic_features', {})

                metadata = {
                    'author': source_metadata.get('author'),
                    'title': source_metadata.get('title'),
                    'literary_period': source_metadata.get('literary_period'),
                    'linguistic_signals': {
                        'pos': candidate.get('part_of_speech'),
                        'features': linguistic_features,
                    },
                    'morphological_type': candidate.get('morphological_type', []),
                    'validation_reason': reason,
                    'wordfreq_zipf': zipf_score,
                }

                raw_definition = (
                    f"Classical term from {source_metadata.get('author', 'unknown author')}"
                )

                values.append((
                    term,
                    'gutenberg',
                    candidate.get('part_of_speech', 'unknown'),
                    candidate.get('preliminary_score', 5.0),
                    json.dumps(metadata),
                    candidate.get('context', '')[:500],
                    raw_definition[:500],
                    json.dumps({'literary_period': source_metadata.get('literary_period')})[:500],
                    datetime.now()
                ))

                validated_candidates.append(candidate)

            if values:
                cursor.executemany(insert_query, values)
                conn.commit()

            total_filtered = (
                dedup_stats['duplicates'] + precheck_rejected + non_english_rejected + frequency_rejected
            )
            self.logger.info(
                "Stored %d classical vocabulary candidates (filtered %d total: %d duplicates, %d pre-check, %d non-English, %d not rare enough)",
                len(validated_candidates),
                total_filtered,
                dedup_stats['duplicates'],
                precheck_rejected,
                non_english_rejected,
                frequency_rejected,
            )
            
        except Error as e:
            self.logger.error(f"Database error storing candidates: {e}")
            
        finally:
            if 'conn' in locals() and conn.is_connected():
                cursor.close()
                conn.close()


# Test the Gutenberg harvester
async def test_gutenberg_harvester():
    """Test the Gutenberg harvester"""
    logging.basicConfig(level=logging.INFO)
    
    db_config = get_db_config()
    harvester = ProjectGutenbergHarvester(db_config)
    
    print("Testing Project Gutenberg Harvester")
    print("=" * 50)
    
    # Get some classical texts
    books = await harvester.get_vocabulary_rich_texts(max_books=3)
    
    print(f"Successfully harvested {len(books)} books:")
    
    all_candidates = []
    for book in books:
        print(f"\nBook: {book['title']} by {book['author']}")
        print(f"   Period: {book['literary_period']}")
        print(f"   Content length: {len(book['content'])} characters")
        
        # Extract vocabulary
        candidates = harvester.extract_classical_vocabulary(book)
        all_candidates.extend(candidates)
        
        print(f"   Vocabulary candidates: {len(candidates)}")
        
        # Show top 5 candidates
        if candidates:
            print("   Top candidates:")
            for i, candidate in enumerate(candidates[:5]):
                print(f"     {i+1}. {candidate['term']} (score: {candidate['preliminary_score']:.1f})")
    
    # Store candidates
    if all_candidates:
        batch_id = f"gutenberg_test_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        await harvester.store_candidates(all_candidates, batch_id)
        
        print(f"\nStored {len(all_candidates)} total candidates in database")
    
    # Show session stats
    stats = harvester.scraper.get_session_stats()
    if stats:
        print(f"\nScraping session stats:")
        for source, stat in stats.items():
            print(f"   {source}: {stat['pages_scraped']} pages, {stat['daily_count']}/{stat['daily_limit']} daily")


if __name__ == "__main__":
    asyncio.run(test_gutenberg_harvester())
