#!/usr/bin/env python3
"""
Progress Tracking and Resumption System for Vocabulary Harvesting
Keeps track of where each source left off and allows seamless resumption
"""

import json
import mysql.connector
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, asdict
import sys
import os
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
sys.path.insert(0, parent_dir)
from core.secure_config import get_db_config
import logging

logger = logging.getLogger(__name__)

@dataclass
class SourceProgress:
    """Track progress for a specific source"""
    source_type: str
    last_position: Dict[str, Any]  # Source-specific position markers
    items_processed: int
    candidates_found: int
    last_run: datetime
    status: str  # 'active', 'paused', 'completed', 'error'
    error_message: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None

@dataclass
class HarvestSession:
    """Represents a harvesting session"""
    session_id: Optional[int]
    source_type: str
    started_at: datetime
    total_processed: int
    candidates_found: int
    candidates_accepted: int
    status: str
    position_markers: Dict[str, Any]
    error_message: Optional[str] = None

class ProgressTracker:
    """Manages progress tracking across all vocabulary sources"""
    
    def __init__(self):
        self.db_config = get_db_config()
    
    def get_source_progress(self, source_type: str) -> Optional[SourceProgress]:
        """Get current progress for a source"""
        try:
            conn = mysql.connector.connect(**self.db_config)
            cursor = conn.cursor(dictionary=True)
            
            # Get latest session info
            cursor.execute("""
                SELECT source_type, session_end as last_run, total_processed, 
                       candidates_found, status, error_message, notes
                FROM harvesting_sessions 
                WHERE source_type = %s 
                ORDER BY session_end DESC 
                LIMIT 1
            """, (source_type,))
            
            session = cursor.fetchone()
            if not session:
                return None
            
            # Get position markers from harvester_config
            cursor.execute("""
                SELECT config_key, config_value 
                FROM harvester_config 
                WHERE source_type = %s
                AND config_key LIKE '%_position%' OR config_key LIKE '%_offset%'
            """, (source_type,))
            
            position_data = cursor.fetchall()
            last_position = {}
            for row in position_data:
                try:
                    last_position[row['config_key']] = json.loads(row['config_value'])
                except:
                    last_position[row['config_key']] = row['config_value']
            
            # Get metadata
            cursor.execute("""
                SELECT config_key, config_value 
                FROM harvester_config 
                WHERE source_type = %s
                AND config_key NOT LIKE '%_position%' AND config_key NOT LIKE '%_offset%'
            """, (source_type,))
            
            metadata_rows = cursor.fetchall()
            metadata = {}
            for row in metadata_rows:
                try:
                    metadata[row['config_key']] = json.loads(row['config_value'])
                except:
                    metadata[row['config_key']] = row['config_value']
            
            return SourceProgress(
                source_type=session['source_type'],
                last_position=last_position,
                items_processed=session['total_processed'] or 0,
                candidates_found=session['candidates_found'] or 0,
                last_run=session['last_run'],
                status=session['status'] or 'unknown',
                error_message=session['error_message'],
                metadata=metadata
            )
            
        except Exception as e:
            logger.error(f"Error getting source progress for {source_type}: {e}")
            return None
        finally:
            if 'conn' in locals() and conn.is_connected():
                cursor.close()
                conn.close()
    
    def save_progress(self, progress: SourceProgress) -> bool:
        """Save current progress for a source"""
        try:
            conn = mysql.connector.connect(**self.db_config)
            cursor = conn.cursor()
            
            # Save position markers to harvester_config
            for key, value in progress.last_position.items():
                cursor.execute("""
                    INSERT INTO harvester_config (source_type, config_key, config_value, last_updated)
                    VALUES (%s, %s, %s, %s)
                    ON DUPLICATE KEY UPDATE 
                    config_value = VALUES(config_value),
                    last_updated = VALUES(last_updated)
                """, (
                    progress.source_type,
                    key,
                    json.dumps(value) if isinstance(value, (dict, list)) else str(value),
                    datetime.now()
                ))
            
            # Save metadata
            if progress.metadata:
                for key, value in progress.metadata.items():
                    cursor.execute("""
                        INSERT INTO harvester_config (source_type, config_key, config_value, last_updated)
                        VALUES (%s, %s, %s, %s)
                        ON DUPLICATE KEY UPDATE 
                        config_value = VALUES(config_value),
                        last_updated = VALUES(last_updated)
                    """, (
                        progress.source_type,
                        key,
                        json.dumps(value) if isinstance(value, (dict, list)) else str(value),
                        datetime.now()
                    ))
            
            conn.commit()
            logger.info(f"Saved progress for {progress.source_type}")
            return True
            
        except Exception as e:
            logger.error(f"Error saving progress for {progress.source_type}: {e}")
            return False
        finally:
            if 'conn' in locals() and conn.is_connected():
                cursor.close()
                conn.close()
    
    def start_session(self, source_type: str, position_markers: Dict[str, Any] = None) -> int:
        """Start a new harvesting session"""
        try:
            conn = mysql.connector.connect(**self.db_config)
            cursor = conn.cursor()
            
            cursor.execute("""
                INSERT INTO harvesting_sessions 
                (source_type, session_start, status, notes)
                VALUES (%s, %s, %s, %s)
            """, (
                source_type,
                datetime.now(),
                'active',
                json.dumps(position_markers) if position_markers else None
            ))
            
            session_id = cursor.lastrowid
            conn.commit()
            
            logger.info(f"Started session {session_id} for {source_type}")
            return session_id
            
        except Exception as e:
            logger.error(f"Error starting session for {source_type}: {e}")
            return None
        finally:
            if 'conn' in locals() and conn.is_connected():
                cursor.close()
                conn.close()
    
    def update_session(self, session_id: int, processed: int = 0, 
                      candidates_found: int = 0, candidates_accepted: int = 0,
                      position_markers: Dict[str, Any] = None) -> bool:
        """Update session progress"""
        try:
            conn = mysql.connector.connect(**self.db_config)
            cursor = conn.cursor()
            
            update_parts = []
            params = []
            
            if processed > 0:
                update_parts.append("total_processed = COALESCE(total_processed, 0) + %s")
                params.append(processed)
            
            if candidates_found > 0:
                update_parts.append("candidates_found = COALESCE(candidates_found, 0) + %s")
                params.append(candidates_found)
                
            if candidates_accepted > 0:
                update_parts.append("candidates_accepted = COALESCE(candidates_accepted, 0) + %s")
                params.append(candidates_accepted)
                
            if position_markers:
                update_parts.append("notes = %s")
                params.append(json.dumps(position_markers))
            
            if update_parts:
                params.append(session_id)
                cursor.execute(f"""
                    UPDATE harvesting_sessions 
                    SET {', '.join(update_parts)}
                    WHERE id = %s
                """, params)
                
                conn.commit()
                return True
                
        except Exception as e:
            logger.error(f"Error updating session {session_id}: {e}")
            return False
        finally:
            if 'conn' in locals() and conn.is_connected():
                cursor.close()
                conn.close()
        
        return False
    
    def end_session(self, session_id: int, status: str = 'completed', 
                   error_message: str = None) -> bool:
        """End a harvesting session"""
        try:
            conn = mysql.connector.connect(**self.db_config)
            cursor = conn.cursor()
            
            cursor.execute("""
                UPDATE harvesting_sessions 
                SET session_end = %s, status = %s, error_message = %s
                WHERE id = %s
            """, (datetime.now(), status, error_message, session_id))
            
            conn.commit()
            logger.info(f"Ended session {session_id} with status: {status}")
            return True
            
        except Exception as e:
            logger.error(f"Error ending session {session_id}: {e}")
            return False
        finally:
            if 'conn' in locals() and conn.is_connected():
                cursor.close()
                conn.close()
    
    def get_resumption_point(self, source_type: str) -> Dict[str, Any]:
        """Get the point where harvesting should resume for a source"""
        progress = self.get_source_progress(source_type)
        
        if not progress:
            # No previous progress, start from beginning
            return self._get_default_starting_point(source_type)
        
        # Check if last run was successful
        if progress.status in ['completed', 'active']:
            return progress.last_position
        elif progress.status == 'error':
            # If there was an error, go back a bit to retry
            return self._adjust_position_for_retry(source_type, progress.last_position)
        else:
            return progress.last_position
    
    def _get_default_starting_point(self, source_type: str) -> Dict[str, Any]:
        """Get default starting point for each source type"""
        defaults = {
            'arxiv': {'start_index': 0, 'query_offset': 0, 'last_id': None},
            'wikipedia': {'page_offset': 0, 'category_index': 0, 'last_title': None},
            'news_api': {'page': 1, 'last_published': None},
            'gutenberg': {'book_index': 0, 'last_book_id': None, 'author_offset': 0},
            'wiktionary': {'category_offset': 0, 'page_offset': 0, 'last_title': None},
            'pubmed': {'start_index': 0, 'last_pmid': None},
            'universal_extractor': {'document_offset': 0, 'last_doc_id': None}
        }
        return defaults.get(source_type, {})
    
    def _adjust_position_for_retry(self, source_type: str, last_position: Dict[str, Any]) -> Dict[str, Any]:
        """Adjust position to retry after error"""
        adjusted = last_position.copy()
        
        # Go back a bit depending on source type
        if source_type == 'arxiv' and 'start_index' in adjusted:
            adjusted['start_index'] = max(0, adjusted['start_index'] - 10)
        elif source_type == 'gutenberg' and 'book_index' in adjusted:
            adjusted['book_index'] = max(0, adjusted['book_index'] - 1)
        elif source_type in ['wikipedia', 'wiktionary'] and 'page_offset' in adjusted:
            adjusted['page_offset'] = max(0, adjusted['page_offset'] - 5)
        
        return adjusted
    
    def get_all_source_status(self) -> Dict[str, Dict[str, Any]]:
        """Get status of all sources"""
        sources = ['arxiv', 'wikipedia', 'news_api', 'gutenberg', 'wiktionary', 'pubmed', 'universal_extractor']
        status = {}
        
        for source in sources:
            progress = self.get_source_progress(source)
            if progress:
                status[source] = {
                    'status': progress.status,
                    'last_run': progress.last_run.isoformat() if progress.last_run else None,
                    'items_processed': progress.items_processed,
                    'candidates_found': progress.candidates_found,
                    'position': progress.last_position,
                    'error': progress.error_message
                }
            else:
                status[source] = {
                    'status': 'never_run',
                    'last_run': None,
                    'items_processed': 0,
                    'candidates_found': 0,
                    'position': self._get_default_starting_point(source),
                    'error': None
                }
        
        return status
    
    def should_run_source(self, source_type: str, min_interval_hours: int = 1) -> bool:
        """Check if enough time has passed to run a source again"""
        progress = self.get_source_progress(source_type)
        
        if not progress:
            return True  # Never run before
            
        if progress.status == 'error':
            return True  # Retry errors immediately
            
        # Check time since last run
        time_since = datetime.now() - progress.last_run
        return time_since.total_seconds() >= min_interval_hours * 3600
    
    def reset_source_progress(self, source_type: str) -> bool:
        """Reset progress for a source (start from beginning)"""
        try:
            conn = mysql.connector.connect(**self.db_config)
            cursor = conn.cursor()
            
            # Clear harvester_config entries
            cursor.execute("""
                DELETE FROM harvester_config 
                WHERE source_type = %s
            """, (source_type,))
            
            conn.commit()
            logger.info(f"Reset progress for {source_type}")
            return True
            
        except Exception as e:
            logger.error(f"Error resetting progress for {source_type}: {e}")
            return False
        finally:
            if 'conn' in locals() and conn.is_connected():
                cursor.close()
                conn.close()


