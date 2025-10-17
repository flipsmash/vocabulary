#!/usr/bin/env python3
"""
Vocabulary Quiz System with Spaced Repetition
Supports multiple choice, T/F, and matching questions with smart distractors
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
    correct_answer: str
    options: List[str]  # For multiple choice
    explanation: str

@dataclass
class UserResponse:
    user_id: int
    word_id: int
    question_type: QuestionType
    is_correct: bool
    response_time_ms: int
    answered_at: datetime

class QuizSystem:
    def __init__(self):
        self.config = get_db_config()
    
    def get_connection(self):
        return mysql.connector.connect(**self.config)
    
    def create_quiz_tables(self):
        """Create tables for tracking user quiz performance"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        try:
            # User quiz results table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS user_quiz_results (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    user_id INT NOT NULL,
                    word_id INT NOT NULL,
                    question_type ENUM('multiple_choice', 'true_false', 'matching') NOT NULL,
                    is_correct BOOLEAN NOT NULL,
                    response_time_ms INT,
                    answered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    difficulty_level ENUM('easy', 'medium', 'hard') DEFAULT 'medium',
                    
                    INDEX idx_user_word (user_id, word_id),
                    INDEX idx_user_time (user_id, answered_at),
                    INDEX idx_word_results (word_id, is_correct),
                    
                    FOREIGN KEY (word_id) REFERENCES defined(id) ON DELETE CASCADE
                )
            """)
            
            # User word mastery tracking
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS user_word_mastery (
                    user_id INT NOT NULL,
                    word_id INT NOT NULL,
                    mastery_level ENUM('learning', 'reviewing', 'mastered') DEFAULT 'learning',
                    total_attempts INT DEFAULT 0,
                    correct_attempts INT DEFAULT 0,
                    last_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    next_review TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    streak INT DEFAULT 0,
                    ease_factor FLOAT DEFAULT 2.5,
                    
                    PRIMARY KEY (user_id, word_id),
                    INDEX idx_next_review (user_id, next_review),
                    INDEX idx_mastery (user_id, mastery_level),
                    
                    FOREIGN KEY (word_id) REFERENCES defined(id) ON DELETE CASCADE
                )
            """)
            
            conn.commit()
            logger.info("Quiz tables created successfully")
            
        except Exception as e:
            conn.rollback()
            logger.error(f"Error creating quiz tables: {e}")
            raise
        finally:
            cursor.close()
            conn.close()
    
    def find_phonetic_distractors(self, target_word_id: int, limit: int = 10) -> List[QuizWord]:
        """Find phonetically similar words using existing pronunciation_similarity data"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        try:
            # Use existing pronunciation similarity data
            cursor.execute("""
                SELECT 
                    d.id, d.term, d.definition, d.part_of_speech,
                    wd.primary_domain, wfi.frequency_rank,
                    wp.ipa_transcription, wp.arpabet_transcription,
                    ps.overall_similarity
                FROM vocab.pronunciation_similarity ps
                JOIN vocab.defined d ON (
                    CASE 
                        WHEN ps.word1_id = %s THEN d.id = ps.word2_id
                        WHEN ps.word2_id = %s THEN d.id = ps.word1_id
                        ELSE FALSE
                    END
                )
                LEFT JOIN vocab.word_domains wd ON d.id = wd.word_id
                LEFT JOIN vocab.word_frequencies_independent wfi ON d.id = wfi.word_id  
                LEFT JOIN vocab.word_phonetics wp ON d.id = wp.word_id
                WHERE ps.overall_similarity > 0.3
                AND d.id != %s
                ORDER BY ps.overall_similarity DESC
                LIMIT %s
            """, (target_word_id, target_word_id, target_word_id, limit))
            
            results = cursor.fetchall()
            # Extract only the QuizWord fields (exclude similarity score)
            return [QuizWord(*row[:8]) for row in results]
            
        except Exception as e:
            logger.error(f"Error finding phonetic distractors: {e}")
            return []
        finally:
            cursor.close()
            conn.close()
    
    def find_semantic_distractors(self, target_word_id: int, same_domain: bool = True, 
                                same_pos: bool = True, limit: int = 10) -> List[QuizWord]:
        """Find semantically similar words using definition similarity"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        try:
            # Get target word info first
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
            
            # Build query with optional filters
            base_query = """
                SELECT 
                    d.id, d.term, d.definition, d.part_of_speech,
                    wd.primary_domain, wfi.frequency_rank,
                    wp.ipa_transcription, wp.arpabet_transcription,
                    ds.cosine_similarity
                FROM vocab.definition_similarity ds
                JOIN vocab.defined d ON (
                    CASE 
                        WHEN ds.word1_id = %s THEN d.id = ds.word2_id
                        WHEN ds.word2_id = %s THEN d.id = ds.word1_id
                        ELSE FALSE
                    END
                )
                LEFT JOIN vocab.word_domains wd ON d.id = wd.word_id
                LEFT JOIN vocab.word_frequencies_independent wfi ON d.id = wfi.word_id
                LEFT JOIN vocab.word_phonetics wp ON d.id = wp.word_id
                WHERE ds.cosine_similarity > 0.2
                AND ds.cosine_similarity < 0.8
                AND d.id != %s
            """
            
            params = [target_word_id, target_word_id, target_word_id]
            
            # Add POS filter (always same POS per requirements)
            if same_pos and target_pos:
                base_query += " AND d.part_of_speech = %s"
                params.append(target_pos)
            
            # Add domain filter (60% of the time per requirements)
            if same_domain and target_domain and random.random() < 0.6:
                base_query += " AND wd.primary_domain = %s"
                params.append(target_domain)
            
            base_query += " ORDER BY ds.cosine_similarity DESC LIMIT %s"
            params.append(limit)
            
            cursor.execute(base_query, params)
            results = cursor.fetchall()
            # Extract only the QuizWord fields (exclude similarity score)
            return [QuizWord(*row[:8]) for row in results]
            
        except Exception as e:
            logger.error(f"Error finding semantic distractors: {e}")
            return []
        finally:
            cursor.close()
            conn.close()
    
    def find_random_distractors(self, target_word_id: int, same_pos: bool = True, limit: int = 5) -> List[QuizWord]:
        """Find random distractors with same part of speech"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        try:
            # Get target word POS
            cursor.execute("SELECT part_of_speech FROM vocab.defined WHERE id = %s", (target_word_id,))
            result = cursor.fetchone()
            if not result:
                return []
                
            target_pos = result[0]
            
            query = """
                SELECT DISTINCT
                    d.id, d.term, d.definition, d.part_of_speech,
                    wd.primary_domain, wfi.frequency_rank,
                    wp.ipa_transcription, wp.arpabet_transcription
                FROM vocab.defined d
                LEFT JOIN vocab.word_domains wd ON d.id = wd.word_id
                LEFT JOIN vocab.word_frequencies_independent wfi ON d.id = wfi.word_id
                LEFT JOIN vocab.word_phonetics wp ON d.id = wp.word_id
                WHERE d.id != %s
            """
            
            params = [target_word_id]
            
            if same_pos and target_pos:
                query += " AND d.part_of_speech = %s"
                params.append(target_pos)
            
            query += " ORDER BY RAND() LIMIT %s"
            params.append(limit)
            
            cursor.execute(query, params)
            results = cursor.fetchall()
            return [QuizWord(*row) for row in results]
            
        except Exception as e:
            logger.error(f"Error finding random distractors: {e}")
            return []
        finally:
            cursor.close()
            conn.close()
    
    def get_smart_distractors(self, target_word: QuizWord, num_distractors: int = 3) -> List[QuizWord]:
        """Get a mix of semantic, phonetic, and random distractors"""
        all_distractors = []
        
        # Get semantic distractors (50% of distractors)
        semantic_count = max(1, num_distractors // 2)
        semantic_distractors = self.find_semantic_distractors(
            target_word.id, same_domain=True, same_pos=True, limit=semantic_count * 2
        )
        all_distractors.extend(semantic_distractors[:semantic_count])
        
        # Get phonetic distractors (25% of distractors)
        phonetic_count = max(1, num_distractors // 4)
        phonetic_distractors = self.find_phonetic_distractors(
            target_word.id, limit=phonetic_count * 2
        )
        # Filter out already selected distractors
        phonetic_distractors = [d for d in phonetic_distractors 
                              if d.id not in [dist.id for dist in all_distractors]]
        all_distractors.extend(phonetic_distractors[:phonetic_count])
        
        # Fill remaining with random distractors
        remaining = num_distractors - len(all_distractors)
        if remaining > 0:
            random_distractors = self.find_random_distractors(
                target_word.id, same_pos=True, limit=remaining * 2
            )
            # Filter out already selected distractors
            random_distractors = [d for d in random_distractors 
                                if d.id not in [dist.id for dist in all_distractors]]
            all_distractors.extend(random_distractors[:remaining])
        
        return all_distractors[:num_distractors]
    
    def create_multiple_choice_question(self, word: QuizWord) -> Question:
        """Create a multiple choice question with smart distractors"""
        distractors = self.get_smart_distractors(word, num_distractors=3)
        
        # Create options list
        options = [word.definition]  # Correct answer
        for distractor in distractors:
            options.append(distractor.definition)
        
        # Shuffle options
        correct_answer = word.definition
        random.shuffle(options)
        
        question = Question(
            question_id=f"mc_{word.id}_{random.randint(1000, 9999)}",
            question_type=QuestionType.MULTIPLE_CHOICE,
            word=word,
            question_text=f"What is the definition of '{word.term}'?",
            correct_answer=correct_answer,
            options=options,
            explanation=f"'{word.term}' means: {word.definition}"
        )
        
        return question
    
    def create_true_false_question(self, word: QuizWord) -> Question:
        """Create a true/false question"""
        # 50% true, 50% false
        is_true_question = random.choice([True, False])
        
        if is_true_question:
            question_text = f"True or False: '{word.term}' means '{word.definition}'"
            correct_answer = "True"
            explanation = f"Correct! '{word.term}' does mean '{word.definition}'"
        else:
            # Get a wrong definition from distractors
            distractors = self.get_smart_distractors(word, num_distractors=1)
            if distractors:
                wrong_definition = distractors[0].definition
                question_text = f"True or False: '{word.term}' means '{wrong_definition}'"
                correct_answer = "False"
                explanation = f"False! '{word.term}' actually means '{word.definition}', not '{wrong_definition}'"
            else:
                # Fallback to true question if no distractors found
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
            explanation=explanation
        )
        
        return question

def main():
    """Test the quiz system"""
    quiz = QuizSystem()
    
    # Create tables
    quiz.create_quiz_tables()
    
    # Test with a sample word
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
        
        # Test multiple choice question
        mc_question = quiz.create_multiple_choice_question(test_word)
        print("=== MULTIPLE CHOICE QUESTION ===")
        print(f"Q: {mc_question.question_text}")
        for i, option in enumerate(mc_question.options, 1):
            print(f"{i}. {option}")
        print(f"Correct: {mc_question.correct_answer}")
        print(f"Explanation: {mc_question.explanation}")
        print()
        
        # Test true/false question  
        tf_question = quiz.create_true_false_question(test_word)
        print("=== TRUE/FALSE QUESTION ===")
        print(f"Q: {tf_question.question_text}")
        print(f"Correct: {tf_question.correct_answer}")
        print(f"Explanation: {tf_question.explanation}")
        
    cursor.close()
    conn.close()

if __name__ == "__main__":
    main()