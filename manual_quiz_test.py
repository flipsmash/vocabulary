#!/usr/bin/env python3
"""
Manual quiz test - opens browser for manual interaction to test auto-save
"""

import asyncio
from playwright.async_api import async_playwright

async def manual_quiz_test():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False, slow_mo=1000)
        context = await browser.new_context()
        page = await context.new_page()

        console_messages = []

        # Capture all console messages
        def handle_console(msg):
            console_messages.append(f"{msg.type}: {msg.text}")
            print(f"🔍 Console: {msg.type}: {msg.text}")

        page.on("console", handle_console)

        # Capture network requests to see AJAX calls
        def handle_request(request):
            if 'quiz' in request.url and request.method == 'POST':
                print(f"🌐 Network POST: {request.url}")

        page.on("request", handle_request)

        try:
            print("🚀 Opening browser for manual quiz testing...")
            print("📋 Test Instructions:")
            print("1. Browser will open to login page")
            print("2. Login with: quiz_test_admin / quiz_test_123")
            print("3. Navigate to Quiz and complete a full quiz")
            print("4. Watch console messages for auto-save indicators")
            print("5. Check final results page for absence of Save button")
            print("6. Press Enter in this terminal when done testing")

            # Navigate to login
            await page.goto("http://localhost:8001/login")

            # Fill in credentials
            await page.fill('input[name="username"]', 'quiz_test_admin')
            await page.fill('input[name="password"]', 'quiz_test_123')

            print("✅ Credentials filled. Ready for manual testing.")
            print("👆 Click 'Sign In' button in the browser to continue...")

            # Wait for user to complete the test
            input("\n⏳ Press Enter after completing the quiz and reviewing the results page...")

            # Take final screenshot
            await page.screenshot(path=".playwright-mcp/manual-test-final.png")

            # Analyze results
            print("\n" + "="*60)
            print("🔍 MANUAL TEST ANALYSIS")
            print("="*60)

            print(f"📝 Total console messages captured: {len(console_messages)}")

            # Look for auto-save indicators
            auto_save_msgs = [msg for msg in console_messages if any(keyword in msg.lower() for keyword in ['auto-saving', 'results saved', 'saving quiz', 'submit quiz'])]

            print(f"🔄 Auto-save related messages: {len(auto_save_msgs)}")
            if auto_save_msgs:
                for msg in auto_save_msgs:
                    print(f"   ✅ {msg}")

            # Check current page for save buttons
            save_buttons = page.locator("button:has-text('Save Results'), button:has-text('Save & Continue'), button:has-text('Save Quiz')")
            save_count = await save_buttons.count()
            print(f"💾 Manual save buttons found: {save_count}")

            # Check for navigation buttons
            nav_buttons = page.locator("button:has-text('Take Another Quiz'), button:has-text('Back to Home'), a:has-text('Take Another Quiz'), a:has-text('Back to Home'), a:has-text('Home')")
            nav_count = await nav_buttons.count()
            print(f"🧭 Navigation buttons found: {nav_count}")

            print("\n📊 All captured console messages:")
            for i, msg in enumerate(console_messages, 1):
                print(f"   {i:2}. {msg}")

            # Final assessment
            print("\n🎯 AUTO-SAVE TEST ASSESSMENT:")
            if len(auto_save_msgs) > 0 and save_count == 0:
                print("✅ PASSED - Automatic saving appears to be working correctly")
                print("   - Auto-save console messages detected")
                print("   - No manual save buttons present")
            elif len(auto_save_msgs) > 0:
                print("⚠️  PARTIAL - Auto-save detected but manual save options still present")
            else:
                print("❌ NEEDS INVESTIGATION - No clear auto-save indicators found")

        except Exception as e:
            print(f"❌ Error during test: {e}")
            await page.screenshot(path=".playwright-mcp/manual-test-error.png")

        finally:
            print("\n🏁 Test completed. Browser will remain open for 10 seconds for final review...")
            await asyncio.sleep(10)
            await browser.close()

if __name__ == "__main__":
    asyncio.run(manual_quiz_test())