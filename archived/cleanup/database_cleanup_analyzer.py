#!/usr/bin/env python3
"""
Database Cleanup Analyzer - Identify unused tables and cruft for safe removal
"""

import mysql.connector
import os
import re
from pathlib import Path
from typing import Dict, Set, List, Tuple
from config import get_db_config

class DatabaseCleanupAnalyzer:
    """Analyzes database usage to identify safe-to-remove tables"""
    
    def __init__(self):
        self.db_config = get_db_config()
        self.project_root = Path("C:/Users/Brian/vocabulary")
        
    def get_all_tables(self) -> List[Dict]:
        """Get all tables in the database with metadata"""
        try:
            conn = mysql.connector.connect(**self.db_config)
            cursor = conn.cursor(dictionary=True)
            
            # Get all tables with sizes
            cursor.execute("""
                SELECT 
                    TABLE_NAME as table_name,
                    TABLE_ROWS as table_rows,
                    DATA_LENGTH as data_length,
                    INDEX_LENGTH as index_length,
                    (DATA_LENGTH + INDEX_LENGTH) as total_size,
                    TABLE_COMMENT as table_comment
                FROM information_schema.tables 
                WHERE table_schema = 'vocab'
                ORDER BY total_size DESC
            """)
            
            tables = cursor.fetchall()
            return tables
            
        except Exception as e:
            print(f"Error getting tables: {e}")
            return []
        finally:
            if 'conn' in locals() and conn.is_connected():
                cursor.close()
                conn.close()
    
    def scan_code_for_table_usage(self) -> Dict[str, Set[str]]:
        """Scan all Python files for table name references"""
        table_usage = {}
        
        # Get all Python files
        python_files = list(self.project_root.glob("*.py"))
        
        for file_path in python_files:
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                    
                # Look for table references in various patterns
                patterns = [
                    r'FROM\s+(\w+)',           # FROM table_name
                    r'JOIN\s+(\w+)',          # JOIN table_name  
                    r'INTO\s+(\w+)',          # INSERT INTO table_name
                    r'UPDATE\s+(\w+)',        # UPDATE table_name
                    r'DELETE.*FROM\s+(\w+)',  # DELETE FROM table_name
                    r'CREATE\s+TABLE\s+(\w+)', # CREATE TABLE table_name
                    r'DROP\s+TABLE\s+(\w+)',  # DROP TABLE table_name
                    r'ALTER\s+TABLE\s+(\w+)', # ALTER TABLE table_name
                    r'TRUNCATE\s+(\w+)',      # TRUNCATE table_name
                    r'["\'](\w+)["\']',       # String literals that might be table names
                ]
                
                found_tables = set()
                for pattern in patterns:
                    matches = re.findall(pattern, content, re.IGNORECASE)
                    found_tables.update(match.lower() for match in matches)
                
                if found_tables:
                    table_usage[file_path.name] = found_tables
                    
            except Exception as e:
                print(f"Error reading {file_path}: {e}")
                
        return table_usage
    
    def analyze_table_relationships(self) -> Dict[str, List[str]]:
        """Analyze foreign key relationships between tables"""
        try:
            conn = mysql.connector.connect(**self.db_config)
            cursor = conn.cursor(dictionary=True)
            
            cursor.execute("""
                SELECT 
                    table_name,
                    column_name,
                    referenced_table_name,
                    referenced_column_name
                FROM information_schema.key_column_usage
                WHERE table_schema = 'vocab'
                AND referenced_table_name IS NOT NULL
            """)
            
            relationships = {}
            for row in cursor.fetchall():
                table = row['table_name']
                ref_table = row['referenced_table_name']
                
                if table not in relationships:
                    relationships[table] = []
                relationships[table].append(ref_table)
                
            return relationships
            
        except Exception as e:
            print(f"Error analyzing relationships: {e}")
            return {}
        finally:
            if 'conn' in locals() and conn.is_connected():
                cursor.close()
                conn.close()
    
    def check_table_data(self, table_name: str) -> Dict:
        """Check if table has data and when it was last modified"""
        try:
            conn = mysql.connector.connect(**self.db_config)
            cursor = conn.cursor(dictionary=True)
            
            # Get row count
            cursor.execute(f"SELECT COUNT(*) as row_count FROM {table_name}")
            row_count = cursor.fetchone()['row_count']
            
            # Try to get recent activity (if table has timestamp columns)
            timestamp_columns = []
            cursor.execute(f"""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name = '{table_name}' 
                AND table_schema = 'vocab'
                AND (data_type LIKE '%timestamp%' OR data_type LIKE '%datetime%' 
                     OR column_name LIKE '%created%' OR column_name LIKE '%updated%'
                     OR column_name LIKE '%date%' OR column_name LIKE '%time%')
            """)
            
            timestamp_columns = [row['column_name'] for row in cursor.fetchall()]
            
            last_activity = None
            if timestamp_columns and row_count > 0:
                # Try to find the most recent timestamp
                for col in timestamp_columns:
                    try:
                        cursor.execute(f"SELECT MAX({col}) as max_date FROM {table_name}")
                        result = cursor.fetchone()
                        if result and result['max_date']:
                            if last_activity is None or result['max_date'] > last_activity:
                                last_activity = result['max_date']
                    except:
                        continue
            
            return {
                'row_count': row_count,
                'last_activity': last_activity,
                'timestamp_columns': timestamp_columns
            }
            
        except Exception as e:
            return {
                'row_count': 0,
                'last_activity': None,
                'timestamp_columns': [],
                'error': str(e)
            }
        finally:
            if 'conn' in locals() and conn.is_connected():
                cursor.close()
                conn.close()
    
    def identify_current_system_tables(self) -> Set[str]:
        """Identify tables that are definitely part of the current system"""
        current_tables = {
            # Core vocabulary tables
            'defined', 'terms', 'word_phonetics', 'pronunciation_similarity',
            
            # User management  
            'users', 'user_word_mastery', 'user_quiz_results', 'user_flashcard_progress',
            
            # Quiz and flashcards
            'quiz_sessions', 'flashcard_decks', 'flashcard_deck_items',
            
            # Harvesting system (confirmed active)
            'candidate_words', 'candidate_terms', 'harvesting_sessions', 
            'harvester_config', 'harvesting_stats',
            
            # Definition system
            'definition_similarity', 'definition_embeddings',
            
            # Frequency analysis
            'word_frequencies_independent', 'word_frequency_data',
            
            # Source management
            'sources', 'documents',
            
            # Administrative
            'promotions', 'rejections'
        }
        return current_tables
    
    def generate_cleanup_report(self) -> Dict:
        """Generate comprehensive cleanup recommendations"""
        print("Analyzing database for cleanup opportunities...")
        
        # Get all table information
        all_tables = self.get_all_tables()
        table_usage_in_code = self.scan_code_for_table_usage()
        table_relationships = self.analyze_table_relationships()
        current_system_tables = self.identify_current_system_tables()
        
        # Analyze each table
        analysis = {}
        safe_to_remove = []
        questionable = []
        keep = []
        
        print(f"\nFound {len(all_tables)} tables in database")
        print("Analyzing usage patterns...\n")
        
        for table in all_tables:
            table_name = table['table_name']
            
            # Get additional data about the table
            table_data = self.check_table_data(table_name)
            
            # Determine if table is referenced in code
            referenced_in_code = any(
                table_name.lower() in usage 
                for usage in table_usage_in_code.values()
            )
            
            # Check if it's a known current system table
            is_current_system = table_name.lower() in current_system_tables
            
            # Check if it has foreign key relationships
            has_relationships = (
                table_name in table_relationships or
                any(table_name in refs for refs in table_relationships.values())
            )
            
            analysis_result = {
                'table_info': table,
                'data_info': table_data,
                'referenced_in_code': referenced_in_code,
                'is_current_system': is_current_system,
                'has_relationships': has_relationships,
                'size_mb': round((table['total_size'] or 0) / 1024 / 1024, 2)
            }
            
            # Determine classification
            if is_current_system:
                keep.append((table_name, analysis_result, "Core system table"))
            elif referenced_in_code and table_data['row_count'] > 0:
                keep.append((table_name, analysis_result, "Active table with data"))
            elif table_data['row_count'] == 0 and not has_relationships:
                safe_to_remove.append((table_name, analysis_result, "Empty table, no relationships"))
            elif not referenced_in_code and table_data['row_count'] > 0:
                if table_data.get('last_activity'):
                    from datetime import datetime, timedelta
                    if table_data['last_activity'] < datetime.now() - timedelta(days=30):
                        questionable.append((table_name, analysis_result, "Not referenced in code, old data"))
                    else:
                        questionable.append((table_name, analysis_result, "Not referenced in code, recent data"))
                else:
                    questionable.append((table_name, analysis_result, "Not referenced in code, unknown age"))
            else:
                questionable.append((table_name, analysis_result, "Needs manual review"))
            
            analysis[table_name] = analysis_result
        
        return {
            'safe_to_remove': safe_to_remove,
            'questionable': questionable,
            'keep': keep,
            'analysis': analysis,
            'table_usage_in_code': table_usage_in_code
        }
    
    def print_cleanup_report(self, report: Dict):
        """Print formatted cleanup report"""
        
        print("="*70)
        print("DATABASE CLEANUP ANALYSIS REPORT")
        print("="*70)
        
        # Safe to remove
        print(f"\nSAFE TO REMOVE ({len(report['safe_to_remove'])} tables):")
        print("-" * 50)
        total_safe_size = 0
        for table_name, analysis, reason in report['safe_to_remove']:
            size_mb = analysis['size_mb']
            total_safe_size += size_mb
            rows = analysis['data_info']['row_count']
            print(f"  SAFE  {table_name:<25} | {size_mb:>6.2f} MB | {rows:>8,} rows | {reason}")
        
        print(f"\nTotal space to reclaim: {total_safe_size:.2f} MB")
        
        # Questionable
        print(f"\nQUESTIONABLE ({len(report['questionable'])} tables):")
        print("-" * 50)
        for table_name, analysis, reason in report['questionable']:
            size_mb = analysis['size_mb']
            rows = analysis['data_info']['row_count']
            last_activity = analysis['data_info']['last_activity']
            activity_str = last_activity.strftime("%Y-%m-%d") if last_activity else "unknown"
            print(f"  CHECK {table_name:<25} | {size_mb:>6.2f} MB | {rows:>8,} rows | Last: {activity_str} | {reason}")
        
        # Keep
        print(f"\nKEEP ({len(report['keep'])} tables):")
        print("-" * 50)
        for table_name, analysis, reason in report['keep']:
            size_mb = analysis['size_mb']
            rows = analysis['data_info']['row_count']
            print(f"  KEEP  {table_name:<25} | {size_mb:>6.2f} MB | {rows:>8,} rows | {reason}")
        
        # Generate removal commands
        if report['safe_to_remove']:
            print(f"\nSAFE REMOVAL COMMANDS:")
            print("-" * 50)
            for table_name, _, _ in report['safe_to_remove']:
                print(f"DROP TABLE {table_name};")
    
    def generate_removal_script(self, report: Dict) -> str:
        """Generate SQL script for safe table removal"""
        script = "-- Database Cleanup Script\n"
        script += "-- Generated automatically - contains only SAFE to remove tables\n"
        script += f"-- Generated on: {__import__('datetime').datetime.now()}\n\n"
        
        if not report['safe_to_remove']:
            script += "-- No tables identified as safe to remove\n"
            return script
        
        script += "-- Disable foreign key checks for cleanup\n"
        script += "SET FOREIGN_KEY_CHECKS = 0;\n\n"
        
        for table_name, analysis, reason in report['safe_to_remove']:
            size_mb = analysis['size_mb']
            rows = analysis['data_info']['row_count']
            script += f"-- {table_name}: {reason} ({size_mb:.2f} MB, {rows:,} rows)\n"
            script += f"DROP TABLE IF EXISTS {table_name};\n\n"
        
        script += "-- Re-enable foreign key checks\n"
        script += "SET FOREIGN_KEY_CHECKS = 1;\n"
        
        return script


def main():
    analyzer = DatabaseCleanupAnalyzer()
    
    print("Starting Database Cleanup Analysis...")
    print(f"Scanning project directory: {analyzer.project_root}")
    
    report = analyzer.generate_cleanup_report()
    analyzer.print_cleanup_report(report)
    
    # Generate removal script
    if report['safe_to_remove']:
        script = analyzer.generate_removal_script(report)
        script_path = analyzer.project_root / "database_cleanup.sql"
        
        with open(script_path, 'w') as f:
            f.write(script)
        
        print(f"\nCleanup script generated: {script_path}")
        print("   Review the script before executing!")
    
    print(f"\nAnalysis complete!")
    print(f"   Safe to remove: {len(report['safe_to_remove'])} tables")
    print(f"   Need review: {len(report['questionable'])} tables") 
    print(f"   Keep: {len(report['keep'])} tables")

if __name__ == "__main__":
    main()