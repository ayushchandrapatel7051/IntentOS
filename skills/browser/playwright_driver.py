"""
OpenClaw Skill — Browser Control (Playwright + CDP)
=====================================================
Connects to Chrome via Chrome DevTools Protocol for full browser automation.
"""

import asyncio
import os
from typing import Optional
from pathlib import Path


class PlaywrightDriver:
    """
    Browser automation via Playwright connected to Chrome over CDP.
    
    Supports: navigation, search, form filling, clicking, text extraction,
    screenshots, tab management, Gmail, and Google Calendar automation.
    """

    def __init__(self):
        self.browser = None
        self.context = None
        self.page = None
        self._playwright = None

    async def connect(self, cdp_url: str = "http://localhost:9222"):
        """Connect to an existing Chrome instance via CDP."""
        try:
            from playwright.async_api import async_playwright
            self._playwright = await async_playwright().start()
            self.browser = await self._playwright.chromium.connect_over_cdp(cdp_url)
            contexts = self.browser.contexts
            if contexts:
                self.context = contexts[0]
                pages = self.context.pages
                if pages:
                    self.page = pages[0]
            if not self.context:
                self.context = await self.browser.new_context()
            if not self.page:
                self.page = await self.context.new_page()
        except Exception as e:
            raise ConnectionError(f"Failed to connect to Chrome CDP at {cdp_url}: {e}")

    async def launch(self, headless: bool = False):
        """Launch a new Chrome instance (fallback when CDP is unavailable)."""
        from playwright.async_api import async_playwright
        self._playwright = await async_playwright().start()
        self.browser = await self._playwright.chromium.launch(headless=headless)
        self.context = await self.browser.new_context()
        self.page = await self.context.new_page()

    async def close(self):
        """Close the browser connection."""
        if self.browser:
            await self.browser.close()
        if self._playwright:
            await self._playwright.stop()

    # --- Core Actions ---

    async def execute(self, action: str, params: dict) -> str:
        """Dispatch an action by name."""
        actions = {
            "navigate": self.navigate,
            "search": self.search,
            "fill_form": self.fill_form,
            "click": self.click,
            "extract_text": self.extract_text,
            "screenshot": self.take_screenshot,
            "manage_tabs": self.manage_tabs,
            "type_text": self.type_text,
            "wait_for": self.wait_for_selector,
            "evaluate": self.evaluate_js,
        }

        handler = actions.get(action)
        if not handler:
            raise ValueError(f"Unknown browser action: {action}")

        if not self.page:
            # Auto-launch if not connected
            await self.launch()

        return await handler(**params)

    async def navigate(self, url: str, wait_until: str = "domcontentloaded") -> str:
        """Navigate to a URL."""
        await self.page.goto(url, wait_until=wait_until)
        return f"Navigated to {url}"

    async def search(self, query: str, engine: str = "google") -> str:
        """Perform a web search."""
        engines = {
            "google": f"https://www.google.com/search?q={query}",
            "bing": f"https://www.bing.com/search?q={query}",
            "duckduckgo": f"https://duckduckgo.com/?q={query}",
        }
        url = engines.get(engine, engines["google"])
        await self.page.goto(url, wait_until="domcontentloaded")
        await self.page.wait_for_timeout(2000)

        # Extract search result titles and URLs
        results = await self.page.evaluate("""
            () => {
                const items = document.querySelectorAll('div.g, li.b_algo');
                return Array.from(items).slice(0, 5).map(item => {
                    const link = item.querySelector('a');
                    const title = item.querySelector('h3');
                    return {
                        title: title ? title.textContent : '',
                        url: link ? link.href : ''
                    };
                });
            }
        """)
        return f"Search results for '{query}': {results}"

    async def fill_form(self, selector: str, value: str, **kwargs) -> str:
        """Fill a form field."""
        await self.page.fill(selector, value)
        return f"Filled '{selector}' with value"

    async def click(self, selector: str, **kwargs) -> str:
        """Click an element."""
        await self.page.click(selector)
        return f"Clicked '{selector}'"

    async def type_text(self, selector: str, text: str, delay: int = 50, **kwargs) -> str:
        """Type text into an element with human-like delay."""
        await self.page.type(selector, text, delay=delay)
        return f"Typed text into '{selector}'"

    async def extract_text(self, selector: str = "body", **kwargs) -> str:
        """Extract text content from an element."""
        text = await self.page.inner_text(selector)
        # Truncate long text
        if len(text) > 5000:
            text = text[:5000] + "... (truncated)"
        return text

    async def take_screenshot(self, path: str = "", full_page: bool = False, **kwargs) -> str:
        """Take a screenshot of the current page."""
        if not path:
            screenshots_dir = os.getenv("SCREENSHOTS_PATH", "./screenshots")
            os.makedirs(screenshots_dir, exist_ok=True)
            from datetime import datetime
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            path = os.path.join(screenshots_dir, f"browser_{timestamp}.png")

        await self.page.screenshot(path=path, full_page=full_page)
        return f"Screenshot saved to {path}"

    async def manage_tabs(self, operation: str, tab_index: int = 0, url: str = "", **kwargs) -> str:
        """Manage browser tabs."""
        pages = self.context.pages

        if operation == "list":
            tabs = [{"index": i, "url": p.url, "title": await p.title()} for i, p in enumerate(pages)]
            return f"Open tabs: {tabs}"

        elif operation == "switch":
            if 0 <= tab_index < len(pages):
                self.page = pages[tab_index]
                await self.page.bring_to_front()
                return f"Switched to tab {tab_index}"
            return f"Invalid tab index: {tab_index}"

        elif operation == "new":
            self.page = await self.context.new_page()
            if url:
                await self.page.goto(url)
            return f"Opened new tab"

        elif operation == "close":
            if 0 <= tab_index < len(pages):
                await pages[tab_index].close()
                if pages:
                    self.page = self.context.pages[0] if self.context.pages else None
                return f"Closed tab {tab_index}"
            return f"Invalid tab index: {tab_index}"

        return f"Unknown tab operation: {operation}"

    async def wait_for_selector(self, selector: str, timeout: int = 30000, **kwargs) -> str:
        """Wait for an element to appear on the page."""
        await self.page.wait_for_selector(selector, timeout=timeout)
        return f"Element '{selector}' is now visible"

    async def evaluate_js(self, code: str, **kwargs) -> str:
        """Execute JavaScript in the page context."""
        result = await self.page.evaluate(code)
        return str(result)
