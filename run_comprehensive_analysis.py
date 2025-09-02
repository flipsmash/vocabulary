#!/usr/bin/env python3
"""
Run Comprehensive Independent Frequency Analysis
Auto-confirms and runs the full analysis
"""

from independent_frequency_calculator import IndependentFrequencyCalculator
from config import get_db_config
import logging

logging.basicConfig(level=logging.INFO)

def run_comprehensive_analysis(sample_size=None):
    """Run comprehensive frequency analysis with optional sample size"""
    print("COMPREHENSIVE INDEPENDENT FREQUENCY CALCULATOR")
    print("=" * 60)
    print("Analyzing words in database with independent frequency sources")
    print("Results will be stored separately from existing frequency data")
    print("=" * 60)
    
    calculator = IndependentFrequencyCalculator(get_db_config())
    
    # Load words for analysis
    words_data = calculator.load_words_to_analyze(limit=sample_size)
    
    if not words_data:
        print("No words found in database")
        return
    
    print(f"\nStarting analysis of {len(words_data):,} words...")
    
    if sample_size:
        print(f"Running sample analysis with {sample_size:,} words")
    else:
        print("Running FULL analysis of entire database")
        print("This will take 2-4 hours due to API rate limits")
    
    # Calculate frequencies
    print("Starting frequency calculation...")
    frequency_results = calculator.batch_analyze_frequencies(words_data, max_workers=3)
    
    # Store results
    calculator.store_calculated_frequencies(frequency_results)
    
    # Generate report
    calculator.generate_comprehensive_report()
    
    print(f"\n" + "="*80)
    print("COMPREHENSIVE INDEPENDENT FREQUENCY ANALYSIS COMPLETE!")
    print("="*80)
    print(f"Analyzed: {len(frequency_results):,} words")
    print(f"Results stored in: 'word_frequencies_independent' table")
    print(f"Data includes: frequency rankings, rarity percentiles, source breakdowns")
    print(f"This analysis is completely separate from your existing frequency data")
    print("="*80)

if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1:
        try:
            sample_size = int(sys.argv[1])
            print(f"Running with sample size: {sample_size}")
            run_comprehensive_analysis(sample_size)
        except ValueError:
            print("Invalid sample size. Using full analysis.")
            run_comprehensive_analysis()
    else:
        # Default: run with larger sample for demonstration
        print("Running with 1000-word sample for demonstration")
        print("To run full analysis: python run_comprehensive_analysis.py 22094")
        run_comprehensive_analysis(1000)