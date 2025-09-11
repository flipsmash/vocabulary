#!/usr/bin/env python3
"""
Test script to debug Wiktionary lookup specifically
"""

import asyncio
import logging
import sys
import os

# Add the project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core.comprehensive_definition_lookup import ComprehensiveDefinitionLookup

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,  # Set to DEBUG to see more details
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

async def test_wiktionary():
    """Test Wiktionary lookup specifically"""
    
    async with ComprehensiveDefinitionLookup() as lookup:
        print("Testing Wiktionary directly...")
        
        # First test the API call works
        import aiohttp
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
                if data is not None and 'parse' in data and 'text' in data['parse']:
                    html_text = data['parse']['text']['*']
                    print(f"Got HTML text, length: {len(html_text)}")
                    
                    # Test the HTML parsing directly
                    from bs4 import BeautifulSoup
                    soup = BeautifulSoup(html_text, 'html.parser')
                    
                    english_h2 = soup.find('h2', {'id': 'English'})
                    print(f"Direct h2 search: {english_h2 is not None}")
                    
                    english_div = soup.find('div', class_='mw-heading mw-heading2')
                    print(f"Div search: {english_div is not None}")
                    if english_div:
                        h2_in_div = english_div.find('h2', {'id': 'English'})
                        print(f"H2 in div: {h2_in_div is not None}")
                    
                    # Test the actual parsing
                    parsed_defs = lookup._parse_wiktionary_html(html_text, "tabacosis")
                    print(f"Parsed definitions: {len(parsed_defs)}")
                else:
                    print("No parse data in response")
            else:
                print(f"HTTP error: {response.status}")
        
        # Now test via the method  
        wiktionary_defs = await lookup._lookup_wiktionary("tabacosis")
        
        print(f"Wiktionary returned {len(wiktionary_defs)} definitions")
        for i, defn in enumerate(wiktionary_defs):
            print(f"  {i+1}. {defn.text[:100]}... (from {defn.source})")

if __name__ == "__main__":
    asyncio.run(test_wiktionary())