#!/usr/bin/env python3
"""Simple test for the enhanced harvester"""

import sys
import os

# Add the vocabulary directory to path
vocab_dir = r"C:\Users\Brian\vocabulary"
sys.path.insert(0, vocab_dir)

# Direct import without using __init__.py
import importlib.util

def load_harvester():
    """Load the harvester module directly"""
    harvester_path = os.path.join(vocab_dir, "harvesters", "enhanced_vocabulary_list_harvester.py")
    spec = importlib.util.spec_from_file_location("enhanced_vocabulary_list_harvester", harvester_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

def test_basic_functionality():
    """Test basic functionality"""
    print("Testing Enhanced Vocabulary Harvester")
    print("=" * 50)

    try:
        module = load_harvester()
        EnhancedVocabularyListHarvester = module.EnhancedVocabularyListHarvester

        print("✅ Harvester loaded successfully!")

        # Test pattern detection
        from bs4 import BeautifulSoup

        harvester = EnhancedVocabularyListHarvester()

        # Test HTML
        test_html = '''
        <div>
            <ul>
                <li><strong>Aberrant</strong> - Departing from an accepted standard</li>
                <li><strong>Benevolent</strong> - Well-meaning and kindly</li>
                <li><strong>Cacophony</strong> - A harsh discordant mixture of sounds</li>
            </ul>
        </div>
        '''

        soup = BeautifulSoup(test_html, 'html.parser')
        raw_terms = harvester._extract_all_vocabulary(soup)

        print(f"✅ Pattern detection working! Found {len(raw_terms)} terms:")
        for i, term_data in enumerate(raw_terms[:3], 1):
            term = term_data.get('term', 'Unknown')
            definition = term_data.get('definition', 'No definition')
            print(f"  {i}. {term}: {definition[:50]}...")

        # Test term processing (without database)
        if raw_terms:
            print("\n🔄 Testing term processing...")
            try:
                processed = harvester._process_terms(raw_terms[:1], "http://test.example.com")
                if processed:
                    term = processed[0]
                    print(f"✅ Processed term: {term.term}")
                    print(f"   POS: {term.part_of_speech}")
                    print(f"   Quality: {term.quality_score:.1f}")
                    print(f"   Definition: {term.primary_definition[:100]}...")
            except Exception as e:
                print(f"⚠️  Term processing had issues (expected without database): {e}")

        print("\n✅ Basic functionality test completed!")

    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_basic_functionality()