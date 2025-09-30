#!/usr/bin/env python3
"""
Test Independent Frequency Calculator
Tests the comprehensive frequency analysis system on a small sample
"""

from independent_frequency_calculator import IndependentFrequencyCalculator
from config import get_db_config
import logging

logging.basicConfig(level=logging.INFO)

def test_frequency_analysis():
    """Test the frequency analysis on a small sample"""
    print("TESTING INDEPENDENT FREQUENCY CALCULATOR")
    print("=" * 60)
    
    calculator = IndependentFrequencyCalculator(get_db_config())
    
    # Load small sample for testing
    words_data = calculator.load_words_to_analyze(limit=50)  # Test with 50 words
    
    print(f"Testing with {len(words_data)} words...")
    
    # Calculate frequencies
    frequency_results = calculator.batch_analyze_frequencies(words_data, max_workers=2)
    
    # Store results
    calculator.store_calculated_frequencies(frequency_results)
    
    # Generate report
    calculator.generate_comprehensive_report()
    
    print("\nTest completed! Check results in 'word_frequencies_independent' table")

if __name__ == "__main__":
    test_frequency_analysis()