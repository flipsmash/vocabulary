"""
Custom Database Manager configured for your specific database schema
"""

import mysql.connector
import pandas as pd
import json
import logging
from typing import List, Tuple, Optional, Dict

logger = logging.getLogger(__name__)


class CustomDatabaseManager:
    """Database manager configured for your specific Vocab database schema"""

    def __init__(self, host: str, port: int, database: str, user: str, password: str):
        self.connection_params = {
            'host': host,
            'port': port,
            'database': database,
            'user': user,
            'password': password
        }

        # Your specific table and column configuration
        self.words_table = 'defined'
        self.id_column = 'id'
        self.word_column = 'term'

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

            # Focus on the defined table
            cursor.execute(f"DESCRIBE {self.words_table}")
            columns = cursor.fetchall()
            schema_info = {self.words_table: columns}

            logger.info(f"Main words table '{self.words_table}' structure:")
            for col in columns:
                logger.info(f"  {col}")

            # Get word count
            cursor.execute(f"SELECT COUNT(*) FROM {self.words_table}")
            count = cursor.fetchone()[0]
            logger.info(f"Total words in {self.words_table}: {count:,}")

            # Get sample words
            cursor.execute(f"SELECT {self.id_column}, {self.word_column} FROM {self.words_table} LIMIT 10")
            samples = cursor.fetchall()
            logger.info(f"Sample words: {samples}")

            return schema_info

    def create_phonetic_tables(self):
        """Create tables for phonetic data and similarity scores"""

        create_phonetics_table = f"""
        CREATE TABLE IF NOT EXISTS word_phonetics (
            word_id INT PRIMARY KEY,
            word VARCHAR(255) NOT NULL,
            ipa_transcription TEXT,
            arpabet_transcription TEXT,
            syllable_count INT,
            stress_pattern VARCHAR(50),
            phonemes_json TEXT,
            transcription_source VARCHAR(50),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (word_id) REFERENCES {self.words_table}({self.id_column}) ON DELETE CASCADE,
            INDEX idx_word (word),
            INDEX idx_syllables (syllable_count),
            INDEX idx_source (transcription_source)
        )
        """

        create_similarity_table = f"""
        CREATE TABLE IF NOT EXISTS pronunciation_similarity (
            word1_id INT,
            word2_id INT,
            overall_similarity DECIMAL(6,5),
            phonetic_distance DECIMAL(6,5),
            stress_similarity DECIMAL(6,5),
            rhyme_score DECIMAL(6,5),
            syllable_similarity DECIMAL(6,5),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (word1_id, word2_id),
            INDEX idx_overall_similarity (overall_similarity DESC),
            INDEX idx_word1_similarity (word1_id, overall_similarity DESC),
            INDEX idx_word2_similarity (word2_id, overall_similarity DESC),
            INDEX idx_high_similarity (overall_similarity DESC, word1_id, word2_id),
            CONSTRAINT chk_word_order CHECK (word1_id < word2_id),
            FOREIGN KEY (word1_id) REFERENCES {self.words_table}({self.id_column}) ON DELETE CASCADE,
            FOREIGN KEY (word2_id) REFERENCES {self.words_table}({self.id_column}) ON DELETE CASCADE
        )
        """

        with self.get_connection() as conn:
            cursor = conn.cursor()

            # Drop existing tables if they have wrong foreign key constraints
            try:
                cursor.execute("DROP TABLE IF EXISTS pronunciation_similarity")
                cursor.execute("DROP TABLE IF EXISTS word_phonetics")
                logger.info("Dropped existing phonetic tables")
            except:
                pass

            cursor.execute(create_phonetics_table)
            cursor.execute(create_similarity_table)
            conn.commit()
            logger.info("Created phonetic tables successfully")

    def get_words(self, limit: Optional[int] = None) -> List[Tuple[int, str]]:
        """Retrieve words from your defined table"""
        with self.get_connection() as conn:
            cursor = conn.cursor()

            query = f"SELECT {self.id_column}, {self.word_column} FROM {self.words_table} WHERE {self.word_column} IS NOT NULL"
            if limit:
                query += f" LIMIT {limit}"

            cursor.execute(query)
            results = cursor.fetchall()

            # Filter out None values and clean up the words
            filtered_results = []
            for word_id, word in results:
                if word and word.strip():
                    # Clean up the word (remove extra whitespace, convert to lowercase for consistency)
                    clean_word = word.strip().lower()
                    filtered_results.append((word_id, clean_word))

            logger.info(f"Retrieved {len(filtered_results)} words from {self.words_table}")
            return filtered_results

    def get_word_by_id(self, word_id: int) -> Optional[str]:
        """Get a specific word by ID"""
        with self.get_connection() as conn:
            cursor = conn.cursor()

            query = f"SELECT {self.word_column} FROM {self.words_table} WHERE {self.id_column} = %s"
            cursor.execute(query, (word_id,))
            result = cursor.fetchone()

            return result[0] if result else None

    def insert_phonetic_data(self, phonetic_data_list):
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

    def get_processing_stats(self) -> Dict:
        """Get statistics about phonetic processing"""
        with self.get_connection() as conn:
            cursor = conn.cursor()

            # Total words in main table
            cursor.execute(f"SELECT COUNT(*) FROM {self.words_table} WHERE {self.word_column} IS NOT NULL")
            total_words = cursor.fetchone()[0]

            # Processed words
            cursor.execute("SELECT COUNT(*) FROM word_phonetics")
            processed_words = cursor.fetchone()[0]

            # Source breakdown
            cursor.execute("""
                           SELECT transcription_source, COUNT(*)
                           FROM word_phonetics
                           GROUP BY transcription_source
                           ORDER BY COUNT(*) DESC
                           """)
            source_breakdown = cursor.fetchall()

            # Similarity count
            cursor.execute("SELECT COUNT(*) FROM pronunciation_similarity")
            similarity_count = cursor.fetchone()[0]

            return {
                'total_words': total_words,
                'processed_words': processed_words,
                'processing_percentage': (processed_words / total_words * 100) if total_words > 0 else 0,
                'source_breakdown': source_breakdown,
                'similarity_count': similarity_count
            }


# Quick test function
def test_custom_database():
    """Test the custom database manager"""
    from config import get_db_config
    DB_CONFIG = get_db_config()

    try:
        db_manager = CustomDatabaseManager(**DB_CONFIG)

        print("🧪 Testing Custom Database Manager")
        print("=" * 50)

        # Test connection and schema
        schema_info = db_manager.examine_schema()
        print("✅ Schema examination successful")

        # Test word retrieval
        words = db_manager.get_words(limit=10)
        print(f"✅ Retrieved {len(words)} sample words:")
        for word_id, word in words[:5]:
            print(f"  ID {word_id}: '{word}'")

        # Test stats
        stats = db_manager.get_processing_stats()
        print(f"✅ Database stats:")
        print(f"  Total words: {stats['total_words']:,}")
        print(f"  Processed: {stats['processed_words']:,}")
        print(f"  Similarities: {stats['similarity_count']:,}")

        return True

    except Exception as e:
        print(f"❌ Test failed: {e}")
        return False


if __name__ == "__main__":
    test_custom_database()