#!/usr/bin/env python3
"""
Universal Vocabulary Extractor - Extract sophisticated vocabulary from any text source
"""

import re
import unicodedata
import logging
from typing import List, Dict, Set, Tuple, Optional
from collections import Counter
from dataclasses import dataclass
import wordfreq
import nltk

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@dataclass
class VocabularyCandidate:
    """Structured vocabulary candidate"""
    term: str
    original_form: str
    part_of_speech: str
    fine_pos: str
    lemma: str
    context: str
    linguistic_features: Dict
    morphological_type: List[str]
    source_metadata: Dict
    preliminary_score: float = 0.0

class UniversalVocabularyExtractor:
    """Extract vocabulary candidates from any text source using linguistic analysis"""
    
    def __init__(self):
        # Try to use spaCy for better analysis, fall back to NLTK
        self.nlp = None
        self.use_spacy = False
        
        try:
            import spacy
            try:
                self.nlp = spacy.load("en_core_web_sm")
                self.use_spacy = True
                logger.info("Using spaCy for linguistic analysis")
            except OSError:
                logger.warning("spaCy model en_core_web_sm not found, attempting to download...")
                try:
                    spacy.cli.download("en_core_web_sm")
                    self.nlp = spacy.load("en_core_web_sm")
                    self.use_spacy = True
                    logger.info("Successfully downloaded and loaded spaCy model")
                except Exception as e:
                    logger.warning(f"Could not download spaCy model: {e}, falling back to NLTK")
        except ImportError:
            logger.warning("spaCy not available, using NLTK for analysis")
        
        # Initialize NLTK components as fallback
        if not self.use_spacy:
            try:
                nltk.download('punkt', quiet=True)
                nltk.download('averaged_perceptron_tagger', quiet=True) 
                nltk.download('wordnet', quiet=True)
                from nltk.tokenize import sent_tokenize, word_tokenize
                from nltk.tag import pos_tag
                from nltk.corpus import wordnet
                from nltk.stem import WordNetLemmatizer
                
                self.sent_tokenize = sent_tokenize
                self.word_tokenize = word_tokenize
                self.pos_tag = pos_tag
                self.wordnet = wordnet
                self.lemmatizer = WordNetLemmatizer()
                logger.info("Using NLTK for linguistic analysis")
            except Exception as e:
                logger.error(f"Error initializing NLTK: {e}")
                
        self.common_words = self._load_common_word_sets()
        
        # Enhanced morphological patterns for sophisticated vocabulary
        self.interesting_patterns = {
            # Classical roots and affixes
            'greek_roots': re.compile(r'\b\w*(?:phil|phob|graph|log|chron|geo|bio|psych|path|morph|anthropo|demo|theo|phon|photo|micro|macro|hydro|pneum|neuro|cardio|gastro|dermat|oste|my|arthr|neur|hem|leuk|erythr|thromb|angi|hepat|nephr|pulmon|rhin|ophthalm|ot|laryng|enter|cyst|hist|cyt|gen|metr|scop|tom|alg|phag|phil|phor|plas|trop|tax|kine|stat|path|lys|oid|oma|itis|osis|iasis|emia|uria)\w*\b', re.IGNORECASE),
            
            'latin_roots': re.compile(r'\b\w*(?:aqua|terra|flora|fauna|corpus|opus|genus|species|homo|vit|mort|anim|spir|sens|vid|aud|loqu|dict|scrib|graph|mit|port|duc|fac|cap|ten|vert|volv|grad|ced|flu|cur|sta|sed|pos|pon|leg|lig|solv|tang|tract|struct|rupt|fract|flex|pend|spect|vol|mal|ben|magn|mult|uni|bi|tri|quad|quint|sex|sept|oct|non|dec|cent|mill|semi|hemi|circum|ambi|ante|post|inter|intra|trans|super|sub|pre|pro|retro|extra|ultra|contra|anti|de|re|ex|in|ad|ab|per|con|com|dis|ob)\w*\b', re.IGNORECASE),
            
            'academic_suffixes': re.compile(r'\b\w*(?:tion|sion|ment|ness|ity|acy|ism|ology|ography|aceous|aneous|arious|ative|atory|escent|itious|tious|uous|ous|eous|ious|able|ible|ent|ant|ive|ary|ory|al|ic|ical|istic|esque|oid|form|ward|wise|like|ful|less|ship|hood|dom|age|ure|ance|ence|cy|ty|ry|ery|ary)\b', re.IGNORECASE),
            
            'technical_prefixes': re.compile(r'\b(?:proto|pseudo|quasi|meta|hyper|super|ultra|micro|macro|mega|giga|nano|pico|multi|poly|mono|uni|bi|di|tri|tetra|penta|hexa|hepta|octa|nona|deca|hemi|semi|demi|anti|counter|contra|retro|pre|post|ante|inter|intra|trans|supra|infra|sub|over|under|out|auto|self|co|syn|homo|hetero|iso|neo|paleo|archaeo|crypto|stealth|cyber)\w+\b', re.IGNORECASE),
            
            'sophisticated_compounds': re.compile(r'\b(?:\w{4,}-\w{4,}|\w{8,})\b'),  # Long words or hyphenated compounds
            
            'archaic_patterns': re.compile(r'\b(?:\w*(?:eth|est|st)\b|\b(?:whence|whither|wherefore|whilst|amongst|betwixt|forsooth|verily|hither|thither|henceforth|heretofore|whereupon|notwithstanding)\b)', re.IGNORECASE),
            
            'medical_legal': re.compile(r'\b\w*(?:cide|genic|pathic|tropic|philic|phobic|static|dynamic|kinetic|metric|scopic|graphic|logic|nomics|therapy|pathy|iatry|ectomy|otomy|ostomy|plasty|rrhaphy|pexy|tripsy|clasis|synthesis|analysis|diagnosis|prognosis|syndrome|trauma|lesion|neoplasm|carcinoma|sarcoma|lymphoma|leukemia)\w*\b', re.IGNORECASE)
        }
        
        # Words to exclude (too common, not interesting, or problematic)
        self.exclusion_patterns = [
            re.compile(r'^\d+$'),  # Pure numbers
            re.compile(r'^[A-Z]+$'),  # Pure acronyms
            re.compile(r'.*\d.*'),  # Contains numbers
            re.compile(r'^.{1,3}$'),  # Too short
            re.compile(r'^.{30,}$'),  # Too long (likely errors)
            re.compile(r'^(?:http|www|com|org|net|edu|gov)'),  # URLs
            re.compile(r'[^\w\-\']'),  # Non-word characters (except hyphens and apostrophes)
        ]
    
    def extract_candidates(self, text: str, source_metadata: Dict = None) -> List[VocabularyCandidate]:
        """Extract vocabulary candidates from text"""
        if not text or len(text.strip()) < 50:
            return []
        
        # Clean and normalize text
        text = self._clean_text(text)
        
        candidates = []
        processed_tokens = set()
        
        if self.use_spacy and self.nlp:
            candidates = self._extract_with_spacy(text, source_metadata, processed_tokens)
        else:
            candidates = self._extract_with_nltk(text, source_metadata, processed_tokens)
        
        # Rank candidates by interestingness
        return self._rank_candidates(candidates)
    
    def _extract_with_spacy(self, text: str, source_metadata: Dict, processed_tokens: set) -> List[VocabularyCandidate]:
        """Extract using spaCy for superior linguistic analysis"""
        candidates = []
        
        try:
            # Process text with spaCy
            doc = self.nlp(text)
            
            for sent in doc.sents:
                sentence_text = sent.text.strip()
                
                for token in sent:
                    # Skip if already processed, is punctuation, stop word, or common
                    if (token.lemma_.lower() in processed_tokens or 
                        token.is_punct or token.is_space or token.is_stop or
                        token.lemma_.lower() in self.common_words):
                        continue
                    
                    lemma = token.lemma_.lower()
                    
                    # Apply exclusion filters
                    if any(pattern.match(lemma) for pattern in self.exclusion_patterns):
                        continue
                    
                    # Check if word matches interesting patterns
                    if self._is_interesting_word_spacy(token, lemma):
                        candidate = VocabularyCandidate(
                            term=lemma,
                            original_form=token.text,
                            part_of_speech=token.pos_,
                            fine_pos=token.tag_,
                            lemma=lemma,
                            context=sentence_text,
                            linguistic_features=self._extract_linguistic_features_spacy(token),
                            morphological_type=self._classify_morphology(lemma),
                            source_metadata=source_metadata or {}
                        )
                        candidates.append(candidate)
                        processed_tokens.add(lemma)
        
        except Exception as e:
            logger.error(f"Error in spaCy extraction: {e}")
        
        return candidates
    
    def _extract_with_nltk(self, text: str, source_metadata: Dict, processed_tokens: set) -> List[VocabularyCandidate]:
        """Extract using NLTK as fallback"""
        candidates = []
        
        try:
            # Tokenize sentences
            sentences = self.sent_tokenize(text)
            
            for sentence in sentences:
                # Tokenize and tag words
                words = self.word_tokenize(sentence)
                pos_tags = self.pos_tag(words)
                
                for word, pos in pos_tags:
                    word_lower = word.lower()
                    
                    # Skip if already processed or is common
                    if (word_lower in processed_tokens or
                        word_lower in self.common_words or
                        len(word_lower) < 4):
                        continue
                    
                    # Apply exclusion filters
                    if any(pattern.match(word_lower) for pattern in self.exclusion_patterns):
                        continue
                    
                    # Get lemma
                    try:
                        lemma = self.lemmatizer.lemmatize(word_lower, self._get_wordnet_pos(pos))
                    except:
                        lemma = word_lower
                    
                    # Check if word matches interesting patterns
                    if self._is_interesting_word_nltk(word_lower, pos):
                        candidate = VocabularyCandidate(
                            term=lemma,
                            original_form=word,
                            part_of_speech=pos,
                            fine_pos=pos,
                            lemma=lemma,
                            context=sentence,
                            linguistic_features=self._extract_linguistic_features_nltk(word_lower),
                            morphological_type=self._classify_morphology(lemma),
                            source_metadata=source_metadata or {}
                        )
                        candidates.append(candidate)
                        processed_tokens.add(lemma)
        
        except Exception as e:
            logger.error(f"Error in NLTK extraction: {e}")
        
        return candidates
    
    def _clean_text(self, text: str) -> str:
        """Clean and normalize text for processing"""
        # Remove citations, footnotes, URLs, etc.
        text = re.sub(r'\[\d+\]|\(\d+\)|<[^>]+>|https?://\S+|www\.\S+', '', text)
        
        # Remove special characters but keep hyphens and apostrophes
        text = re.sub(r'[^\w\s\-\']', ' ', text)
        
        # Normalize unicode
        text = unicodedata.normalize('NFKD', text)
        
        # Remove excessive whitespace
        text = re.sub(r'\s+', ' ', text)
        
        return text.strip()
    
    def _is_interesting_word_spacy(self, token, lemma: str) -> bool:
        """Determine if a spaCy token represents an interesting word"""
        # Minimum length requirement
        if len(lemma) < 5:
            return False
        
        # Check morphological patterns
        for pattern_name, pattern in self.interesting_patterns.items():
            if pattern.search(lemma):
                return True
        
        # Academic/technical vocabulary based on POS and features
        if token.pos_ in ['NOUN', 'VERB', 'ADJ', 'ADV']:
            # Longer words tend to be more specialized
            if len(lemma) >= 8:
                return True
            
            # Specific linguistic features
            if (token.tag_ in ['VBN', 'VBG', 'JJS', 'RBS'] or  # Participles, superlatives
                self._has_unusual_phonetics(lemma) or
                not token.is_alpha):  # Contains non-alphabetic characters
                return True
        
        # Words not in common frequency lists
        try:
            zipf_freq = wordfreq.zipf_frequency(lemma, 'en')
            if zipf_freq < 3.0:  # Relatively uncommon
                return True
        except:
            # If we can't get frequency data, it might be rare
            return True
        
        return False
    
    def _is_interesting_word_nltk(self, word: str, pos: str) -> bool:
        """Determine if an NLTK word/POS pair is interesting"""
        # Minimum length requirement
        if len(word) < 5:
            return False
        
        # Check morphological patterns
        for pattern_name, pattern in self.interesting_patterns.items():
            if pattern.search(word):
                return True
        
        # POS-based filtering
        interesting_pos = ['NN', 'NNS', 'NNP', 'NNPS', 'VB', 'VBD', 'VBG', 'VBN', 'VBP', 'VBZ',
                          'JJ', 'JJR', 'JJS', 'RB', 'RBR', 'RBS']
        
        if pos in interesting_pos:
            if len(word) >= 8 or self._has_unusual_phonetics(word):
                return True
        
        # Check frequency
        try:
            zipf_freq = wordfreq.zipf_frequency(word, 'en')
            if zipf_freq < 3.0:
                return True
        except:
            return True
        
        return False
    
    def _extract_linguistic_features_spacy(self, token) -> Dict:
        """Extract linguistic features from spaCy token"""
        return {
            'syllable_count': self._estimate_syllables(token.text),
            'has_prefix': bool(re.match(r'^(?:un|re|pre|dis|over|under|inter|trans|super|sub|anti|counter|meta|pseudo|proto|quasi)', token.lemma_)),
            'has_suffix': bool(re.search(r'(?:tion|sion|ment|ness|ity|ism|ology|ography|able|ible|ous|eous|ious|uous|ent|ant|ive|ary|ory)$', token.lemma_)),
            'capitalized_in_text': token.text[0].isupper(),
            'is_named_entity': token.ent_type_ != '',
            'entity_type': token.ent_type_,
            'dependency_relation': token.dep_,
            'has_morphology': bool(token.morph),
            'is_oov': token.is_oov,  # Out of vocabulary
            'similarity_available': token.has_vector
        }
    
    def _extract_linguistic_features_nltk(self, word: str) -> Dict:
        """Extract linguistic features using NLTK"""
        return {
            'syllable_count': self._estimate_syllables(word),
            'has_prefix': bool(re.match(r'^(?:un|re|pre|dis|over|under|inter|trans|super|sub|anti|counter|meta|pseudo|proto|quasi)', word)),
            'has_suffix': bool(re.search(r'(?:tion|sion|ment|ness|ity|ism|ology|ography|able|ible|ous|eous|ious|uous|ent|ant|ive|ary|ory)$', word)),
            'capitalized_in_text': False,  # NLTK doesn't preserve this easily
            'is_named_entity': False,
            'entity_type': '',
            'dependency_relation': '',
            'has_morphology': False,
            'is_oov': False,
            'similarity_available': False
        }
    
    def _classify_morphology(self, word: str) -> List[str]:
        """Classify word by morphological type"""
        types = []
        
        # Classical roots
        if re.search(r'(?:phil|phob|graph|log|chron|geo|bio|psych|path|morph|anthropo|demo|theo)', word, re.IGNORECASE):
            types.append('greek_root')
        
        if re.search(r'(?:aqua|terra|flora|fauna|corpus|opus|genus|species|vit|mort|anim|spir)', word, re.IGNORECASE):
            types.append('latin_root')
        
        # Academic vocabulary patterns
        if re.search(r'(?:tion|sion|ment|ness|ity|acy|ism|ology|ography)$', word, re.IGNORECASE):
            types.append('academic_noun')
        
        if re.search(r'(?:ous|eous|ious|uous|ent|ant|ive|ary|ory|al|ic|ical|istic)$', word, re.IGNORECASE):
            types.append('academic_adjective')
        
        # Technical/scientific
        if re.search(r'^(?:proto|pseudo|quasi|meta|hyper|super|ultra|micro|macro|multi)', word, re.IGNORECASE):
            types.append('technical_prefix')
        
        # Medical/legal terminology
        if re.search(r'(?:pathic|genic|iatry|ectomy|osis|itis|emia|uria|cidal|therapy)$', word, re.IGNORECASE):
            types.append('medical_legal')
        
        # Archaic or literary
        if re.search(r'(?:eth|est)$|^(?:whence|whither|wherefore|whilst|amongst|betwixt)$', word, re.IGNORECASE):
            types.append('archaic_literary')
        
        return types if types else ['standard']
    
    def _estimate_syllables(self, word: str) -> int:
        """Estimate syllable count"""
        word = word.lower()
        vowels = 'aeiouy'
        syllable_count = 0
        previous_was_vowel = False
        
        for char in word:
            is_vowel = char in vowels
            if is_vowel and not previous_was_vowel:
                syllable_count += 1
            previous_was_vowel = is_vowel
        
        # Adjust for silent 'e'
        if word.endswith('e') and syllable_count > 1:
            syllable_count -= 1
        
        # Special cases for -le endings
        if word.endswith('le') and len(word) > 2 and word[-3] not in vowels:
            syllable_count += 1
        
        return max(1, syllable_count)
    
    def _has_unusual_phonetics(self, word: str) -> bool:
        """Check for unusual letter combinations that suggest sophisticated vocabulary"""
        unusual_patterns = [
            r'[qx]', r'ph', r'gh', r'sch', r'tch', r'dge', r'ch', r'sh', r'th',
            r'ough', r'augh', r'eigh', r'tion', r'sion', r'eur', r'eau', 
            r'ae', r'oe', r'ue', r'gue', r'que', r'psy', r'rhy', r'rrh'
        ]
        return any(re.search(pattern, word, re.IGNORECASE) for pattern in unusual_patterns)
    
    def _get_wordnet_pos(self, nltk_pos: str) -> str:
        """Convert NLTK POS tag to WordNet POS"""
        if nltk_pos.startswith('J'):
            return self.wordnet.ADJ
        elif nltk_pos.startswith('V'):
            return self.wordnet.VERB
        elif nltk_pos.startswith('N'):
            return self.wordnet.NOUN
        elif nltk_pos.startswith('R'):
            return self.wordnet.ADV
        else:
            return self.wordnet.NOUN
    
    def _rank_candidates(self, candidates: List[VocabularyCandidate]) -> List[VocabularyCandidate]:
        """Rank candidates by estimated interestingness"""
        for candidate in candidates:
            score = 0
            
            # Length bonus (longer = potentially more specialized)
            length = len(candidate.term)
            if 8 <= length <= 15:
                score += 3
            elif 6 <= length <= 7:
                score += 2
            elif length > 15:
                score += 1  # Very long words can be interesting but penalize slightly
            elif length >= 20:
                score -= 2  # Extremely long likely to be errors
            
            # Morphological type bonuses
            morph_types = candidate.morphological_type
            score += len(morph_types)  # More types = more interesting
            
            if 'greek_root' in morph_types or 'latin_root' in morph_types:
                score += 3
            if 'academic_noun' in morph_types or 'academic_adjective' in morph_types:
                score += 2
            if 'technical_prefix' in morph_types:
                score += 2
            if 'medical_legal' in morph_types:
                score += 2
            if 'archaic_literary' in morph_types:
                score += 1
            
            # Linguistic feature bonuses
            features = candidate.linguistic_features
            if features['syllable_count'] >= 4:
                score += 1
            if features['has_prefix'] and features['has_suffix']:
                score += 2
            if features.get('is_oov', False):  # Out of vocabulary suggests rarity
                score += 2
            if features.get('is_named_entity', False):
                score += 1
            
            # Context quality
            if len(candidate.context) > 100:
                score += 1
            
            # Frequency-based scoring
            try:
                zipf_freq = wordfreq.zipf_frequency(candidate.term, 'en')
                if zipf_freq == 0:
                    score += 3  # Very rare
                elif zipf_freq < 2.0:
                    score += 2  # Quite rare
                elif zipf_freq < 3.0:
                    score += 1  # Uncommon
                elif zipf_freq > 5.0:
                    score -= 2  # Too common
            except:
                score += 1  # Unknown frequency might mean rare
            
            candidate.preliminary_score = score
        
        # Sort by preliminary score
        candidates.sort(key=lambda x: x.preliminary_score, reverse=True)
        return candidates
    
    def _load_common_word_sets(self) -> Set[str]:
        """Load sets of common words to exclude"""
        basic_common = {
            'the', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for', 'of', 'with',
            'by', 'from', 'up', 'about', 'into', 'through', 'during', 'before',
            'after', 'above', 'below', 'between', 'among', 'until', 'while',
            'because', 'although', 'since', 'unless', 'when', 'where', 'how', 'why',
            'what', 'which', 'who', 'whom', 'whose', 'that', 'this', 'these', 'those',
            'be', 'have', 'do', 'will', 'would', 'could', 'should', 'may', 'might',
            'can', 'must', 'shall', 'ought', 'need', 'dare', 'used', 'able',
            'get', 'got', 'give', 'gave', 'take', 'took', 'make', 'made', 'come', 'came',
            'go', 'went', 'see', 'saw', 'know', 'knew', 'think', 'thought', 'say', 'said',
            'tell', 'told', 'ask', 'asked', 'work', 'worked', 'seem', 'seemed',
            'feel', 'felt', 'try', 'tried', 'leave', 'left', 'call', 'called'
        }
        
        # Add high-frequency words from wordfreq if available
        try:
            top_1000 = []
            for i in range(1000):
                try:
                    word = wordfreq.word_frequency('en', i)
                    if word:
                        top_1000.append(word)
                except:
                    break
            basic_common.update(top_1000)
        except:
            pass
        
        return basic_common

# Test function
def test_extractor():
    """Test the vocabulary extractor with sample text"""
    extractor = UniversalVocabularyExtractor()
    
    sample_texts = [
        """The phenomenological approach to consciousness represents a paradigmatic shift 
           in our epistemological understanding of subjective experience.""",
        
        """Cardiovascular pathophysiology encompasses the multifaceted interactions between 
           hemodynamic variables and myocardial contractility.""",
           
        """The archaeological evidence suggests that paleolithic societies demonstrated 
           sophisticated technological innovations in lithic manufacturing processes."""
    ]
    
    for i, text in enumerate(sample_texts):
        print(f"\n--- Sample {i+1} ---")
        print(f"Text: {text[:100]}...")
        
        candidates = extractor.extract_candidates(text, {'source': 'test', 'sample': i+1})
        
        print(f"Found {len(candidates)} candidates:")
        for candidate in candidates[:5]:  # Show top 5
            print(f"  {candidate.term} (score: {candidate.preliminary_score:.1f}) - {candidate.morphological_type}")

if __name__ == "__main__":
    test_extractor()