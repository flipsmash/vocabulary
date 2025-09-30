#!/usr/bin/env python3
"""
Resumable Gutenberg Harvester - Enhanced version with progress tracking
"""

import asyncio
from typing import List, Dict, Any
from gutenberg_harvester import ProjectGutenbergHarvester
from progress_tracker import ResumableHarvester
import logging

logger = logging.getLogger(__name__)

class ResumableGutenbergHarvester(ResumableHarvester):
    """Gutenberg harvester that can resume from where it left off"""
    
    def __init__(self, db_config):
        super().__init__('gutenberg')
        self.gutenberg = ProjectGutenbergHarvester(db_config)
    
    async def harvest_with_resumption(self, max_books: int = 50, 
                                    target_candidates: int = 100) -> Dict[str, Any]:
        """
        Harvest classical literature with full resumption support
        """
        # Start session and get resumption point
        position = self.start_harvest_session()
        
        try:
            # Get position markers
            book_index = position.get('book_index', 0)
            author_offset = position.get('author_offset', 0) 
            last_book_id = position.get('last_book_id')
            
            logger.info(f"Resuming Gutenberg harvest from book_index={book_index}, author_offset={author_offset}")
            
            total_processed = 0
            total_candidates = 0
            all_candidates = []
            
            # Get available authors starting from offset
            authors = await self.gutenberg.get_target_authors()
            remaining_authors = authors[author_offset:] if author_offset < len(authors) else []
            
            if not remaining_authors and author_offset > 0:
                # We've processed all authors, reset to beginning
                remaining_authors = authors
                author_offset = 0
                book_index = 0
                logger.info("Completed all authors, restarting from beginning")
            
            for current_author_index, author in enumerate(remaining_authors):
                actual_author_index = author_offset + current_author_index
                
                logger.info(f"Processing author {actual_author_index + 1}/{len(authors)}: {author}")
                
                # Get books for this author, starting from book_index if it's the first author
                books_to_skip = book_index if current_author_index == 0 else 0
                
                try:
                    # Get books from this author
                    author_books = await self.gutenberg.get_vocabulary_rich_texts(
                        max_books=max_books,
                        target_author=author
                    )
                    
                    # Skip books we've already processed
                    remaining_books = author_books[books_to_skip:] if books_to_skip < len(author_books) else []
                    
                    for book_idx, book in enumerate(remaining_books):
                        current_book_index = books_to_skip + book_idx
                        
                        logger.info(f"Processing book {current_book_index + 1} from {author}: {book.get('title', 'Unknown')}")
                        
                        # Extract vocabulary from this book
                        candidates = self.gutenberg.extract_classical_vocabulary(book)
                        all_candidates.extend(candidates)
                        
                        total_processed += 1
                        total_candidates += len(candidates)
                        
                        # Update progress every book
                        current_position = {
                            'book_index': current_book_index + 1,
                            'author_offset': actual_author_index,
                            'last_book_id': book.get('book_id'),
                            'last_book_title': book.get('title')
                        }
                        
                        self.save_position(current_position)
                        self.update_progress(
                            processed=1,
                            candidates_found=len(candidates),
                            position_markers=current_position
                        )
                        
                        # Check if we have enough candidates
                        if total_candidates >= target_candidates:
                            logger.info(f"Reached target of {target_candidates} candidates")
                            break
                    
                    # Reset book_index when moving to next author
                    book_index = 0
                    
                    # Update position for next author
                    if total_candidates < target_candidates:
                        next_position = {
                            'book_index': 0,
                            'author_offset': actual_author_index + 1,
                            'last_book_id': None
                        }
                        self.save_position(next_position)
                
                except Exception as e:
                    logger.error(f"Error processing author {author}: {e}")
                    # Save position so we can retry this author
                    error_position = {
                        'book_index': book_index,
                        'author_offset': actual_author_index,
                        'last_book_id': last_book_id,
                        'error_author': author
                    }
                    self.save_position(error_position)
                    continue
                
                if total_candidates >= target_candidates:
                    break
            
            # End session successfully
            self.end_harvest_session('completed')
            
            # If we processed all authors and books, reset for next run
            if actual_author_index >= len(authors) - 1:
                reset_position = {
                    'book_index': 0,
                    'author_offset': 0, 
                    'last_book_id': None,
                    'cycle_complete': True
                }
                self.save_position(reset_position)
                logger.info("Completed full cycle of all authors")
            
            return {
                'status': 'completed',
                'books_processed': total_processed,
                'candidates_found': total_candidates,
                'authors_processed': current_author_index + 1,
                'position': current_position,
                'candidates': all_candidates[:target_candidates]  # Return up to target
            }
            
        except Exception as e:
            logger.error(f"Error in resumable harvest: {e}")
            self.end_harvest_session('error', str(e))
            return {
                'status': 'error',
                'error': str(e),
                'books_processed': total_processed,
                'candidates_found': total_candidates
            }

async def main():
    """Test the resumable harvester"""
    from config import get_db_config
    
    logging.basicConfig(level=logging.INFO)
    
    harvester = ResumableGutenbergHarvester(get_db_config())
    
    print("Testing resumable Gutenberg harvester...")
    
    # First run
    print("\n=== First Run ===")
    result1 = await harvester.harvest_with_resumption(max_books=5, target_candidates=20)
    print(f"Result 1: {result1['status']}")
    print(f"Books processed: {result1['books_processed']}")
    print(f"Candidates found: {result1['candidates_found']}")
    
    # Second run (should resume from where first left off)
    print("\n=== Second Run (Resume) ===")
    harvester2 = ResumableGutenbergHarvester(get_db_config())
    result2 = await harvester2.harvest_with_resumption(max_books=5, target_candidates=20)
    print(f"Result 2: {result2['status']}")
    print(f"Books processed: {result2['books_processed']}")
    print(f"Candidates found: {result2['candidates_found']}")
    
    # Check progress
    from progress_tracker import ProgressTracker
    tracker = ProgressTracker()
    progress = tracker.get_source_progress('gutenberg')
    if progress:
        print(f"\nFinal Position: {progress.last_position}")
        print(f"Total processed: {progress.items_processed}")
        print(f"Total candidates: {progress.candidates_found}")

if __name__ == "__main__":
    asyncio.run(main())