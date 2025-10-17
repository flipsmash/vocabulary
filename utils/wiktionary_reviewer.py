#!/usr/bin/env python3
"""
Wiktionary Reviewer - CLI interface for reviewing harvested candidate words
"""

import mysql.connector
from mysql.connector import Error
import json
import sys
from typing import Dict, List, Optional
from dataclasses import dataclass
from config import get_db_config
import textwrap

@dataclass
class CandidateWord:
    id: int
    term: str
    source_type: str
    part_of_speech: str
    utility_score: float
    rarity_indicators: str
    context_snippet: Optional[str]
    raw_definition: str
    etymology_preview: Optional[str]
    date_discovered: str
    days_pending: int

class WordReviewer:
    """CLI interface for reviewing candidate words"""
    
    def __init__(self):
        self.db_config = get_db_config()
        
    def get_pending_candidates(self, limit: int = 20) -> List[CandidateWord]:
        """Fetch pending candidates ordered by score"""
        try:
            conn = mysql.connector.connect(**self.db_config)
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT id, term, source_type, part_of_speech, utility_score,
                       rarity_indicators, context_snippet, raw_definition,
                       etymology_preview, date_discovered,
                       DATEDIFF(CURRENT_DATE, date_discovered) as days_pending
                FROM vocab.candidate_words
                WHERE review_status = 'pending'
                ORDER BY utility_score DESC, date_discovered ASC
                LIMIT %s
            """, (limit,))
            
            results = cursor.fetchall()
            
            candidates = []
            for row in results:
                candidates.append(CandidateWord(
                    id=row[0], term=row[1], source_type=row[2],
                    part_of_speech=row[3], utility_score=row[4],
                    rarity_indicators=row[5], context_snippet=row[6],
                    raw_definition=row[7], etymology_preview=row[8],
                    date_discovered=str(row[9]), days_pending=row[10]
                ))
            
            return candidates
            
        except Error as e:
            print(f"Database error: {e}")
            return []
        finally:
            if 'conn' in locals() and conn.is_connected():
                cursor.close()
                conn.close()
    
    def approve_candidate(self, candidate_id: int, notes: Optional[str] = None) -> bool:
        """Mark candidate as approved"""
        return self._update_review_status(candidate_id, 'approved', notes=notes)
    
    def reject_candidate(self, candidate_id: int, reason: str, notes: Optional[str] = None) -> bool:
        """Mark candidate as rejected with reason"""
        return self._update_review_status(candidate_id, 'rejected', reason=reason, notes=notes)
    
    def needs_info_candidate(self, candidate_id: int, notes: str) -> bool:
        """Mark candidate as needing more information"""
        return self._update_review_status(candidate_id, 'needs_info', notes=notes)
    
    def _update_review_status(self, candidate_id: int, status: str, 
                             reason: Optional[str] = None, notes: Optional[str] = None) -> bool:
        """Update candidate review status"""
        try:
            conn = mysql.connector.connect(**self.db_config)
            cursor = conn.cursor()
            
            cursor.execute("""
                UPDATE vocab.candidate_words 
                SET review_status = %s, rejection_reason = %s, notes = %s,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = %s
            """, (status, reason, notes, candidate_id))
            
            conn.commit()
            return cursor.rowcount > 0
            
        except Error as e:
            print(f"Database error: {e}")
            return False
        finally:
            if 'conn' in locals() and conn.is_connected():
                cursor.close()
                conn.close()
    
    def get_review_stats(self) -> Dict[str, int]:
        """Get review statistics"""
        try:
            conn = mysql.connector.connect(**self.db_config)
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT review_status, COUNT(*) as count
                FROM vocab.candidate_words
                GROUP BY review_status
            """)
            
            stats = dict(cursor.fetchall())
            return stats
            
        except Error as e:
            print(f"Database error: {e}")
            return {}
        finally:
            if 'conn' in locals() and conn.is_connected():
                cursor.close()
                conn.close()

