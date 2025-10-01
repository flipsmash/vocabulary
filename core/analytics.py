#!/usr/bin/env python3
"""
Vocabulary Analytics System
Comprehensive analytics for user progress tracking and vocabulary mastery insights
"""

import psycopg
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime, timedelta
from dataclasses import dataclass
from enum import Enum
import json
import logging

from .config import VocabularyConfig

logger = logging.getLogger(__name__)

class ProgressTrend(Enum):
    IMPROVING = "improving"
    STABLE = "stable"
    DECLINING = "declining"

@dataclass
class WordProgress:
    word_id: int
    term: str
    definition: str
    part_of_speech: str
    total_attempts: int
    correct_attempts: int
    accuracy: float
    mastery_level: str
    streak: int
    last_seen: datetime
    next_review: datetime
    ease_factor: float
    domain: Optional[str] = None
    difficulty_trend: Optional[str] = None

@dataclass
class QuizAnalytics:
    total_sessions: int
    completed_sessions: int
    average_accuracy: float
    total_questions: int
    total_correct: int
    best_streak: int
    current_streak: int
    favorite_difficulty: str
    favorite_question_type: str
    time_spent_minutes: float
    sessions_this_week: int
    accuracy_trend: ProgressTrend

@dataclass
class VocabularyMastery:
    total_words_encountered: int
    words_learning: int
    words_reviewing: int
    words_mastered: int
    mastery_percentage: float
    words_due_today: int
    words_overdue: int
    average_ease_factor: float
    strongest_domains: List[Dict[str, Any]]
    weakest_domains: List[Dict[str, Any]]

@dataclass
class ActivityInsights:
    most_active_day: str
    most_active_hour: int
    days_since_last_quiz: int
    longest_streak_days: int
    study_consistency_score: float
    recent_performance_trend: ProgressTrend

