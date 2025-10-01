#!/usr/bin/env python3
"""
Diagnose analytics calculation issues
"""

# Add current directory to path for imports
import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

try:
    from utils.windows_console import safe_print
except ImportError:
    def safe_print(text):
        try:
            print(text)
        except UnicodeEncodeError:
            print(text.encode('ascii', errors='replace').decode('ascii'))

import mysql.connector
from core.config import VocabularyConfig
from core.analytics import analytics

config = VocabularyConfig()
conn = mysql.connector.connect(**config.get_db_config())
cursor = conn.cursor()

safe_print("=== ANALYTICS DIAGNOSIS ===")

# Check which users have quiz data
cursor.execute("""
    SELECT DISTINCT user_id, COUNT(*) as sessions
    FROM quiz_sessions
    GROUP BY user_id
    ORDER BY sessions DESC
""")

users_with_sessions = cursor.fetchall()
safe_print(f"Users with quiz sessions: {len(users_with_sessions)}")
for user_id, session_count in users_with_sessions:
    safe_print(f"  User {user_id}: {session_count} sessions")

safe_print("")

# For each user, test analytics
for user_id, _ in users_with_sessions:
    safe_print(f"=== USER {user_id} ANALYTICS ===")

    # Test individual components
    try:
        quiz_analytics_data = analytics.get_quiz_analytics(user_id)
        safe_print(f"Quiz Analytics - Total Sessions: {quiz_analytics_data.get('total_sessions', 'ERROR')}")
        safe_print(f"Quiz Analytics - Average Accuracy: {quiz_analytics_data.get('average_accuracy', 'ERROR')}%")
        safe_print(f"Quiz Analytics - Question Types: {len(quiz_analytics_data.get('question_types', []))}")

        vocabulary_data = analytics.get_vocabulary_mastery(user_id)
        safe_print(f"Vocabulary Mastery - Total Words: {vocabulary_data.get('total_words_encountered', 'ERROR')}")
        safe_print(f"Vocabulary Mastery - Mastery %: {vocabulary_data.get('mastery_percentage', 'ERROR')}%")

        word_progress = analytics.get_detailed_word_progress(user_id, limit=5)
        safe_print(f"Word Progress - Words Returned: {len(word_progress)}")

        if word_progress:
            safe_print("Sample word accuracies:")
            for word in word_progress[:3]:
                safe_print(f"  {word.get('term', 'Unknown')}: {word.get('accuracy', 'ERROR')}% ({word.get('correct_attempts', '?')}/{word.get('total_attempts', '?')})")

    except Exception as e:
        safe_print(f"ERROR in analytics for user {user_id}: {e}")

    safe_print("")

# Check raw data inconsistencies
safe_print("=== RAW DATA CHECKS ===")

# Check quiz_sessions vs user_quiz_results
cursor.execute("""
    SELECT qs.id, qs.correct_answers, COUNT(uqr.id) as result_count,
           SUM(CASE WHEN uqr.is_correct = 1 THEN 1 ELSE 0 END) as actual_correct
    FROM quiz_sessions qs
    LEFT JOIN user_quiz_results uqr ON qs.id = uqr.session_id
    WHERE qs.completed_at IS NOT NULL
    GROUP BY qs.id, qs.correct_answers
    LIMIT 10
""")

session_checks = cursor.fetchall()
safe_print("Session discrepancies (quiz_sessions vs user_quiz_results):")
for row in session_checks:
    session_id, stored_correct, result_count, actual_correct = row
    if result_count == 0:
        safe_print(f"  Session {session_id[:8]}...: Stored {stored_correct} correct but NO user_quiz_results found")
    elif stored_correct != actual_correct:
        safe_print(f"  Session {session_id[:8]}...: Stored {stored_correct} vs Actual {actual_correct}")

safe_print("")

# Check user_word_mastery vs user_quiz_results
cursor.execute("""
    SELECT uwm.user_id, uwm.word_id, uwm.total_attempts, uwm.correct_attempts,
           COUNT(uqr.id) as quiz_attempts,
           SUM(CASE WHEN uqr.is_correct = 1 THEN 1 ELSE 0 END) as quiz_correct
    FROM user_word_mastery uwm
    LEFT JOIN user_quiz_results uqr ON uwm.user_id = uqr.user_id AND uwm.word_id = uqr.word_id
    WHERE uwm.total_attempts > 0
    GROUP BY uwm.user_id, uwm.word_id, uwm.total_attempts, uwm.correct_attempts
    HAVING (quiz_attempts != uwm.total_attempts OR quiz_correct != uwm.correct_attempts)
    LIMIT 10
""")

mastery_checks = cursor.fetchall()
if mastery_checks:
    safe_print("Mastery discrepancies (user_word_mastery vs user_quiz_results):")
    for row in mastery_checks:
        user_id, word_id, mastery_attempts, mastery_correct, quiz_attempts, quiz_correct = row
        safe_print(f"  User {user_id}, Word {word_id}: Mastery {mastery_correct}/{mastery_attempts} vs Quiz {quiz_correct or 0}/{quiz_attempts or 0}")
else:
    safe_print("No discrepancies found between user_word_mastery and user_quiz_results")

conn.close()
safe_print("\n=== DIAGNOSIS COMPLETE ===")