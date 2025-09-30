#!/usr/bin/env python3
"""
Test the English validation integration with sample candidate words
"""

import sys
from english_word_validator import validate_english_word

def test_integration():
    """Test validation with real-world examples from the current candidates"""
    
    # Sample candidates from our review system (mix of English and non-English)
    test_candidates = [
        # English words (should pass)
        "wonderful",
        "archaic", 
        "restoration",
        "magnificent",
        "disposition",
        "preservation",
        "theory",
        "animal",
        "unnecessary", 
        "ebullition",
        "amiability",
        
        # Dutch words from Gutenberg (should fail)
        "uitgegeven",
        "meetkundigen", 
        "nageplozen",
        "katholieken",
        "beteekenis",
        "cartesianen",
        "collegianten",
        "psychologie",
        "veroveren", 
        "verloochene",
        "emendatione",
        "cogitata",
        "anthropos",
        
        # Edge cases
        "thou",  # archaic English (should pass)
        "thee",  # archaic English (should pass)
        "",      # empty (should fail)
        "a",     # too short (should fail)
        "xyz",   # nonsense (should fail)
    ]
    
    print("Testing English Word Validation Integration")
    print("=" * 60)
    print()
    
    passed = 0
    failed = 0
    english_accepted = 0
    dutch_rejected = 0
    
    for word in test_candidates:
        is_english, reason = validate_english_word(word)
        
        # Determine expected result based on our knowledge
        if word in ["wonderful", "archaic", "restoration", "magnificent", "disposition", 
                   "preservation", "theory", "animal", "unnecessary", "ebullition", 
                   "amiability", "thou", "thee"]:
            expected = True
            category = "English"
        elif word in ["uitgegeven", "meetkundigen", "nageplozen", "katholieken", 
                     "beteekenis", "cartesianen", "collegianten", "psychologie", 
                     "veroveren", "verloochene", "emendatione", "cogitata", "anthropos"]:
            expected = False
            category = "Dutch" 
        else:
            expected = False
            category = "Edge case"
        
        # Check result
        correct = is_english == expected
        status = "PASS" if correct else "FAIL"
        
        print(f"{status:4} | {word:15} | {category:10} | {is_english:5} | {reason:20}")
        
        if correct:
            passed += 1
        else:
            failed += 1
            
        # Track specific categories
        if category == "English" and is_english:
            english_accepted += 1
        elif category == "Dutch" and not is_english:
            dutch_rejected += 1
    
    print()
    print(f"Results Summary:")
    print(f"Total tests: {len(test_candidates)}")
    print(f"Passed: {passed}")
    print(f"Failed: {failed}")
    print(f"Accuracy: {passed/len(test_candidates)*100:.1f}%")
    print()
    print(f"English words accepted: {english_accepted}/13")
    print(f"Dutch words rejected: {dutch_rejected}/13")
    print()
    
    # Show what would happen in ingestion
    print("Ingestion Impact Simulation:")
    print("-" * 30)
    
    english_words = [w for w in test_candidates if w in ["wonderful", "archaic", "restoration", "magnificent", "disposition", "preservation", "theory", "animal", "unnecessary", "ebullition", "amiability", "thou", "thee"]]
    dutch_words = [w for w in test_candidates if w in ["uitgegeven", "meetkundigen", "nageplozen", "katholieken", "beteekenis", "cartesianen", "collegianten", "psychologie", "veroveren", "verloochene", "emendatione", "cogitata", "anthropos"]]
    
    english_would_pass = [w for w in english_words if validate_english_word(w)[0]]
    dutch_would_be_blocked = [w for w in dutch_words if not validate_english_word(w)[0]]
    
    print(f"Of {len(english_words)} English words, {len(english_would_pass)} would be accepted")
    print(f"Of {len(dutch_words)} Dutch words, {len(dutch_would_be_blocked)} would be blocked")
    
    if len(english_would_pass) < len(english_words):
        print(f"English words that would be incorrectly blocked: {[w for w in english_words if not validate_english_word(w)[0]]}")
    
    if len(dutch_would_be_blocked) < len(dutch_words):
        print(f"Dutch words that would incorrectly pass: {[w for w in dutch_words if validate_english_word(w)[0]]}")
    
    return passed == len(test_candidates)

if __name__ == "__main__":
    success = test_integration()
    sys.exit(0 if success else 1)