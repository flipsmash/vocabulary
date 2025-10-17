#!/usr/bin/env python3
"""
Calculate TTS service capacity for missing pronunciation words
"""

import mysql.connector
from config import get_db_config

def main():
    config = get_db_config()
    conn = mysql.connector.connect(**config)
    cursor = conn.cursor()

    # Get sample of words missing audio to calculate average word length
    cursor.execute("""
    SELECT d.term FROM vocab.defined d 
    LEFT JOIN vocab.word_phonetics wp ON d.id = wp.word_id 
    WHERE (d.wav_url IS NULL OR d.wav_url = '')
    AND (wp.ipa_transcription IS NOT NULL AND wp.ipa_transcription != '')
    LIMIT 1000
    """)

    words = [row[0] for row in cursor.fetchall()]
    total_chars = sum(len(word) for word in words)
    avg_chars_per_word = total_chars / len(words) if words else 10

    print(f'Sample size: {len(words)} words')
    print(f'Total characters: {total_chars:,}')
    print(f'Average characters per word: {avg_chars_per_word:.1f}')
    print()

    # Calculate how many words each service can handle per month
    services = {
        'Microsoft Azure Speech': 500_000,
        'Google Cloud TTS': 1_000_000, 
        'Amazon Polly': 5_000_000,
        'IBM Watson': 10_000
    }

    print('FREE TIER CAPACITY PER MONTH:')
    print('=' * 60)
    for service, chars_limit in services.items():
        words_per_month = int(chars_limit / avg_chars_per_word)
        print(f'{service:25} | {chars_limit:>10,} chars | {words_per_month:>10,} words')

    print()
    print('OUR NEEDS:')
    print('=' * 60)
    total_missing = 15047
    total_chars_needed = int(total_missing * avg_chars_per_word)
    print(f'Words missing audio:         {total_missing:,}')
    print(f'Estimated characters needed: {total_chars_needed:,}')
    print()

    print('TIME TO COMPLETE (using single service):')
    print('=' * 70)
    for service, chars_limit in services.items():
        if chars_limit >= total_chars_needed:
            months = 1
            status = '✅ Complete in 1 month'
        else:
            months = (total_chars_needed / chars_limit)
            status = f'⏳ {months:.1f} months needed'
        
        words_per_month = int(chars_limit / avg_chars_per_word)
        print(f'{service:25} | {words_per_month:>8,} words/month | {status}')

    print()
    print('COMBINED SERVICES (using all free tiers together):')
    print('=' * 70)
    total_monthly_chars = sum(services.values())
    total_monthly_words = int(total_monthly_chars / avg_chars_per_word)
    print(f'Combined capacity:           {total_monthly_words:,} words/month')
    print(f'All services together:       ✅ Complete in 1 month')

    conn.close()

if __name__ == "__main__":
    main()