#!/usr/bin/env python3
"""
Quiz Tracking System
Comprehensive tracking of quiz sessions, user results, and word mastery
"""

import uuid
import psycopg
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta
from dataclasses import dataclass
from enum import Enum
import json
import logging

from .config import VocabularyConfig
from .secure_config import get_database_config

logger = logging.getLogger(__name__)

class QuestionType(Enum):
    MULTIPLE_CHOICE = "multiple_choice"
    TRUE_FALSE = "true_false"
    MATCHING = "matching"

class DifficultyLevel(Enum):
    EASY = "easy"
    MEDIUM = "medium"
    HARD = "hard"

class MasteryLevel(Enum):
    LEARNING = "learning"
    REVIEWING = "reviewing"
    MASTERED = "mastered"

@dataclass
class QuizSession:
    id: str
    user_id: int
    started_at: datetime
    completed_at: Optional[datetime]
    quiz_type: str
    difficulty: str
    topic_domain: Optional[str]
    topic_pos: Optional[str]
    total_questions: int
    correct_answers: int
    session_config: Dict[str, Any]

@dataclass
class QuestionResult:
    user_id: int
    word_id: int
    session_id: str
    question_type: QuestionType
    is_correct: bool
    response_time_ms: Optional[int]
    difficulty_level: DifficultyLevel
    answered_at: datetime

@dataclass
class WordMastery:
    user_id: int
    word_id: int
    mastery_level: MasteryLevel
    total_attempts: int
    correct_attempts: int
    last_seen: datetime
    next_review: datetime
    streak: int
    ease_factor: float