class ResumableHarvester:
    """Base class for harvesters that support resumption"""
    
    def __init__(self, source_type: str):
        self.source_type = source_type
        self.tracker = ProgressTracker()
        self.session_id = None
    
    def start_harvest_session(self) -> Dict[str, Any]:
        """Start a harvesting session and get resumption point"""
        resumption_point = self.tracker.get_resumption_point(self.source_type)
        self.session_id = self.tracker.start_session(self.source_type, resumption_point)
        
        logger.info(f"Starting {self.source_type} harvest from: {resumption_point}")
        return resumption_point
    
    def update_progress(self, processed: int = 0, candidates_found: int = 0, 
                       candidates_accepted: int = 0, position_markers: Dict[str, Any] = None):
        """Update session progress"""
        if self.session_id:
            self.tracker.update_session(
                self.session_id, processed, candidates_found, 
                candidates_accepted, position_markers
            )
    
    def save_position(self, position_markers: Dict[str, Any]):
        """Save current position for resumption"""
        progress = SourceProgress(
            source_type=self.source_type,
            last_position=position_markers,
            items_processed=0,  # Will be updated in session
            candidates_found=0,  # Will be updated in session  
            last_run=datetime.now(),
            status='active'
        )
        self.tracker.save_progress(progress)
    
    def end_harvest_session(self, status: str = 'completed', error_message: str = None):
        """End the harvesting session"""
        if self.session_id:
            self.tracker.end_session(self.session_id, status, error_message)


