#!/usr/bin/env python3
"""
Test script to debug the comprehensive lookup system
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
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

async def test_lookup():
    """Test the lookup system with tabacosis"""
    print("Initializing ComprehensiveDefinitionLookup...")
    
    async with ComprehensiveDefinitionLookup() as lookup:
        print("Testing lookup for 'tabacosis'...")
        
        # First try a simple word that should work
        print("Testing with 'hello' first...")
        hello_result = await lookup.lookup_term("hello", use_cache=False)
        print(f"Hello sources: {hello_result.sources_consulted if hello_result else 'None'}")
        if hello_result:
            total_hello_defs = sum(len(defs) for defs in hello_result.definitions_by_pos.values())
            print(f"Hello has {total_hello_defs} definitions from {len(hello_result.sources_consulted)} sources")
        
        print("\nNow testing with 'tabacosis'...")
        result = await lookup.lookup_term("tabacosis", use_cache=False)
        
        print(f"Result: {result}")
        
        if result:
            total_defs = sum(len(defs) for defs in result.definitions_by_pos.values())
            print(f"Has definitions: {total_defs > 0}")
            print(f"Sources consulted: {result.sources_consulted}")
            print(f"Overall reliability: {result.overall_reliability}")
            print(f"Cache hit: {result.cache_hit}")
            
            if total_defs > 0:
                print(f"Found {total_defs} definitions across {len(result.definitions_by_pos)} parts of speech")
                for pos, definitions in result.definitions_by_pos.items():
                    print(f"  {pos.upper()}: {len(definitions)} definitions")
                    for i, definition in enumerate(definitions):
                        print(f"    {i+1}. {definition.text} (from {definition.source})")
            else:
                print("No definitions found")
        else:
            print("No result returned")

if __name__ == "__main__":
    asyncio.run(test_lookup())