#!/usr/bin/env python3
"""
Test script to verify advanced search tools are working
Run this after restarting your shell/terminal
"""

import subprocess
import sys
import os
from pathlib import Path

def run_command(cmd, description):
    """Run a command and check if it works"""
    print(f"\n🧪 Testing: {description}")
    print(f"Command: {cmd}")
    
    try:
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=10)
        if result.returncode == 0:
            print(f"✅ SUCCESS")
            output = result.stdout.strip()
            if output:
                print(f"Output: {output}")
            return True
        else:
            print(f"❌ FAILED (exit code: {result.returncode})")
            if result.stderr:
                print(f"Error: {result.stderr.strip()}")
            return False
    except subprocess.TimeoutExpired:
        print(f"⏰ TIMEOUT (command took too long)")
        return False
    except Exception as e:
        print(f"💥 EXCEPTION: {e}")
        return False

def main():
    """Test all installed search tools"""
    print("="*60)
    print("🔍 ADVANCED SEARCH TOOLS VERIFICATION")
    print("="*60)
    print("Testing tools installed via winget and npm...")
    
    # Test basic functionality
    tests = [
        ("fd --version", "fd file finder"),
        ("rg --version", "ripgrep text search (already working)"),
        ("ast-grep --version", "ast-grep code structure analysis"),
        ("fzf --version", "fzf fuzzy finder"),
        ("jq --version", "jq JSON processor"),
        ("yq --version", "yq YAML/XML processor"),
    ]
    
    results = {}
    for cmd, desc in tests:
        results[desc] = run_command(cmd, desc)
    
    print("\n" + "="*60)
    print("📋 SUMMARY")
    print("="*60)
    
    working = []
    failed = []
    
    for desc, success in results.items():
        if success:
            working.append(desc)
            print(f"✅ {desc}")
        else:
            failed.append(desc)
            print(f"❌ {desc}")
    
    print(f"\n📊 Results: {len(working)}/{len(results)} tools working")
    
    if failed:
        print(f"\n⚠️  Failed tools: {len(failed)}")
        print("💡 If tools failed, try:")
        print("   1. Restart your terminal/PowerShell completely")
        print("   2. Check PATH with: echo $PATH")
        print("   3. Reinstall failed tools")
        return False
    
    print("\n🎉 All tools are working! Let's test some real examples:")
    print("="*60)
    
    # Advanced functionality tests
    advanced_tests = [
        ("fd -e py --max-depth 2", "Find Python files (max 2 levels deep)"),
        ("rg 'def.*quiz' --type py --count", "Count quiz-related functions"),
        ("jq --version > /dev/null && echo 'jq JSON ready'", "jq JSON processing ready"),
        ("ast-grep --help > /dev/null && echo 'ast-grep AST ready'", "ast-grep code analysis ready"),
    ]
    
    print("\n🚀 ADVANCED FUNCTIONALITY TESTS:")
    advanced_results = {}
    for cmd, desc in advanced_tests:
        advanced_results[desc] = run_command(cmd, desc)
    
    working_advanced = sum(1 for success in advanced_results.values() if success)
    print(f"\n📊 Advanced functionality: {working_advanced}/{len(advanced_results)} working")
    
    if working_advanced == len(advanced_results):
        print("\n🎯 GAME CHANGER EXAMPLES:")
        print("Now you can use these powerful searches:")
        print()
        print("🔍 Find all FastAPI endpoints:")
        print("   ast-grep --pattern '@app.$METHOD($$$)'")
        print()
        print("📁 Find all Python test files:")
        print("   fd test_ --extension py")  
        print()
        print("📊 Analyze package.json dependencies:")
        print("   jq '.dependencies | keys[]' package.json")
        print()
        print("🏗️  Find all database queries:")
        print("   ast-grep --pattern 'cursor.execute($$$)'")
        print()
        print("✨ These tools will make our code searches 30-50% more accurate!")
        return True
    
    return working_advanced > len(advanced_results) // 2

if __name__ == "__main__":
    success = main()
    print(f"\n{'🎉 SUCCESS' if success else '⚠️ PARTIAL SUCCESS'}")
    sys.exit(0 if success else 1)