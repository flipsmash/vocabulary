#!/usr/bin/env python3
"""
Check phonetic data for test words
"""

import mysql.connector
from config import get_db_config

def main():
    config = get_db_config()
    conn = mysql.connector.connect(**config)
    cursor = conn.cursor()

    # Check the phonetic data for our test words
    test_words = ['abapical', 'abarticular', 'abasia', 'abask', 'abatjour', 'abattage', 'abature', 'abb', 'abba', 'abbatoir']

    print('PHONETIC DATA FOR TEST WORDS:')
    print('=' * 80)
    for word in test_words:
        cursor.execute('''
        SELECT d.term, wp.ipa_transcription, wp.arpabet_transcription, wp.stress_pattern
        FROM defined d 
        JOIN word_phonetics wp ON d.id = wp.word_id 
        WHERE d.term = %s
        ''', (word,))
        
        result = cursor.fetchone()
        if result:
            term, ipa, arpabet, stress = result
            print(f'{term:12} | ARPABET: {arpabet:15} | Stress: {stress}')
        else:
            print(f'{word:12} | No phonetic data found')

    print()
    print('CURRENT ISSUE:')
    print('The Windows SAPI generator is NOT using the phonetic data!')
    print('It is just reading the raw word spelling, which may be incorrect.')
    print()
    print('SOLUTIONS:')
    print('1. Use ARPABET transcriptions with SAPI phonetic markup')
    print('2. Use cloud services that accept IPA input')
    print('3. Convert IPA to SSML phonetic markup')

    conn.close()

if __name__ == "__main__":
    main()