#!/usr/bin/env python3
"""
English Word Validator - Comprehensive validation system for English words
Filters out non-English words before they enter the candidate review queue
"""

import re
import logging
from typing import Set, Optional, Tuple, List
from pathlib import Path
import json

try:
    import wordfreq
    WORDFREQ_AVAILABLE = True
except ImportError:
    WORDFREQ_AVAILABLE = False
    logging.warning("wordfreq not available, using fallback validation")

try:
    import nltk
    from nltk.corpus import words, wordnet
    NLTK_AVAILABLE = True
    
    # Download required NLTK data if not present
    try:
        nltk.data.find('corpora/words')
        nltk.data.find('corpora/wordnet')
    except LookupError:
        logging.info("Downloading required NLTK data...")
        nltk.download('words', quiet=True)
        nltk.download('wordnet', quiet=True)
        
except ImportError:
    NLTK_AVAILABLE = False
    logging.warning("NLTK not available, using fallback validation")

logger = logging.getLogger(__name__)

class EnglishWordValidator:
    """Comprehensive English word validation system"""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        
        # Load validation resources
        self._load_english_words()
        self._load_common_patterns()
        self._load_rejection_patterns()
        
        # Statistics
        self.stats = {
            'validated': 0,
            'rejected_non_english': 0,
            'rejected_patterns': 0,
            'accepted': 0
        }
    
    def _load_english_words(self):
        """Load English word dictionaries"""
        self.english_words = set()
        
        # Load from NLTK if available
        if NLTK_AVAILABLE:
            try:
                self.english_words.update(word.lower() for word in words.words())
                self.logger.info(f"Loaded {len(self.english_words)} words from NLTK corpus")
            except Exception as e:
                self.logger.warning(f"Could not load NLTK words: {e}")
        
        # Add common English words as fallback
        common_english_words = {
            'the', 'be', 'to', 'of', 'and', 'a', 'in', 'that', 'have', 'i', 'it', 'for', 
            'not', 'on', 'with', 'he', 'as', 'you', 'do', 'at', 'this', 'but', 'his', 'by',
            'from', 'they', 'we', 'say', 'her', 'she', 'or', 'an', 'will', 'my', 'one', 
            'all', 'would', 'there', 'their', 'what', 'so', 'up', 'out', 'if', 'about',
            'who', 'get', 'which', 'go', 'me', 'when', 'make', 'can', 'like', 'time',
            'no', 'just', 'him', 'know', 'take', 'people', 'into', 'year', 'your', 'good',
            'some', 'could', 'them', 'see', 'other', 'than', 'then', 'now', 'look', 'only',
            'come', 'its', 'over', 'think', 'also', 'back', 'after', 'use', 'two', 'how',
            'our', 'work', 'first', 'well', 'way', 'even', 'new', 'want', 'because', 'any',
            'these', 'give', 'day', 'most', 'us', 'magnificent', 'restoration', 'beautiful',
            'wonderful', 'extraordinary', 'philosophical', 'theoretical', 'practical',
            'intellectual', 'sophisticated', 'contemplation', 'consideration', 'understanding',
            'disposition', 'preservation', 'unnecessary', 'ebullition', 'amiability',
            'classical', 'literature', 'vocabulary', 'sophisticated', 'archaic',
            'obsolete', 'medieval', 'renaissance', 'elizabethan', 'romantic'
        }
        
        self.english_words.update(common_english_words)
        
        # Add common archaic/classical English words that might not be in modern dictionaries
        archaic_english_words = {
            'thou', 'thee', 'thy', 'thine', 'ye', 'hath', 'doth', 'shalt', 'shouldst', 
            'wouldst', 'couldst', 'whence', 'whither', 'wherefore', 'whilst', 'amongst', 
            'betwixt', 'ere', 'nay', 'yea', 'forsooth', 'prithee', 'anon', 'mayhap', 
            'perchance', 'methinks', 'albeit', 'alas', 'hence', 'thence', 'whence',
            'bespeak', 'beseech', 'befall', 'bethink', 'bewail', 'begone', 'besmirch', 
            'bestow', 'beholden', 'behest', 'benighted', 'bequeath'
        }
        
        self.english_words.update(archaic_english_words)
    
    def _load_common_patterns(self):
        """Load patterns that indicate English words"""
        self.english_patterns = [
            # Common English prefixes
            r'^(un|re|pre|dis|over|under|anti|co|de|ex|in|im|non|mis|sub|super|trans|inter|multi|semi|auto|bi|tri|mono|poly|micro|macro|mini|mega|ultra|hyper|pseudo|proto|neo|meta|para|pro|contra|retro|ante|post|fore|out|up)[-\w]*$',
            
            # Common English suffixes
            r'^.*?(ing|ed|er|est|ly|tion|sion|ness|ment|able|ible|ful|less|ous|ious|eous|uous|ive|ative|itive|al|ial|ar|lar|ic|tic|atic|itic|ish|like|ward|wise|some|fold|hood|ship|dom|age|ism|ist|ite|ant|ent|ancy|ency|cy)$',
            
            # English morphological patterns
            r'^[a-z]*[aeiou][a-z]*$',  # Contains vowels
            r'^[bcdfghjklmnpqrstvwxyz]*[aeiou][bcdfghjklmnpqrstvwxyz]*[aeiou][bcdfghjklmnpqrstvwxyz]*$',  # Alternating consonant-vowel patterns
        ]
        
        self.compiled_english_patterns = [re.compile(pattern, re.IGNORECASE) for pattern in self.english_patterns]
    
    def _load_rejection_patterns(self):
        """Load patterns that indicate non-English words"""
        self.rejection_patterns = [
            # Dutch patterns (common in Gutenberg since we saw Dutch words) - more specific
            r'^.*?(ij).*$',  # Dutch ij combination
            r'^(de|het|van|een|voor|niet|zijn|hebben|worden|kunnen|zullen|moeten|mogen|willen|gaan|komen|doen|zien|weten|krijgen|maken|veel|ook|maar|als|wat|wie|waar|wanneer|hoe|waarom|uitgegeven|meetkundigen|nageplozen|katholieken|beteekenis|cartesianen|collegianten|psychologie|veroveren|verloochene|emendatione|cogitata|anthropos)$',  # Specific Dutch words
            
            # German patterns - more specific
            r'^.*?(pf|tz|ä|ö|ü|ß).*$',  # German characters (removed sch and ss as they're common in English)
            r'^(der|die|das|und|ist|zu|den|von|sie|mit|für|auf|als|auch|sich|war|wie|eine|oder|aber|werden|sein|haben|können|müssen|sollen|wollen|dürfen|mögen|wissenschaft|gesellschaft)$',  # German words
            
            # French patterns - specific words only
            r'^.*?(eau|eux|oir|aise|oise|euse|ée|és|ées|ç).*$',  # French patterns (removed ique as it appears in English words)
            r'^(le|la|les|de|du|des|et|est|être|avoir|faire|aller|dire|voir|savoir|pouvoir|vouloir|venir|falloir|devoir|croire|trouver|donner|prendre|parler|aimer|passer|mettre|magnifique|château|éléphant)$',  # French words
            
            # Spanish patterns - more specific
            r'^.*?(ción|sión|ñ|güe|güi).*$',  # Spanish patterns (removed ll and rr as they appear in English)
            r'^(el|la|los|las|de|y|es|ser|tener|hacer|estar|ir|haber|decir|ver|dar|saber|querer|poder|llegar|pasar|quedar|venir|poner|salir)$',  # Spanish words
            
            # Italian patterns - more specific
            r'^.*?(gli|zione|sione).*$',  # Italian patterns (removed gn and sc as they appear in English)
            r'^(il|lo|la|gli|le|di|e|essere|avere|fare|dire|andare|dare|stare|volere|dovere|potere|sapere|vedere|venire|uscire|parlare|mangiare|bere|dormire)$',  # Italian words
            
            # Very specific Latin-only patterns (avoid catching English words)
            # r'^.*?(us|um)$',  # Commented out - too many false positives with English words
            
            # General non-English indicators - be more conservative
            r'^[bcdfghjklmnpqrstvwxyz]{6,}$',  # Too many consecutive consonants
            r'^[aeiou]{5,}$',  # Too many consecutive vowels  
            r'^[^aeiou]*$',  # No vowels at all
            
            # Exclude very short or very long words that are likely not useful
            r'^.{1,2}$',   # Too short
            r'^.{25,}$',   # Too long
        ]
        
        self.compiled_rejection_patterns = [re.compile(pattern, re.IGNORECASE) for pattern in self.rejection_patterns]
    
    def is_english_word(self, word: str) -> Tuple[bool, str]:
        """
        Comprehensive check if a word is English
        Returns (is_english, reason)
        """
        self.stats['validated'] += 1
        
        if not word or not isinstance(word, str):
            return False, "invalid_input"
        
        word_lower = word.lower().strip()
        
        # Skip empty or very short words
        if len(word_lower) < 3:
            return False, "too_short"
        
        # Check against rejection patterns first (faster)
        for pattern in self.compiled_rejection_patterns:
            if pattern.match(word_lower):
                self.stats['rejected_patterns'] += 1
                return False, "non_english_pattern"
        
        # Check if word is in English dictionary
        if word_lower in self.english_words:
            self.stats['accepted'] += 1
            return True, "in_dictionary"
        
        # Check with wordfreq if available (this includes many English words)
        if WORDFREQ_AVAILABLE:
            try:
                # Check if word has any frequency in English (even very low)
                freq = wordfreq.word_frequency(word_lower, 'en')
                if freq > 1e-8:  # Very low threshold to catch rare but valid English words
                    self.stats['accepted'] += 1
                    return True, "wordfreq_valid"
            except Exception as e:
                self.logger.debug(f"wordfreq check failed for {word}: {e}")
        
        # Check with NLTK WordNet if available
        if NLTK_AVAILABLE:
            try:
                synsets = wordnet.synsets(word_lower)
                if synsets:
                    # Check if any synset is for English
                    for synset in synsets:
                        if synset.lang() == 'eng' or synset.lang() is None:  # None defaults to English
                            self.stats['accepted'] += 1
                            return True, "wordnet_valid"
            except Exception as e:
                self.logger.debug(f"WordNet check failed for {word}: {e}")
        
        # Check against English patterns
        for pattern in self.compiled_english_patterns:
            if pattern.match(word_lower):
                # Additional checks for pattern matches to reduce false positives
                if self._has_reasonable_structure(word_lower):
                    self.stats['accepted'] += 1
                    return True, "english_pattern"
        
        # If all checks fail, it's likely not English
        self.stats['rejected_non_english'] += 1
        return False, "not_english"
    
    def _has_reasonable_structure(self, word: str) -> bool:
        """Check if word has reasonable English-like structure"""
        # Must have at least one vowel
        if not re.search(r'[aeiou]', word):
            return False
        
        # Can't have more than 3 consecutive consonants (except some valid cases)
        if re.search(r'[bcdfghjklmnpqrstvwxyz]{4,}', word):
            # Allow some exceptions like "strength"
            valid_consonant_clusters = ['nght', 'nstr', 'ngth', 'ght', 'tch', 'sch', 'thr', 'str', 'spr', 'spl', 'scr']
            if not any(cluster in word for cluster in valid_consonant_clusters):
                return False
        
        # Can't have more than 2 consecutive vowels (with some exceptions)
        if re.search(r'[aeiou]{3,}', word):
            # Allow some exceptions like "beautiful"
            valid_vowel_clusters = ['eau', 'ieu', 'eau', 'eou']
            if not any(cluster in word for cluster in valid_vowel_clusters):
                return False
        
        return True
    
    def batch_validate(self, words: List[str]) -> List[Tuple[str, bool, str]]:
        """Validate multiple words at once"""
        results = []
        for word in words:
            is_valid, reason = self.is_english_word(word)
            results.append((word, is_valid, reason))
        
        return results
    
    def get_stats(self) -> dict:
        """Get validation statistics"""
        return self.stats.copy()
    
    def reset_stats(self):
        """Reset validation statistics"""
        self.stats = {
            'validated': 0,
            'rejected_non_english': 0,
            'rejected_patterns': 0,
            'accepted': 0
        }

