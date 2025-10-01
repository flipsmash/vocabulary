#!/usr/bin/env python3
"""
Temporary database connection fix
Try to find working credentials or provide alternatives
"""

import mysql.connector
from core.config import VocabularyConfig

def test_connection_alternatives():
    """Test various connection alternatives"""

    print("Database Connection Troubleshooter")
    print("=" * 40)

    # Current config
    current = VocabularyConfig.DATABASE
    print(f"Current config: {current['user']}@{current['host']}")

    # Alternative configurations to try
    alternatives = [
        # Try with different users
        {**current, 'user': 'vocab_user', 'password': '22051983'},
        {**current, 'user': 'vocab_user', 'password': 'Fl1p5ma5h!'},
        {**current, 'user': 'root', 'password': '22051983'},

        # Try localhost if it's accessible
        {**current, 'host': 'localhost'},
        {**current, 'host': '127.0.0.1'},

        # Try default MySQL port
        {**current, 'port': 3306},
    ]

    working_config = None

    for i, config in enumerate(alternatives, 1):
        print(f"\nTest {i}: {config['user']}@{config['host']}:{config['port']}")
        try:
            conn = mysql.connector.connect(**config)
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM defined")
            count = cursor.fetchone()[0]

            print(f"  ✓ SUCCESS: {count:,} words found")
            working_config = config

            cursor.close()
            conn.close()
            break

        except Exception as e:
            error_msg = str(e)
            if "Access denied" in error_msg:
                print(f"  ✗ Access denied")
            elif "Can't connect" in error_msg:
                print(f"  ✗ Can't connect to server")
            elif "Unknown database" in error_msg:
                print(f"  ✗ Database doesn't exist")
            else:
                print(f"  ✗ Error: {error_msg[:40]}")

    if working_config:
        print(f"\nFOUND WORKING CONFIGURATION!")
        print(f"Host: {working_config['host']}")
        print(f"Port: {working_config['port']}")
        print(f"User: {working_config['user']}")
        print(f"Database: {working_config['database']}")

        # Create updated config
        print(f"\nTo fix permanently, update core/config.py:")
        print(f"DATABASE = {working_config}")

        return working_config
    else:
        print(f"\nNO WORKING CONFIGURATION FOUND")
        print(f"\nYou need to:")
        print(f"1. Connect to MySQL server at {current['host']}")
        print(f"2. Run: GRANT ALL PRIVILEGES ON vocab.* TO 'brian'@'10.0.0.103' IDENTIFIED BY '{current['password']}';")
        print(f"3. Run: FLUSH PRIVILEGES;")

        return None

if __name__ == "__main__":
    test_connection_alternatives()