#!/usr/bin/env python3
"""
Windows console utilities to handle encoding issues permanently
"""

import sys
import os

def setup_windows_console():
    """
    Setup Windows console to handle Unicode properly and avoid encoding errors
    """
    if sys.platform.startswith('win'):
        # Set console to UTF-8 encoding
        if hasattr(sys.stdout, 'reconfigure'):
            sys.stdout.reconfigure(encoding='utf-8', errors='replace')
            sys.stderr.reconfigure(encoding='utf-8', errors='replace')

        # Set environment variables for consistent UTF-8 handling
        os.environ['PYTHONIOENCODING'] = 'utf-8:replace'

def safe_print(text, use_ascii=True):
    """
    Print text safely, replacing problematic Unicode characters with ASCII equivalents
    """
    if use_ascii:
        # Replace common Unicode characters with ASCII equivalents
        replacements = {
            '✓': '[OK]',
            '✗': '[FAIL]',
            '→': '->',
            '←': '<-',
            '↑': '^',
            '↓': 'v',
            '🎉': '[SUCCESS]',
            '⚠': '[WARNING]',
            '❌': '[ERROR]',
            '🔍': '[SEARCH]',
            '📝': '[NOTE]',
            '💡': '[TIP]',
            '🚀': '[START]',
            '⭐': '*',
            '🎯': '[TARGET]',
            # Add more as needed
        }

        for unicode_char, ascii_replacement in replacements.items():
            text = text.replace(unicode_char, ascii_replacement)

    try:
        print(text)
    except UnicodeEncodeError:
        # Fallback: encode as ASCII with error replacement
        ascii_text = text.encode('ascii', errors='replace').decode('ascii')
        print(ascii_text)

# Auto-setup when module is imported
setup_windows_console()