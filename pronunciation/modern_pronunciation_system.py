"""
Modern Phonetic Processor for Pronunciation Similarity System

This module provides phonetic transcription capabilities using:
- CMU Pronouncing Dictionary (primary source)
- Online IPA APIs (fallback)  
- Rule-based pronunciation generation (last resort)
"""

import mysql.connector
import pandas as pd
import numpy as np
import re
import logging
import requests
import json
from typing import List, Tuple, Dict, Optional, Set
from dataclasses import dataclass
from tqdm import tqdm
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
import Levenshtein
import pickle
import os
from urllib.parse import quote

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


@dataclass
class PhoneticData:
    """Container for phonetic information about a word"""
    word: str
    ipa: str
    arpabet: str
    syllable_count: int
    stress_pattern: str
    phonemes: List[str]
    source: str  # Track which method was used


class ModernPhoneticProcessor:
    """Modern phonetic processor using multiple reliable sources"""

    def __init__(self):
        self.cmu_dict = {}
        self.ipa_cache = {}
        self.cache_file = 'phonetic_cache.pkl'

        # Load CMU Dictionary
        self._load_cmu_dictionary()

        # Load cache if exists
        self._load_cache()

        # ARPAbet to IPA conversion mapping
        self.arpabet_to_ipa = {
            # Vowels
            'AA': 'ɑ', 'AE': 'æ', 'AH': 'ʌ', 'AO': 'ɔ', 'AW': 'aʊ',
            'AX': 'ə', 'AXR': 'ɚ', 'AY': 'aɪ', 'EH': 'ɛ', 'ER': 'ɜr',
            'EY': 'eɪ', 'IH': 'ɪ', 'IX': 'ɨ', 'IY': 'i', 'OW': 'oʊ',
            'OY': 'ɔɪ', 'UH': 'ʊ', 'UW': 'u', 'UX': 'ʉ',

            # Consonants
            'B': 'b', 'CH': 'tʃ', 'D': 'd', 'DH': 'ð', 'DX': 'ɾ',
            'EL': 'l̩', 'EM': 'm̩', 'EN': 'n̩', 'F': 'f', 'G': 'ɡ',
            'HH': 'h', 'JH': 'dʒ', 'K': 'k', 'L': 'l', 'M': 'm',
            'N': 'n', 'NG': 'ŋ', 'NX': 'ɾ̃', 'P': 'p', 'Q': 'ʔ',
            'R': 'r', 'S': 's', 'SH': 'ʃ', 'T': 't', 'TH': 'θ',
            'V': 'v', 'W': 'w', 'WH': 'ʍ', 'Y': 'j', 'Z': 'z',
            'ZH': 'ʒ'
        }

        # English phoneme patterns for fallback
        self.vowel_patterns = {
            'a': ['æ', 'eɪ', 'ɑ'], 'e': ['ɛ', 'i'], 'i': ['ɪ', 'aɪ'],
            'o': ['ɑ', 'oʊ', 'ɔ'], 'u': ['ʌ', 'u', 'ʊ'], 'y': ['ɪ', 'aɪ']
        }

        logger.info("Modern phonetic processor initialized")

    def _load_cmu_dictionary(self):
        """Load CMU Pronouncing Dictionary"""
        try:
            # Try to download CMU dictionary if not exists
            cmu_file = 'cmudict-0.7b.txt'
            if not os.path.exists(cmu_file):
                logger.info("Downloading CMU Pronouncing Dictionary...")
                url = "https://raw.githubusercontent.com/cmusphinx/cmudict/master/cmudict.dict"
                response = requests.get(url, timeout=30)
                if response.status_code == 200:
                    with open(cmu_file, 'w', encoding='utf-8') as f:
                        f.write(response.text)
                    logger.info("CMU dictionary downloaded successfully")
                else:
                    logger.warning("Could not download CMU dictionary, using fallback methods")
                    return

            # Parse CMU dictionary
            with open(cmu_file, 'r', encoding='utf-8') as f:
                for line in f:
                    if line.startswith(';;;') or not line.strip():
                        continue

                    parts = line.strip().split()
                    if len(parts) >= 2:
                        word = parts[0].split('(')[0].lower()  # Remove variant markers
                        phonemes = parts[1:]
                        self.cmu_dict[word] = phonemes

            logger.info(f"Loaded {len(self.cmu_dict)} entries from CMU dictionary")

        except Exception as e:
            logger.warning(f"Could not load CMU dictionary: {e}")

    def _load_cache(self):
        """Load phonetic cache from file"""
        try:
            if os.path.exists(self.cache_file):
                with open(self.cache_file, 'rb') as f:
                    self.ipa_cache = pickle.load(f)
                logger.info(f"Loaded {len(self.ipa_cache)} entries from cache")
        except Exception as e:
            logger.warning(f"Could not load cache: {e}")

    def _save_cache(self):
        """Save phonetic cache to file"""
        try:
            with open(self.cache_file, 'wb') as f:
                pickle.dump(self.ipa_cache, f)
        except Exception as e:
            logger.warning(f"Could not save cache: {e}")

    def _get_ipa_from_api(self, word: str) -> Optional[str]:
        """Get IPA from online API (fallback method)"""
        try:
            # Use a free IPA API service
            url = f"https://api.dictionaryapi.dev/api/v2/entries/en/{quote(word)}"
            response = requests.get(url, timeout=5)

            if response.status_code == 200:
                data = response.json()
                if isinstance(data, list) and len(data) > 0:
                    entry = data[0]
                    if 'phonetics' in entry:
                        for phonetic in entry['phonetics']:
                            if 'text' in phonetic and phonetic['text']:
                                # Clean up the IPA text
                                ipa = phonetic['text'].strip('/')
                                return ipa

        except Exception as e:
            logger.debug(f"API lookup failed for '{word}': {e}")

        return None

    def _arpabet_to_ipa_convert(self, arpabet_phonemes: List[str]) -> str:
        """Convert ARPAbet phonemes to IPA"""
        ipa_phonemes = []

        for phoneme in arpabet_phonemes:
            # Remove stress markers (0, 1, 2)
            clean_phoneme = re.sub(r'[012]', '', phoneme)

            # Convert to IPA
            if clean_phoneme in self.arpabet_to_ipa:
                ipa_phoneme = self.arpabet_to_ipa[clean_phoneme]

                # Add stress markers
                if '1' in phoneme:  # Primary stress
                    ipa_phoneme = 'ˈ' + ipa_phoneme
                elif '2' in phoneme:  # Secondary stress
                    ipa_phoneme = 'ˌ' + ipa_phoneme

                ipa_phonemes.append(ipa_phoneme)
            else:
                # Fallback: use the phoneme as-is
                ipa_phonemes.append(clean_phoneme.lower())

        return ''.join(ipa_phonemes)

    def _generate_fallback_pronunciation(self, word: str) -> Tuple[str, List[str]]:
        """Generate basic pronunciation using English phonetic rules"""
        word = word.lower()
        arpabet_phonemes = []

        # Very basic English pronunciation rules
        i = 0
        while i < len(word):
            char = word[i]

            # Handle common digraphs
            if i < len(word) - 1:
                digraph = word[i:i + 2]
                if digraph in ['ch', 'sh', 'th', 'ph', 'gh']:
                    if digraph == 'ch':
                        arpabet_phonemes.append('CH')
                    elif digraph == 'sh':
                        arpabet_phonemes.append('SH')
                    elif digraph == 'th':
                        # Simple heuristic: voiced vs unvoiced
                        if i == 0 or word[i - 1] in 'aeiou':
                            arpabet_phonemes.append('DH')
                        else:
                            arpabet_phonemes.append('TH')
                    elif digraph == 'ph':
                        arpabet_phonemes.append('F')
                    elif digraph == 'gh':
                        if i == len(word) - 2:  # End of word
                            pass  # Silent
                        else:
                            arpabet_phonemes.append('G')
                    i += 2
                    continue

            # Handle vowels (simplified)
            if char in 'aeiou':
                if char == 'a':
                    # Very simple: 'a' -> AE, except at end -> AH
                    if i == len(word) - 1:
                        arpabet_phonemes.append('AH')
                    else:
                        arpabet_phonemes.append('AE')
                elif char == 'e':
                    if i == len(word) - 1:
                        pass  # Often silent at end
                    else:
                        arpabet_phonemes.append('EH')
                elif char == 'i':
                    arpabet_phonemes.append('IH')
                elif char == 'o':
                    arpabet_phonemes.append('AA')
                elif char == 'u':
                    arpabet_phonemes.append('AH')

            # Handle consonants
            elif char in 'bcdfghjklmnpqrstvwxyz':
                consonant_map = {
                    'b': 'B', 'c': 'K', 'd': 'D', 'f': 'F', 'g': 'G',
                    'h': 'HH', 'j': 'JH', 'k': 'K', 'l': 'L', 'm': 'M',
                    'n': 'N', 'p': 'P', 'q': 'K', 'r': 'R', 's': 'S',
                    't': 'T', 'v': 'V', 'w': 'W', 'x': 'K S', 'y': 'Y',
                    'z': 'Z'
                }

                if char in consonant_map:
                    phonemes = consonant_map[char].split()
                    arpabet_phonemes.extend(phonemes)

            i += 1

        # Convert to IPA
        ipa = self._arpabet_to_ipa_convert(arpabet_phonemes)

        return ipa, arpabet_phonemes

    def _count_syllables_from_arpabet(self, arpabet_phonemes: List[str]) -> int:
        """Count syllables from ARPAbet phonemes"""
        vowel_phonemes = ['AA', 'AE', 'AH', 'AO', 'AW', 'AY', 'EH', 'ER',
                          'EY', 'IH', 'IY', 'OW', 'OY', 'UH', 'UW']

        syllable_count = 0
        for phoneme in arpabet_phonemes:
            # Remove stress markers
            clean_phoneme = re.sub(r'[012]', '', phoneme)
            if clean_phoneme in vowel_phonemes:
                syllable_count += 1

        return max(1, syllable_count)  # At least 1 syllable

    def _extract_stress_pattern_from_arpabet(self, arpabet_phonemes: List[str]) -> str:
        """Extract stress pattern from ARPAbet phonemes"""
        stress_pattern = ""

        for phoneme in arpabet_phonemes:
            if '1' in phoneme:  # Primary stress
                stress_pattern += '1'
            elif '2' in phoneme:  # Secondary stress
                stress_pattern += '2'
            elif any(vowel in phoneme for vowel in ['AA', 'AE', 'AH', 'AO', 'AW', 'AY',
                                                    'EH', 'ER', 'EY', 'IH', 'IY', 'OW',
                                                    'OY', 'UH', 'UW']):
                stress_pattern += '0'  # Unstressed vowel

        return stress_pattern or '0'

    def _extract_phonemes_from_ipa(self, ipa: str) -> List[str]:
        """Extract individual phonemes from IPA string"""
        # Remove stress markers temporarily for processing
        clean_ipa = re.sub(r'[ˈˌ]', '', ipa)

        phonemes = []
        i = 0
        while i < len(clean_ipa):
            # Handle common IPA digraphs and trigraphs
            if i < len(clean_ipa) - 2:
                trigraph = clean_ipa[i:i + 3]
                if trigraph in ['t͡ʃ', 'd͡ʒ']:
                    phonemes.append(trigraph)
                    i += 3
                    continue

            if i < len(clean_ipa) - 1:
                digraph = clean_ipa[i:i + 2]
                if digraph in ['tʃ', 'dʒ', 'eɪ', 'aɪ', 'ɔɪ', 'aʊ', 'oʊ', 'ɪə', 'eə', 'ʊə']:
                    phonemes.append(digraph)
                    i += 2
                    continue

            # Single phoneme
            if clean_ipa[i] not in ' \t\n':
                phonemes.append(clean_ipa[i])
            i += 1

        return phonemes

    def transcribe_word(self, word: str) -> PhoneticData:
        """Generate phonetic transcription for a word using multiple methods"""
        word_lower = word.lower().strip()

        # Check cache first
        if word_lower in self.ipa_cache:
            cached_data = self.ipa_cache[word_lower]
            return PhoneticData(
                word=word,
                ipa=cached_data['ipa'],
                arpabet=cached_data['arpabet'],
                syllable_count=cached_data['syllable_count'],
                stress_pattern=cached_data['stress_pattern'],
                phonemes=cached_data['phonemes'],
                source=cached_data['source']
            )

        ipa = ""
        arpabet_phonemes = []
        source = ""

        try:
            # Method 1: CMU Dictionary (most reliable)
            if word_lower in self.cmu_dict:
                arpabet_phonemes = self.cmu_dict[word_lower]
                ipa = self._arpabet_to_ipa_convert(arpabet_phonemes)
                source = "CMU Dictionary"

            # Method 2: Online API (if CMU fails)
            elif word_lower not in self.cmu_dict:
                api_ipa = self._get_ipa_from_api(word)
                if api_ipa:
                    ipa = api_ipa
                    # Convert IPA back to approximate ARPAbet for consistency
                    arpabet_phonemes = self._ipa_to_arpabet_approximate(ipa)
                    source = "Online API"

                # Method 3: Fallback pronunciation rules
                else:
                    ipa, arpabet_phonemes = self._generate_fallback_pronunciation(word)
                    source = "Fallback Rules"

            # Extract phonetic features
            syllable_count = self._count_syllables_from_arpabet(arpabet_phonemes)
            stress_pattern = self._extract_stress_pattern_from_arpabet(arpabet_phonemes)
            phonemes = self._extract_phonemes_from_ipa(ipa)

            # Cache the result
            cache_data = {
                'ipa': ipa,
                'arpabet': ' '.join(arpabet_phonemes),
                'syllable_count': syllable_count,
                'stress_pattern': stress_pattern,
                'phonemes': phonemes,
                'source': source
            }
            self.ipa_cache[word_lower] = cache_data

            return PhoneticData(
                word=word,
                ipa=ipa,
                arpabet=' '.join(arpabet_phonemes),
                syllable_count=syllable_count,
                stress_pattern=stress_pattern,
                phonemes=phonemes,
                source=source
            )

        except Exception as e:
            logger.error(f"Error transcribing word '{word}': {e}")
            return PhoneticData(
                word=word,
                ipa="",
                arpabet="",
                syllable_count=1,
                stress_pattern="0",
                phonemes=[],
                source="Error"
            )

    def _ipa_to_arpabet_approximate(self, ipa: str) -> List[str]:
        """Convert IPA back to approximate ARPAbet (for consistency)"""
        # Reverse mapping (approximate)
        ipa_to_arpabet = {v: k for k, v in self.arpabet_to_ipa.items()}

        # Additional mappings for common IPA symbols
        ipa_to_arpabet.update({
            'ə': 'AH', 'ɚ': 'ER', 'ɨ': 'IH', 'ɾ': 'T',
            'ʔ': 'T', 'ɡ': 'G', 'ʍ': 'W'
        })

        phonemes = []
        i = 0
        while i < len(ipa):
            found = False

            # Try longer sequences first
            for length in [3, 2, 1]:
                if i + length <= len(ipa):
                    segment = ipa[i:i + length]
                    if segment in ipa_to_arpabet:
                        phonemes.append(ipa_to_arpabet[segment])
                        i += length
                        found = True
                        break

            if not found:
                # Skip unknown characters or stress markers
                if ipa[i] not in 'ˈˌ':
                    phonemes.append('UH')  # Default vowel for unknown
                i += 1

        return phonemes

    def save_cache(self):
        """Save cache to disk"""
        self._save_cache()

    def get_cache_stats(self) -> Dict[str, int]:
        """Get cache statistics"""
        sources = {}
        for data in self.ipa_cache.values():
            source = data.get('source', 'Unknown')
            sources[source] = sources.get(source, 0) + 1

        return {
            'total_cached': len(self.ipa_cache),
            'sources': sources
        }


