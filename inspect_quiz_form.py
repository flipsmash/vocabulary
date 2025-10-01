#!/usr/bin/env python3
"""
Inspect the quiz form to understand the correct selectors
"""
import asyncio
from playwright.async_api import async_playwright
import os

async def inspect_quiz_form():
    """Inspect quiz form structure"""
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context()
        page = await context.new_page()

        try:
            print("🌐 Navigating and logging in...")
            await page.goto("http://localhost:8001")
            await page.click("a[href='/login']")
            await page.fill("input[name='username']", "test_admin") 
            await page.fill("input[name='password']", "test123")
            await page.click("button[type='submit']")
            await page.wait_for_load_state("networkidle")

            print("📋 Going to quiz page...")
            await page.click("a[href='/quiz']")
            await page.wait_for_load_state("networkidle")

            print("📸 Taking quiz setup screenshot...")
            await page.screenshot(path="/mnt/c/Users/Brian/vocabulary/.playwright-mcp/quiz-setup-inspect.png")

            # Get page HTML to analyze form structure
            print("🔍 Analyzing form structure...")
            page_content = await page.content()
            
            # Save HTML for inspection
            with open("/mnt/c/Users/Brian/vocabulary/.playwright-mcp/quiz-page-source.html", "w") as f:
                f.write(page_content)
            
            # Find all form elements
            form_elements = await page.query_selector_all("form input, form select, form button")
            print(f"Found {len(form_elements)} form elements:")
            
            for i, elem in enumerate(form_elements):
                tag = await elem.get_attribute("tagName")
                name = await elem.get_attribute("name")
                type_attr = await elem.get_attribute("type")
                id_attr = await elem.get_attribute("id")
                print(f"  {i+1}. {tag} name='{name}' type='{type_attr}' id='{id_attr}'")

            # Check for select options specifically
            select_elements = await page.query_selector_all("select")
            for i, select in enumerate(select_elements):
                name = await select.get_attribute("name")
                print(f"Select {i+1} name='{name}':")
                options = await select.query_selector_all("option")
                for j, option in enumerate(options):
                    value = await option.get_attribute("value")
                    text = await option.inner_text()
                    print(f"    {j+1}. value='{value}' text='{text}'")

        except Exception as e:
            print(f"❌ Error: {e}")

        finally:
            await browser.close()

if __name__ == "__main__":
    os.makedirs("/mnt/c/Users/Brian/vocabulary/.playwright-mcp", exist_ok=True)
    asyncio.run(inspect_quiz_form())
