#!/usr/bin/env python3
"""
Test script to debug Wiktionary parsing
"""

from wiktionary_harvester import WiktionaryHarvester, WiktionaryParser
import time

def test_specific_word():
    """Test parsing a specific word we know should be archaic"""
    harvester = WiktionaryHarvester(delay=0.5)
    parser = WiktionaryParser()
    
    # Test with a word we expect to be archaic
    test_word = "forsooth"  # Should be archaic
    
    print(f"Testing word: {test_word}")
    print("=" * 50)
    
    # Get content
    content = harvester.get_page_content(test_word)
    
    if not content:
        print("No content retrieved")
        return
    
    print(f"Retrieved content length: {len(content)} characters")
    print(f"First 500 characters:")
    try:
        print(content[:500])
    except UnicodeEncodeError:
        print(content[:500].encode('ascii', 'replace').decode('ascii'))
    print("\n" + "=" * 50)
    
    # Parse entries
    entries = parser.parse_entry(test_word, content)
    
    print(f"Found {len(entries)} entries:")
    for i, entry in enumerate(entries):
        print(f"\nEntry {i+1}:")
        print(f"  Term: {entry.term}")
        print(f"  POS: {entry.part_of_speech}")
        print(f"  Tags: {entry.tags}")
        print(f"  Definition: {entry.definition[:100]}...")
        if entry.etymology:
            print(f"  Etymology: {entry.etymology[:100]}...")

def test_category_parsing():
    """Test getting members from a category"""
    harvester = WiktionaryHarvester(delay=0.5)
    
    print("Testing category member retrieval...")
    print("=" * 50)
    
    # Get a small sample from archaic terms
    members = harvester.get_category_members("English archaic terms", limit=5)
    
    print(f"Found {len(members)} category members:")
    for member in members:
        print(f"  - {member}")
    
    # Test parsing first member
    if members:
        print(f"\nTesting first member: {members[0]}")
        content = harvester.get_page_content(members[0])
        
        if content:
            print(f"Content length: {len(content)}")
            # Look for archaic indicators in raw content
            archaic_indicators = ['archaic', 'obsolete', 'dated', 'historical']
            found_indicators = []
            for indicator in archaic_indicators:
                if indicator.lower() in content.lower():
                    found_indicators.append(indicator)
            
            print(f"Found indicators in raw content: {found_indicators}")
            
            # Show a snippet around any archaic mentions
            content_lower = content.lower()
            for indicator in found_indicators:
                pos = content_lower.find(indicator.lower())
                if pos >= 0:
                    start = max(0, pos - 100)
                    end = min(len(content), pos + 100)
                    print(f"\nContext for '{indicator}':")
                    try:
                        print(f"...{content[start:end]}...")
                    except UnicodeEncodeError:
                        print(f"...{content[start:end].encode('ascii', 'replace').decode('ascii')}...")

if __name__ == "__main__":
    print("Wiktionary Parsing Debug Test")
    print("=" * 50)
    
    print("\n1. Testing specific archaic word...")
    test_specific_word()
    
    print("\n\n2. Testing category retrieval and parsing...")
    test_category_parsing()