# CLI interface for progress management
def main():
    import argparse
    
    parser = argparse.ArgumentParser(description='Vocabulary Harvesting Progress Tracker')
    parser.add_argument('--status', action='store_true', help='Show status of all sources')
    parser.add_argument('--reset', help='Reset progress for a specific source')
    parser.add_argument('--source', help='Show detailed status for specific source')
    
    args = parser.parse_args()
    
    tracker = ProgressTracker()
    
    if args.status:
        status = tracker.get_all_source_status()
        print("Vocabulary Harvesting Progress Status")
        print("=" * 50)
        
        for source, info in status.items():
            print(f"\n{source.upper()}:")
            print(f"  Status: {info['status']}")
            print(f"  Last run: {info['last_run'] or 'Never'}")
            print(f"  Items processed: {info['items_processed']:,}")
            print(f"  Candidates found: {info['candidates_found']:,}")
            if info['error']:
                print(f"  Error: {info['error']}")
            print(f"  Position: {info['position']}")
    
    elif args.reset:
        if tracker.reset_source_progress(args.reset):
            print(f"Reset progress for {args.reset}")
        else:
            print(f"Failed to reset progress for {args.reset}")
    
    elif args.source:
        progress = tracker.get_source_progress(args.source)
        if progress:
            print(f"Progress for {args.source}:")
            print(f"  Status: {progress.status}")
            print(f"  Last run: {progress.last_run}")
            print(f"  Items processed: {progress.items_processed:,}")
            print(f"  Candidates found: {progress.candidates_found:,}")
            print(f"  Position: {progress.last_position}")
            if progress.error_message:
                print(f"  Error: {progress.error_message}")
            if progress.metadata:
                print(f"  Metadata: {progress.metadata}")
        else:
            print(f"No progress found for {args.source}")


if __name__ == "__main__":
    main()