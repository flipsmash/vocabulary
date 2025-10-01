#!/usr/bin/env python3
"""
Create a backup of the vocab database using Python and PyMySQL.
This doesn't require MySQL client tools to be installed.
"""

import os
import pymysql
import datetime
import json
from core.config import VocabularyConfig

def get_table_list(cursor):
    """Get list of all tables in the database."""
    cursor.execute("SHOW TABLES")
    tables = [row[0] for row in cursor.fetchall()]
    return tables

def backup_table_structure(cursor, table_name):
    """Get CREATE TABLE statement for a table."""
    cursor.execute(f"SHOW CREATE TABLE `{table_name}`")
    result = cursor.fetchone()
    return result[1] if result else None

def backup_table_data(cursor, table_name):
    """Get all data from a table."""
    cursor.execute(f"SELECT * FROM `{table_name}`")
    columns = [desc[0] for desc in cursor.description]
    rows = cursor.fetchall()
    return columns, rows

def backup_database():
    """Create a comprehensive backup of the vocab database."""

    # Get database configuration
    db_config = VocabularyConfig.get_db_config()

    # Create backup filename with timestamp
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_filename = f"vocab_backup_{timestamp}.sql"
    backup_path = os.path.join("backups", backup_filename)

    # Also create a JSON backup for easier analysis
    json_backup_filename = f"vocab_backup_{timestamp}.json"
    json_backup_path = os.path.join("backups", json_backup_filename)

    # Create backups directory if it doesn't exist
    os.makedirs("backups", exist_ok=True)

    print(f"Creating database backup...")
    print(f"Host: {db_config['host']}")
    print(f"Database: {db_config['database']}")
    print(f"SQL file: {backup_path}")
    print(f"JSON file: {json_backup_path}")

    try:
        # Connect to database
        conn = pymysql.connect(**db_config)
        cursor = conn.cursor()

        # Get list of tables
        tables = get_table_list(cursor)
        print(f"Found {len(tables)} tables: {', '.join(tables)}")

        backup_data = {
            'timestamp': timestamp,
            'database': db_config['database'],
            'tables': {}
        }

        # Create SQL backup file
        with open(backup_path, 'w', encoding='utf-8') as sql_file:
            # Write header
            sql_file.write(f"-- Vocabulary Database Backup\n")
            sql_file.write(f"-- Generated: {datetime.datetime.now()}\n")
            sql_file.write(f"-- Database: {db_config['database']}\n")
            sql_file.write(f"-- Host: {db_config['host']}\n\n")

            sql_file.write(f"CREATE DATABASE IF NOT EXISTS `{db_config['database']}`;\n")
            sql_file.write(f"USE `{db_config['database']}`;\n\n")

            # Backup each table
            for table_name in tables:
                print(f"  Backing up table: {table_name}")

                # Get table structure
                create_statement = backup_table_structure(cursor, table_name)
                if create_statement:
                    sql_file.write(f"-- Table structure for {table_name}\n")
                    sql_file.write(f"DROP TABLE IF EXISTS `{table_name}`;\n")
                    sql_file.write(f"{create_statement};\n\n")

                # Get table data
                columns, rows = backup_table_data(cursor, table_name)

                # Store in JSON backup
                backup_data['tables'][table_name] = {
                    'columns': columns,
                    'row_count': len(rows),
                    'structure': create_statement
                }

                if rows:
                    sql_file.write(f"-- Data for table {table_name}\n")
                    sql_file.write(f"LOCK TABLES `{table_name}` WRITE;\n")
                    sql_file.write(f"/*!40000 ALTER TABLE `{table_name}` DISABLE KEYS */;\n")

                    # Write data in chunks for large tables
                    chunk_size = 1000
                    for i in range(0, len(rows), chunk_size):
                        chunk = rows[i:i + chunk_size]

                        if chunk:
                            values_list = []
                            for row in chunk:
                                # Escape values for SQL
                                escaped_values = []
                                for value in row:
                                    if value is None:
                                        escaped_values.append('NULL')
                                    elif isinstance(value, str):
                                        escaped_value = value.replace("'", "''").replace("\\", "\\\\")
                                        escaped_values.append(f"'{escaped_value}'")
                                    elif isinstance(value, (int, float)):
                                        escaped_values.append(str(value))
                                    else:
                                        escaped_value = str(value).replace("'", "''").replace("\\", "\\\\")
                                        escaped_values.append(f"'{escaped_value}'")

                                values_list.append(f"({','.join(escaped_values)})")

                            column_list = ','.join([f"`{col}`" for col in columns])
                            sql_file.write(f"INSERT INTO `{table_name}` ({column_list}) VALUES\n")
                            sql_file.write(',\n'.join(values_list))
                            sql_file.write(';\n')

                    sql_file.write(f"/*!40000 ALTER TABLE `{table_name}` ENABLE KEYS */;\n")
                    sql_file.write(f"UNLOCK TABLES;\n\n")

                print(f"    {len(rows):,} rows backed up")

        # Create JSON backup (metadata only, not full data)
        with open(json_backup_path, 'w', encoding='utf-8') as json_file:
            json.dump(backup_data, json_file, indent=2, default=str)

        # Check file sizes
        sql_size = os.path.getsize(backup_path)
        json_size = os.path.getsize(json_backup_path)

        print(f"\n✓ Backup completed successfully!")
        print(f"  SQL file: {backup_path} ({sql_size / (1024*1024):.1f} MB)")
        print(f"  JSON file: {json_backup_path} ({json_size / 1024:.1f} KB)")

        return backup_path, json_backup_path

    except Exception as e:
        print(f"ERROR: Backup failed: {e}")
        return None, None

    finally:
        if 'cursor' in locals():
            cursor.close()
        if 'conn' in locals():
            conn.close()

def verify_backup(backup_path):
    """Verify the backup file looks valid."""
    if not backup_path or not os.path.exists(backup_path):
        return False

    try:
        with open(backup_path, 'r', encoding='utf-8') as f:
            content = f.read(1000)  # Read first 1KB

        # Check for expected patterns
        required_patterns = [
            "-- Vocabulary Database Backup",
            "CREATE DATABASE",
            "USE `vocab`"
        ]

        found_patterns = sum(1 for pattern in required_patterns if pattern in content)

        if found_patterns >= 2:
            print(f"✓ Backup verification passed")
            return True
        else:
            print(f"⚠ Backup verification failed")
            return False

    except Exception as e:
        print(f"ERROR: Could not verify backup: {e}")
        return False

if __name__ == "__main__":
    print("=" * 60)
    print("Python Database Backup Utility")
    print("=" * 60)

    sql_backup, json_backup = backup_database()

    if sql_backup:
        verify_backup(sql_backup)
        print(f"\nBackup files created:")
        print(f"  SQL: {sql_backup}")
        print(f"  JSON: {json_backup}")
    else:
        print("\nBackup failed!")
        exit(1)