# Update the main system to use the modern processor
class DatabaseManager:
    """Handles all database operations - unchanged"""

    def __init__(self, host: str, port: int, database: str, user: str, password: str):
        self.connection_params = {
            'host': host,
            'port': port,
            'database': database,
            'user': user,
            'password': password
        }

    def get_connection(self):
        """Create a new database connection"""
        return mysql.connector.connect(**self.connection_params)

    def examine_schema(self):
        """Examine existing database structure"""
        with self.get_connection() as conn:
            cursor = conn.cursor()

            # Get all tables
            cursor.execute("SHOW TABLES")
            tables = [table[0] for table in cursor.fetchall()]
            logger.info(f"Found tables: {tables}")

            # Examine each table structure
            schema_info = {}
            for table in tables:
                cursor.execute(f"DESCRIBE {table}")
                columns = cursor.fetchall()
                schema_info[table] = columns
                logger.info(f"Table '{table}' structure:")
                for col in columns:
                    logger.info(f"  {col}")

            # Get word count if words table exists
            if any('word' in table.lower() for table in tables):
                word_table = next(table for table in tables if 'word' in table.lower())
                cursor.execute(f"SELECT COUNT(*) FROM {word_table}")
                count = cursor.fetchone()[0]
                logger.info(f"Total words in {word_table}: {count}")

                # Get sample words
                cursor.execute(f"SELECT * FROM {word_table} LIMIT 10")
                samples = cursor.fetchall()
                logger.info(f"Sample words: {samples}")

            return schema_info

    def create_phonetic_tables(self):
        """Create tables for phonetic data and similarity scores"""

        create_phonetics_table = """
                                 CREATE TABLE IF NOT EXISTS word_phonetics \
                                 ( \
                                     word_id \
                                     INT \
                                     PRIMARY \
                                     KEY, \
                                     word \
                                     VARCHAR \
                                 ( \
                                     255 \
                                 ) NOT NULL,
                                     ipa_transcription TEXT,
                                     arpabet_transcription TEXT,
                                     syllable_count INT,
                                     stress_pattern VARCHAR \
                                 ( \
                                     50 \
                                 ),
                                     phonemes_json TEXT,
                                     transcription_source VARCHAR \
                                 ( \
                                     50 \
                                 ),
                                     created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                                     INDEX idx_word \
                                 ( \
                                     word \
                                 ),
                                     INDEX idx_syllables \
                                 ( \
                                     syllable_count \
                                 ),
                                     INDEX idx_source \
                                 ( \
                                     transcription_source \
                                 )
                                     ) \
                                 """

        create_similarity_table = """
                                  CREATE TABLE IF NOT EXISTS pronunciation_similarity \
                                  ( \
                                      word1_id \
                                      INT, \
                                      word2_id \
                                      INT, \
                                      overall_similarity \
                                      DECIMAL \
                                  ( \
                                      6, \
                                      5 \
                                  ),
                                      phonetic_distance DECIMAL \
                                  ( \
                                      6, \
                                      5 \
                                  ),
                                      stress_similarity DECIMAL \
                                  ( \
                                      6, \
                                      5 \
                                  ),
                                      rhyme_score DECIMAL \
                                  ( \
                                      6, \
                                      5 \
                                  ),
                                      syllable_similarity DECIMAL \
                                  ( \
                                      6, \
                                      5 \
                                  ),
                                      created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                                      PRIMARY KEY \
                                  ( \
                                      word1_id, \
                                      word2_id \
                                  ),
                                      INDEX idx_overall_similarity \
                                  ( \
                                      overall_similarity \
                                      DESC \
                                  ),
                                      INDEX idx_word1_similarity \
                                  ( \
                                      word1_id, \
                                      overall_similarity \
                                      DESC \
                                  ),
                                      INDEX idx_word2_similarity \
                                  ( \
                                      word2_id, \
                                      overall_similarity \
                                      DESC \
                                  ),
                                      INDEX idx_high_similarity \
                                  ( \
                                      overall_similarity \
                                      DESC, \
                                      word1_id, \
                                      word2_id \
                                  ),
                                      CONSTRAINT chk_word_order CHECK \
                                  ( \
                                      word1_id < \
                                      word2_id \
                                  )
                                      ) \
                                  """

        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(create_phonetics_table)
            cursor.execute(create_similarity_table)
            conn.commit()
            logger.info("Created phonetic tables successfully")

    def get_words(self, limit: Optional[int] = None) -> List[Tuple[int, str]]:
        """Retrieve words from database"""
        with self.get_connection() as conn:
            cursor = conn.cursor()

            # First, find the correct table name
            cursor.execute("SHOW TABLES")
            tables = [table[0] for table in cursor.fetchall()]

            # Look for words table (common names: words, word, vocabulary, vocab)
            word_table = None
            for table in tables:
                if any(name in table.lower() for name in ['word', 'vocab']):
                    word_table = table
                    break

            if not word_table:
                raise ValueError("Could not find words table. Please specify the correct table name.")

            # Get table structure to find ID and word columns
            cursor.execute(f"DESCRIBE {word_table}")
            columns = [col[0] for col in cursor.fetchall()]

            # Find ID column (usually 'id' or ends with '_id')
            id_col = next((col for col in columns if col.lower() in ['id', 'word_id']), columns[0])

            # Find word column
            word_col = next((col for col in columns if 'word' in col.lower() and col != id_col), None)
            if not word_col:
                raise ValueError("Could not find word column in table")

            query = f"SELECT {id_col}, {word_col} FROM {word_table}"
            if limit:
                query += f" LIMIT {limit}"

            cursor.execute(query)
            return cursor.fetchall()

    def insert_phonetic_data(self, phonetic_data_list: List[PhoneticData]):
        """Insert phonetic data into database"""
        with self.get_connection() as conn:
            cursor = conn.cursor()

            insert_query = """
                           INSERT INTO word_phonetics
                           (word_id, word, ipa_transcription, arpabet_transcription,
                            syllable_count, stress_pattern, phonemes_json, transcription_source)
                           VALUES (%(word_id)s, %(word)s, %(ipa)s, %(arpabet)s,
                                   %(syllable_count)s, %(stress_pattern)s, %(phonemes_json)s, \
                                   %(source)s) ON DUPLICATE KEY \
                           UPDATE \
                               ipa_transcription = \
                           VALUES (ipa_transcription), arpabet_transcription = \
                           VALUES (arpabet_transcription), syllable_count = \
                           VALUES (syllable_count), stress_pattern = \
                           VALUES (stress_pattern), phonemes_json = \
                           VALUES (phonemes_json), transcription_source = \
                           VALUES (transcription_source) \
                           """

            # Convert phonetic data to dict format for insertion
            data_dicts = []
            for data in phonetic_data_list:
                data_dict = {
                    'word_id': getattr(data, 'word_id', None),
                    'word': data.word,
                    'ipa': data.ipa,
                    'arpabet': data.arpabet,
                    'syllable_count': data.syllable_count,
                    'stress_pattern': data.stress_pattern,
                    'phonemes_json': json.dumps(data.phonemes),
                    'source': data.source
                }
                data_dicts.append(data_dict)

            cursor.executemany(insert_query, data_dicts)
            conn.commit()
            logger.info(f"Inserted {len(data_dicts)} phonetic records")

    def insert_similarity_scores(self, similarity_scores):
        """Insert similarity scores into database"""
        with self.get_connection() as conn:
            cursor = conn.cursor()

            insert_query = """
                           INSERT INTO pronunciation_similarity
                           (word1_id, word2_id, overall_similarity, phonetic_distance,
                            stress_similarity, rhyme_score, syllable_similarity)
                           VALUES (%(word1_id)s, %(word2_id)s, %(overall_similarity)s, %(phonetic_distance)s,
                                   %(stress_similarity)s, %(rhyme_score)s, %(syllable_similarity)s) ON DUPLICATE KEY \
                           UPDATE \
                               overall_similarity = \
                           VALUES (overall_similarity), phonetic_distance = \
                           VALUES (phonetic_distance), stress_similarity = \
                           VALUES (stress_similarity), rhyme_score = \
                           VALUES (rhyme_score), syllable_similarity = \
                           VALUES (syllable_similarity) \
                           """

            data_dicts = []
            for score in similarity_scores:
                data_dict = {
                    'word1_id': score.word1_id,
                    'word2_id': score.word2_id,
                    'overall_similarity': score.overall_similarity,
                    'phonetic_distance': score.phonetic_distance,
                    'stress_similarity': score.stress_similarity,
                    'rhyme_score': score.rhyme_score,
                    'syllable_similarity': score.syllable_similarity
                }
                data_dicts.append(data_dict)

            cursor.executemany(insert_query, data_dicts)
            conn.commit()
            logger.info(f"Inserted {len(data_dicts)} similarity records")


