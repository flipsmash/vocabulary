#!/usr/bin/env python3
"""
Quick check of homepage structure to understand navigation
"""

from playwright.sync_api import sync_playwright

def check_homepage():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        page = browser.new_page()

        try:
            print("🌐 Navigating to homepage...")
            page.goto("http://localhost:8001")
            page.wait_for_load_state("networkidle")

            # Take screenshot
            page.screenshot(path=".playwright-mcp/homepage-structure.png")

            # Get page title
            print(f"📄 Page title: {page.title()}")

            # Get all links
            links = page.query_selector_all("a")
            print(f"🔗 Found {len(links)} links:")
            for i, link in enumerate(links[:10]):  # Show first 10 links
                text = link.inner_text().strip()
                href = link.get_attribute("href") or ""
                print(f"   {i+1}. '{text}' -> {href}")

            # Look for buttons
            buttons = page.query_selector_all("button")
            print(f"🔘 Found {len(buttons)} buttons:")
            for i, button in enumerate(buttons[:10]):
                text = button.inner_text().strip()
                print(f"   {i+1}. '{text}'")

            # Check for login-related elements
            login_elements = page.query_selector_all("*:has-text('login'), *:has-text('Login'), *:has-text('LOGIN')")
            print(f"🔐 Found {len(login_elements)} login-related elements:")
            for elem in login_elements:
                print(f"   - {elem.tag_name}: '{elem.inner_text().strip()}'")

        except Exception as e:
            print(f"❌ Error: {e}")
            page.screenshot(path=".playwright-mcp/homepage-error.png")

        finally:
            browser.close()

if __name__ == "__main__":
    check_homepage()