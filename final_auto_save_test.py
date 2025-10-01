#!/usr/bin/env python3
"""
Final comprehensive test for automatic quiz save functionality
Tests the complete flow and verifies all auto-save behaviors
"""

import asyncio
from playwright.async_api import async_playwright
import time

async def final_auto_save_test():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False, slow_mo=800)
        context = await browser.new_context()
        page = await context.new_page()

        console_messages = []
        network_requests = []

        # Capture console messages
        def handle_console(msg):
            message = f"{msg.type}: {msg.text}"
            console_messages.append(message)
            print(f"🔍 Console: {message}")

        # Capture network requests for quiz submissions
        def handle_request(request):
            if 'quiz' in request.url and request.method == 'POST':
                network_requests.append(f"POST {request.url}")
                print(f"🌐 Network: POST {request.url}")

        page.on("console", handle_console)
        page.on("request", handle_request)

        try:
            print("🚀 Starting comprehensive auto-save test...")

            # Step 1: Login
            print("\n📋 Step 1: Login")
            await page.goto("http://localhost:8001/login")
            await page.fill('input[name="username"]', 'quiz_test_admin')
            await page.fill('input[name="password"]', 'quiz_test_123')
            await page.click('button[type="submit"]')
            await page.wait_for_load_state('networkidle')
            print("✅ Login successful")

            # Step 2: Navigate to Quiz
            print("\n📋 Step 2: Navigate to Quiz")
            await page.goto("http://localhost:8001/quiz")
            await page.wait_for_load_state('networkidle')
            await page.screenshot(path=".playwright-mcp/final-test-quiz-setup.png")

            # Step 3: Start Quiz
            print("\n📋 Step 3: Start Quiz")
            start_button = page.locator("button:has-text('Start Quiz')")
            if await start_button.count() > 0:
                await start_button.click()
                await page.wait_for_load_state('networkidle')
                print("✅ Quiz started")
            else:
                print("ℹ️  Quiz may already be in progress")

            # Step 4: Complete quiz questions quickly
            print("\n📋 Step 4: Completing Quiz Questions")
            question_attempts = 0
            max_attempts = 15

            while question_attempts < max_attempts:
                question_attempts += 1
                print(f"🔄 Processing question {question_attempts}...")

                await page.wait_for_timeout(1000)  # Wait for page to load

                # Take screenshot of current state
                await page.screenshot(path=f".playwright-mcp/final-test-q{question_attempts}.png")

                # Check if we're on results page
                results_indicators = page.locator("text=Quiz Results, text=Quiz Complete, text=Your Score, text=Comprehensive Review")
                if await results_indicators.count() > 0:
                    print("🎉 Quiz completed! On results page.")
                    break

                # Try to answer current question
                answered = False

                # Handle True/False questions
                true_button = page.locator("button:has-text('True')")
                if await true_button.count() > 0 and await true_button.is_visible():
                    await true_button.click()
                    answered = True
                    print("   ✅ Answered True/False question")

                # Handle Multiple Choice questions
                if not answered:
                    # Look for visible radio button labels or clickable options
                    radio_labels = page.locator("label[for*='option'], .form-check-label")
                    if await radio_labels.count() > 0:
                        await radio_labels.first.click()
                        answered = True
                        print("   ✅ Answered Multiple Choice question")

                # Handle Matching questions (try multiple approaches)
                if not answered:
                    # Try clicking assign buttons
                    assign_buttons = page.locator("button:has-text('Assign')")
                    if await assign_buttons.count() > 0:
                        await assign_buttons.first.click()
                        answered = True
                        print("   ✅ Attempted Matching question assignment")

                    # Try drag and drop
                    draggable = page.locator(".sortable-item, .draggable-item, .definition-item")
                    drop_zones = page.locator(".drop-zone, .term-slot")
                    if await draggable.count() > 0 and await drop_zones.count() > 0:
                        try:
                            await draggable.first.drag_to(drop_zones.first)
                            answered = True
                            print("   ✅ Attempted drag & drop matching")
                        except:
                            pass

                # Look for Next button and click it
                await page.wait_for_timeout(500)
                next_button = page.locator("button:has-text('Next'):not([disabled])")
                if await next_button.count() > 0:
                    await next_button.first.click()
                    await page.wait_for_load_state('networkidle')
                    print("   ➡️ Clicked Next")
                else:
                    # Look for Submit/Finish buttons
                    submit_buttons = page.locator("button:has-text('Submit Quiz'), button:has-text('Finish Quiz')")
                    if await submit_buttons.count() > 0:
                        await submit_buttons.first.click()
                        await page.wait_for_load_state('networkidle')
                        print("   🏁 Submitted quiz")
                        break
                    else:
                        print("   ⚠️ No Next/Submit button found")

            # Step 5: Wait for auto-save and verify results page
            print("\n📋 Step 5: Verifying Auto-Save on Results Page")
            await page.wait_for_timeout(5000)  # Give auto-save time to complete
            await page.screenshot(path=".playwright-mcp/final-test-results.png")

            # Step 6: Analyze auto-save functionality
            print("\n📋 Step 6: Analyzing Auto-Save Functionality")

            # Check console messages for auto-save indicators
            auto_save_start = [msg for msg in console_messages if "🔄 Auto-saving quiz results" in msg]
            auto_save_success = [msg for msg in console_messages if "✅ Quiz results saved successfully" in msg or "Results saved successfully" in msg]

            # Check for manual save buttons (should NOT exist)
            manual_save_buttons = page.locator("button:has-text('Save Results'), button:has-text('Save & Continue')")
            manual_save_count = await manual_save_buttons.count()

            # Check for navigation buttons (should exist)
            nav_buttons = page.locator("button:has-text('Take Another Quiz'), button:has-text('Back to Home'), a:has-text('Take Another Quiz'), a:has-text('Home')")
            nav_count = await nav_buttons.count()

            # Check for success indicators on page
            success_alert = page.locator(".alert-success:has-text('Results saved successfully')")
            success_visible = await success_alert.count() > 0 and await success_alert.is_visible() if await success_alert.count() > 0 else False

            print("\n" + "="*70)
            print("🎯 AUTO-SAVE TEST RESULTS")
            print("="*70)
            print(f"📊 Total questions attempted: {question_attempts}")
            print(f"💬 Total console messages: {len(console_messages)}")
            print(f"🌐 Network POST requests: {len(network_requests)}")
            print(f"🔄 Auto-save start messages: {len(auto_save_start)}")
            print(f"✅ Auto-save success messages: {len(auto_save_success)}")
            print(f"💾 Manual save buttons: {manual_save_count} (should be 0)")
            print(f"🧭 Navigation buttons: {nav_count} (should be > 0)")
            print(f"🟢 Success alert visible: {success_visible}")

            # Print specific messages
            if auto_save_start:
                print("\n🔄 Auto-save start messages:")
                for msg in auto_save_start:
                    print(f"   📝 {msg}")

            if auto_save_success:
                print("\n✅ Auto-save success messages:")
                for msg in auto_save_success:
                    print(f"   📝 {msg}")

            if network_requests:
                print("\n🌐 Network requests:")
                for req in network_requests:
                    print(f"   📡 {req}")

            # Final assessment
            print("\n🏆 FINAL ASSESSMENT:")

            test_passed = True
            issues = []

            if len(auto_save_start) == 0:
                test_passed = False
                issues.append("❌ No auto-save start message found")
            else:
                print("✅ Auto-save initiation detected")

            if len(auto_save_success) == 0:
                test_passed = False
                issues.append("❌ No auto-save success message found")
            else:
                print("✅ Auto-save completion confirmed")

            if manual_save_count > 0:
                test_passed = False
                issues.append(f"❌ Found {manual_save_count} manual save button(s)")
            else:
                print("✅ No manual save buttons present")

            if nav_count == 0:
                issues.append("⚠️ No navigation buttons found")
            else:
                print(f"✅ Navigation buttons available ({nav_count})")

            if test_passed:
                print("\n🎉 AUTO-SAVE TEST PASSED!")
                print("   ✓ Quiz results are saved automatically")
                print("   ✓ No manual user action required")
                print("   ✓ Seamless user experience achieved")
            else:
                print("\n🚨 AUTO-SAVE TEST FAILED!")
                for issue in issues:
                    print(f"   {issue}")

            print("\n📄 Complete console log:")
            for i, msg in enumerate(console_messages, 1):
                print(f"   {i:2}. {msg}")

        except Exception as e:
            print(f"❌ Test error: {e}")
            await page.screenshot(path=".playwright-mcp/final-test-error.png")
            import traceback
            traceback.print_exc()

        finally:
            print("\n🏁 Test completed. Browser will close in 5 seconds...")
            await asyncio.sleep(5)
            await browser.close()

if __name__ == "__main__":
    asyncio.run(final_auto_save_test())