# Rest of the classes remain the same (SimilarityCalculator, etc.)
# Just update the main system class to use ModernPhoneticProcessor

class ModernPronunciationSimilaritySystem:
    """Main system using modern phonetic processor"""

    def __init__(self, db_config: Dict[str, any]):
        self.db_manager = DatabaseManager(**db_config)
        self.phonetic_processor = ModernPhoneticProcessor()  # Updated!
        # Include other components...

    def initialize_system(self):
        """Initialize the system"""
        logger.info("Initializing Modern Pronunciation Similarity System...")

        # Examine existing database
        schema_info = self.db_manager.examine_schema()

        # Create new tables
        self.db_manager.create_phonetic_tables()

        logger.info("System initialization complete")
        return schema_info

    def process_all_words(self, batch_size: int = 1000, save_cache_every: int = 5000):
        """Process all words with cache saving"""
        logger.info("Starting phonetic processing for all words...")

        words = self.db_manager.get_words()
        logger.info(f"Found {len(words)} words to process")

        processed_count = 0

        for i in range(0, len(words), batch_size):
            batch = words[i:i + batch_size]
            logger.info(f"Processing batch {i // batch_size + 1}/{(len(words) - 1) // batch_size + 1}")

            phonetic_data_list = []
            for word_id, word in tqdm(batch, desc="Transcribing words"):
                phonetic_data = self.phonetic_processor.transcribe_word(word)
                phonetic_data.word_id = word_id
                phonetic_data_list.append(phonetic_data)

                processed_count += 1

                # Save cache periodically
                if processed_count % save_cache_every == 0:
                    self.phonetic_processor.save_cache()
                    logger.info(f"Cache saved after processing {processed_count} words")

            # Store batch in database
            self.db_manager.insert_phonetic_data(phonetic_data_list)

        # Final cache save
        self.phonetic_processor.save_cache()

        # Log cache statistics
        cache_stats = self.phonetic_processor.get_cache_stats()
        logger.info(f"Phonetic processing complete. Cache stats: {cache_stats}")

    def get_processing_report(self) -> Dict[str, any]:
        """Get a report on phonetic processing sources"""
        with self.db_manager.get_connection() as conn:
            query = """
                    SELECT transcription_source, \
                           COUNT(*) as count,
                COUNT(*) * 100.0 / (SELECT COUNT(*) FROM word_phonetics) as percentage
                    FROM word_phonetics
                    GROUP BY transcription_source
                    ORDER BY count DESC \
                    """
            cursor = conn.cursor()
            cursor.execute(query)
            results = cursor.fetchall()

            return {
                'source_breakdown': results,
                'total_processed': sum(row[1] for row in results)
            }


