#!/usr/bin/env python3
"""
Quick Analysis Sample - Test a few words to show the system working
"""

from independent_frequency_calculator import IndependentFrequencyCalculator
from config import get_db_config
import logging

logging.basicConfig(level=logging.INFO)

def quick_sample():
    """Quick sample analysis to demonstrate the system"""
    print("QUICK INDEPENDENT FREQUENCY ANALYSIS SAMPLE")
    print("=" * 60)
    
    calculator = IndependentFrequencyCalculator(get_db_config())
    
    # Load just 100 words for quick demonstration
    words_data = calculator.load_words_to_analyze(limit=100)
    
    print(f"Analyzing {len(words_data)} words for demonstration...")
    
    # Calculate frequencies
    frequency_results = calculator.batch_analyze_frequencies(words_data, max_workers=2)
    
    # Store results
    calculator.store_calculated_frequencies(frequency_results)
    
    # Generate report
    calculator.generate_comprehensive_report()
    
    print(f"\nQuick sample complete!")
    print(f"Analyzed {len(frequency_results)} words")
    print("Results stored in 'word_frequencies_independent' table")

if __name__ == "__main__":
    quick_sample()