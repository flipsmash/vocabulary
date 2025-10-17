#!/usr/bin/env python3
"""
Migration script to update key components to use centralized database manager
"""

import os
import re
from pathlib import Path

def update_file_imports(file_path: str):
    """Update a file to use centralized database manager"""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()

        original_content = content
        modified = False

        # Add import for database_manager if mysql.connector is used
        if 'mysql.connector' in content and 'database_manager' not in content:
            # Find where to add the import
            if 'from core.config import' in content:
                content = content.replace(
                    'from core.config import get_db_config',
                    'from core.config import get_db_config\nfrom core.database_manager import db_manager, database_cursor'
                )
                modified = True

        # Update common connection patterns
        patterns_to_replace = [
            # Pattern 1: mysql.connector.connect(**config)
            (
                r'conn = mysql\.connector\.connect\(\*\*([^)]+)\)',
                r'with db_manager.get_connection() as conn'
            ),

            # Pattern 2: Connection from config
            (
                r'conn = mysql\.connector\.connect\(\*\*self\.config\)',
                r'with db_manager.get_connection() as conn'
            ),

            # Pattern 3: Simple get_connection pattern
            (
                r'def get_connection\(.*?\):\s*.*?return mysql\.connector\.connect\(\*\*.*?\)',
                r'def get_connection(self):\n        return db_manager.get_connection()'
            )
        ]

        for pattern, replacement in patterns_to_replace:
            if re.search(pattern, content, re.DOTALL):
                content = re.sub(pattern, replacement, content, flags=re.DOTALL)
                modified = True

        if modified:
            # Create backup
            backup_path = file_path + '.backup'
            with open(backup_path, 'w', encoding='utf-8') as f:
                f.write(original_content)

            # Write updated content
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(content)

            print(f"Updated: {file_path}")
            return True

        return False

    except Exception as e:
        print(f"Error updating {file_path}: {e}")
        return False

def main():
    """Update key files to use centralized database manager"""
    print("Migrating to Centralized Database Manager")
    print("=" * 50)

    # Key files to update (prioritized list)
    priority_files = [
        'core/auth.py',
        'web_apps/simple_vocab_app.py',
        'harvesters/vocabulary_list_harvester.py',
        'harvesters/enhanced_vocabulary_list_harvester.py',
        'analysis/domain_classifier.py',
        'core/comprehensive_definition_lookup.py'
    ]

    updated_count = 0

    for file_path in priority_files:
        if os.path.exists(file_path):
            if update_file_imports(file_path):
                updated_count += 1
        else:
            print(f"File not found: {file_path}")

    print(f"\nMigration Summary:")
    print(f"  Files updated: {updated_count}")
    print(f"  Backup files created: {updated_count}")

    # Create usage examples
    create_usage_examples()

    print(f"\nMigration completed!")
    print(f"New database usage patterns:")
    print(f"  - Use 'db_manager.execute_query()' for simple queries")
    print(f"  - Use 'with database_cursor() as cursor:' for complex queries")
    print(f"  - Use 'db_manager.execute_many()' for batch operations")

def create_usage_examples():
    """Create example file showing new usage patterns"""
    examples = '''#!/usr/bin/env python3
"""
Database Manager Usage Examples
Demonstrates how to use the centralized database manager
"""

from core.database_manager import db_manager, database_cursor, database_connection

# Example 1: Simple query execution
def get_word_count():
    """Get total word count using simple query"""
    result = db_manager.execute_query("SELECT COUNT(*) FROM vocab.defined")
    return result[0][0] if result else 0

# Example 2: Query with parameters
def find_words_by_pattern(pattern: str):
    """Find words matching a pattern"""
    results = db_manager.execute_query(
        "SELECT term, definition FROM vocab.defined WHERE term LIKE %s LIMIT 10",
        (f"%{pattern}%",),
        dictionary=True
    )
    return results

# Example 3: Using cursor context manager
def get_word_details(word_id: int):
    """Get detailed word information using cursor"""
    with database_cursor(dictionary=True) as cursor:
        cursor.execute("""
            SELECT d.*, p.ipa_transcription, p.syllable_count
            FROM vocab.defined d
            LEFT JOIN vocab.word_phonetics p ON d.id = p.word_id
            WHERE d.id = %s
        """, (word_id,))

        return cursor.fetchone()

# Example 4: Batch insert operations
def store_multiple_candidates(candidates: list):
    """Store multiple candidate words efficiently"""
    insert_data = [
        (term, 'other', 'http://example.com', definition, definition,
         None, None, 5.0, '{}', '2024-01-01', 'pending')
        for term, definition in candidates
    ]

    rows_affected = db_manager.execute_many("""
        INSERT INTO vocab.candidate_words
        (term, source_type, source_reference, context_snippet, raw_definition,
         etymology_preview, part_of_speech, utility_score, rarity_indicators,
         date_discovered, review_status)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
    """, insert_data)

    return rows_affected

# Example 5: Connection context manager (for complex operations)
def complex_database_operation():
    """Example of complex multi-query operation"""
    with database_connection() as conn:
        cursor = conn.cursor(dictionary=True)

        try:
            # Multiple related queries
            cursor.execute("SELECT COUNT(*) as count FROM vocab.defined")
            count = cursor.fetchone()['count']

            cursor.execute("SELECT AVG(frequency) as avg_freq FROM vocab.defined WHERE frequency IS NOT NULL")
            avg_freq = cursor.fetchone()['avg_freq']

            # Insert summary
            cursor.execute("""
                INSERT INTO analysis_summary (total_words, avg_frequency, analysis_date)
                VALUES (%s, %s, NOW())
            """, (count, avg_freq))

            # Connection will auto-commit when exiting context
            return {'count': count, 'avg_frequency': avg_freq}

        finally:
            cursor.close()

if __name__ == "__main__":
    # Test the examples
    print("Database Manager Examples")
    print("=" * 30)

    print(f"Total words: {get_word_count():,}")

    words = find_words_by_pattern("ab")
    print(f"Words starting with 'ab': {len(words)}")

    # Test connection
    if db_manager.test_connection():
        print("Database connection: OK")
    else:
        print("Database connection: FAILED")
'''

    with open('database_manager_examples.py', 'w', encoding='utf-8') as f:
        f.write(examples)

    print("Created: database_manager_examples.py")

if __name__ == "__main__":
    main()