# Similarity Calculator (unchanged from previous version)
@dataclass
class SimilarityScore:
    """Container for similarity metrics between two words"""
    word1_id: int
    word2_id: int
    overall_similarity: float
    phonetic_distance: float
    stress_similarity: float
    rhyme_score: float
    syllable_similarity: float


class SimilarityCalculator:
    """Calculates pronunciation similarity between words"""

    def __init__(self):
        pass

    def calculate_similarity(self, phonetic1: PhoneticData, phonetic2: PhoneticData) -> SimilarityScore:
        """Calculate comprehensive similarity score between two words"""

        # Calculate individual similarity components
        phonetic_dist = self._phonetic_distance(phonetic1, phonetic2)
        stress_sim = self._stress_similarity(phonetic1, phonetic2)
        rhyme_sim = self._rhyme_similarity(phonetic1, phonetic2)
        syllable_sim = self._syllable_similarity(phonetic1, phonetic2)

        # Combine into overall similarity (weighted average)
        weights = {
            'phonetic': 0.4,
            'stress': 0.2,
            'rhyme': 0.3,
            'syllable': 0.1
        }

        overall = (
                weights['phonetic'] * (1 - phonetic_dist) +
                weights['stress'] * stress_sim +
                weights['rhyme'] * rhyme_sim +
                weights['syllable'] * syllable_sim
        )

        return SimilarityScore(
            word1_id=0,  # Will be set by caller
            word2_id=0,  # Will be set by caller
            overall_similarity=overall,
            phonetic_distance=phonetic_dist,
            stress_similarity=stress_sim,
            rhyme_score=rhyme_sim,
            syllable_similarity=syllable_sim
        )

    def _phonetic_distance(self, p1: PhoneticData, p2: PhoneticData) -> float:
        """Calculate normalized Levenshtein distance between phoneme sequences"""
        if not p1.phonemes or not p2.phonemes:
            return 1.0

        # Use phoneme sequences for more accurate comparison
        seq1 = ''.join(p1.phonemes)
        seq2 = ''.join(p2.phonemes)

        distance = Levenshtein.distance(seq1, seq2)
        max_len = max(len(seq1), len(seq2))

        return distance / max_len if max_len > 0 else 0.0

    def _stress_similarity(self, p1: PhoneticData, p2: PhoneticData) -> float:
        """Calculate similarity of stress patterns"""
        if not p1.stress_pattern or not p2.stress_pattern:
            return 0.0

        # Normalize patterns to same length
        max_len = max(len(p1.stress_pattern), len(p2.stress_pattern))
        pattern1 = p1.stress_pattern.ljust(max_len, '0')
        pattern2 = p2.stress_pattern.ljust(max_len, '0')

        matches = sum(1 for c1, c2 in zip(pattern1, pattern2) if c1 == c2)
        return matches / max_len if max_len > 0 else 0.0

    def _rhyme_similarity(self, p1: PhoneticData, p2: PhoneticData) -> float:
        """Calculate rhyming similarity based on ending sounds"""
        if not p1.phonemes or not p2.phonemes:
            return 0.0

        # Compare last 2-3 phonemes (ending sounds)
        ending1 = p1.phonemes[-3:] if len(p1.phonemes) >= 3 else p1.phonemes
        ending2 = p2.phonemes[-3:] if len(p2.phonemes) >= 3 else p2.phonemes

        # Calculate similarity of endings
        min_len = min(len(ending1), len(ending2))
        if min_len == 0:
            return 0.0

        matches = sum(1 for i in range(min_len)
                      if ending1[-(i + 1)] == ending2[-(i + 1)])

        return matches / min_len

    def _syllable_similarity(self, p1: PhoneticData, p2: PhoneticData) -> float:
        """Calculate similarity based on syllable count"""
        if p1.syllable_count == 0 and p2.syllable_count == 0:
            return 1.0

        max_syllables = max(p1.syllable_count, p2.syllable_count)
        diff = abs(p1.syllable_count - p2.syllable_count)

        return 1.0 - (diff / max_syllables) if max_syllables > 0 else 0.0


