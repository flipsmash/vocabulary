#!/usr/bin/env python3
"""
Definition Reviewer - Interactive tool for reviewing and correcting circular definitions
"""

import mysql.connector
from typing import List, Dict, Optional
from config import get_db_config
from circular_definition_detector import CircularDefinitionDetector

class DefinitionReviewer:
    def __init__(self):
        self.config = get_db_config()
        self.detector = CircularDefinitionDetector()
    
    def get_connection(self):
        return mysql.connector.connect(**self.config)
    
    def get_problematic_definitions(self, limit: int = 20) -> List[Dict]:
        """Get definitions that need manual review"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT id, term, definition, corrected_definition, part_of_speech
            FROM defined 
            WHERE has_circular_definition = TRUE 
            AND (corrected_definition IS NULL OR LENGTH(corrected_definition) < 20)
            ORDER BY term
            LIMIT %s
        """, (limit,))
        
        results = []
        for row in cursor.fetchall():
            results.append({
                'id': row[0],
                'term': row[1],
                'original_definition': row[2],
                'corrected_definition': row[3],
                'part_of_speech': row[4]
            })
        
        cursor.close()
        conn.close()
        return results
    
    def update_definition(self, def_id: int, corrected_definition: str):
        """Update a corrected definition"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            UPDATE defined 
            SET corrected_definition = %s
            WHERE id = %s
        """, (corrected_definition, def_id))
        
        conn.commit()
        cursor.close()
        conn.close()
    
    def suggest_corrections(self, word: str, definition: str, pos: str) -> List[str]:
        """Suggest possible corrections based on word patterns"""
        suggestions = []
        
        # Pattern-based suggestions for common word types
        if word.endswith('ly') and pos == 'ADVERB':
            base = word[:-2]
            suggestions.append(f"In a {base} manner; showing {base} characteristics")
            
        elif word.endswith('ic') and pos == 'ADJECTIVE':
            suggestions.append(f"Having characteristics of; relating to")
            
        elif word.endswith('ness') and pos == 'NOUN':
            base = word[:-4]
            suggestions.append(f"The quality or state of being {base}")
            
        elif word.endswith('ment') and pos == 'NOUN':
            suggestions.append(f"The act, process, or result of")
            
        elif word.endswith('tion') or word.endswith('sion'):
            suggestions.append(f"The action or process of")
        
        # Generic suggestions
        suggestions.extend([
            "Related to or characterized by",
            "Having the quality of",
            "In the manner of"
        ])
        
        return suggestions[:3]  # Return top 3 suggestions
    
    def interactive_review(self):
        """Interactive CLI for reviewing definitions"""
        problematic = self.get_problematic_definitions()
        
        if not problematic:
            print("No problematic definitions found! ✓")
            return
        
        print(f"\nFound {len(problematic)} definitions that need review:\n")
        
        for i, item in enumerate(problematic, 1):
            print(f"\n{'='*60}")
            print(f"DEFINITION {i}/{len(problematic)}")
            print(f"{'='*60}")
            print(f"Term: {item['term']}")
            print(f"POS: {item['part_of_speech']}")
            print(f"Original: {item['original_definition']}")
            print(f"Auto-corrected: {item['corrected_definition'] or '(None)'}")
            
            # Show suggestions
            suggestions = self.suggest_corrections(
                item['term'], 
                item['original_definition'], 
                item['part_of_speech'] or ''
            )
            
            print(f"\nSuggestions:")
            for j, suggestion in enumerate(suggestions, 1):
                print(f"  {j}. {suggestion}")
            
            print(f"\nOptions:")
            print(f"  1-{len(suggestions)}: Use suggestion")
            print(f"  c: Enter custom definition")
            print(f"  s: Skip this definition")
            print(f"  q: Quit")
            
            while True:
                choice = input(f"\nChoose action: ").strip().lower()
                
                if choice == 'q':
                    return
                elif choice == 's':
                    break
                elif choice == 'c':
                    custom = input("Enter custom definition: ").strip()
                    if custom:
                        self.update_definition(item['id'], custom)
                        print(f"✓ Updated definition for '{item['term']}'")
                    break
                elif choice.isdigit() and 1 <= int(choice) <= len(suggestions):
                    suggestion_idx = int(choice) - 1
                    self.update_definition(item['id'], suggestions[suggestion_idx])
                    print(f"✓ Updated definition for '{item['term']}'")
                    break
                else:
                    print("Invalid choice, please try again.")

def main():
    """Main review interface"""
    reviewer = DefinitionReviewer()
    
    print("CIRCULAR DEFINITION REVIEWER")
    print("=" * 40)
    print("This tool helps you review and correct definitions that contain")
    print("circular references (definitions that use the word being defined).")
    print()
    
    while True:
        print("\nOptions:")
        print("1. Start interactive review")
        print("2. Show problematic definitions")
        print("3. Run detection scan")
        print("4. Exit")
        
        choice = input("\nChoose option (1-4): ").strip()
        
        if choice == '1':
            reviewer.interactive_review()
        elif choice == '2':
            problematic = reviewer.get_problematic_definitions()
            print(f"\nFound {len(problematic)} problematic definitions:")
            for item in problematic:
                print(f"  {item['term']}: {item['original_definition'][:50]}...")
        elif choice == '3':
            detector = CircularDefinitionDetector()
            print("Running detection scan (limit 500)...")
            stats = detector.scan_and_flag_definitions(limit=500)
            print(f"Processed: {stats['total_processed']}")
            print(f"Circular found: {stats['circular_found']}")
            print(f"Auto-corrected: {stats['corrected']}")
            print(f"Need review: {stats['needs_review']}")
        elif choice == '4':
            break
        else:
            print("Invalid choice, please try again.")

if __name__ == "__main__":
    main()