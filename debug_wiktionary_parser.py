#!/usr/bin/env python3
"""
Focused debugging of Wiktionary HTML parsing for tabacosis
"""

import asyncio
import logging
import sys
import os
from bs4 import BeautifulSoup

# Add the project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core.comprehensive_definition_lookup import ComprehensiveDefinitionLookup

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

async def debug_wiktionary_parsing():
    """Debug the exact HTML parsing steps"""
    
    async with ComprehensiveDefinitionLookup() as lookup:
        print("=== DEBUGGING WIKTIONARY PARSING ===")
        
        # Get the raw HTML
        url = f"https://en.wiktionary.org/w/api.php"
        params = {
            'action': 'parse',
            'format': 'json',
            'page': 'tabacosis',
            'prop': 'text'
        }
        
        async with lookup.session.get(url, params=params) as response:
            if response.status == 200:
                data = await response.json()
                html_text = data['parse']['text']['*']
                
                print(f"[OK] Got HTML, length: {len(html_text)}")
                
                # Parse with BeautifulSoup
                soup = BeautifulSoup(html_text, 'html.parser')
                
                # Step 1: Find English section
                print("\n=== STEP 1: Finding English Section ===")
                english_header = soup.find('h2', {'id': 'English'})
                if not english_header:
                    english_div = soup.find('div', class_='mw-heading mw-heading2')
                    if english_div:
                        english_header = english_div.find('h2', {'id': 'English'})
                
                if english_header:
                    print(f"[OK] Found English header: {english_header}")
                else:
                    print("[ERROR] No English header found")
                    return
                
                # Step 2: Traverse siblings - but we need to start from the right place!
                print(f"\n=== STEP 2: Traversing Elements After English Header ===")
                
                # Check if the h2 is wrapped in a div
                english_container = english_header.parent
                print(f"English header parent: <{english_container.name}> with classes: {english_container.get('class', [])}")
                
                # Start traversal from the container div, not the h2
                if english_container.name == 'div' and 'mw-heading' in english_container.get('class', []):
                    current_element = english_container.find_next_sibling()
                    print("Starting traversal from container div")
                else:
                    current_element = english_header.find_next_sibling()
                    print("Starting traversal from h2 directly")
                element_count = 0
                found_ol = False
                
                while current_element and element_count < 50:
                    element_count += 1
                    print(f"Element {element_count}: <{current_element.name}> with classes: {current_element.get('class', [])}")
                    
                    if current_element.name == 'h2':
                        print("  [STOP] Hit another h2, stopping")
                        break
                    
                    # Check for part of speech in divs
                    if current_element.name == 'div' and 'mw-heading' in current_element.get('class', []):
                        if 'mw-heading3' in current_element.get('class', []):
                            h3_in_div = current_element.find('h3')
                            if h3_in_div:
                                print(f"  [POS] Found POS header: {h3_in_div.get_text().strip()}")
                    
                    # Check for definition lists
                    if current_element.name == 'ol':
                        found_ol = True
                        print(f"  [FOUND OL!] Contains {len(current_element.find_all('li', recursive=False))} list items")
                        
                        # Examine each list item
                        for i, li in enumerate(current_element.find_all('li', recursive=False)):
                            print(f"    Li {i+1}: {li.get_text()[:100]}...")
                            
                            # Try to extract text the way the parser does
                            definition_text = ""
                            for content in li.contents:
                                if hasattr(content, 'string') and content.string:
                                    definition_text += content.string
                                elif hasattr(content, 'get_text'):
                                    if content.name == 'span' and 'usage-label-sense' in content.get('class', []):
                                        definition_text += content.get_text() + ' '
                                    elif content.name not in ['ul', 'ol']:
                                        text = content.get_text()
                                        if 'citation-whole' in str(content) or content.name == 'ul':
                                            break
                                        definition_text += text
                                elif isinstance(content, str):
                                    definition_text += content
                            
                            cleaned_def = definition_text.strip()[:100]
                            print(f"      Extracted: '{cleaned_def}...'")
                    
                    current_element = current_element.find_next_sibling()
                
                if not found_ol:
                    print("\n[ERROR] NO ORDERED LISTS FOUND!")
                    print("Let's check if there are ANY <ol> elements in the HTML:")
                    all_ols = soup.find_all('ol')
                    print(f"Total <ol> elements in HTML: {len(all_ols)}")
                    for i, ol in enumerate(all_ols):
                        print(f"  OL {i+1}: {len(ol.find_all('li'))} items, first text: {ol.get_text()[:50]}...")
                else:
                    print("[OK] Found ordered list during traversal")

if __name__ == "__main__":
    asyncio.run(debug_wiktionary_parsing())