# Complete the main system class
class ModernPronunciationSimilaritySystem:
    """Main system using modern phonetic processor"""

    def __init__(self, db_config: Dict[str, any]):
        self.db_manager = DatabaseManager(**db_config)
        self.phonetic_processor = ModernPhoneticProcessor()
        self.similarity_calculator = SimilarityCalculator()

    def initialize_system(self):
        """Initialize the system"""
        logger.info("Initializing Modern Pronunciation Similarity System...")

        # Examine existing database
        schema_info = self.db_manager.examine_schema()

        # Create new tables
        self.db_manager.create_phonetic_tables()

        logger.info("System initialization complete")
        return schema_info

    def process_all_words(self, batch_size: int = 1000, save_cache_every: int = 5000):
        """Process all words with cache saving"""
        logger.info("Starting phonetic processing for all words...")

        words = self.db_manager.get_words()
        logger.info(f"Found {len(words)} words to process")

        processed_count = 0

        for i in range(0, len(words), batch_size):
            batch = words[i:i + batch_size]
            logger.info(f"Processing batch {i // batch_size + 1}/{(len(words) - 1) // batch_size + 1}")

            phonetic_data_list = []
            for word_id, word in tqdm(batch, desc="Transcribing words"):
                phonetic_data = self.phonetic_processor.transcribe_word(word)
                phonetic_data.word_id = word_id
                phonetic_data_list.append(phonetic_data)

                processed_count += 1

                # Save cache periodically
                if processed_count % save_cache_every == 0:
                    self.phonetic_processor.save_cache()
                    logger.info(f"Cache saved after processing {processed_count} words")

            # Store batch in database
            self.db_manager.insert_phonetic_data(phonetic_data_list)

        # Final cache save
        self.phonetic_processor.save_cache()

        # Log cache statistics
        cache_stats = self.phonetic_processor.get_cache_stats()
        logger.info(f"Phonetic processing complete. Cache stats: {cache_stats}")

    def calculate_all_similarities(self, similarity_threshold: float = 0.1, batch_size: int = 10000):
        """Calculate pairwise similarities for all words"""
        logger.info("Starting similarity calculation...")

        # Get all phonetic data
        with self.db_manager.get_connection() as conn:
            query = """
                    SELECT word_id, \
                           word, \
                           ipa_transcription, \
                           arpabet_transcription,
                           syllable_count, \
                           stress_pattern, \
                           phonemes_json
                    FROM word_phonetics
                    WHERE ipa_transcription != '' \
                    """
            df = pd.read_sql(query, conn)

        logger.info(f"Calculating similarities for {len(df)} words")

        # Convert to PhoneticData objects
        phonetic_data = {}
        for _, row in df.iterrows():
            phonemes = json.loads(row['phonemes_json']) if row['phonemes_json'] else []
            phonetic_data[row['word_id']] = PhoneticData(
                word=row['word'],
                ipa=row['ipa_transcription'],
                arpabet=row['arpabet_transcription'],
                syllable_count=row['syllable_count'],
                stress_pattern=row['stress_pattern'],
                phonemes=phonemes,
                source="database"
            )

        # Calculate pairwise similarities
        word_ids = list(phonetic_data.keys())
        total_pairs = len(word_ids) * (len(word_ids) - 1) // 2
        logger.info(f"Total pairs to calculate: {total_pairs}")

        similarity_scores = []
        processed_pairs = 0

        for i in range(len(word_ids)):
            for j in range(i + 1, len(word_ids)):
                word1_id, word2_id = word_ids[i], word_ids[j]

                similarity = self.similarity_calculator.calculate_similarity(
                    phonetic_data[word1_id],
                    phonetic_data[word2_id]
                )

                # Only store similarities above threshold
                if similarity.overall_similarity >= similarity_threshold:
                    similarity.word1_id = word1_id
                    similarity.word2_id = word2_id
                    similarity_scores.append(similarity)

                processed_pairs += 1

                # Store batch when it reaches batch_size
                if len(similarity_scores) >= batch_size:
                    self.db_manager.insert_similarity_scores(similarity_scores)
                    similarity_scores = []

                # Progress reporting
                if processed_pairs % 100000 == 0:
                    logger.info(f"Processed {processed_pairs}/{total_pairs} pairs")

        # Store remaining similarities
        if similarity_scores:
            self.db_manager.insert_similarity_scores(similarity_scores)

        logger.info("Similarity calculation complete")

    def get_processing_report(self) -> Dict[str, any]:
        """Get a report on phonetic processing sources"""
        with self.db_manager.get_connection() as conn:
            query = """
                    SELECT transcription_source, \
                           COUNT(*) as count,
                COUNT(*) * 100.0 / (SELECT COUNT(*) FROM word_phonetics) as percentage
                    FROM word_phonetics
                    GROUP BY transcription_source
                    ORDER BY count DESC \
                    """
            cursor = conn.cursor()
            cursor.execute(query)
            results = cursor.fetchall()

            return {
                'source_breakdown': results,
                'total_processed': sum(row[1] for row in results)
            }

    def add_new_word(self, word_id: int, word: str):
        """Add a new word and calculate its similarities"""
        logger.info(f"Adding new word: {word}")

        # Generate phonetic data
        phonetic_data = self.phonetic_processor.transcribe_word(word)
        phonetic_data.word_id = word_id

        # Store phonetic data
        self.db_manager.insert_phonetic_data([phonetic_data])

        # Get all existing phonetic data for similarity calculation
        with self.db_manager.get_connection() as conn:
            query = """
                    SELECT word_id, \
                           word, \
                           ipa_transcription, \
                           arpabet_transcription,
                           syllable_count, \
                           stress_pattern, \
                           phonemes_json
                    FROM word_phonetics
                    WHERE word_id != %s \
                      AND ipa_transcription != '' \
                    """
            cursor = conn.cursor()
            cursor.execute(query, (word_id,))
            existing_words = cursor.fetchall()

        # Calculate similarities with all existing words
        similarity_scores = []
        for row in existing_words:
            phonemes = json.loads(row[6]) if row[6] else []
            existing_phonetic = PhoneticData(
                word=row[1],
                ipa=row[2],
                arpabet=row[3],
                syllable_count=row[4],
                stress_pattern=row[5],
                phonemes=phonemes,
                source="database"
            )

            similarity = self.similarity_calculator.calculate_similarity(
                phonetic_data, existing_phonetic
            )

            # Store only significant similarities
            if similarity.overall_similarity >= 0.1:
                similarity.word1_id = min(word_id, row[0])
                similarity.word2_id = max(word_id, row[0])
                similarity_scores.append(similarity)

        # Store similarities
        if similarity_scores:
            self.db_manager.insert_similarity_scores(similarity_scores)

        logger.info(f"Added {word} with {len(similarity_scores)} similarities")


