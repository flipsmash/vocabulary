#!/usr/bin/env python3
"""
FINAL comprehensive test of Next button functionality.
This test targets the actual quiz interface elements correctly.
"""

from playwright.sync_api import sync_playwright
import time
import json

def test_next_button_final():
    """Test Next button functionality across all question types - FINAL VERSION"""

    results = {
        "multiple_choice": {"status": "not_tested", "errors": [], "details": [], "questions_tested": []},
        "true_false": {"status": "not_tested", "errors": [], "details": [], "questions_tested": []},
        "matching": {"status": "not_tested", "errors": [], "details": [], "questions_tested": []},
        "console_errors": []
    }

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False, args=["--no-sandbox"])
        context = browser.new_context()
        page = context.new_page()

        def handle_console(msg):
            if msg.type in ["error", "warning"]:
                results["console_errors"].append({
                    "type": msg.type,
                    "text": msg.text
                })

        page.on("console", handle_console)

        try:
            print("🚀 FINAL COMPREHENSIVE NEXT BUTTON TEST")
            print("=" * 60)

            # Setup quiz
            print("🌐 Setting up quiz session...")
            page.goto("http://localhost:8001")
            page.click("text=Sign In")
            page.fill('input[name="username"]', "quiz_test_admin")
            page.fill('input[name="password"]', "quiz_test_123")
            page.click('button[type="submit"]')
            page.wait_for_load_state("networkidle")

            page.click("text=Quiz")
            page.wait_for_load_state("networkidle")
            page.click('button:has-text("🚀 Start Quiz")')
            page.wait_for_load_state("networkidle")

            print("✅ Quiz session started successfully")
            page.screenshot(path=".playwright-mcp/final-test-quiz-started.png")

            questions_tested = 0
            max_questions = 10

            for question_num in range(1, max_questions + 1):
                print(f"\n📝 Testing Question #{question_num}")

                # Check if this question is currently visible
                question_card = page.query_selector(f'[data-question="{question_num}"]')
                if not question_card or not question_card.is_visible():
                    print(f"   ⏭️ Question {question_num} not visible, skipping")
                    continue

                questions_tested += 1

                # Determine question type by checking elements within this question
                is_multiple_choice = question_card.query_selector('input[type="radio"][value="0"]') is not None
                is_true_false = question_card.query_selector('input[type="radio"][value="true"]') is not None or question_card.query_selector('input[type="radio"][value="false"]') is not None
                is_matching = question_card.query_selector('.sortable') is not None

                question_type = "unknown"

                if is_multiple_choice:
                    question_type = "multiple_choice"
                    print("   📊 Multiple Choice Question detected")

                    # Find the label for the first option
                    first_option_label = question_card.query_selector('label[for*="option_"][for*="_0"]')
                    if first_option_label:
                        print("   🎯 Clicking first option label...")
                        first_option_label.click()
                        time.sleep(0.5)

                        # Check Next button status
                        next_button = page.query_selector('button:has-text("Next"):not([style*="display: none"])')
                        if next_button:
                            is_disabled = next_button.get_attribute("disabled") is not None
                            if not is_disabled:
                                print("   ✅ Next button enabled after selection")
                                results["multiple_choice"]["status"] = "working"
                                results["multiple_choice"]["details"].append(f"Q{question_num}: Next enabled")
                                results["multiple_choice"]["questions_tested"].append(question_num)
                            else:
                                print("   ❌ Next button still disabled")
                                results["multiple_choice"]["status"] = "failed"
                                results["multiple_choice"]["errors"].append(f"Q{question_num}: Next disabled after selection")
                        else:
                            print("   ❌ Next button not found")
                            results["multiple_choice"]["errors"].append(f"Q{question_num}: Next button missing")
                    else:
                        print("   ❌ Option label not found")
                        results["multiple_choice"]["errors"].append(f"Q{question_num}: Option label missing")

                elif is_true_false:
                    question_type = "true_false"
                    print("   ✅❌ True/False Question detected")

                    # Find the label for "true" option
                    true_option_label = question_card.query_selector('label[for*="true"], label[for*="True"]')
                    if not true_option_label:
                        # Try alternative approach - look for True button
                        true_option_label = question_card.query_selector('button:has-text("True")')

                    if true_option_label:
                        print("   🎯 Clicking True option...")
                        true_option_label.click()
                        time.sleep(0.5)

                        # Check Next button status
                        next_button = page.query_selector('button:has-text("Next"):not([style*="display: none"])')
                        if next_button:
                            is_disabled = next_button.get_attribute("disabled") is not None
                            if not is_disabled:
                                print("   ✅ Next button enabled after selection")
                                results["true_false"]["status"] = "working"
                                results["true_false"]["details"].append(f"Q{question_num}: Next enabled")
                                results["true_false"]["questions_tested"].append(question_num)
                            else:
                                print("   ❌ Next button still disabled")
                                results["true_false"]["status"] = "failed"
                                results["true_false"]["errors"].append(f"Q{question_num}: Next disabled after selection")
                        else:
                            print("   ❌ Next button not found")
                            results["true_false"]["errors"].append(f"Q{question_num}: Next button missing")
                    else:
                        print("   ❌ True option not found")
                        results["true_false"]["errors"].append(f"Q{question_num}: True option missing")

                elif is_matching:
                    question_type = "matching"
                    print("   🔗 Matching Question detected")

                    # For matching questions, we need to complete assignments
                    # Try to trigger the matching completion
                    try:
                        # Look for sortable elements within this question
                        sortable_lists = question_card.query_selector_all('.sortable')

                        if len(sortable_lists) >= 2:
                            # Try to move items between lists
                            source_items = sortable_lists[0].query_selector_all('li')
                            target_list = sortable_lists[1]

                            if source_items:
                                print(f"   🎯 Found {len(source_items)} items to match")

                                # Try to drag first item to target list
                                if source_items[0] and target_list:
                                    source_items[0].drag_to(target_list)
                                    time.sleep(1)

                                    # Check if this enabled Next button
                                    next_button = page.query_selector('button:has-text("Next"):not([style*="display: none"])')
                                    if next_button:
                                        is_disabled = next_button.get_attribute("disabled") is not None
                                        if not is_disabled:
                                            print("   ✅ Next button enabled after matching")
                                            results["matching"]["status"] = "working"
                                            results["matching"]["details"].append(f"Q{question_num}: Next enabled")
                                            results["matching"]["questions_tested"].append(question_num)
                                        else:
                                            print("   ⚠️ Next still disabled (may need more matches)")
                                            results["matching"]["status"] = "partial"
                                            results["matching"]["details"].append(f"Q{question_num}: Partial completion")
                                    else:
                                        print("   ❌ Next button not found")
                                        results["matching"]["errors"].append(f"Q{question_num}: Next button missing")
                            else:
                                print("   ❌ No matchable items found")
                                results["matching"]["errors"].append(f"Q{question_num}: No items to match")
                        else:
                            print("   ❌ Insufficient sortable lists")
                            results["matching"]["errors"].append(f"Q{question_num}: Insufficient lists")

                    except Exception as e:
                        print(f"   ⚠️ Error with matching: {e}")
                        results["matching"]["errors"].append(f"Q{question_num}: Drag error - {str(e)}")

                # Take screenshot of current state
                page.screenshot(path=f".playwright-mcp/final-test-q{question_num}-{question_type}.png")

                # Try to proceed to next question if Next button is enabled
                next_button = page.query_selector('button:has-text("Next"):not([style*="display: none"])')
                if next_button and next_button.get_attribute("disabled") is None:
                    print(f"   🔄 Proceeding to next question...")
                    next_button.click()
                    time.sleep(2)
                    page.wait_for_load_state("networkidle")

                    # Check if we completed the quiz
                    if "quiz/results" in page.url:
                        print("   ✅ Quiz completed!")
                        break
                else:
                    print(f"   ⛔ Cannot proceed - Next button disabled")
                    # Continue to test other question types that might be loaded

        except Exception as e:
            print(f"❌ Test exception: {e}")
            page.screenshot(path=".playwright-mcp/final-test-exception.png")

        finally:
            browser.close()

    return results

