#!/usr/bin/env python3
"""
Create a backup of the vocab database using mysqldump.
"""

import os
import subprocess
import datetime
from core.config import VocabularyConfig

def backup_database():
    """Create a MySQL dump backup of the vocab database."""

    # Get database configuration
    db_config = VocabularyConfig.get_db_config()

    # Create backup filename with timestamp
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_filename = f"vocab_backup_{timestamp}.sql"
    backup_path = os.path.join("backups", backup_filename)

    # Create backups directory if it doesn't exist
    os.makedirs("backups", exist_ok=True)

    print(f"Creating database backup...")
    print(f"Host: {db_config['host']}")
    print(f"Database: {db_config['database']}")
    print(f"Output file: {backup_path}")

    # Build mysqldump command
    mysqldump_path = r"C:\Program Files\MySQL\MySQL Workbench 8.0 CE\mysqldump.exe"
    cmd = [
        mysqldump_path,
        f"--host={db_config['host']}",
        f"--port={db_config['port']}",
        f"--user={db_config['user']}",
        f"--password={db_config['password']}",
        "--single-transaction",  # For InnoDB consistency
        "--routines",           # Include stored procedures/functions
        "--triggers",           # Include triggers
        "--events",             # Include events
        "--add-drop-table",     # Add DROP TABLE statements
        "--create-options",     # Include table options
        "--disable-keys",       # Faster import
        "--extended-insert",    # Faster import
        "--lock-tables=false",  # Don't lock tables
        db_config['database']
    ]

    try:
        # Run mysqldump and save to file
        with open(backup_path, 'w', encoding='utf-8') as f:
            result = subprocess.run(
                cmd,
                stdout=f,
                stderr=subprocess.PIPE,
                text=True,
                check=True
            )

        # Check file size
        file_size = os.path.getsize(backup_path)
        file_size_mb = file_size / (1024 * 1024)

        print(f"✓ Backup completed successfully!")
        print(f"  File: {backup_path}")
        print(f"  Size: {file_size_mb:.1f} MB")

        return backup_path

    except subprocess.CalledProcessError as e:
        print(f"ERROR: mysqldump failed: {e}")
        if e.stderr:
            print(f"Error details: {e.stderr}")
        return None
    except FileNotFoundError:
        print("ERROR: mysqldump not found. Please ensure MySQL client tools are installed and in PATH.")
        return None
    except Exception as e:
        print(f"ERROR: Unexpected error: {e}")
        return None

def verify_backup(backup_path):
    """Verify the backup file looks valid."""
    if not backup_path or not os.path.exists(backup_path):
        return False

    try:
        with open(backup_path, 'r', encoding='utf-8') as f:
            # Read first few lines to check if it looks like a valid SQL dump
            first_lines = [f.readline().strip() for _ in range(10)]

        # Check for mysqldump header patterns
        valid_patterns = [
            "-- MySQL dump",
            "-- Host:",
            "-- Server version",
            "CREATE TABLE",
            "USE `vocab`"
        ]

        content = ' '.join(first_lines)
        found_patterns = sum(1 for pattern in valid_patterns if pattern in content)

        if found_patterns >= 2:
            print(f"✓ Backup verification passed ({found_patterns}/{len(valid_patterns)} patterns found)")
            return True
        else:
            print(f"⚠ Backup verification questionable ({found_patterns}/{len(valid_patterns)} patterns found)")
            return False

    except Exception as e:
        print(f"ERROR: Could not verify backup: {e}")
        return False

if __name__ == "__main__":
    print("=" * 60)
    print("MySQL Database Backup Utility")
    print("=" * 60)

    backup_path = backup_database()

    if backup_path:
        verify_backup(backup_path)
        print(f"\nBackup completed: {backup_path}")
    else:
        print("\nBackup failed!")
        exit(1)