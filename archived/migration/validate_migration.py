#!/usr/bin/env python3
"""
Validation and Testing Script for Supabase Migration
Validates data integrity and functionality after migration
"""

import mysql.connector
import psycopg2
import psycopg2.extras
import json
import time
from typing import Dict, List, Tuple, Optional
import argparse
import sys
from datetime import datetime
from tqdm import tqdm

class MigrationValidator:
    """Validates migration from MySQL to PostgreSQL/Supabase"""
    
    def __init__(self, mysql_config: Dict, postgres_config: Dict):
        self.mysql_config = mysql_config
        self.postgres_config = postgres_config
        self.mysql_conn = None
        self.postgres_conn = None
        self.validation_results = {}
        
    def connect_databases(self):
        """Connect to both databases"""
        try:
            self.mysql_conn = mysql.connector.connect(**self.mysql_config)
            print("✅ Connected to MySQL database")
        except Exception as e:
            print(f"❌ Failed to connect to MySQL: {e}")
            raise
            
        try:
            self.postgres_conn = psycopg2.connect(**self.postgres_config)
            print("✅ Connected to PostgreSQL database")
        except Exception as e:
            print(f"❌ Failed to connect to PostgreSQL: {e}")
            raise
    
    def validate_table_counts(self, tables: List[str]) -> Dict[str, Dict]:
        """Compare record counts between MySQL and PostgreSQL"""
        print("\n📊 Validating table record counts...")
        results = {}
        
        mysql_cursor = self.mysql_conn.cursor()
        postgres_cursor = self.postgres_conn.cursor()
        
        for table in tables:
            # Get MySQL count
            mysql_count = 0
            try:
                mysql_cursor.execute(f"SELECT COUNT(*) FROM {table}")
                mysql_count = mysql_cursor.fetchone()[0]
            except Exception as e:
                print(f"⚠️  MySQL table {table} not found or error: {e}")
                mysql_count = None
                
            # Get PostgreSQL count
            postgres_count = 0
            try:
                postgres_cursor.execute(f"SELECT COUNT(*) FROM {table}")
                postgres_count = postgres_cursor.fetchone()[0]
            except Exception as e:
                print(f"⚠️  PostgreSQL table {table} not found or error: {e}")
                postgres_count = None
                
            # Compare
            status = "✅ MATCH" if mysql_count == postgres_count else "❌ MISMATCH"
            results[table] = {
                'mysql_count': mysql_count,
                'postgres_count': postgres_count,
                'status': status
            }
            
            print(f"{table:25} | MySQL: {mysql_count:>8} | PostgreSQL: {postgres_count:>8} | {status}")
            
        mysql_cursor.close()
        postgres_cursor.close()
        return results
    
    def validate_data_integrity(self, table: str, sample_size: int = 1000) -> bool:
        """Validate data integrity for a specific table"""
        print(f"\n🔍 Validating data integrity for {table} (sample: {sample_size})...")
        
        mysql_cursor = self.mysql_conn.cursor(dictionary=True)
        postgres_cursor = self.postgres_conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        
        try:
            # Get random sample from MySQL
            mysql_cursor.execute(f"SELECT * FROM {table} ORDER BY RAND() LIMIT {sample_size}")
            mysql_data = mysql_cursor.fetchall()
            
            if not mysql_data:
                print(f"⚠️  No data found in MySQL table {table}")
                return True
                
            mismatches = 0
            
            for row in tqdm(mysql_data, desc=f"Validating {table}"):
                # Get corresponding row from PostgreSQL
                primary_key = self.get_primary_key(table, row)
                if not primary_key:
                    continue
                    
                where_clause, params = self.build_where_clause(primary_key)
                postgres_cursor.execute(f"SELECT * FROM {table} WHERE {where_clause}", params)
                postgres_row = postgres_cursor.fetchone()
                
                if not postgres_row:
                    print(f"❌ Row not found in PostgreSQL: {primary_key}")
                    mismatches += 1
                    continue
                    
                # Compare data
                if not self.compare_rows(dict(row), dict(postgres_row), table):
                    mismatches += 1
                    
            success_rate = ((sample_size - mismatches) / sample_size) * 100
            
            if success_rate >= 99:
                print(f"✅ Data integrity validation passed: {success_rate:.1f}%")
                return True
            else:
                print(f"❌ Data integrity validation failed: {success_rate:.1f}% ({mismatches} mismatches)")
                return False
                
        except Exception as e:
            print(f"❌ Error validating {table}: {e}")
            return False
        finally:
            mysql_cursor.close()
            postgres_cursor.close()
            
    def get_primary_key(self, table: str, row: Dict) -> Optional[Dict]:
        """Get primary key fields for a row"""
        primary_keys = {
            'defined': ['id'],
            'users': ['id'],
            'word_phonetics': ['word_id'],
            'word_domains': ['word_id'],
            'word_frequencies_independent': ['word_id'],
            'pronunciation_similarity': ['word1_id', 'word2_id'],
            'definition_similarity': ['word1_id', 'word2_id'],
            'user_quiz_results': ['id'],
            'user_word_mastery': ['user_id', 'word_id']
        }
        
        if table not in primary_keys:
            return None
            
        pk_fields = primary_keys[table]
        return {field: row[field] for field in pk_fields if field in row}
    
    def build_where_clause(self, primary_key: Dict) -> Tuple[str, List]:
        """Build WHERE clause for primary key lookup"""
        conditions = []
        params = []
        
        for field, value in primary_key.items():
            conditions.append(f"{field} = %s")
            params.append(value)
            
        return " AND ".join(conditions), params
    
    def compare_rows(self, mysql_row: Dict, postgres_row: Dict, table: str) -> bool:
        """Compare two rows for data integrity"""
        # Skip auto-generated fields that may differ
        skip_fields = {'created_at', 'updated_at'}
        
        for field, mysql_value in mysql_row.items():
            if field in skip_fields:
                continue
                
            postgres_value = postgres_row.get(field)
            
            # Handle None/null values
            if mysql_value is None and postgres_value is None:
                continue
                
            # Handle JSON fields
            if field in ['all_domains', 'confidence_scores', 'source_frequencies', 'phonemes_json']:
                if isinstance(mysql_value, str) and mysql_value:
                    try:
                        mysql_value = json.loads(mysql_value)
                    except:
                        pass
                        
            # Handle decimal/float precision differences
            if isinstance(mysql_value, float) and isinstance(postgres_value, float):
                if abs(mysql_value - postgres_value) < 0.00001:
                    continue
                    
            # Compare values
            if mysql_value != postgres_value:
                print(f"❌ Field mismatch in {table}.{field}: MySQL='{mysql_value}' vs PostgreSQL='{postgres_value}'")
                return False
                
        return True
    
    def test_queries(self) -> bool:
        """Test common queries against PostgreSQL"""
        print("\n🧪 Testing common queries...")
        
        test_queries = [
            # Basic vocabulary queries
            ("Basic word lookup", "SELECT COUNT(*) FROM defined WHERE term LIKE 'test%'"),
            
            # Phonetic queries
            ("Phonetic data", "SELECT COUNT(*) FROM word_phonetics WHERE ipa_transcription IS NOT NULL"),
            
            # Similarity queries  
            ("High similarity words", "SELECT COUNT(*) FROM pronunciation_similarity WHERE overall_similarity > 0.5"),
            
            # Join queries
            ("Word with phonetics", """
                SELECT COUNT(*) FROM defined d 
                JOIN word_phonetics wp ON d.id = wp.word_id 
                WHERE wp.syllable_count > 2
            """),
            
            # Quiz queries
            ("Quiz results", "SELECT COUNT(*) FROM user_quiz_results WHERE is_correct = true"),
            
            # Full-text search (PostgreSQL specific)
            ("Full-text search", """
                SELECT COUNT(*) FROM defined 
                WHERE to_tsvector('english', definition || ' ' || term) @@ to_tsquery('english', 'test')
            """)
        ]
        
        postgres_cursor = self.postgres_conn.cursor()
        all_passed = True
        
        for query_name, query in test_queries:
            try:
                start_time = time.time()
                postgres_cursor.execute(query)
                result = postgres_cursor.fetchone()[0]
                execution_time = time.time() - start_time
                
                print(f"✅ {query_name:20} | Result: {result:>8} | Time: {execution_time:.3f}s")
                
            except Exception as e:
                print(f"❌ {query_name:20} | Error: {e}")
                all_passed = False
                
        postgres_cursor.close()
        return all_passed
    
    def test_performance(self) -> Dict[str, float]:
        """Test query performance on PostgreSQL"""
        print("\n⚡ Testing query performance...")
        
        performance_tests = [
            ("Simple SELECT", "SELECT COUNT(*) FROM defined"),
            ("Similarity lookup", """
                SELECT d.term, ps.overall_similarity 
                FROM pronunciation_similarity ps 
                JOIN defined d ON d.id = ps.word2_id 
                WHERE ps.word1_id = 1000 AND ps.overall_similarity > 0.3 
                ORDER BY ps.overall_similarity DESC 
                LIMIT 10
            """),
            ("Complex JOIN", """
                SELECT d.term, wp.ipa_transcription, wd.primary_domain 
                FROM defined d
                JOIN word_phonetics wp ON d.id = wp.word_id
                JOIN word_domains wd ON d.id = wd.word_id
                WHERE wp.syllable_count = 3 AND wd.primary_domain = 'science'
                LIMIT 100
            """),
            ("Aggregation", """
                SELECT wd.primary_domain, COUNT(*) as word_count, AVG(wp.syllable_count) as avg_syllables
                FROM word_domains wd
                JOIN word_phonetics wp ON wd.word_id = wp.word_id
                GROUP BY wd.primary_domain
                ORDER BY word_count DESC
                LIMIT 10
            """)
        ]
        
        results = {}
        postgres_cursor = self.postgres_conn.cursor()
        
        for test_name, query in performance_tests:
            times = []
            
            # Run each query 3 times and take average
            for _ in range(3):
                start_time = time.time()
                try:
                    postgres_cursor.execute(query)
                    postgres_cursor.fetchall()  # Ensure all data is retrieved
                    execution_time = time.time() - start_time
                    times.append(execution_time)
                except Exception as e:
                    print(f"❌ {test_name} failed: {e}")
                    times.append(float('inf'))
                    
            avg_time = sum(times) / len(times) if times else float('inf')
            results[test_name] = avg_time
            
            status = "✅ FAST" if avg_time < 1.0 else "⚠️  SLOW" if avg_time < 5.0 else "❌ VERY SLOW"
            print(f"{test_name:20} | Avg: {avg_time:.3f}s | {status}")
            
        postgres_cursor.close()
        return results
    
    def run_full_validation(self, tables: List[str]) -> Dict:
        """Run complete validation suite"""
        print("🔍 Starting full migration validation")
        print("=" * 60)
        
        results = {
            'timestamp': datetime.now().isoformat(),
            'tables': {},
            'queries_passed': False,
            'performance': {},
            'overall_status': 'UNKNOWN'
        }
        
        try:
            self.connect_databases()
            
            # 1. Count validation
            count_results = self.validate_table_counts(tables)
            results['tables'] = count_results
            
            # 2. Data integrity validation (sample-based)
            integrity_results = {}
            for table in tables:
                if count_results.get(table, {}).get('postgres_count', 0) > 0:
                    integrity_results[table] = self.validate_data_integrity(table, sample_size=100)
                    
            # 3. Query testing
            results['queries_passed'] = self.test_queries()
            
            # 4. Performance testing
            results['performance'] = self.test_performance()
            
            # Determine overall status
            count_matches = all(r['status'] == '✅ MATCH' for r in count_results.values())
            integrity_passes = all(integrity_results.values()) if integrity_results else True
            
            if count_matches and integrity_passes and results['queries_passed']:
                results['overall_status'] = '✅ PASSED'
                print("\n🎉 Migration validation PASSED!")
            else:
                results['overall_status'] = '❌ FAILED'
                print("\n💥 Migration validation FAILED!")
                
        except Exception as e:
            print(f"❌ Validation error: {e}")
            results['overall_status'] = '❌ ERROR'
            results['error'] = str(e)
            
        finally:
            if self.mysql_conn:
                self.mysql_conn.close()
            if self.postgres_conn:
                self.postgres_conn.close()
                
        return results

