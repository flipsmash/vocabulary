#!/usr/bin/env python3
"""
Manual test - opens browser and waits for manual interaction to test matching
"""

import asyncio
from playwright.async_api import async_playwright

async def manual_test():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        page = await browser.new_page()

        # Console logging
        console_messages = []
        page.on("console", lambda msg: console_messages.append(f"[{msg.type}] {msg.text}"))

        try:
            # Auto-login
            print("Auto-logging in...")
            await page.goto("http://localhost:8001/login")
            await page.fill('input[name="username"]', "quiz_test_admin")
            await page.fill('input[name="password"]', "quiz_test_123")
            await page.click('button[type="submit"]')
            await page.wait_for_url("http://localhost:8001/")

            # Go to quiz
            await page.click('a[href="/quiz"]')
            await page.wait_for_load_state("networkidle")

            print("\n" + "="*60)
            print("MANUAL TESTING INSTRUCTIONS:")
            print("="*60)
            print("1. Click 'Start Quiz' to begin")
            print("2. Answer non-matching questions to advance through the quiz")
            print("3. When you find a MATCHING question:")
            print("   a. Complete the matching by dragging definitions to terms")
            print("   b. Click the 'Next' button")
            print("   c. Watch the console below for JavaScript errors")
            print("4. Look for 'showMatchingFeedback is not defined' errors")
            print("5. When done, close the browser window")
            print("="*60)
            print("\nConsole messages will appear below:")
            print("-" * 40)

            # Monitor console and print messages in real-time
            last_message_count = 0
            while True:
                await asyncio.sleep(1)

                # Print new console messages
                if len(console_messages) > last_message_count:
                    for msg in console_messages[last_message_count:]:
                        if "showMatchingFeedback is not defined" in msg:
                            print(f"🚨 CRITICAL ERROR: {msg}")
                        elif "error" in msg.lower():
                            print(f"❌ ERROR: {msg}")
                        else:
                            print(f"ℹ️  {msg}")
                    last_message_count = len(console_messages)

        except Exception as e:
            print(f"Error: {e}")

        finally:
            print("\nBrowser session ended.")
            print("\nFINAL CONSOLE ANALYSIS:")
            print("="*40)

            showMatchingFeedback_errors = [msg for msg in console_messages
                                         if "showMatchingFeedback is not defined" in msg]

            if showMatchingFeedback_errors:
                print("❌ FAILURE: showMatchingFeedback errors detected!")
                for error in showMatchingFeedback_errors:
                    print(f"   {error}")
            else:
                print("✅ SUCCESS: No showMatchingFeedback errors detected!")

            print(f"\nTotal console messages: {len(console_messages)}")

if __name__ == "__main__":
    asyncio.run(manual_test())