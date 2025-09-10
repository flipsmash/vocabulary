#!/usr/bin/env python3
import mysql.connector
from config import get_db_config

try:
    conn = mysql.connector.connect(**get_db_config())
    cursor = conn.cursor()
    cursor.execute("DROP TABLE IF EXISTS candidate_review_queue")
    conn.commit()
    print("Successfully removed candidate_review_queue")
finally:
    if 'conn' in locals() and conn.is_connected():
        cursor.close()
        conn.close()