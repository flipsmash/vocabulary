#!/usr/bin/env python3
"""
Test script for matching quiz functionality using Playwright
Tests drag and drop behavior and identifies specific issues
"""

import asyncio
import time
from playwright.async_api import async_playwright
import os

async def test_matching_quiz():
    async with async_playwright() as p:
        # Launch browser in headless mode for WSL compatibility
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(viewport={'width': 1920, 'height': 1080})
        page = await context.new_page()

        print("1. Navigating to vocabulary web app...")
        await page.goto('http://localhost:8001')
        await page.screenshot(path='.playwright-mcp/01-homepage.png')
        print("   ✓ Homepage loaded")

        # Update todo
        print("\n2. Logging in with test_admin credentials...")

        # Look for login link
        login_link = page.locator('a[href="/login"]')
        if await login_link.count() > 0:
            await login_link.click()
            await page.wait_for_load_state('networkidle')
            await page.screenshot(path='.playwright-mcp/02-login-page.png')

            # Fill login form
            await page.fill('input[name="username"]', 'test_admin')
            await page.fill('input[name="password"]', 'test123')
            await page.screenshot(path='.playwright-mcp/03-login-filled.png')

            # Submit login
            await page.click('button[type="submit"]')
            await page.wait_for_load_state('networkidle')
            await page.screenshot(path='.playwright-mcp/04-after-login.png')
            print("   ✓ Login completed")
        else:
            print("   ⚠ Already logged in or no login required")

        print("\n3. Navigating to quiz section...")

        # Look for quiz navigation
        quiz_links = await page.locator('a').all()
        quiz_found = False

        for link in quiz_links:
            text = await link.inner_text()
            if 'quiz' in text.lower() or 'test' in text.lower():
                print(f"   Found quiz link: {text}")
                await link.click()
                quiz_found = True
                break

        if not quiz_found:
            # Try direct navigation
            await page.goto('http://localhost:8001/quiz')

        await page.wait_for_load_state('networkidle')
        await page.screenshot(path='.playwright-mcp/05-quiz-page.png')
        print("   ✓ Quiz page loaded")

        print("\n4. Starting matching quiz...")

        # Look for matching quiz option
        matching_option = page.locator('input[value="matching"]')
        if await matching_option.count() > 0:
            await matching_option.check()
            await page.screenshot(path='.playwright-mcp/06-matching-selected.png')

            # Start quiz
            start_button = page.locator('button:has-text("Start Quiz")')
            if await start_button.count() > 0:
                await start_button.click()
                await page.wait_for_load_state('networkidle')
                await page.screenshot(path='.playwright-mcp/07-matching-quiz-started.png')
                print("   ✓ Matching quiz started")
            else:
                print("   ⚠ Start Quiz button not found")
        else:
            print("   ⚠ Matching option not found")

        print("\n5. Testing drag and drop behavior...")

        # Wait for quiz content to load
        await page.wait_for_timeout(2000)

        # Take detailed screenshot of the quiz interface
        await page.screenshot(path='.playwright-mcp/08-quiz-interface-detail.png')

        # Find definitions and terms
        definitions = await page.locator('.definition-item, .draggable-definition, [draggable="true"]').all()
        term_slots = await page.locator('.term-slot, .drop-zone, .term-item').all()

        print(f"   Found {len(definitions)} definitions and {len(term_slots)} term slots")

        if len(definitions) > 0 and len(term_slots) > 0:
            print("\n   Testing Issue 1: Do definitions disappear when dropped?")

            # Get initial state
            first_def = definitions[0]
            first_def_text = await first_def.inner_text()
            first_slot = term_slots[0]

            print(f"   Dragging definition: '{first_def_text[:50]}...'")

            # Perform drag and drop
            await first_def.drag_to(first_slot)
            await page.wait_for_timeout(1000)
            await page.screenshot(path='.playwright-mcp/09-after-first-drop.png')

            # Check if definition disappeared
            remaining_definitions = await page.locator('.definition-item, .draggable-definition, [draggable="true"]').all()
            print(f"   Definitions before drop: {len(definitions)}, after drop: {len(remaining_definitions)}")

            if len(remaining_definitions) < len(definitions):
                print("   ❌ ISSUE 1 CONFIRMED: Definition disappeared after drop!")
            else:
                print("   ✅ Issue 1 not found: Definition still visible")

            print("\n   Testing Issue 2: Does placeholder text disappear?")

            # Check placeholder text in the slot where we dropped
            slot_text = await first_slot.inner_text()
            print(f"   Slot text after drop: '{slot_text}'")

            if "Click definition first" in slot_text:
                print("   ❌ ISSUE 2 CONFIRMED: Placeholder text still visible!")
            else:
                print("   ✅ Issue 2 not found: Placeholder text properly replaced")

            print("\n   Testing Issue 3: Can multiple definitions be dropped on one term?")

            if len(remaining_definitions) > 0:
                # Try dropping another definition on the same slot
                second_def = remaining_definitions[0]
                second_def_text = await second_def.inner_text()
                print(f"   Dropping second definition: '{second_def_text[:50]}...'")

                await second_def.drag_to(first_slot)
                await page.wait_for_timeout(1000)
                await page.screenshot(path='.playwright-mcp/10-multiple-drops-test.png')

                # Check slot content
                slot_text_after = await first_slot.inner_text()
                print(f"   Slot text after second drop: '{slot_text_after}'")

                if slot_text != slot_text_after:
                    print("   ❌ ISSUE 3 CONFIRMED: Multiple definitions can be dropped on one term!")
                else:
                    print("   ✅ Issue 3 not found: Second drop was properly rejected")

            print("\n   Testing Issue 4: Do definitions disappear when rearranging?")

            if len(term_slots) > 1:
                # Try to drag definition from first slot to second slot
                if len(remaining_definitions) > 0:
                    third_def = remaining_definitions[0] if len(remaining_definitions) > 0 else None
                    if third_def:
                        # First place a definition in second slot
                        second_slot = term_slots[1]
                        await third_def.drag_to(second_slot)
                        await page.wait_for_timeout(1000)
                        await page.screenshot(path='.playwright-mcp/11-second-slot-filled.png')

                        # Now try to move definition from first slot to second slot
                        # This requires finding the definition in the first slot
                        first_slot_def = page.locator(f'{first_slot} .definition-text, {first_slot} .placed-definition')
                        if await first_slot_def.count() > 0:
                            await first_slot_def.drag_to(second_slot)
                            await page.wait_for_timeout(1000)
                            await page.screenshot(path='.playwright-mcp/12-rearrange-test.png')

                            # Check if definition disappeared
                            first_slot_after = await first_slot.inner_text()
                            print(f"   First slot after rearrange: '{first_slot_after}'")

                            if "Click definition first" in first_slot_after:
                                print("   ❌ ISSUE 4 CONFIRMED: Definition disappeared during rearrange!")
                            else:
                                print("   ✅ Issue 4 not found: Rearrange worked properly")

        else:
            print("   ⚠ Could not find definitions or term slots to test")

        print("\n6. Taking final screenshots...")
        await page.screenshot(path='.playwright-mcp/13-final-state.png')

        # Get page HTML for debugging
        html_content = await page.content()
        with open('.playwright-mcp/quiz-page-source.html', 'w') as f:
            f.write(html_content)

        print("\n✓ Testing completed! Check .playwright-mcp/ directory for screenshots")

        # Brief pause before closing
        await page.wait_for_timeout(2000)

        await browser.close()

if __name__ == "__main__":
    # Create screenshots directory
    os.makedirs('.playwright-mcp', exist_ok=True)

    # Run the test
    asyncio.run(test_matching_quiz())