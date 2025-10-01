#!/usr/bin/env python3
"""
Audit pronunciation file coverage in database
Quick script to assess current wav_url status
"""

import sys
import os

# Direct import to avoid core.__init__ dependencies
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import psycopg

# Import database config directly
def get_db_config():
    """Quick database config for standalone script"""
    return {
        'host': '10.0.0.99',
        'port': 6543,
        'dbname': 'postgres',
        'user': 'postgres.your-tenant-id',
        'password': 'your-super-secret-and-long-postgres-password',
        'options': '-c search_path=vocab'
    }

def main():
    db_config = get_db_config()

    with psycopg.connect(**db_config) as conn:
        with conn.cursor() as cursor:
            # Explicitly set schema for this session
            cursor.execute('SET search_path TO vocab')

            # Total words
            cursor.execute('SELECT COUNT(*) as total FROM defined')
            total = cursor.fetchone()[0]

            # Words with wav_url
            cursor.execute("SELECT COUNT(*) FROM defined WHERE wav_url IS NOT NULL AND wav_url != ''")
            with_wav = cursor.fetchone()[0]

            # Sample of wav_url patterns
            cursor.execute("SELECT DISTINCT wav_url FROM defined WHERE wav_url IS NOT NULL AND wav_url != '' LIMIT 20")
            samples = cursor.fetchall()

            # Check for external URLs (http/https)
            cursor.execute("SELECT COUNT(*) FROM defined WHERE wav_url LIKE 'http%'")
            external_urls = cursor.fetchone()[0]

            # Check for local paths
            cursor.execute("SELECT COUNT(*) FROM defined WHERE wav_url LIKE '/pronunciation/%'")
            local_paths = cursor.fetchone()[0]

            print('=' * 60)
            print('PRONUNCIATION FILE COVERAGE AUDIT')
            print('=' * 60)
            print(f'\nTotal words in database: {total:,}')
            print(f'Words with wav_url set: {with_wav:,} ({with_wav/total*100:.1f}%)')
            print(f'Words missing wav_url: {total - with_wav:,} ({(total-with_wav)/total*100:.1f}%)')
            print(f'\n  External URLs (http/https): {external_urls:,}')
            print(f'  Local paths (/pronunciation/): {local_paths:,}')

            print('\nSample wav_url values:')
            for s in samples:
                url = s[0] if s[0] else 'NULL'
                print(f'  {url}')

            # Check for existing files
            from pathlib import Path
            pron_dir = Path('pronunciation_files')
            if pron_dir.exists():
                existing_files = list(pron_dir.glob('*.wav'))
                print(f'\nExisting .wav files in pronunciation_files/: {len(existing_files):,}')
            else:
                print(f'\nWarning: pronunciation_files/ directory not found')

if __name__ == '__main__':
    main()
