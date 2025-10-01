#!/usr/bin/env python3
"""
Simple login test to verify credentials work
"""

import asyncio
from playwright.async_api import async_playwright

async def test_login():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        page = await browser.new_page()

        try:
            print("Navigating to login page...")
            await page.goto("http://localhost:8001/login")
            await page.screenshot(path=".playwright-mcp/simple-login-before.png")

            print("Filling login form...")
            await page.fill('input[name="username"]', "quiz_test_admin")
            await page.fill('input[name="password"]', "quiz_test_123")
            await page.screenshot(path=".playwright-mcp/simple-login-filled.png")

            print("Submitting form...")
            await page.click('button[type="submit"]')

            # Wait a moment for redirect
            await page.wait_for_timeout(3000)

            current_url = page.url
            print(f"Current URL after login: {current_url}")

            await page.screenshot(path=".playwright-mcp/simple-login-after.png")

            # Check if we're logged in by looking for user-specific content
            page_content = await page.content()
            if "Could not validate credentials" in page_content:
                print("❌ Login failed - invalid credentials")
            elif "/login" in current_url:
                print("❌ Still on login page")
            else:
                print("✅ Login successful!")

        except Exception as e:
            print(f"Error: {e}")
            await page.screenshot(path=".playwright-mcp/simple-login-error.png")

        # Keep browser open for inspection
        await asyncio.sleep(10)
        await browser.close()

if __name__ == "__main__":
    asyncio.run(test_login())