class QuizTracker:
    """Main class for tracking quiz results and user progress"""

    def __init__(self):
        self.db_config = VocabularyConfig.get_db_config()
        self.db_schema = getattr(get_database_config(), "schema", None)

    def get_connection(self):
        """Get database connection"""
        conn = psycopg.connect(**self.db_config)
        if self.db_schema:
            conn.execute(
                f'SET search_path TO "{self.db_schema}"',
                prepare=False,
            )
        return conn

    def create_quiz_session(self, user_id: int, quiz_type: str, difficulty: str,
                          topic_domain: Optional[str] = None, topic_pos: Optional[str] = None,
                          total_questions: int = 10, session_config: Dict[str, Any] = None) -> str:
        """Create a new quiz session and return session ID"""
        session_id = str(uuid.uuid4())
        session_config = session_config or {}

        conn = self.get_connection()
        cursor = conn.cursor()

        try:
            cursor.execute("""
                INSERT INTO vocab.quiz_sessions
                (id, user_id, started_at, quiz_type, difficulty, topic_domain,
                 topic_pos, total_questions, correct_answers, session_config)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (session_id, user_id, datetime.now(), quiz_type, difficulty,
                  topic_domain, topic_pos, total_questions, 0, json.dumps(session_config)))

            conn.commit()
            logger.info(f"Created quiz session {session_id} for user {user_id}")
            return session_id

        except Exception as e:
            logger.error(f"Error creating quiz session: {e}")
            conn.rollback()
            raise
        finally:
            cursor.close()
            conn.close()

    def record_question_result(self, user_id: int, word_id: int, session_id: str,
                             question_type: QuestionType, is_correct: bool,
                             response_time_ms: Optional[int] = None,
                             difficulty_level: DifficultyLevel = DifficultyLevel.MEDIUM) -> bool:
        """Record result for a single question"""
        conn = self.get_connection()
        cursor = conn.cursor()

        try:
            # Insert question result
            cursor.execute("""
                INSERT INTO vocab.user_quiz_results
                (user_id, word_id, session_id, question_type, is_correct,
                 response_time_ms, answered_at, difficulty_level)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """, (user_id, word_id, session_id, question_type.value, is_correct,
                  response_time_ms, datetime.now(), difficulty_level.value))

            # Update word mastery
            self._update_word_mastery(cursor, user_id, word_id, is_correct, difficulty_level)

            conn.commit()
            logger.debug(f"Recorded question result: user={user_id}, word={word_id}, correct={is_correct}")
            return True

        except Exception as e:
            logger.error(f"Error recording question result: {e}")
            conn.rollback()
            return False
        finally:
            cursor.close()
            conn.close()

    def complete_quiz_session(self, session_id: str, final_score: int) -> bool:
        """Mark quiz session as completed with final score"""
        conn = self.get_connection()
        cursor = conn.cursor()

        try:
            cursor.execute("""
                UPDATE vocab.quiz_sessions
                SET completed_at = %s, correct_answers = %s
                WHERE id = %s
            """, (datetime.now(), final_score, session_id))

            conn.commit()
            logger.info(f"Completed quiz session {session_id} with score {final_score}")
            return True

        except Exception as e:
            logger.error(f"Error completing quiz session: {e}")
            conn.rollback()
            return False
        finally:
            cursor.close()
            conn.close()

    def _update_word_mastery(self, cursor, user_id: int, word_id: int, is_correct: bool,
                           difficulty_level: DifficultyLevel):
        """Update word mastery tracking (internal method using existing cursor)"""
        try:
            # Get current mastery record
            cursor.execute("""
                SELECT mastery_level, total_attempts, correct_attempts, streak, ease_factor
                FROM vocab.user_word_mastery
                WHERE user_id = %s AND word_id = %s
            """, (user_id, word_id))

            existing = cursor.fetchone()

            if existing:
                # Update existing record
                mastery_level, total_attempts, correct_attempts, streak, ease_factor = existing

                # Update counters
                total_attempts += 1
                if is_correct:
                    correct_attempts += 1
                    streak += 1
                else:
                    streak = 0

                # Calculate new ease factor (spaced repetition algorithm)
                if is_correct:
                    ease_factor = min(2.5, ease_factor + 0.1)
                else:
                    ease_factor = max(1.3, ease_factor - 0.2)

                # Determine mastery level
                accuracy = correct_attempts / total_attempts if total_attempts > 0 else 0

                if accuracy >= 0.9 and total_attempts >= 5 and streak >= 3:
                    new_mastery = MasteryLevel.MASTERED.value
                elif accuracy >= 0.7 and total_attempts >= 3:
                    new_mastery = MasteryLevel.REVIEWING.value
                else:
                    new_mastery = MasteryLevel.LEARNING.value

                # Calculate next review time (spaced repetition)
                if new_mastery == MasteryLevel.MASTERED.value:
                    next_review = datetime.now() + timedelta(days=int(7 * ease_factor))
                elif new_mastery == MasteryLevel.REVIEWING.value:
                    next_review = datetime.now() + timedelta(days=int(3 * ease_factor))
                else:
                    next_review = datetime.now() + timedelta(days=1)

                cursor.execute("""
                    UPDATE vocab.user_word_mastery
                    SET mastery_level = %s, total_attempts = %s, correct_attempts = %s,
                        last_seen = %s, next_review = %s, streak = %s, ease_factor = %s
                    WHERE user_id = %s AND word_id = %s
                """, (new_mastery, total_attempts, correct_attempts, datetime.now(),
                      next_review, streak, ease_factor, user_id, word_id))

            else:
                # Create new record
                ease_factor = 2.5
                streak = 1 if is_correct else 0
                mastery_level = MasteryLevel.LEARNING.value
                next_review = datetime.now() + timedelta(days=1)

                cursor.execute("""
                    INSERT INTO vocab.user_word_mastery
                    (user_id, word_id, mastery_level, total_attempts, correct_attempts,
                     last_seen, next_review, streak, ease_factor)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                """, (user_id, word_id, mastery_level, 1, 1 if is_correct else 0,
                      datetime.now(), next_review, streak, ease_factor))

        except Exception as e:
            logger.error(f"Error updating word mastery: {e}")
            raise

    def get_user_stats(self, user_id: int) -> Dict[str, Any]:
        """Get comprehensive user quiz statistics"""
        conn = self.get_connection()
        cursor = conn.cursor()

        try:
            # Overall quiz stats
            cursor.execute("""
                SELECT COUNT(*) as total_sessions,
                       AVG(correct_answers / total_questions * 100) as avg_accuracy,
                       SUM(correct_answers) as total_correct,
                       SUM(total_questions) as total_questions
                FROM vocab.quiz_sessions
                WHERE user_id = %s AND completed_at IS NOT NULL
            """, (user_id,))

            quiz_stats = cursor.fetchone()

            # Word mastery breakdown
            cursor.execute("""
                SELECT mastery_level, COUNT(*)
                FROM vocab.user_word_mastery
                WHERE user_id = %s
                GROUP BY mastery_level
            """, (user_id,))

            mastery_breakdown = dict(cursor.fetchall())

            # Recent performance
            cursor.execute("""
                SELECT DATE(answered_at) as quiz_date,
                       COUNT(*) as questions,
                       SUM(is_correct) as correct
                FROM vocab.user_quiz_results
                WHERE user_id = %s AND answered_at >= (NOW() - INTERVAL '30 days')
                GROUP BY DATE(answered_at)
                ORDER BY quiz_date DESC
                LIMIT 30
            """, (user_id,))

            recent_performance = [
                {"date": row[0].isoformat(), "questions": row[1], "correct": row[2]}
                for row in cursor.fetchall()
            ]

            return {
                "total_sessions": quiz_stats[0] or 0,
                "average_accuracy": round(quiz_stats[1] or 0, 1),
                "total_correct": quiz_stats[2] or 0,
                "total_questions": quiz_stats[3] or 0,
                "mastery_breakdown": mastery_breakdown,
                "recent_performance": recent_performance
            }

        except Exception as e:
            logger.error(f"Error getting user stats: {e}")
            return {}
        finally:
            cursor.close()
            conn.close()

    def get_words_for_review(self, user_id: int, limit: int = 20) -> List[Dict[str, Any]]:
        """Get words that need review based on spaced repetition"""
        conn = self.get_connection()
        cursor = conn.cursor()

        try:
            cursor.execute("""
                SELECT d.id, d.term, d.definition, uwm.mastery_level, uwm.next_review,
                       uwm.total_attempts, uwm.correct_attempts
                FROM vocab.user_word_mastery uwm
                JOIN vocab.defined d ON uwm.word_id = d.id
                WHERE uwm.user_id = %s AND uwm.next_review <= NOW()
                ORDER BY uwm.next_review ASC, uwm.mastery_level ASC
                LIMIT %s
            """, (user_id, limit))

            words = []
            for row in cursor.fetchall():
                words.append({
                    "word_id": row[0],
                    "term": row[1],
                    "definition": row[2],
                    "mastery_level": row[3],
                    "next_review": row[4].isoformat() if row[4] else None,
                    "total_attempts": row[5],
                    "correct_attempts": row[6],
                    "accuracy": round(row[6] / row[5] * 100, 1) if row[5] > 0 else 0
                })

            return words

        except Exception as e:
            logger.error(f"Error getting words for review: {e}")
            return []
        finally:
            cursor.close()
            conn.close()

# Global tracker instance
quiz_tracker = QuizTracker()
