#!/usr/bin/env python3
"""
Enhanced Vocabulary Quiz System with Advanced Features
- Smart distractors using similarity tables
- True/False questions
- Matching questions  
- Spaced repetition algorithm
- User analytics
"""

import mysql.connector
import sys
import os

# Add parent directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from core.secure_config import get_db_config
from typing import List, Dict, Optional, Tuple, Any
import random
import logging
from datetime import datetime, timedelta
from dataclasses import dataclass
from enum import Enum
import json
import math

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class QuestionType(Enum):
    MULTIPLE_CHOICE = "multiple_choice"
    TRUE_FALSE = "true_false"
    MATCHING = "matching"

class Difficulty(Enum):
    EASY = "easy"
    MEDIUM = "medium"
    HARD = "hard"
    ADAPTIVE = "adaptive"

class MasteryLevel(Enum):
    LEARNING = "learning"
    REVIEWING = "reviewing"
    MASTERED = "mastered"

@dataclass
class QuizWord:
    id: int
    term: str
    definition: str
    part_of_speech: Optional[str]
    domain: Optional[str]
    frequency_rank: Optional[int]
    ipa_transcription: Optional[str]
    arpabet_transcription: Optional[str]

@dataclass
class Question:
    question_id: str
    question_type: QuestionType
    word: QuizWord
    question_text: str
    correct_answer: Any
    options: List[Any]
    explanation: str
    difficulty: str
    distractor_id: Optional[int] = None  # For T/F questions, the chosen distractor ID

@dataclass
class UserStats:
    user_id: int
    total_questions: int
    correct_answers: int
    accuracy: float
    words_learned: int
    words_reviewing: int
    words_mastered: int
    streak: int
    avg_response_time: float