class VocabularyAnalytics:
    """Main analytics class for comprehensive user progress analysis"""

    def __init__(self):
        self.db_config = VocabularyConfig.get_db_config()

    def get_connection(self):
        """Get database connection"""
        return psycopg.connect(**self.db_config)

    def get_comprehensive_analytics(self, user_id: int) -> Dict[str, Any]:
        """Get complete analytics dashboard data for a user"""
        try:
            quiz_analytics = self.get_quiz_analytics(user_id)
            vocabulary_mastery = self.get_vocabulary_mastery(user_id)
            word_progress = self.get_detailed_word_progress(user_id)
            activity_insights = self.get_activity_insights(user_id)
            recent_sessions = self.get_recent_quiz_sessions(user_id, limit=5)
            problem_areas = self.identify_problem_areas(user_id)

            return {
                "quiz_analytics": quiz_analytics,
                "vocabulary_mastery": vocabulary_mastery,
                "word_progress": word_progress,
                "activity_insights": activity_insights,
                "recent_sessions": recent_sessions,
                "problem_areas": problem_areas,
                "generated_at": datetime.now().isoformat()
            }

        except Exception as e:
            logger.error(f"Error generating comprehensive analytics for user {user_id}: {e}")
            return self._get_empty_analytics()

    def get_quiz_analytics(self, user_id: int) -> Dict[str, Any]:
        """Get detailed quiz performance analytics"""
        conn = self.get_connection()
        cursor = conn.cursor()

        try:
            # Basic quiz statistics - using individual question results for accuracy
            cursor.execute("""
                SELECT COUNT(DISTINCT qs.id) as total_sessions,
                       SUM(CASE WHEN qs.completed_at IS NOT NULL THEN 1 ELSE 0 END) as completed_sessions,
                       COUNT(uqr.id) as total_questions,
                       SUM(CASE WHEN uqr.is_correct = 1 THEN 1 ELSE 0 END) as total_correct
                FROM quiz_sessions qs
                LEFT JOIN user_quiz_results uqr ON qs.id = uqr.session_id
                WHERE qs.user_id = %s
            """, (user_id,))

            basic_stats = cursor.fetchone()
            total_sessions, completed_sessions, total_questions, total_correct = basic_stats

            # Calculate average accuracy from individual results
            avg_accuracy = (total_correct / total_questions * 100) if total_questions > 0 else 0

            # Question type preferences
            cursor.execute("""
                SELECT question_type, COUNT(*) as count, AVG(is_correct) as accuracy
                FROM user_quiz_results
                WHERE user_id = %s
                GROUP BY question_type
                ORDER BY count DESC
            """, (user_id,))

            question_types = [
                {"type": row[0], "count": row[1], "accuracy": float(row[2] or 0) * 100}
                for row in cursor.fetchall()
            ]

            # Difficulty analysis - using individual results joined with session difficulty
            cursor.execute("""
                SELECT qs.difficulty,
                       COUNT(DISTINCT qs.id) as sessions,
                       COUNT(uqr.id) as questions,
                       AVG(CASE WHEN uqr.is_correct = 1 THEN 100.0 ELSE 0.0 END) as accuracy
                FROM quiz_sessions qs
                LEFT JOIN user_quiz_results uqr ON qs.id = uqr.session_id
                WHERE qs.user_id = %s AND qs.completed_at IS NOT NULL
                GROUP BY qs.difficulty
                ORDER BY sessions DESC
            """, (user_id,))

            difficulty_stats = [
                {"difficulty": row[0], "sessions": row[1], "questions": row[2], "accuracy": float(row[3] or 0)}
                for row in cursor.fetchall()
            ]

            # Recent performance trend (last 10 sessions with question data)
            cursor.execute("""
                SELECT qs.id, qs.completed_at,
                       COUNT(uqr.id) as questions,
                       SUM(CASE WHEN uqr.is_correct = 1 THEN 1 ELSE 0 END) as correct
                FROM quiz_sessions qs
                LEFT JOIN user_quiz_results uqr ON qs.id = uqr.session_id
                WHERE qs.user_id = %s AND qs.completed_at IS NOT NULL
                GROUP BY qs.id, qs.completed_at
                HAVING questions > 0
                ORDER BY qs.completed_at DESC
                LIMIT 10
            """, (user_id,))

            recent_sessions = cursor.fetchall()
            recent_accuracies = [(row[2] / row[3] * 100) if row[3] > 0 else 0 for row in recent_sessions]
            trend = self._calculate_trend(recent_accuracies)

            # This week's activity
            cursor.execute("""
                SELECT COUNT(*)
                FROM quiz_sessions
                WHERE user_id = %s AND started_at >= (NOW() - INTERVAL '7 days')
            """, (user_id,))

            sessions_this_week = cursor.fetchone()[0]

            return {
                "total_sessions": total_sessions or 0,
                "completed_sessions": completed_sessions or 0,
                "average_accuracy": round(avg_accuracy, 1),
                "total_questions": total_questions or 0,
                "total_correct": total_correct or 0,
                "question_types": question_types,
                "difficulty_stats": difficulty_stats,
                "sessions_this_week": sessions_this_week,
                "performance_trend": trend.value,
                "completion_rate": round((completed_sessions or 0) / max(total_sessions or 1, 1) * 100, 1)
            }

        except Exception as e:
            logger.error(f"Error getting quiz analytics for user {user_id}: {e}")
            return {}
        finally:
            cursor.close()
            conn.close()

    def get_vocabulary_mastery(self, user_id: int) -> Dict[str, Any]:
        """Get vocabulary mastery breakdown and insights"""
        conn = self.get_connection()
        cursor = conn.cursor()

        try:
            # Mastery level breakdown
            cursor.execute("""
                SELECT mastery_level, COUNT(*) as count
                FROM user_word_mastery
                WHERE user_id = %s
                GROUP BY mastery_level
            """, (user_id,))

            mastery_breakdown = {row[0]: row[1] for row in cursor.fetchall()}

            # Words due for review
            cursor.execute("""
                SELECT COUNT(*) as due_today
                FROM user_word_mastery
                WHERE user_id = %s AND next_review <= NOW()
            """, (user_id,))

            due_today = cursor.fetchone()[0]

            cursor.execute("""
                SELECT COUNT(*) as overdue
                FROM user_word_mastery
                WHERE user_id = %s AND next_review < (NOW() - INTERVAL '1 day')
            """, (user_id,))

            overdue = cursor.fetchone()[0]

            # Domain performance analysis
            cursor.execute("""
                SELECT wd.primary_domain,
                       COUNT(*) as word_count,
                       AVG(uwm.correct_attempts / uwm.total_attempts * 100) as avg_accuracy,
                       SUM(CASE WHEN uwm.mastery_level = 'mastered' THEN 1 ELSE 0 END) as mastered_count
                FROM user_word_mastery uwm
                JOIN word_domains wd ON uwm.word_id = wd.word_id
                WHERE uwm.user_id = %s AND wd.primary_domain IS NOT NULL
                GROUP BY wd.primary_domain
                HAVING word_count >= 3
                ORDER BY avg_accuracy DESC
            """, (user_id,))

            domain_stats = []
            for row in cursor.fetchall():
                domain_stats.append({
                    "domain": row[0],
                    "word_count": row[1],
                    "accuracy": round(row[2] or 0, 1),
                    "mastered_count": row[3],
                    "mastery_rate": round(row[3] / row[1] * 100, 1)
                })

            total_words = sum(mastery_breakdown.values())
            mastered_count = mastery_breakdown.get('mastered', 0)

            return {
                "total_words_encountered": total_words,
                "words_learning": mastery_breakdown.get('learning', 0),
                "words_reviewing": mastery_breakdown.get('reviewing', 0),
                "words_mastered": mastered_count,
                "mastery_percentage": round(mastered_count / max(total_words, 1) * 100, 1),
                "words_due_today": due_today,
                "words_overdue": overdue,
                "domain_performance": domain_stats[:10],  # Top 10 domains
                "strongest_domains": domain_stats[:3],
                "weakest_domains": domain_stats[-3:] if len(domain_stats) > 3 else []
            }

        except Exception as e:
            logger.error(f"Error getting vocabulary mastery for user {user_id}: {e}")
            return {}
        finally:
            cursor.close()
            conn.close()

    def get_detailed_word_progress(self, user_id: int, limit: int = 50) -> List[Dict[str, Any]]:
        """Get detailed progress for individual words"""
        conn = self.get_connection()
        cursor = conn.cursor()

        try:
            cursor.execute("""
                SELECT uwm.word_id, d.term, d.definition, d.part_of_speech, wd.primary_domain,
                       uwm.total_attempts, uwm.correct_attempts, uwm.mastery_level,
                       uwm.streak, uwm.last_seen, uwm.next_review, uwm.ease_factor
                FROM user_word_mastery uwm
                JOIN defined d ON uwm.word_id = d.id
                LEFT JOIN word_domains wd ON uwm.word_id = wd.word_id
                WHERE uwm.user_id = %s
                ORDER BY uwm.last_seen DESC
                LIMIT %s
            """, (user_id, limit))

            words = []
            for row in cursor.fetchall():
                accuracy = (row[6] / max(row[5], 1)) * 100 if row[5] > 0 else 0
                words.append({
                    "word_id": row[0],
                    "term": row[1],
                    "definition": row[2][:100] + "..." if len(row[2] or "") > 100 else row[2],
                    "part_of_speech": row[3],
                    "domain": row[4],
                    "total_attempts": row[5],
                    "correct_attempts": row[6],
                    "accuracy": round(accuracy, 1),
                    "mastery_level": row[7],
                    "streak": row[8],
                    "last_seen": row[9].isoformat() if row[9] else None,
                    "next_review": row[10].isoformat() if row[10] else None,
                    "ease_factor": float(row[11]) if row[11] else 2.5,
                    "status": self._get_word_status(row[7], row[10])
                })

            return words

        except Exception as e:
            logger.error(f"Error getting detailed word progress for user {user_id}: {e}")
            return []
        finally:
            cursor.close()
            conn.close()

    def get_recent_quiz_sessions(self, user_id: int, limit: int = 5) -> List[Dict[str, Any]]:
        """Get recent quiz sessions with summary data"""
        conn = self.get_connection()
        cursor = conn.cursor()

        try:
            cursor.execute("""
                SELECT id, quiz_type, difficulty, total_questions, correct_answers,
                       started_at, completed_at, topic_domain
                FROM quiz_sessions
                WHERE user_id = %s
                ORDER BY started_at DESC
                LIMIT %s
            """, (user_id, limit))

            sessions = []
            for row in cursor.fetchall():
                accuracy = (row[4] / max(row[3], 1)) * 100 if row[3] > 0 else 0
                duration = None
                if row[5] and row[6]:
                    duration = (row[6] - row[5]).total_seconds() / 60  # minutes

                sessions.append({
                    "session_id": row[0],
                    "quiz_type": row[1],
                    "difficulty": row[2],
                    "total_questions": row[3],
                    "correct_answers": row[4],
                    "accuracy": round(accuracy, 1),
                    "started_at": row[5].isoformat() if row[5] else None,
                    "completed_at": row[6].isoformat() if row[6] else None,
                    "topic_domain": row[7],
                    "duration_minutes": round(duration, 1) if duration else None,
                    "status": "completed" if row[6] else "incomplete"
                })

            return sessions

        except Exception as e:
            logger.error(f"Error getting recent quiz sessions for user {user_id}: {e}")
            return []
        finally:
            cursor.close()
            conn.close()

    def identify_problem_areas(self, user_id: int) -> Dict[str, Any]:
        """Identify areas where the user needs improvement"""
        conn = self.get_connection()
        cursor = conn.cursor()

        try:
            # Words with consistently poor performance
            cursor.execute("""
                SELECT d.term, d.part_of_speech, wd.primary_domain,
                       uwm.total_attempts, uwm.correct_attempts,
                       (uwm.correct_attempts / uwm.total_attempts * 100) as accuracy
                FROM user_word_mastery uwm
                JOIN defined d ON uwm.word_id = d.id
                LEFT JOIN word_domains wd ON uwm.word_id = wd.word_id
                WHERE uwm.user_id = %s AND uwm.total_attempts >= 3
                  AND (uwm.correct_attempts / uwm.total_attempts) < 0.5
                ORDER BY accuracy ASC, uwm.total_attempts DESC
                LIMIT 10
            """, (user_id,))

            struggling_words = [
                {
                    "term": row[0],
                    "part_of_speech": row[1],
                    "domain": row[2],
                    "attempts": row[3],
                    "correct": row[4],
                    "accuracy": round(row[5], 1)
                }
                for row in cursor.fetchall()
            ]

            # Question types with poor performance
            cursor.execute("""
                SELECT question_type, COUNT(*) as total, SUM(is_correct) as correct,
                       AVG(is_correct) * 100 as accuracy
                FROM user_quiz_results
                WHERE user_id = %s
                GROUP BY question_type
                HAVING total >= 5 AND accuracy < 70
                ORDER BY accuracy ASC
            """, (user_id,))

            weak_question_types = [
                {
                    "type": row[0],
                    "total": row[1],
                    "correct": row[2],
                    "accuracy": round(row[3], 1)
                }
                for row in cursor.fetchall()
            ]

            # Domains needing attention
            cursor.execute("""
                SELECT wd.primary_domain, COUNT(*) as word_count,
                       AVG(uwm.correct_attempts / uwm.total_attempts * 100) as avg_accuracy
                FROM user_word_mastery uwm
                JOIN word_domains wd ON uwm.word_id = wd.word_id
                WHERE uwm.user_id = %s AND wd.primary_domain IS NOT NULL
                GROUP BY wd.primary_domain
                HAVING word_count >= 3 AND avg_accuracy < 60
                ORDER BY avg_accuracy ASC
                LIMIT 5
            """, (user_id,))

            weak_domains = [
                {
                    "domain": row[0],
                    "word_count": row[1],
                    "accuracy": round(row[2] or 0, 1)
                }
                for row in cursor.fetchall()
            ]

            return {
                "struggling_words": struggling_words,
                "weak_question_types": weak_question_types,
                "weak_domains": weak_domains,
                "total_issues": len(struggling_words) + len(weak_question_types) + len(weak_domains)
            }

        except Exception as e:
            logger.error(f"Error identifying problem areas for user {user_id}: {e}")
            return {"struggling_words": [], "weak_question_types": [], "weak_domains": [], "total_issues": 0}
        finally:
            cursor.close()
            conn.close()

    def _calculate_trend(self, values: List[float]) -> ProgressTrend:
        """Calculate trend from a list of values"""
        if len(values) < 3:
            return ProgressTrend.STABLE

        # Simple linear trend calculation
        n = len(values)
        x_mean = (n - 1) / 2
        y_mean = sum(values) / n

        numerator = sum((i - x_mean) * (values[i] - y_mean) for i in range(n))
        denominator = sum((i - x_mean) ** 2 for i in range(n))

        if denominator == 0:
            return ProgressTrend.STABLE

        slope = numerator / denominator

        if slope > 2:
            return ProgressTrend.IMPROVING
        elif slope < -2:
            return ProgressTrend.DECLINING
        else:
            return ProgressTrend.STABLE

    def _get_word_status(self, mastery_level: str, next_review: datetime) -> str:
        """Get status indicator for a word"""
        if not next_review:
            return "unknown"

        now = datetime.now()
        if next_review <= now:
            return "due"
        elif next_review <= now + timedelta(days=1):
            return "due_soon"
        elif mastery_level == "mastered":
            return "mastered"
        else:
            return "learning"

    def get_activity_insights(self, user_id: int) -> Dict[str, Any]:
        """Get user activity patterns and insights"""
        conn = self.get_connection()
        cursor = conn.cursor()

        try:
            # Most active day of week
            cursor.execute("""
                SELECT DAYNAME(started_at) as day, COUNT(*) as sessions
                FROM quiz_sessions
                WHERE user_id = %s
                GROUP BY DAYOFWEEK(started_at)
                ORDER BY sessions DESC
                LIMIT 1
            """, (user_id,))

            most_active_day_result = cursor.fetchone()
            most_active_day = most_active_day_result[0] if most_active_day_result else "No data"

            # Most active hour
            cursor.execute("""
                SELECT HOUR(started_at) as hour, COUNT(*) as sessions
                FROM quiz_sessions
                WHERE user_id = %s
                GROUP BY HOUR(started_at)
                ORDER BY sessions DESC
                LIMIT 1
            """, (user_id,))

            most_active_hour_result = cursor.fetchone()
            most_active_hour = most_active_hour_result[0] if most_active_hour_result else 12

            # Days since last quiz
            cursor.execute("""
                SELECT DATEDIFF(NOW(), MAX(started_at)) as days_since
                FROM quiz_sessions
                WHERE user_id = %s
            """, (user_id,))

            days_since_result = cursor.fetchone()
            days_since_last = days_since_result[0] if days_since_result and days_since_result[0] else 0

            # Study consistency (sessions in last 7 days)
            cursor.execute("""
                SELECT COUNT(DISTINCT DATE(started_at)) as active_days
                FROM quiz_sessions
                WHERE user_id = %s AND started_at >= (NOW() - INTERVAL '7 days')
            """, (user_id,))

            active_days_result = cursor.fetchone()
            active_days = active_days_result[0] if active_days_result else 0
            consistency_score = (active_days / 7) * 100  # Percentage of days active in last week

            return {
                "most_active_day": most_active_day,
                "most_active_hour": most_active_hour,
                "days_since_last_quiz": days_since_last,
                "study_consistency_score": round(consistency_score, 1),
                "longest_streak_days": 0,  # TODO: Calculate actual streak
                "recent_performance_trend": "stable"  # TODO: Calculate actual trend
            }

        except Exception as e:
            logger.error(f"Error getting activity insights for user {user_id}: {e}")
            return {
                "most_active_day": "No data",
                "most_active_hour": 12,
                "days_since_last_quiz": 0,
                "study_consistency_score": 0,
                "longest_streak_days": 0,
                "recent_performance_trend": "stable"
            }
        finally:
            cursor.close()
            conn.close()

    def _get_empty_analytics(self) -> Dict[str, Any]:
        """Return empty analytics structure for error cases"""
        return {
            "quiz_analytics": {},
            "vocabulary_mastery": {},
            "word_progress": [],
            "activity_insights": {},
            "recent_sessions": [],
            "problem_areas": {"struggling_words": [], "weak_question_types": [], "weak_domains": [], "total_issues": 0},
            "generated_at": datetime.now().isoformat(),
            "error": True,
            "message": "Unable to load analytics data. This could be because you haven't taken any quizzes yet or there was a database error."
        }

# Global analytics instance
analytics = VocabularyAnalytics()
