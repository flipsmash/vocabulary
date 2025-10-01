#!/usr/bin/env python3
"""
Check quiz page structure to understand how to start a quiz
"""

from playwright.sync_api import sync_playwright

def check_quiz_page():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        page = browser.new_page()

        try:
            print("🌐 Navigating to homepage...")
            page.goto("http://localhost:8001")

            print("🔐 Going to login...")
            page.click("text=Sign In")
            page.fill('input[name="username"]', "quiz_test_admin")
            page.fill('input[name="password"]', "quiz_test_123")
            page.click('button[type="submit"]')
            page.wait_for_load_state("networkidle")

            print("🧠 Going to quiz page...")
            # Check what navigation options are available
            links = page.query_selector_all("a")
            print("🔗 Available links:")
            for link in links:
                text = link.inner_text().strip()
                href = link.get_attribute("href") or ""
                print(f"   - '{text}' -> {href}")

            # Try clicking on Quiz if it exists
            quiz_link = page.query_selector('a[href*="quiz"], a:has-text("Quiz"), a:has-text("quiz")')
            if quiz_link:
                print("✓ Found quiz link, clicking...")
                quiz_link.click()
                page.wait_for_load_state("networkidle")
            else:
                print("❓ No quiz link found, trying direct navigation...")
                page.goto("http://localhost:8001/quiz")

            page.screenshot(path=".playwright-mcp/quiz-page-check.png")

            # Check what's on the quiz page
            print(f"📄 Quiz page title: {page.title()}")

            # Look for buttons
            buttons = page.query_selector_all("button")
            print(f"🔘 Buttons on quiz page ({len(buttons)}):")
            for button in buttons:
                text = button.inner_text().strip()
                disabled = button.get_attribute("disabled")
                print(f"   - '{text}' (disabled: {disabled is not None})")

            # Look for forms
            forms = page.query_selector_all("form")
            print(f"📝 Forms found: {len(forms)}")

            # Look for quiz-related elements
            quiz_elements = page.query_selector_all('*[class*="quiz"], *[id*="quiz"]')
            print(f"🎯 Quiz elements found: {len(quiz_elements)}")
            for elem in quiz_elements[:5]:
                classes = elem.get_attribute("class") or ""
                elem_id = elem.get_attribute("id") or ""
                text = elem.inner_text().strip()[:50]
                print(f"   - {elem.tag_name} class='{classes}' id='{elem_id}' text='{text}'")

        except Exception as e:
            print(f"❌ Error: {e}")
            page.screenshot(path=".playwright-mcp/quiz-page-error.png")

        finally:
            browser.close()

if __name__ == "__main__":
    check_quiz_page()