def print_results(results):
    """Print comprehensive test results"""

    print("\n" + "="*70)
    print("📊 FINAL TEST RESULTS")
    print("="*70)

    question_types = ["multiple_choice", "true_false", "matching"]

    for qtype in question_types:
        if qtype not in results:
            continue

        data = results[qtype]
        status = data.get("status", "not_tested")
        questions_tested = data.get("questions_tested", [])
        errors = data.get("errors", [])
        details = data.get("details", [])

        print(f"\n🎯 {qtype.replace('_', ' ').title()}:")

        if status == "working":
            print(f"   ✅ STATUS: WORKING CORRECTLY")
            print(f"   📊 Questions tested: {len(questions_tested)} {questions_tested}")
        elif status == "failed":
            print(f"   ❌ STATUS: FAILED")
            print(f"   📊 Questions tested: {len(questions_tested)} {questions_tested}")
        elif status == "partial":
            print(f"   ⚠️  STATUS: PARTIAL SUCCESS")
            print(f"   📊 Questions tested: {len(questions_tested)} {questions_tested}")
        else:
            print(f"   ❓ STATUS: NOT TESTED")

        if details:
            print("   📝 Details:")
            for detail in details:
                print(f"      - {detail}")

        if errors:
            print("   ❌ Issues:")
            for error in errors:
                print(f"      - {error}")

    # Console errors summary
    console_errors = results.get("console_errors", [])
    if console_errors:
        print(f"\n🔍 Console Issues ({len(console_errors)}):")
        for error in console_errors[-5:]:  # Last 5 errors
            print(f"   {error['type']}: {error['text'][:100]}...")
    else:
        print(f"\n✅ No console errors detected")

    # Overall assessment
    working_count = sum(1 for qtype in question_types if results.get(qtype, {}).get("status") == "working")
    tested_count = sum(1 for qtype in question_types if results.get(qtype, {}).get("status") != "not_tested")

    print(f"\n📈 OVERALL ASSESSMENT:")
    print(f"   Question types tested: {tested_count}/3")
    print(f"   Working correctly: {working_count}")

    if working_count == tested_count and tested_count > 0:
        print(f"   🎉 RESULT: ALL TESTED TYPES ARE WORKING!")
    elif working_count > 0:
        print(f"   ✅ RESULT: SOME TYPES WORKING, SOME HAVE ISSUES")
    else:
        print(f"   ❌ RESULT: SIGNIFICANT ISSUES DETECTED")

if __name__ == "__main__":
    results = test_next_button_final()
    print_results(results)

    # Save results
    with open(".playwright-mcp/final-next-button-results.json", "w") as f:
        json.dump(results, f, indent=2)

    print(f"\n📁 Detailed results: .playwright-mcp/final-next-button-results.json")
    print(f"📸 Screenshots: .playwright-mcp/final-test-*.png")