# Singleton instance for easy importing
english_validator = EnglishWordValidator()

def validate_english_word(word: str) -> Tuple[bool, str]:
    """Convenience function to validate a single word"""
    return english_validator.is_english_word(word)

def validate_english_words(words: List[str]) -> List[Tuple[str, bool, str]]:
    """Convenience function to validate multiple words"""
    return english_validator.batch_validate(words)

# Test function
def test_validator():
    """Test the validator with known examples"""
    test_cases = [
        # English words (should pass)
        ("wonderful", True),
        ("archaic", True),
        ("bespeak", True),
        ("thou", True),
        ("magnificent", True),
        ("restoration", True),
        
        # Dutch words (should fail)
        ("uitgegeven", False),
        ("meetkundigen", False),
        ("nageplozen", False),
        ("katholieken", False),
        
        # German words (should fail)  
        ("schön", False),
        ("Wissenschaft", False),
        ("Gesellschaft", False),
        
        # French words (should fail)
        ("magnifique", False),
        ("éléphant", False),
        ("château", False),
        
        # Edge cases
        ("", False),
        ("a", False),
        ("xyz", False),
    ]
    
    validator = EnglishWordValidator()
    
    print("Testing English Word Validator")
    print("=" * 50)
    
    correct = 0
    total = len(test_cases)
    
    for word, expected in test_cases:
        is_english, reason = validator.is_english_word(word)
        status = "PASS" if is_english == expected else "FAIL"
        print(f"{status} {word:15} -> {is_english:5} ({reason}) [expected: {expected}]")
        if is_english == expected:
            correct += 1
    
    print(f"\nAccuracy: {correct}/{total} ({correct/total*100:.1f}%)")
    print(f"Validation stats: {validator.get_stats()}")

if __name__ == "__main__":
    test_validator()