# Analyzer and utility classes
class SimilarityAnalyzer:
    """Tools for analyzing and managing the similarity data"""

    def __init__(self, db_manager: DatabaseManager):
        self.db_manager = db_manager

    def generate_similarity_report(self) -> Dict[str, any]:
        """Generate a comprehensive report on similarity data"""
        with self.db_manager.get_connection() as conn:
            cursor = conn.cursor()

            # Basic statistics
            cursor.execute("SELECT COUNT(*) FROM word_phonetics")
            total_words = cursor.fetchone()[0]

            cursor.execute("SELECT COUNT(*) FROM pronunciation_similarity")
            total_similarities = cursor.fetchone()[0]

            cursor.execute("SELECT AVG(overall_similarity) FROM pronunciation_similarity")
            avg_similarity = cursor.fetchone()[0]

            cursor.execute("SELECT MAX(overall_similarity) FROM pronunciation_similarity")
            max_similarity = cursor.fetchone()[0]

            # Source breakdown
            cursor.execute("""
                           SELECT transcription_source, COUNT(*) as count
                           FROM word_phonetics
                           GROUP BY transcription_source
                           ORDER BY count DESC
                           """)
            source_breakdown = cursor.fetchall()

            # Similarity distribution
            cursor.execute("""
                           SELECT CASE
                                      WHEN overall_similarity >= 0.8 THEN 'Very High (0.8-1.0)'
                                      WHEN overall_similarity >= 0.6 THEN 'High (0.6-0.8)'
                                      WHEN overall_similarity >= 0.4 THEN 'Medium (0.4-0.6)'
                                      WHEN overall_similarity >= 0.2 THEN 'Low (0.2-0.4)'
                                      ELSE 'Very Low (0.0-0.2)'
                                      END as similarity_range,
                                  COUNT(*) as count
                           FROM pronunciation_similarity
                           GROUP BY similarity_range
                           ORDER BY MIN (overall_similarity) DESC
                           """)
            similarity_distribution = cursor.fetchall()

            return {
                'total_words': total_words,
                'total_similarities': total_similarities,
                'average_similarity': float(avg_similarity) if avg_similarity else 0,
                'max_similarity': float(max_similarity) if max_similarity else 0,
                'source_breakdown': source_breakdown,
                'similarity_distribution': similarity_distribution
            }

    def find_best_distractors(self, target_word_id: int, num_distractors: int = 4,
                              similarity_range: Tuple[float, float] = (0.3, 0.7)) -> List[Tuple[int, str, float]]:
        """Find the best distractors for a target word within a similarity range"""
        with self.db_manager.get_connection() as conn:
            query = """
                    SELECT CASE \
                               WHEN ps.word1_id = %s THEN ps.word2_id \
                               ELSE ps.word1_id \
                               END as distractor_word_id, \
                           CASE \
                               WHEN ps.word1_id = %s THEN wp2.word \
                               ELSE wp1.word \
                               END as distractor_word, \
                           ps.overall_similarity, \
                           ps.phonetic_distance, \
                           ps.rhyme_score, \
                           CASE \
                               WHEN ps.word1_id = %s THEN wp2.transcription_source \
                               ELSE wp1.transcription_source \
                               END as source
                    FROM pronunciation_similarity ps
                             JOIN word_phonetics wp1 ON ps.word1_id = wp1.word_id
                             JOIN word_phonetics wp2 ON ps.word2_id = wp2.word_id
                    WHERE (ps.word1_id = %s OR ps.word2_id = %s)
                      AND ps.overall_similarity BETWEEN %s AND %s
                    ORDER BY ps.overall_similarity DESC, ps.rhyme_score DESC
                        LIMIT %s \
                    """

            cursor = conn.cursor()
            cursor.execute(query, (
                target_word_id, target_word_id, target_word_id,
                target_word_id, target_word_id,
                similarity_range[0], similarity_range[1], num_distractors
            ))
            return cursor.fetchall()


