#!/usr/bin/env python3
"""
AI-Powered Definition Corrector
Uses intelligent analysis to properly correct circular definitions
"""

import mysql.connector
import re
import json
import logging
from typing import List, Dict, Optional, Tuple
from config import get_db_config
from circular_definition_detector import CircularDefinitionDetector

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class AIDefinitionCorrector:
    def __init__(self):
        self.config = get_db_config()
        self.detector = CircularDefinitionDetector()
        
        # Common circular patterns that can often be removed entirely
        self.removable_patterns = [
            r"of,?\s+relating\s+to,?\s+or\s+of\s+the\s+nature\s+of\s+",
            r"of\s+or\s+relating\s+to\s+",
            r"relating\s+to\s+",
            r"pertaining\s+to\s+",
            r"concerning\s+",
            r"having\s+to\s+do\s+with\s+",
            r"in\s+the\s+manner\s+of\s+",
            r"in\s+a\s+\w*\s+manner",
            r"like\s+",
            r"resembling\s+",
        ]
        
        # Load a basic word-to-definition mapping for common terms
        self.common_definitions = {
            'seraph': 'six-winged celestial being',
            'seraphim': 'six-winged celestial beings',
            'angel': 'celestial being or divine messenger',
            'demon': 'evil spirit or malevolent supernatural being',
            'dragon': 'large mythical reptilian creature',
            'unicorn': 'mythical horse-like creature with a single horn',
            'phoenix': 'mythical bird that rises from its own ashes',
            'sphinx': 'mythical creature with human head and lion body',
            'centaur': 'mythical creature with human torso and horse body',
            'muse': 'source of artistic inspiration',
            'titan': 'powerful primordial deity',
            'olympian': 'one of the twelve major Greek gods',
            'prophet': 'one who speaks divine messages',
            'sage': 'wise person or philosopher',
            'monk': 'religious person living in monastic community',
            'friar': 'member of mendicant religious order',
            'bishop': 'high-ranking Christian clergyman',
            'cardinal': 'high church official ranking below pope',
            'pope': 'head of Roman Catholic Church',
            'rabbi': 'Jewish religious leader and teacher',
            'imam': 'Islamic religious leader',
            'shaman': 'spiritual healer and guide',
            'druid': 'ancient Celtic priest',
            'bard': 'poet-singer or storyteller',
            'minstrel': 'traveling musician and entertainer',
            'troubadour': 'medieval lyric poet and musician',
            'scribe': 'professional writer or copyist',
            'herald': 'official messenger or announcer',
            'knight': 'medieval warrior of noble rank',
            'baron': 'nobleman of lowest rank',
            'duke': 'high-ranking nobleman',
            'earl': 'British nobleman ranking above viscount',
            'marquis': 'nobleman ranking below duke',
            'count': 'European nobleman equivalent to earl',
            'peasant': 'rural agricultural worker',
            'serf': 'feudal tenant bound to land',
            'vassal': 'feudal tenant owing allegiance to lord',
            'mercenary': 'soldier fighting for payment',
            'gladiator': 'arena fighter in ancient Rome',
            'centurion': 'Roman army officer commanding hundred men',
            'praetor': 'Roman magistrate',
            'consul': 'chief Roman magistrate',
            'tribune': 'Roman official protecting plebeian rights',
            'pharaoh': 'ancient Egyptian ruler',
            'vizier': 'high government official',
            'emir': 'Muslim ruler or commander',
            'sultan': 'Muslim sovereign ruler',
            'caliph': 'Islamic religious and political leader',
            'shogun': 'Japanese military dictator',
            'samurai': 'Japanese warrior class member',
            'geisha': 'Japanese female entertainer',
            'mandarin': 'Chinese imperial official',
            'brahmin': 'highest Hindu caste member',
        }
    
    def get_connection(self):
        return mysql.connector.connect(**self.config)
    
    def analyze_definition_structure(self, word: str, definition: str) -> Dict:
        """Analyze the structure of a definition to understand correction options"""
        analysis = {
            'has_multiple_parts': False,
            'circular_phrases': [],
            'remaining_content': '',
            'can_remove_circular': False,
            'needs_replacement': False,
            'circular_words': []
        }
        
        # Find circular references
        is_circular, matches = self.detector.contains_circular_reference(word, definition)
        if not is_circular:
            return analysis
        
        analysis['circular_words'] = matches
        
        # Split definition by common delimiters
        parts = re.split(r'[;,]\s*', definition)
        analysis['has_multiple_parts'] = len(parts) > 1
        
        # Find which parts contain circular references
        circular_parts = []
        non_circular_parts = []
        
        for part in parts:
            part_is_circular = False
            for match in matches:
                pattern = r'\b' + re.escape(match) + r'\b'
                if re.search(pattern, part.lower()):
                    circular_parts.append(part.strip())
                    part_is_circular = True
                    break
            
            if not part_is_circular:
                non_circular_parts.append(part.strip())
        
        analysis['circular_phrases'] = circular_parts
        analysis['remaining_content'] = '; '.join(non_circular_parts) if non_circular_parts else ''
        
        # Decision logic
        if analysis['remaining_content'] and len(analysis['remaining_content']) > 10:
            analysis['can_remove_circular'] = True
        elif any(self.get_definition_for_word(word) for word in matches):
            analysis['needs_replacement'] = True
        else:
            analysis['can_remove_circular'] = True  # Last resort
        
        return analysis
    
    def get_definition_for_word(self, word: str) -> Optional[str]:
        """Get a definition for a word to replace circular references"""
        word_lower = word.lower()
        
        # Check our common definitions first
        if word_lower in self.common_definitions:
            return self.common_definitions[word_lower]
        
        # Try to get definition from the database (non-circular ones)
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT definition 
            FROM defined 
            WHERE term = %s 
            AND (has_circular_definition IS FALSE OR has_circular_definition IS NULL)
            AND definition IS NOT NULL
            AND LENGTH(definition) > 20
            LIMIT 1
        """, (word,))
        
        result = cursor.fetchone()
        cursor.close()
        conn.close()
        
        if result:
            return result[0].strip()
        
        return None
    
    def create_smart_correction(self, word: str, definition: str) -> Tuple[str, str]:
        """Create an intelligent correction with reasoning"""
        analysis = self.analyze_definition_structure(word, definition)
        
        if not analysis['circular_words']:
            return definition, "No circular reference found"
        
        # Strategy 1: Remove circular phrases if we have good remaining content
        if analysis['can_remove_circular'] and analysis['remaining_content']:
            corrected = analysis['remaining_content']
            # Capitalize first letter
            corrected = corrected[0].upper() + corrected[1:] if corrected else ''
            return corrected, f"Removed circular phrases, kept: '{analysis['remaining_content']}'"
        
        # Strategy 2: Replace circular words with definitions
        if analysis['needs_replacement']:
            corrected = definition
            reasoning_parts = []
            
            for circular_word in analysis['circular_words']:
                replacement = self.get_definition_for_word(circular_word)
                if replacement:
                    # Replace the circular word with its definition
                    pattern = r'\b' + re.escape(circular_word) + r'\b'
                    corrected = re.sub(pattern, replacement, corrected, flags=re.IGNORECASE)
                    reasoning_parts.append(f"'{circular_word}' -> '{replacement}'")
            
            return corrected, f"Replaced circular words: {'; '.join(reasoning_parts)}"
        
        # Strategy 3: Intelligent pattern removal
        corrected = definition
        for pattern in self.removable_patterns:
            for circular_word in analysis['circular_words']:
                full_pattern = pattern + r'\w*' + re.escape(circular_word) + r'\w*'
                corrected = re.sub(full_pattern, '', corrected, flags=re.IGNORECASE)
        
        # Clean up the result
        corrected = re.sub(r'\s*[;,]\s*[;,]\s*', '; ', corrected)
        corrected = re.sub(r'^\s*[;,]\s*', '', corrected)
        corrected = re.sub(r'\s*[;,]\s*$', '', corrected)
        corrected = re.sub(r'\s+', ' ', corrected).strip()
        
        if corrected and len(corrected) > 5:
            corrected = corrected[0].upper() + corrected[1:] if len(corrected) > 1 else corrected.upper()
            return corrected, "Applied intelligent pattern removal"
        
        # Fallback: return remaining content or original
        if analysis['remaining_content']:
            return analysis['remaining_content'], "Fallback: used remaining content"
        
        return definition, "Unable to improve definition automatically"
    
    def process_flagged_definitions(self, limit: Optional[int] = None) -> Dict:
        """Process all flagged definitions with smart corrections"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        sql = """
            SELECT id, term, definition, corrected_definition 
            FROM defined 
            WHERE has_circular_definition = TRUE
        """
        if limit:
            sql += f" LIMIT {limit}"
        
        cursor.execute(sql)
        definitions = cursor.fetchall()
        
        stats = {
            'total_processed': 0,
            'improved': 0,
            'unchanged': 0,
            'examples': []
        }
        
        for def_id, term, original_def, old_correction in definitions:
            stats['total_processed'] += 1
            
            new_correction, reasoning = self.create_smart_correction(term, original_def)
            
            # Only update if we have a meaningful improvement
            if (new_correction != original_def and 
                len(new_correction) > 10 and 
                new_correction != old_correction and
                'or relating to or' not in new_correction.lower()):
                
                cursor.execute("""
                    UPDATE defined 
                    SET corrected_definition = %s
                    WHERE id = %s
                """, (new_correction, def_id))
                
                stats['improved'] += 1
                stats['examples'].append({
                    'term': term,
                    'original': original_def,
                    'old_correction': old_correction,
                    'new_correction': new_correction,
                    'reasoning': reasoning
                })
                
                logger.info(f"Improved '{term}': {reasoning}")
            else:
                stats['unchanged'] += 1
        
        conn.commit()
        cursor.close()
        conn.close()
        
        return stats

def main():
    """Run the AI-powered definition corrector"""
    corrector = AIDefinitionCorrector()
    
    print("AI-POWERED DEFINITION CORRECTOR")
    print("=" * 50)
    print("Applying intelligent corrections to circular definitions...")
    
    # Process all flagged definitions
    stats = corrector.process_flagged_definitions()
    
    print(f"\nRESULTS:")
    print(f"Total processed: {stats['total_processed']:,}")
    print(f"Improved: {stats['improved']:,}")
    print(f"Unchanged: {stats['unchanged']:,}")
    
    # Show examples
    if stats['examples']:
        print(f"\nEXAMPLES OF IMPROVEMENTS:")
        print("-" * 40)
        for i, example in enumerate(stats['examples'][:5], 1):
            print(f"\n{i}. {example['term']}")
            print(f"   Original: {example['original']}")
            print(f"   Old: {example['old_correction']}")
            print(f"   New: {example['new_correction']}")
            print(f"   Why: {example['reasoning']}")

if __name__ == "__main__":
    main()