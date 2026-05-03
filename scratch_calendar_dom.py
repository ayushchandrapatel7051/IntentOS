import asyncio
from playwright.async_api import async_playwright

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context()
        page = await context.new_page()
        # Open Google Calendar event creation page
        await page.goto("https://calendar.google.com/calendar/render?action=TEMPLATE")
        
        # Wait a bit for the page to load
        await page.wait_for_timeout(5000)
        
        # Look for the meet button
        selectors = [
            '[data-id="videochat"]',
            '[aria-label*="Google Meet"]',
            '[aria-label*="video conferencing"]',
            '[data-tooltip*="Google Meet"]',
            'button[jsname*="meet"]'
        ]
        
        for sel in selectors:
            elements = await page.locator(sel).count()
            print(f"Selector {sel}: found {elements} elements")
            
        # Get all buttons to see what we can find
        buttons = await page.locator('button, [role="button"]').all_text_contents()
        meet_buttons = [b for b in buttons if 'meet' in b.lower() or 'video' in b.lower()]
        print(f"Buttons with 'meet' or 'video': {meet_buttons}")
        
        await browser.close()

asyncio.run(main())