# Usage example and CLI
def create_modern_cli():
    """Create a command-line interface for the modern system"""
    import argparse

    parser = argparse.ArgumentParser(description='Modern Pronunciation Similarity System (No eSpeak)')
    parser.add_argument('--initialize', action='store_true', help='Initialize the system')
    parser.add_argument('--process-words', action='store_true', help='Process all words for phonetics')
    parser.add_argument('--calculate-similarities', action='store_true', help='Calculate all similarities')
    parser.add_argument('--similarity-threshold', type=float, default=0.1, help='Minimum similarity to store')
    parser.add_argument('--batch-size', type=int, default=1000, help='Batch size for processing')
    parser.add_argument('--generate-report', action='store_true', help='Generate similarity report')
    parser.add_argument('--processing-report', action='store_true', help='Generate phonetic processing report')
    parser.add_argument('--test-word', type=str, help='Test phonetic transcription for a word')
    parser.add_argument('--cache-stats', action='store_true', help='Show cache statistics')

    return parser


if __name__ == "__main__":
    # Database configuration
    DB_CONFIG = {
        'host': '10.0.0.196',
        'port': 3306,
        'database': 'Vocab',
        'user': 'brian',
        'password': 'Fl1p5ma5h!'
    }

    import sys

    if len(sys.argv) > 1:
        parser = create_modern_cli()
        args = parser.parse_args()

        # Initialize system
        system = ModernPronunciationSimilaritySystem(DB_CONFIG)

        if args.initialize:
            system.initialize_system()
            print("✅ Modern system initialized successfully")

        if args.test_word:
            phonetic_data = system.phonetic_processor.transcribe_word(args.test_word)
            print(f"=== Phonetic Analysis for '{args.test_word}' ===")
            print(f"IPA: {phonetic_data.ipa}")
            print(f"ARPAbet: {phonetic_data.arpabet}")
            print(f"Syllables: {phonetic_data.syllable_count}")
            print(f"Stress: {phonetic_data.stress_pattern}")
            print(f"Phonemes: {phonetic_data.phonemes}")
            print(f"Source: {phonetic_data.source}")

        if args.cache_stats:
            stats = system.phonetic_processor.get_cache_stats()
            print("=== Cache Statistics ===")
            print(f"Total cached entries: {stats['total_cached']}")
            print("Sources breakdown:")
            for source, count in stats['sources'].items():
                print(f"  {source}: {count}")

        if args.process_words:
            system.process_all_words(batch_size=args.batch_size)
            print("✅ Word processing complete")

        if args.calculate_similarities:
            system.calculate_all_similarities(similarity_threshold=args.similarity_threshold)
            print("✅ Similarity calculation complete")

        if args.processing_report:
            report = system.get_processing_report()
            print("=== Phonetic Processing Report ===")
            print(f"Total processed: {report['total_processed']}")
            print("Source breakdown:")
            for source, count, percentage in report['source_breakdown']:
                print(f"  {source}: {count} ({percentage:.1f}%)")

        if args.generate_report:
            analyzer = SimilarityAnalyzer(system.db_manager)
            report = analyzer.generate_similarity_report()
            print("=== Pronunciation Similarity Report ===")
            for key, value in report.items():
                if key == 'source_breakdown':
                    print(f"{key}:")
                    for source, count in value:
                        print(f"  {source}: {count}")
                elif key == 'similarity_distribution':
                    print(f"{key}:")
                    for range_name, count in value:
                        print(f"  {range_name}: {count}")
                else:
                    print(f"{key}: {value}")

    else:
        print("Modern Pronunciation Similarity System (No eSpeak Required)")
        print("Run with --help for command line options")
        print("\nTesting phonetic processor...")

        # Quick test
        processor = ModernPhoneticProcessor()
        test_words = ["serendipity", "perspicacious", "obfuscate", "hello", "world"]

        for word in test_words:
            result = processor.transcribe_word(word)
            print(f"{word}: {result.ipa} ({result.source})")