def main():
    parser = argparse.ArgumentParser(description='Validate Supabase migration')
    parser.add_argument('--mysql-host', default='10.0.0.160', help='MySQL host')
    parser.add_argument('--mysql-port', type=int, default=3306, help='MySQL port')
    parser.add_argument('--mysql-db', default='vocab', help='MySQL database name')
    parser.add_argument('--mysql-user', default='brian', help='MySQL username')
    parser.add_argument('--mysql-password', default='Fl1p5ma5h!', help='MySQL password')
    
    parser.add_argument('--postgres-host', default='localhost', help='PostgreSQL host')
    parser.add_argument('--postgres-port', type=int, default=5432, help='PostgreSQL port')
    parser.add_argument('--postgres-db', default='postgres', help='PostgreSQL database name')
    parser.add_argument('--postgres-user', default='postgres', help='PostgreSQL username')
    parser.add_argument('--postgres-password', required=True, help='PostgreSQL password')
    
    parser.add_argument('--tables', nargs='+', 
                       default=['defined', 'word_phonetics', 'pronunciation_similarity', 
                               'definition_similarity', 'word_domains', 'word_frequencies_independent'],
                       help='Tables to validate')
    
    args = parser.parse_args()
    
    mysql_config = {
        'host': args.mysql_host,
        'port': args.mysql_port,
        'database': args.mysql_db,
        'user': args.mysql_user,
        'password': args.mysql_password
    }
    
    postgres_config = {
        'host': args.postgres_host,
        'port': args.postgres_port,
        'database': args.postgres_db,
        'user': args.postgres_user,
        'password': args.postgres_password
    }
    
    validator = MigrationValidator(mysql_config, postgres_config)
    results = validator.run_full_validation(args.tables)
    
    # Save results to file
    results_file = f"validation_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(results_file, 'w') as f:
        json.dump(results, f, indent=2, default=str)
    
    print(f"\n📊 Validation results saved to: {results_file}")
    
    # Exit with appropriate code
    if results['overall_status'] == '✅ PASSED':
        print("✅ All validations passed - migration successful!")
        sys.exit(0)
    else:
        print("❌ Validation failed - check results for details")
        sys.exit(1)

if __name__ == '__main__':
    main()