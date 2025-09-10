#!/usr/bin/env python3
"""
Quick Browse Functionality Checker
Specifically designed to prevent the recurring browse functionality regression.
"""

import requests
from urllib.parse import urljoin

def check_browse_functionality(base_url="http://localhost:8000"):
    """Quick check for browse functionality"""
    print("Checking Browse Functionality...")
    print("="*40)
    
    critical_tests = [
        ('/browse', 'Browse main page'),
        ('/browse?page=1', 'Browse pagination'),
        ('/browse?letters=a', 'Browse letter filtering'),
        ('/browse?per_page=25', 'Browse per-page control'),
    ]
    
    all_good = True
    
    for path, description in critical_tests:
        url = urljoin(base_url, path)
        try:
            response = requests.get(url, timeout=5)
            if response.status_code == 200 and "Browse Vocabulary" in response.text:
                print(f"[+] {description}: OK")
            else:
                print(f"[-] {description}: FAILED (status: {response.status_code})")
                all_good = False
        except Exception as e:
            print(f"[-] {description}: ERROR - {e}")
            all_good = False
    
    print("="*40)
    if all_good:
        print("[*] BROWSE FUNCTIONALITY IS WORKING!")
        return True
    else:
        print("[!] BROWSE FUNCTIONALITY IS BROKEN!")
        print("This is the recurring problem that needs immediate attention.")
        return False

if __name__ == "__main__":
    success = check_browse_functionality()
    exit(0 if success else 1)