class ReviewInterface:
    """Interactive CLI review interface"""
    
    def __init__(self):
        self.reviewer = WordReviewer()
        self.session_approved = 0
        self.session_rejected = 0
        self.session_skipped = 0
    
    def display_candidate(self, candidate: CandidateWord) -> None:
        """Display candidate word details for review"""
        print("\n" + "=" * 80)
        print(f"WORD: {candidate.term.upper()}")
        print(f"Score: {candidate.utility_score:.2f} | POS: {candidate.part_of_speech} | "
              f"Pending: {candidate.days_pending} days")
        print("-" * 80)
        
        # Definition
        definition = textwrap.fill(candidate.raw_definition, width=76)
        print(f"Definition: {definition}")
        
        # Context/example
        if candidate.context_snippet:
            context = textwrap.fill(f"Context: {candidate.context_snippet}", width=76)
            print(f"\n{context}")
        
        # Etymology
        if candidate.etymology_preview:
            etymology = textwrap.fill(f"Etymology: {candidate.etymology_preview}", width=76)
            print(f"\n{etymology}")
        
        # Rarity indicators
        try:
            tags_data = json.loads(candidate.rarity_indicators)
            if 'tags' in tags_data and tags_data['tags']:
                print(f"\nTags: {', '.join(tags_data['tags'])}")
        except (json.JSONDecodeError, KeyError):
            pass
        
        print("-" * 80)
    
    def get_user_decision(self) -> str:
        """Get user decision on current candidate"""
        while True:
            print("\nActions:")
            print("  (a)ccept  - Add to approved vocabulary")
            print("  (r)eject  - Reject with reason")  
            print("  (i)nfo   - Mark as needing more info")
            print("  (s)kip    - Skip for now")
            print("  (q)uit    - End review session")
            print("  (h)elp    - Show help")
            
            choice = input("\nChoose action: ").lower().strip()
            
            if choice in ['a', 'r', 'i', 's', 'q', 'h']:
                return choice
            else:
                print("Invalid choice. Please try again.")
    
    def handle_approval(self, candidate: CandidateWord) -> bool:
        """Handle candidate approval"""
        notes = input("Notes (optional): ").strip()
        
        if self.reviewer.approve_candidate(candidate.id, notes or None):
            print(f"[APPROVED] {candidate.term}")
            self.session_approved += 1
            return True
        else:
            print(f"[ERROR] Failed to approve {candidate.term}")
            return False
    
    def handle_rejection(self, candidate: CandidateWord) -> bool:
        """Handle candidate rejection"""
        print("\nCommon rejection reasons:")
        print("  1. Too obscure/specialized")
        print("  2. Poor definition quality") 
        print("  3. Not actually archaic/rare")
        print("  4. Technical jargon")
        print("  5. Duplicate of existing word")
        print("  6. Other")
        
        reason_choice = input("Reason (1-6 or custom): ").strip()
        
        reason_map = {
            '1': 'Too obscure/specialized',
            '2': 'Poor definition quality',
            '3': 'Not actually archaic/rare',
            '4': 'Technical jargon', 
            '5': 'Duplicate of existing word',
            '6': 'Other'
        }
        
        if reason_choice in reason_map:
            if reason_choice == '6':
                reason = input("Custom reason: ").strip()
            else:
                reason = reason_map[reason_choice]
        else:
            reason = reason_choice
        
        notes = input("Additional notes (optional): ").strip()
        
        if self.reviewer.reject_candidate(candidate.id, reason, notes or None):
            print(f"[REJECTED] {candidate.term} - {reason}")
            self.session_rejected += 1
            return True
        else:
            print(f"[ERROR] Failed to reject {candidate.term}")
            return False
    
    def handle_needs_info(self, candidate: CandidateWord) -> bool:
        """Handle marking candidate as needing info"""
        notes = input("What information is needed? ").strip()
        
        if not notes:
            print("Notes required for 'needs info' status")
            return False
        
        if self.reviewer.needs_info_candidate(candidate.id, notes):
            print(f"[NEEDS INFO] {candidate.term}")
            return True
        else:
            print(f"[ERROR] Failed to update {candidate.term}")
            return False
    
    def show_help(self) -> None:
        """Show help information"""
        print("\n" + "=" * 80)
        print("VOCABULARY REVIEW HELP")
        print("=" * 80)
        print("""
This tool helps you review candidate words harvested from Wiktionary.

SCORING CRITERIA:
- Words are scored 0-10 based on utility for vocabulary building
- Higher scores = more useful/interesting words
- Factors: length, etymology richness, recognizable morphology, rarity tags

APPROVAL GUIDELINES:
- Accept words that would be interesting to learn
- Consider whether the word has practical application
- Prefer words with clear, well-written definitions
- Etymology adds educational value

REJECTION REASONS:
- Too specialized/technical for general vocabulary
- Poor or confusing definition 
- Not actually rare (mislabeled by Wiktionary)
- Duplicate of existing vocabulary

The goal is building a curated collection of fascinating, learnable words!
        """)
        print("=" * 80)
    
    def show_session_stats(self) -> None:
        """Show current session statistics"""
        total = self.session_approved + self.session_rejected + self.session_skipped
        if total > 0:
            print(f"\nSession Stats: {total} reviewed | "
                  f"{self.session_approved} approved | "
                  f"{self.session_rejected} rejected | "
                  f"{self.session_skipped} skipped")
    
    def review_session(self, limit: int = 20) -> None:
        """Interactive review session"""
        print("Vocabulary Candidate Review Session")
        print("=" * 80)
        
        # Show overall stats first
        stats = self.reviewer.get_review_stats()
        if stats:
            print("Current Review Status:")
            for status, count in stats.items():
                print(f"  {status.title()}: {count}")
        
        # Get candidates to review
        candidates = self.reviewer.get_pending_candidates(limit)
        
        if not candidates:
            print("\nNo pending candidates found!")
            return
        
        print(f"\nStarting review of {len(candidates)} candidates...\n")
        
        for i, candidate in enumerate(candidates, 1):
            print(f"\n[{i}/{len(candidates)}]")
            self.display_candidate(candidate)
            
            while True:
                decision = self.get_user_decision()
                
                if decision == 'a':
                    if self.handle_approval(candidate):
                        break
                elif decision == 'r':
                    if self.handle_rejection(candidate):
                        break
                elif decision == 'i':
                    if self.handle_needs_info(candidate):
                        break
                elif decision == 's':
                    print(f"[SKIPPED] {candidate.term}")
                    self.session_skipped += 1
                    break
                elif decision == 'q':
                    print("\nEnding review session...")
                    self.show_session_stats()
                    return
                elif decision == 'h':
                    self.show_help()
                    continue
        
        print("\nReview session complete!")
        self.show_session_stats()

def main():
    """Main CLI interface"""
    import argparse
    
    parser = argparse.ArgumentParser(description='Review harvested vocabulary candidates')
    parser.add_argument('--limit', type=int, default=20,
                       help='Maximum number of candidates to review')
    parser.add_argument('--stats', action='store_true',
                       help='Show review statistics and exit')
    
    args = parser.parse_args()
    
    interface = ReviewInterface()
    
    if args.stats:
        stats = interface.reviewer.get_review_stats()
        print("Review Statistics:")
        print("-" * 30)
        for status, count in stats.items():
            print(f"{status.title():15}: {count:>5}")
    else:
        try:
            interface.review_session(args.limit)
        except KeyboardInterrupt:
            print("\n\nReview session interrupted by user")
            interface.show_session_stats()
        except Exception as e:
            print(f"\nError during review: {e}")

if __name__ == "__main__":
    main()