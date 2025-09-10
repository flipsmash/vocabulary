#!/usr/bin/env python3
"""
Comprehensive Endpoint Verification System
Ensures all navigation endpoints work properly and prevents regression of browse functionality.
"""

import requests
import json
from typing import Dict, List, Tuple, Optional
import time
from urllib.parse import urljoin

class EndpointVerifier:
    def __init__(self, base_url: str = "http://localhost:8000"):
        self.base_url = base_url
        self.session = requests.Session()
        self.test_results = []
        
    def verify_endpoint(self, path: str, method: str = "GET", 
                       expected_status: int = 200, 
                       expected_content: Optional[str] = None,
                       description: str = "") -> bool:
        """Verify a single endpoint works as expected"""
        url = urljoin(self.base_url, path)
        
        try:
            start_time = time.time()
            response = self.session.request(method, url, timeout=10)
            response_time = (time.time() - start_time) * 1000
            
            # Check status code
            status_ok = response.status_code == expected_status
            
            # Check content if specified
            content_ok = True
            if expected_content:
                content_ok = expected_content in response.text
            
            success = status_ok and content_ok
            
            result = {
                'path': path,
                'method': method,
                'status_code': response.status_code,
                'expected_status': expected_status,
                'response_time_ms': round(response_time, 2),
                'success': success,
                'description': description or f"{method} {path}",
                'content_length': len(response.text) if hasattr(response, 'text') else 0
            }
            
            if not status_ok:
                result['error'] = f"Expected status {expected_status}, got {response.status_code}"
            if expected_content and not content_ok:
                result['content_error'] = f"Expected content '{expected_content}' not found"
                
            self.test_results.append(result)
            return success
            
        except Exception as e:
            result = {
                'path': path,
                'method': method,
                'success': False,
                'description': description or f"{method} {path}",
                'error': str(e),
                'response_time_ms': 0
            }
            self.test_results.append(result)
            return False
    
    def verify_all_endpoints(self) -> Dict[str, int]:
        """Verify all critical navigation endpoints"""
        print("[*] Starting comprehensive endpoint verification...")
        print(f"Base URL: {self.base_url}")
        print("-" * 60)
        
        # Core navigation endpoints
        endpoints = [
            # Home and basic pages
            ('/', 'GET', 200, 'Vocabulary Learning', 'Home page'),
            ('/login', 'GET', 200, 'Login', 'Login page'),
            ('/register', 'GET', 200, 'Register', 'Registration page'),
            
            # Browse functionality (critical - this was the recurring problem)
            ('/browse', 'GET', 200, 'Browse Vocabulary', 'Browse main page'),
            ('/browse?page=1', 'GET', 200, 'Browse Vocabulary', 'Browse page 1'),
            ('/browse?page=2', 'GET', 200, 'Browse Vocabulary', 'Browse page 2'),
            ('/browse?per_page=25', 'GET', 200, 'Browse Vocabulary', 'Browse with 25 per page'),
            ('/browse?per_page=100', 'GET', 200, 'Browse Vocabulary', 'Browse with 100 per page'),
            ('/browse?letters=a', 'GET', 200, 'Browse Vocabulary', 'Browse words starting with A'),
            ('/browse?letters=ab', 'GET', 200, 'Browse Vocabulary', 'Browse words starting with AB'),
            
            # Search functionality
            ('/search', 'GET', 200, 'Search', 'Search page'),
            ('/search?q=test', 'GET', 200, 'Search Results', 'Search with query'),
            
            # Random word
            ('/random', 'GET', 200, None, 'Random word (may redirect)'),
            
            # Quiz endpoints (should redirect to login for unauthenticated users)
            ('/quiz', 'GET', 302, None, 'Quiz home (should redirect to login)'),
            
            # Word detail pages (test a few IDs)
            ('/word/1', 'GET', 200, None, 'Word detail page ID 1'),
            ('/word/100', 'GET', 200, None, 'Word detail page ID 100'),
            ('/word/1000', 'GET', 200, None, 'Word detail page ID 1000'),
            
            # API endpoints
            ('/api/stats', 'GET', 200, None, 'API stats endpoint'),
        ]
        
        passed = 0
        failed = 0
        
        for endpoint_data in endpoints:
            path = endpoint_data[0]
            method = endpoint_data[1] 
            expected_status = endpoint_data[2]
            expected_content = endpoint_data[3]
            description = endpoint_data[4]
            
            print(f"Testing: {description}")
            success = self.verify_endpoint(path, method, expected_status, expected_content, description)
            
            if success:
                print(f"  [+] PASS")
                passed += 1
            else:
                print(f"  [-] FAIL")
                failed += 1
        
        print("-" * 60)
        print(f"Results: {passed} passed, {failed} failed")
        
        return {'passed': passed, 'failed': failed, 'total': len(endpoints)}
    
    def verify_browse_functionality_specifically(self) -> bool:
        """Specific verification for browse functionality that keeps breaking"""
        print("\n[*] Specific Browse Functionality Verification:")
        print("-" * 50)
        
        critical_browse_tests = [
            ('/browse', 'Browse main page loads'),
            ('/browse?page=1', 'First page pagination works'),
            ('/browse?letters=a', 'Letter filtering works'),
            ('/browse?per_page=25', 'Per-page control works'),
            ('/browse?domain=general', 'Domain filtering works (if domain exists)'),
        ]
        
        all_passed = True
        for path, description in critical_browse_tests:
            print(f"  Testing: {description}")
            success = self.verify_endpoint(path, expected_content="Browse Vocabulary", description=description)
            if success:
                print(f"    [+] PASS")
            else:
                print(f"    [-] FAIL - This is critical!")
                all_passed = False
        
        if all_passed:
            print("\n[*] All critical browse functionality is working!")
        else:
            print("\n[!] CRITICAL BROWSE ISSUES DETECTED!")
            print("This is the recurring problem that needs immediate attention.")
        
        return all_passed
    
    def generate_report(self) -> str:
        """Generate detailed test report"""
        if not self.test_results:
            return "No test results available."
        
        passed = sum(1 for r in self.test_results if r['success'])
        failed = len(self.test_results) - passed
        
        report = [
            "=" * 80,
            "VOCABULARY APP ENDPOINT VERIFICATION REPORT",
            "=" * 80,
            f"Test Date: {time.strftime('%Y-%m-%d %H:%M:%S')}",
            f"Base URL: {self.base_url}",
            f"Total Tests: {len(self.test_results)}",
            f"Passed: {passed}",
            f"Failed: {failed}",
            f"Success Rate: {(passed/len(self.test_results)*100):.1f}%",
            "",
        ]
        
        # Failed tests first (most important)
        if failed > 0:
            report.extend([
                "[-] FAILED TESTS:",
                "-" * 40,
            ])
            for result in self.test_results:
                if not result['success']:
                    report.append(f"FAIL: {result['description']}")
                    report.append(f"      Path: {result['path']}")
                    if 'error' in result:
                        report.append(f"      Error: {result['error']}")
                    if 'content_error' in result:
                        report.append(f"      Content Error: {result['content_error']}")
                    report.append("")
        
        # Passed tests summary
        report.extend([
            "[+] PASSED TESTS:",
            "-" * 40,
        ])
        for result in self.test_results:
            if result['success']:
                report.append(f"PASS: {result['description']} ({result['response_time_ms']}ms)")
        
        report.extend([
            "",
            "=" * 80,
        ])
        
        return "\n".join(report)
    
    def save_report(self, filename: str = "endpoint_verification_report.txt"):
        """Save report to file"""
        report = self.generate_report()
        with open(filename, 'w') as f:
            f.write(report)
        print(f"\n[*] Report saved to: {filename}")


def main():
    """Main verification function"""
    verifier = EndpointVerifier()
    
    # Run comprehensive verification
    results = verifier.verify_all_endpoints()
    
    # Specifically verify browse functionality 
    browse_ok = verifier.verify_browse_functionality_specifically()
    
    # Generate and save report
    verifier.save_report()
    
    # Print summary
    print("\n" + "="*60)
    print("FINAL SUMMARY")
    print("="*60)
    print(f"Total endpoint tests: {results['total']}")
    print(f"Passed: {results['passed']}")
    print(f"Failed: {results['failed']}")
    print(f"Browse functionality: {'[+] Working' if browse_ok else '[-] BROKEN'}")
    
    if results['failed'] == 0 and browse_ok:
        print("\n[*] ALL SYSTEMS OPERATIONAL!")
        print("Browse functionality regression should be prevented.")
        return True
    else:
        print(f"\n[!] {results['failed']} ISSUES DETECTED!")
        if not browse_ok:
            print("[!] CRITICAL: Browse functionality is broken!")
        print("Please fix these issues before deployment.")
        return False


if __name__ == "__main__":
    main()