class EnhancedQuizSystem:
    def __init__(self):
        self.config = get_db_config()
        self.spaced_repetition_intervals = [1, 3, 7, 14, 30, 90]  # days
    
    def get_connection(self):
        return mysql.connector.connect(**self.config)
    
    def create_enhanced_tables(self):
        """Create enhanced tables for quiz system"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        try:
            # Enhanced user quiz results
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS user_quiz_results (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    user_id INT NOT NULL,
                    word_id INT NOT NULL,
                    question_type ENUM('multiple_choice', 'true_false', 'matching') NOT NULL,
                    is_correct BOOLEAN NOT NULL,
                    response_time_ms INT,
                    answered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    difficulty_level ENUM('easy', 'medium', 'hard', 'adaptive') DEFAULT 'medium',
                    distractor_types JSON,
                    session_id VARCHAR(50),
                    
                    INDEX idx_user_word (user_id, word_id),
                    INDEX idx_user_time (user_id, answered_at),
                    INDEX idx_word_results (word_id, is_correct),
                    INDEX idx_session (session_id),
                    
                    FOREIGN KEY (word_id) REFERENCES defined(id) ON DELETE CASCADE
                )
            """)
            
            # Enhanced user word mastery
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS user_word_mastery (
                    user_id INT NOT NULL,
                    word_id INT NOT NULL,
                    mastery_level ENUM('learning', 'reviewing', 'mastered') DEFAULT 'learning',
                    total_attempts INT DEFAULT 0,
                    correct_attempts INT DEFAULT 0,
                    consecutive_correct INT DEFAULT 0,
                    last_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    next_review TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    interval_days INT DEFAULT 1,
                    ease_factor FLOAT DEFAULT 2.5,
                    difficulty_rating FLOAT DEFAULT 0.5,
                    
                    PRIMARY KEY (user_id, word_id),
                    INDEX idx_next_review (user_id, next_review),
                    INDEX idx_mastery (user_id, mastery_level),
                    INDEX idx_difficulty (difficulty_rating),
                    
                    FOREIGN KEY (word_id) REFERENCES defined(id) ON DELETE CASCADE
                )
            """)
            
            # Quiz sessions for tracking
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS quiz_sessions (
                    id VARCHAR(50) PRIMARY KEY,
                    user_id INT,
                    started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    completed_at TIMESTAMP NULL,
                    quiz_type VARCHAR(20),
                    difficulty VARCHAR(20),
                    topic_domain VARCHAR(100),
                    topic_pos VARCHAR(50),
                    total_questions INT,
                    correct_answers INT DEFAULT 0,
                    session_config JSON,
                    
                    INDEX idx_user_sessions (user_id, started_at)
                )
            """)
            
            # User mistake patterns for intelligent distractor generation
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS user_mistake_patterns (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    user_id INT NOT NULL,
                    correct_word_id INT NOT NULL,
                    chosen_distractor_word_id INT NOT NULL,
                    mistake_count INT DEFAULT 1,
                    last_mistake TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    question_type ENUM('multiple_choice', 'true_false', 'matching') NOT NULL,
                    confidence_level FLOAT DEFAULT 0.5,
                    
                    UNIQUE KEY unique_mistake (user_id, correct_word_id, chosen_distractor_word_id, question_type),
                    INDEX idx_user_mistakes (user_id, correct_word_id),
                    INDEX idx_global_patterns (correct_word_id, chosen_distractor_word_id),
                    INDEX idx_mistake_frequency (chosen_distractor_word_id, mistake_count DESC),
                    
                    FOREIGN KEY (correct_word_id) REFERENCES defined(id) ON DELETE CASCADE,
                    FOREIGN KEY (chosen_distractor_word_id) REFERENCES defined(id) ON DELETE CASCADE
                )
            """)
            
            conn.commit()
            logger.info("Enhanced quiz tables created successfully")
            
        except Exception as e:
            conn.rollback()
            logger.error(f"Error creating enhanced quiz tables: {e}")
            raise
        finally:
            cursor.close()
            conn.close()
    
    def get_semantic_distractors(self, target_word_id: int, same_domain: bool = True, 
                                same_pos: bool = True, limit: int = 10) -> List[QuizWord]:
        """Get semantically similar words using optimized similarity query"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        try:
            # Get target word info for filtering
            cursor.execute("""
                SELECT d.part_of_speech, wd.primary_domain
                FROM vocab.defined d
                LEFT JOIN vocab.word_domains wd ON d.id = wd.word_id
                WHERE d.id = %s
            """, (target_word_id,))
            
            target_info = cursor.fetchone()
            if not target_info:
                return []
                
            target_pos, target_domain = target_info
            
            # Optimized query using indexes
            query = """
                SELECT d2.id, d2.term, d2.definition, d2.part_of_speech,
                       wd2.primary_domain, wfi2.frequency_rank,
                       wp2.ipa_transcription, wp2.arpabet_transcription
                FROM vocab.definition_similarity ds
                JOIN vocab.defined d2 ON (
                    CASE WHEN ds.word1_id = %s THEN d2.id = ds.word2_id
                         ELSE d2.id = ds.word1_id END
                )
                LEFT JOIN vocab.word_domains wd2 ON d2.id = wd2.word_id
                LEFT JOIN vocab.word_frequencies_independent wfi2 ON d2.id = wfi2.word_id
                LEFT JOIN vocab.word_phonetics wp2 ON d2.id = wp2.word_id
                WHERE (ds.word1_id = %s OR ds.word2_id = %s)
                AND ds.cosine_similarity BETWEEN 0.2 AND 0.8
                AND d2.id != %s
            """
            
            params = [target_word_id, target_word_id, target_word_id, target_word_id]
            
            # Add filters based on requirements
            if same_pos and target_pos:
                query += " AND d2.part_of_speech = %s"
                params.append(target_pos)
            
            # 60% chance of same domain filter
            if same_domain and target_domain and random.random() < 0.6:
                query += " AND wd2.primary_domain = %s"
                params.append(target_domain)
            
            query += " ORDER BY ds.cosine_similarity DESC LIMIT %s"
            params.append(limit)
            
            cursor.execute(query, params)
            results = cursor.fetchall()
            return [QuizWord(*row) for row in results]
            
        except Exception as e:
            logger.error(f"Error getting semantic distractors: {e}")
            return []
        finally:
            cursor.close()
            conn.close()
    
    def get_phonetic_distractors(self, target_word_id: int, same_pos: bool = True, 
                                limit: int = 10) -> List[QuizWord]:
        """Get phonetically similar words using pronunciation similarity"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        try:
            # Get target POS for filtering
            cursor.execute("""
                SELECT part_of_speech FROM vocab.defined WHERE id = %s
            """, (target_word_id,))
            
            target_info = cursor.fetchone()
            if not target_info:
                return []
                
            target_pos = target_info[0]
            
            # Optimized phonetic similarity query
            query = """
                SELECT d2.id, d2.term, d2.definition, d2.part_of_speech,
                       wd2.primary_domain, wfi2.frequency_rank,
                       wp2.ipa_transcription, wp2.arpabet_transcription
                FROM vocab.pronunciation_similarity ps
                JOIN vocab.defined d2 ON (
                    CASE WHEN ps.word1_id = %s THEN d2.id = ps.word2_id
                         ELSE d2.id = ps.word1_id END
                )
                LEFT JOIN vocab.word_domains wd2 ON d2.id = wd2.word_id
                LEFT JOIN vocab.word_frequencies_independent wfi2 ON d2.id = wfi2.word_id
                LEFT JOIN vocab.word_phonetics wp2 ON d2.id = wp2.word_id
                WHERE (ps.word1_id = %s OR ps.word2_id = %s)
                AND ps.overall_similarity > 0.3
                AND d2.id != %s
            """
            
            params = [target_word_id, target_word_id, target_word_id, target_word_id]
            
            if same_pos and target_pos:
                query += " AND d2.part_of_speech = %s"
                params.append(target_pos)
            
            query += " ORDER BY ps.overall_similarity DESC LIMIT %s"
            params.append(limit)
            
            cursor.execute(query, params)
            results = cursor.fetchall()
            return [QuizWord(*row) for row in results]
            
        except Exception as e:
            logger.error(f"Error getting phonetic distractors: {e}")
            return []
        finally:
            cursor.close()
            conn.close()
    
    def get_random_distractors(self, target_word_id: int, same_pos: bool = True, 
                              exclude_ids: List[int] = None, limit: int = 5) -> List[QuizWord]:
        """Get random distractors with filtering"""
        if exclude_ids is None:
            exclude_ids = []
        
        conn = self.get_connection()
        cursor = conn.cursor()
        
        try:
            # Get target POS
            cursor.execute("SELECT part_of_speech FROM vocab.defined WHERE id = %s", (target_word_id,))
            result = cursor.fetchone()
            if not result:
                return []
                
            target_pos = result[0]
            
            # Build exclusion list
            exclude_list = [target_word_id] + exclude_ids
            exclude_placeholders = ','.join(['%s'] * len(exclude_list))
            
            query = f"""
                SELECT d.id, d.term, d.definition, d.part_of_speech,
                       wd.primary_domain, wfi.frequency_rank,
                       wp.ipa_transcription, wp.arpabet_transcription
                FROM vocab.defined d
                LEFT JOIN vocab.word_domains wd ON d.id = wd.word_id
                LEFT JOIN vocab.word_frequencies_independent wfi ON d.id = wfi.word_id
                LEFT JOIN vocab.word_phonetics wp ON d.id = wp.word_id
                WHERE d.id NOT IN ({exclude_placeholders})
                AND d.definition IS NOT NULL AND d.definition != ''
            """
            
            params = exclude_list
            
            if same_pos and target_pos:
                query += " AND d.part_of_speech = %s"
                params.append(target_pos)
            
            query += " ORDER BY RAND() LIMIT %s"
            params.append(limit)
            
            cursor.execute(query, params)
            results = cursor.fetchall()
            return [QuizWord(*row) for row in results]
            
        except Exception as e:
            logger.error(f"Error getting random distractors: {e}")
            return []
        finally:
            cursor.close()
            conn.close()
    
    def get_mistake_based_distractors(self, target_word_id: int, user_id: int = None, 
                                     same_pos: bool = True, limit: int = 10) -> List[QuizWord]:
        """Get distractors based on user's past mistakes and global mistake patterns"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        try:
            # Get target word POS for filtering
            cursor.execute("SELECT part_of_speech FROM vocab.defined WHERE id = %s", (target_word_id,))
            target_info = cursor.fetchone()
            if not target_info:
                return []
            target_pos = target_info[0]
            
            distractor_words = []
            
            # 1. Get user's personal mistake patterns (if user is logged in)
            if user_id:
                personal_query = """
                    SELECT d.id, d.term, d.definition, d.part_of_speech,
                           wd.primary_domain, wfi.frequency_rank,
                           wp.ipa_transcription, wp.arpabet_transcription,
                           ump.mistake_count, ump.confidence_level
                    FROM user_mistake_patterns ump
                    JOIN vocab.defined d ON ump.chosen_distractor_word_id = d.id
                    LEFT JOIN vocab.word_domains wd ON d.id = wd.word_id
                    LEFT JOIN vocab.word_frequencies_independent wfi ON d.id = wfi.word_id
                    LEFT JOIN vocab.word_phonetics wp ON d.id = wp.word_id
                    WHERE ump.user_id = %s 
                    AND ump.correct_word_id = %s
                    AND d.id != %s
                """
                
                params = [user_id, target_word_id, target_word_id]
                
                if same_pos and target_pos:
                    personal_query += " AND d.part_of_speech = %s"
                    params.append(target_pos)
                
                personal_query += " ORDER BY ump.mistake_count DESC, ump.last_mistake DESC LIMIT %s"
                params.append(min(limit // 2, 5))  # Up to half of distractors from personal mistakes
                
                cursor.execute(personal_query, params)
                personal_results = cursor.fetchall()
                distractor_words.extend([QuizWord(*row[:8]) for row in personal_results])
            
            # 2. Get global mistake patterns for this word
            remaining_limit = limit - len(distractor_words)
            if remaining_limit > 0:
                global_query = """
                    SELECT d.id, d.term, d.definition, d.part_of_speech,
                           wd.primary_domain, wfi.frequency_rank,
                           wp.ipa_transcription, wp.arpabet_transcription,
                           SUM(ump.mistake_count) as total_mistakes
                    FROM user_mistake_patterns ump
                    JOIN vocab.defined d ON ump.chosen_distractor_word_id = d.id
                    LEFT JOIN vocab.word_domains wd ON d.id = wd.word_id
                    LEFT JOIN vocab.word_frequencies_independent wfi ON d.id = wfi.word_id
                    LEFT JOIN vocab.word_phonetics wp ON d.id = wp.word_id
                    WHERE ump.correct_word_id = %s
                    AND d.id != %s
                """
                
                params = [target_word_id, target_word_id]
                
                # Exclude already selected personal mistakes
                if distractor_words:
                    exclude_ids = [str(d.id) for d in distractor_words]
                    global_query += f" AND d.id NOT IN ({','.join(exclude_ids)})"
                
                if same_pos and target_pos:
                    global_query += " AND d.part_of_speech = %s"
                    params.append(target_pos)
                
                global_query += """ 
                    GROUP BY d.id 
                    ORDER BY total_mistakes DESC, MAX(ump.last_mistake) DESC 
                    LIMIT %s
                """
                params.append(remaining_limit)
                
                cursor.execute(global_query, params)
                global_results = cursor.fetchall()
                distractor_words.extend([QuizWord(*row[:8]) for row in global_results])
            
            return distractor_words
            
        except Exception as e:
            logger.error(f"Error getting mistake-based distractors: {e}")
            return []
        finally:
            cursor.close()
            conn.close()
    
    def record_mistake(self, user_id: int, correct_word_id: int, chosen_distractor_id: int, 
                      question_type: str, confidence: float = 0.5) -> None:
        """Record a user's mistake for future distractor generation"""
        if not user_id:
            return
            
        conn = self.get_connection()
        cursor = conn.cursor()
        
        try:
            # Upsert mistake pattern
            cursor.execute("""
                INSERT INTO user_mistake_patterns 
                (user_id, correct_word_id, chosen_distractor_word_id, question_type, confidence_level, mistake_count, last_mistake)
                VALUES (%s, %s, %s, %s, %s, 1, NOW())
                ON DUPLICATE KEY UPDATE
                mistake_count = mistake_count + 1,
                last_mistake = NOW(),
                confidence_level = (confidence_level + %s) / 2
            """, (user_id, correct_word_id, chosen_distractor_id, question_type, confidence, confidence))
            
            conn.commit()
            logger.info(f"Recorded mistake: user {user_id}, correct word {correct_word_id}, chose {chosen_distractor_id}")
            
        except Exception as e:
            conn.rollback()
            logger.error(f"Error recording mistake: {e}")
        finally:
            cursor.close()
            conn.close()
    
    def get_smart_distractors(self, target_word: QuizWord, num_distractors: int = 3, user_id: int = None) -> Dict[str, List[QuizWord]]:
        """Get a strategic mix of distractors with tracking of types used"""
        mistake_distractors = []
        semantic_distractors = []
        phonetic_distractors = []
        random_distractors = []
        
        # NEW: Get mistake-based distractors first (50% of total if available)
        mistake_count = max(1, int(num_distractors * 0.5)) if user_id else 0
        if mistake_count > 0:
            mistake_candidates = self.get_mistake_based_distractors(target_word.id, user_id, limit=mistake_count * 2)
            mistake_distractors = mistake_candidates[:mistake_count]
        
        used_ids = [d.id for d in mistake_distractors]
        remaining_distractors = num_distractors - len(mistake_distractors)
        
        if remaining_distractors > 0:
            # Adjust percentages for remaining slots
            # Semantic: 40% of remaining, Phonetic: 30% of remaining, Random: 30% of remaining
            semantic_count = max(1, int(remaining_distractors * 0.4))
            phonetic_count = max(1, int(remaining_distractors * 0.3))
            
            # Get semantic distractors
            semantic_candidates = self.get_semantic_distractors(target_word.id, limit=semantic_count * 2)
            semantic_distractors = [d for d in semantic_candidates if d.id not in used_ids][:semantic_count]
            used_ids.extend([d.id for d in semantic_distractors])
            
            # Get phonetic distractors
            phonetic_candidates = self.get_phonetic_distractors(target_word.id, limit=phonetic_count * 2)
            phonetic_distractors = [d for d in phonetic_candidates if d.id not in used_ids][:phonetic_count]
            used_ids.extend([d.id for d in phonetic_distractors])
            
            # Fill remaining with random distractors
            remaining = num_distractors - len(mistake_distractors) - len(semantic_distractors) - len(phonetic_distractors)
            if remaining > 0:
                random_candidates = self.get_random_distractors(target_word.id, exclude_ids=used_ids, limit=remaining * 2)
                random_distractors = random_candidates[:remaining]
        
        return {
            'mistake': mistake_distractors,
            'semantic': semantic_distractors,
            'phonetic': phonetic_distractors,
            'random': random_distractors,
            'all': mistake_distractors + semantic_distractors + phonetic_distractors + random_distractors
        }
    
    def create_multiple_choice_question(self, word: QuizWord, difficulty: str = "medium", user_id: int = None) -> Question:
        """Create enhanced multiple choice question with smart distractors"""
        distractors_info = self.get_smart_distractors(word, num_distractors=3, user_id=user_id)
        distractors = distractors_info['all']
        
        # Create options with word IDs for mistake tracking
        options = [{"definition": word.definition, "word_id": word.id}]
        for distractor in distractors:
            options.append({"definition": distractor.definition, "word_id": distractor.id})
        
        # Ensure we have exactly 4 options
        while len(options) < 4:
            fallback = self.get_random_distractors(word.id, limit=1)
            if fallback:
                options.append({"definition": fallback[0].definition, "word_id": fallback[0].id})
            else:
                break
        
        options = options[:4]  # Limit to 4
        correct_answer_data = options[0]  # Store the correct answer data before shuffling
        random.shuffle(options)
        
        # Find the correct index after shuffling
        correct_index = next(i for i, opt in enumerate(options) if opt["word_id"] == word.id)
        
        # Track distractor types used
        distractor_types = {
            'mistake': len(distractors_info.get('mistake', [])),
            'semantic': len(distractors_info['semantic']),
            'phonetic': len(distractors_info['phonetic']), 
            'random': len(distractors_info['random'])
        }
        
        question = Question(
            question_id=f"mc_{word.id}_{random.randint(1000, 9999)}",
            question_type=QuestionType.MULTIPLE_CHOICE,
            word=word,
            question_text=f"What is the definition of '{word.term}'?",
            correct_answer=correct_index,
            options=options,  # Now includes word_ids for mistake tracking
            explanation=f"'{word.term}' means: {word.definition}",
            difficulty=difficulty
        )
        
        return question, distractor_types
    
    def create_true_false_question(self, word: QuizWord, difficulty: str = "medium", user_id: int = None) -> Tuple[Question, Dict]:
        """Create true/false question with smart wrong definitions"""
        is_true_question = random.choice([True, False])
        distractor_types = {'mistake': 0, 'semantic': 0, 'phonetic': 0, 'random': 0}
        chosen_distractor_id = None
        
        if is_true_question:
            question_text = f"True or False: '{word.term}' means '{word.definition}'"
            correct_answer = "True"
            explanation = f"Correct! '{word.term}' does mean '{word.definition}'"
        else:
            # Get a smart distractor for false question
            distractors_info = self.get_smart_distractors(word, num_distractors=1, user_id=user_id)
            distractors = distractors_info['all']
            
            if distractors:
                chosen_distractor = distractors[0]
                wrong_definition = chosen_distractor.definition
                chosen_distractor_id = chosen_distractor.id
                distractor_types = {
                    'mistake': len(distractors_info.get('mistake', [])),
                    'semantic': len(distractors_info['semantic']),
                    'phonetic': len(distractors_info['phonetic']),
                    'random': len(distractors_info['random'])
                }
            else:
                # Fallback to random
                random_distractors = self.get_random_distractors(word.id, limit=1)
                if random_distractors:
                    chosen_distractor = random_distractors[0]
                    wrong_definition = chosen_distractor.definition
                    chosen_distractor_id = chosen_distractor.id
                    distractor_types['random'] = 1
                else:
                    # Ultimate fallback - make it a true question
                    is_true_question = True
                    wrong_definition = word.definition
            
            if not is_true_question:
                question_text = f"True or False: '{word.term}' means '{wrong_definition}'"
                correct_answer = "False"
                explanation = f"False! '{word.term}' actually means '{word.definition}', not '{wrong_definition}'"
            else:
                question_text = f"True or False: '{word.term}' means '{word.definition}'"
                correct_answer = "True"
                explanation = f"Correct! '{word.term}' does mean '{word.definition}'"
        
        question = Question(
            question_id=f"tf_{word.id}_{random.randint(1000, 9999)}",
            question_type=QuestionType.TRUE_FALSE,
            word=word,
            question_text=question_text,
            correct_answer=correct_answer,
            options=["True", "False"],
            explanation=explanation,
            difficulty=difficulty,
            distractor_id=chosen_distractor_id
        )
        
        return question, distractor_types
    
    def create_matching_question(self, words: List[QuizWord], difficulty: str = "medium") -> Tuple[Question, Dict]:
        """Create matching question with 3-10 word pairs"""
        num_pairs = min(len(words), random.randint(3, 8))  # Variable number of pairs
        selected_words = random.sample(words, num_pairs)
        
        # Create terms and definitions lists
        terms = [word.term for word in selected_words]
        definitions = [word.definition for word in selected_words]
        
        # Shuffle definitions to create the matching challenge
        shuffled_definitions = definitions.copy()
        random.shuffle(shuffled_definitions)
        
        # Create correct answer mapping (term index -> definition index in shuffled list)
        correct_answer = {}
        for i, word in enumerate(selected_words):
            correct_def_index = shuffled_definitions.index(word.definition)
            correct_answer[i] = correct_def_index
        
        question_text = f"Match each term to its correct definition ({num_pairs} pairs):"
        
        question = Question(
            question_id=f"match_{random.randint(10000, 99999)}",
            question_type=QuestionType.MATCHING,
            word=selected_words[0],  # Primary word for tracking
            question_text=question_text,
            correct_answer=correct_answer,
            options={"terms": terms, "definitions": shuffled_definitions},
            explanation=f"Correct matches: {', '.join([f'{word.term} = {word.definition[:50]}...' for word in selected_words])}",
            difficulty=difficulty
        )
        
        distractor_types = {'semantic': 0, 'phonetic': 0, 'random': num_pairs}
        return question, distractor_types
    
    def calculate_next_review(self, ease_factor: float, interval_days: int, quality: int) -> Tuple[int, float]:
        """Calculate next review interval using spaced repetition algorithm (SuperMemo2)"""
        if quality < 3:
            # Failed recall - start over
            new_interval = 1
            new_ease = max(1.3, ease_factor - 0.2)
        else:
            # Successful recall
            if interval_days == 1:
                new_interval = 6
            elif interval_days == 6:
                new_interval = 14
            else:
                new_interval = int(interval_days * ease_factor)
            
            # Update ease factor based on quality
            new_ease = ease_factor + (0.1 - (5 - quality) * (0.08 + (5 - quality) * 0.02))
            new_ease = max(1.3, new_ease)  # Minimum ease factor
        
        return new_interval, new_ease
    
    def update_word_mastery(self, user_id: int, word_id: int, is_correct: bool, 
                           response_time_ms: int = None) -> None:
        """Update user's mastery data for a word using spaced repetition"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        try:
            # Get current mastery data
            cursor.execute("""
                SELECT mastery_level, total_attempts, correct_attempts, consecutive_correct,
                       interval_days, ease_factor, difficulty_rating
                FROM vocab.user_word_mastery 
                WHERE user_id = %s AND word_id = %s
            """, (user_id, word_id))
            
            existing = cursor.fetchone()
            
            if existing:
                mastery_level, total_attempts, correct_attempts, consecutive_correct, interval_days, ease_factor, difficulty_rating = existing
            else:
                # New word for this user
                mastery_level = "learning"
                total_attempts = 0
                correct_attempts = 0
                consecutive_correct = 0
                interval_days = 1
                ease_factor = 2.5
                difficulty_rating = 0.5
            
            # Update attempt counts
            total_attempts += 1
            if is_correct:
                correct_attempts += 1
                consecutive_correct += 1
                quality = min(5, 3 + consecutive_correct // 2)  # Quality 3-5 based on streak
            else:
                consecutive_correct = 0
                quality = max(0, 2 - (total_attempts - correct_attempts))  # Quality 0-2 based on failures
            
            # Calculate next review using spaced repetition
            new_interval, new_ease = self.calculate_next_review(ease_factor, interval_days, quality)
            next_review = datetime.now() + timedelta(days=new_interval)
            
            # Update mastery level based on performance
            accuracy = correct_attempts / total_attempts if total_attempts > 0 else 0
            if consecutive_correct >= 5 and accuracy >= 0.8:
                new_mastery_level = "mastered"
            elif consecutive_correct >= 2 and accuracy >= 0.6:
                new_mastery_level = "reviewing"
            else:
                new_mastery_level = "learning"
            
            # Update difficulty rating (exponential moving average)
            if response_time_ms:
                time_factor = min(1.0, response_time_ms / 10000)  # Normalize to 10 seconds
                accuracy_factor = 1.0 if is_correct else 0.0
                new_difficulty = 0.8 * difficulty_rating + 0.2 * (time_factor + (1 - accuracy_factor)) / 2
            else:
                new_difficulty = difficulty_rating
            
            # Upsert mastery record
            cursor.execute("""
                INSERT INTO vocab.user_word_mastery 
                (user_id, word_id, mastery_level, total_attempts, correct_attempts, 
                 consecutive_correct, last_seen, next_review, interval_days, ease_factor, difficulty_rating)
                VALUES (%s, %s, %s, %s, %s, %s, NOW(), %s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE
                mastery_level = VALUES(mastery_level),
                total_attempts = VALUES(total_attempts),
                correct_attempts = VALUES(correct_attempts),
                consecutive_correct = VALUES(consecutive_correct),
                last_seen = NOW(),
                next_review = VALUES(next_review),
                interval_days = VALUES(interval_days),
                ease_factor = VALUES(ease_factor),
                difficulty_rating = VALUES(difficulty_rating)
            """, (user_id, word_id, new_mastery_level, total_attempts, correct_attempts,
                  consecutive_correct, next_review, new_interval, new_ease, new_difficulty))
            
            conn.commit()
            
        except Exception as e:
            conn.rollback()
            logger.error(f"Error updating word mastery: {e}")
            raise
        finally:
            cursor.close()
            conn.close()
    
    def get_words_for_review(self, user_id: int, limit: int = 10, difficulty: str = "medium") -> List[QuizWord]:
        """Get words due for review based on spaced repetition"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        try:
            # Get words due for review, prioritizing by urgency
            query = """
                SELECT d.id, d.term, d.definition, d.part_of_speech,
                       wd.primary_domain, wfi.frequency_rank,
                       wp.ipa_transcription, wp.arpabet_transcription,
                       uwm.mastery_level, uwm.next_review, uwm.difficulty_rating
                FROM vocab.user_word_mastery uwm
                JOIN vocab.defined d ON uwm.word_id = d.id
                LEFT JOIN vocab.word_domains wd ON d.id = wd.word_id
                LEFT JOIN vocab.word_frequencies_independent wfi ON d.id = wfi.word_id
                LEFT JOIN vocab.word_phonetics wp ON d.id = wp.word_id
                WHERE uwm.user_id = %s 
                AND uwm.next_review <= NOW()
                AND d.definition IS NOT NULL
            """
            
            params = [user_id]
            
            # Filter by difficulty if specified
            if difficulty == "easy":
                query += " AND uwm.difficulty_rating <= 0.4"
            elif difficulty == "hard":
                query += " AND uwm.difficulty_rating >= 0.7"
            elif difficulty == "medium":
                query += " AND uwm.difficulty_rating BETWEEN 0.3 AND 0.8"
            
            query += """
                ORDER BY 
                    CASE uwm.mastery_level 
                        WHEN 'learning' THEN 1
                        WHEN 'reviewing' THEN 2
                        WHEN 'mastered' THEN 3
                    END,
                    uwm.next_review ASC,
                    uwm.difficulty_rating DESC
                LIMIT %s
            """
            params.append(limit)
            
            cursor.execute(query, params)
            results = cursor.fetchall()
            
            # Convert to QuizWord objects (first 8 columns)
            return [QuizWord(*row[:8]) for row in results]
            
        except Exception as e:
            logger.error(f"Error getting words for review: {e}")
            return []
        finally:
            cursor.close()
            conn.close()
    
    def get_user_analytics(self, user_id: int, days: int = 30) -> UserStats:
        """Get comprehensive user analytics"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        try:
            # Get quiz results from specified time period
            cursor.execute("""
                SELECT 
                    COUNT(*) as total_questions,
                    SUM(CASE WHEN is_correct THEN 1 ELSE 0 END) as correct_answers,
                    AVG(response_time_ms) as avg_response_time
                FROM vocab.user_quiz_results
                WHERE user_id = %s AND answered_at >= DATE_SUB(NOW(), INTERVAL %s DAY)
            """, (user_id, days))
            
            quiz_stats = cursor.fetchone()
            total_questions = quiz_stats[0] or 0
            correct_answers = quiz_stats[1] or 0
            avg_response_time = quiz_stats[2] or 0
            accuracy = (correct_answers / total_questions * 100) if total_questions > 0 else 0
            
            # Get mastery level counts
            cursor.execute("""
                SELECT 
                    SUM(CASE WHEN mastery_level = 'learning' THEN 1 ELSE 0 END) as words_learning,
                    SUM(CASE WHEN mastery_level = 'reviewing' THEN 1 ELSE 0 END) as words_reviewing,
                    SUM(CASE WHEN mastery_level = 'mastered' THEN 1 ELSE 0 END) as words_mastered
                FROM vocab.user_word_mastery
                WHERE user_id = %s
            """, (user_id,))
            
            mastery_stats = cursor.fetchone()
            words_learning = mastery_stats[0] or 0
            words_reviewing = mastery_stats[1] or 0
            words_mastered = mastery_stats[2] or 0
            
            # Calculate current streak
            cursor.execute("""
                SELECT DATE(answered_at) as answer_date, 
                       SUM(CASE WHEN is_correct THEN 1 ELSE 0 END) as daily_correct,
                       COUNT(*) as daily_total
                FROM vocab.user_quiz_results
                WHERE user_id = %s
                GROUP BY DATE(answered_at)
                ORDER BY answer_date DESC
                LIMIT 30
            """, (user_id,))
            
            daily_results = cursor.fetchall()
            current_streak = 0
            for date, correct, total in daily_results:
                if correct / total >= 0.7:  # 70% accuracy required for streak
                    current_streak += 1
                else:
                    break
            
            return UserStats(
                user_id=user_id,
                total_questions=total_questions,
                correct_answers=correct_answers,
                accuracy=round(accuracy, 1),
                words_learned=words_learning,
                words_reviewing=words_reviewing,
                words_mastered=words_mastered,
                streak=current_streak,
                avg_response_time=round(avg_response_time, 0)
            )
            
        except Exception as e:
            logger.error(f"Error getting user analytics: {e}")
            return UserStats(user_id, 0, 0, 0.0, 0, 0, 0, 0, 0.0)
        finally:
            cursor.close()
            conn.close()

def main():
    """Test enhanced quiz system"""
    quiz = EnhancedQuizSystem()
    
    try:
        # Create enhanced tables
        quiz.create_enhanced_tables()
        
        # Test with sample word
        conn = quiz.get_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT d.id, d.term, d.definition, d.part_of_speech,
                   wd.primary_domain, wfi.frequency_rank,
                   wp.ipa_transcription, wp.arpabet_transcription
            FROM vocab.defined d
            LEFT JOIN vocab.word_domains wd ON d.id = wd.word_id
            LEFT JOIN vocab.word_frequencies_independent wfi ON d.id = wfi.word_id
            LEFT JOIN vocab.word_phonetics wp ON d.id = wp.word_id
            WHERE d.term = 'abacinate'
            LIMIT 1
        """)
        
        result = cursor.fetchone()
        if result:
            test_word = QuizWord(*result)
            
            # Test enhanced multiple choice
            print("=== ENHANCED MULTIPLE CHOICE ===")
            mc_question, mc_types = quiz.create_multiple_choice_question(test_word)
            print(f"Q: {mc_question.question_text}")
            for i, option in enumerate(mc_question.options, 1):
                marker = "[CORRECT]" if i-1 == mc_question.correct_answer else "         "
                print(f"{marker}{i}. {option}")
            print(f"Distractor types: {mc_types}")
            print()
            
            # Test true/false
            print("=== TRUE/FALSE ===")
            tf_question, tf_types = quiz.create_true_false_question(test_word)
            print(f"Q: {tf_question.question_text}")
            print(f"Answer: {tf_question.correct_answer}")
            print(f"Distractor types: {tf_types}")
            print()
            
        cursor.close()
        conn.close()
        
    except Exception as e:
        logger.error(f"Test failed: {e}")
        raise

if __name__ == "__main__":
    main()