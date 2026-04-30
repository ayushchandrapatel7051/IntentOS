"""
OpenClaw Skill — Browser Control (Playwright + Direct Launch)
=============================================================
Navigation strategy:
  - Simple navigate / search → open URL in the user's real browser via subprocess
    (this uses their existing profile/accounts — no new Playwright window)
  - Complex automation (fill_form, click, extract_text, evaluate) → Playwright headless/headed

Browser detection order per request:
  1. Honour explicit browser="chrome" / browser="edge" / browser="firefox" param
  2. Try CDP (if user started browser with --remote-debugging-port=9222)
  3. Launch the requested browser directly (subprocess for navigate, Playwright for automation)
"""

import asyncio
import os
import subprocess
from typing import Optional
from pathlib import Path
from datetime import datetime


# ---------------------------------------------------------------------------
# Browser executable detection
# ---------------------------------------------------------------------------

_BROWSER_PATHS = {
    "edge": [
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    ],
    "chrome": [
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        str(Path.home() / "AppData" / "Local" / "Google" / "Chrome" / "Application" / "chrome.exe"),
    ],
    "firefox": [
        r"C:\Program Files\Mozilla Firefox\firefox.exe",
        r"C:\Program Files (x86)\Mozilla Firefox\firefox.exe",
    ],
}


def _find_browser_exe(browser: str) -> Optional[str]:
    """Return the path to a browser executable, or None if not found."""
    browser = browser.lower().strip()
    candidates = _BROWSER_PATHS.get(browser, [])
    for path in candidates:
        if Path(path).exists():
            return path
    return None


def _open_url_in_browser(url: str, browser: str = "edge") -> str:
    """
    Open a URL in the user's real browser using subprocess.
    This preserves the user's existing profile and sessions.
    """
    exe = _find_browser_exe(browser)
    if exe:
        subprocess.Popen([exe, url], shell=False)
        return f"Opened {url} in {browser.title()}"

    # Fallback: system default browser
    import webbrowser
    webbrowser.open(url)
    return f"Opened {url} in system default browser ('{browser}' not found)"


# ---------------------------------------------------------------------------
# Playwright driver (for complex automation only)
# ---------------------------------------------------------------------------

class PlaywrightDriver:
    """
    Browser skill dispatcher.

    Simple actions (navigate, search) → open in user's real browser via subprocess.
    Complex actions (click, fill_form, extract_text, evaluate) → Playwright automation.

    Actions:
        navigate      — open a URL in the requested browser (real profile, no duplicate)
        search        — web search and optionally extract results
        fill_form     — fill a form field via Playwright
        click         — click a CSS selector via Playwright
        extract_text  — extract inner text via Playwright
        screenshot    — take a screenshot via Playwright
        manage_tabs   — list/switch/open/close tabs via Playwright
        type_text     — type text into the page via Playwright
        wait_for      — wait for a CSS selector via Playwright
        evaluate      — run JavaScript via Playwright
    """

    def __init__(self):
        self._pw_browser = None
        self._pw_context = None
        self._pw_page = None
        self._playwright = None
        self._connected_via = None  # "cdp" | "playwright"

    # ------------------------------------------------------------------
    # Simple actions — subprocess (user's real browser)
    # ------------------------------------------------------------------

    async def navigate(self, url: str, browser: str = "edge", **kwargs) -> str:
        """
        Open a URL in the user's real browser.
        Preserves existing profile and sessions — no duplicate window.
        """
        result = await asyncio.to_thread(_open_url_in_browser, url, browser)
        return result

    async def search(self, query: str, engine: str = "google", browser: str = "edge", **kwargs) -> str:
        """Open a web search in the user's browser."""
        engines = {
            "google":     f"https://www.google.com/search?q={query}",
            "bing":       f"https://www.bing.com/search?q={query}",
            "duckduckgo": f"https://duckduckgo.com/?q={query}",
        }
        url = engines.get(engine.lower(), engines["google"])
        result = await asyncio.to_thread(_open_url_in_browser, url, browser)
        return f"Searched '{query}' — {result}"

    # ------------------------------------------------------------------
    # Complex actions — Playwright (automation)
    # ------------------------------------------------------------------

    async def _ensure_playwright(self, browser: str = "edge"):
        """Ensure a Playwright browser page is available for automation."""
        if self._pw_page:
            return

        # 1. Try CDP (user-started browser with --remote-debugging-port=9222)
        cdp_url = os.getenv("BROWSER_CDP_URL", "http://localhost:9222")
        try:
            await self._connect_cdp(cdp_url)
            return
        except Exception:
            pass

        # 2. Launch the correct browser via Playwright
        await self._launch_playwright(browser)

    async def _connect_cdp(self, cdp_url: str):
        """Connect to an existing browser via CDP."""
        from playwright.async_api import async_playwright
        self._playwright = await async_playwright().start()
        pw_browser = await self._playwright.chromium.connect_over_cdp(cdp_url)
        contexts = pw_browser.contexts
        self._pw_browser = pw_browser
        if contexts:
            self._pw_context = contexts[0]
            pages = self._pw_context.pages
            self._pw_page = pages[0] if pages else await self._pw_context.new_page()
        else:
            self._pw_context = await pw_browser.new_context()
            self._pw_page = await self._pw_context.new_page()
        self._connected_via = "cdp"

    async def _launch_playwright(self, browser: str = "edge"):
        """Launch a browser via Playwright for automation."""
        from playwright.async_api import async_playwright
        self._playwright = await async_playwright().start()

        exe = _find_browser_exe(browser)
        if exe:
            pw_browser = await self._playwright.chromium.launch(
                executable_path=exe,
                headless=False,
                args=["--start-maximized"],
            )
        else:
            pw_browser = await self._playwright.chromium.launch(headless=False)

        self._pw_browser = pw_browser
        self._pw_context = await pw_browser.new_context(no_viewport=True)
        self._pw_page = await self._pw_context.new_page()
        self._connected_via = "playwright"

    async def close(self):
        """Cleanly close the Playwright browser if one was opened."""
        try:
            if self._pw_browser:
                await self._pw_browser.close()
        except Exception:
            pass
        try:
            if self._playwright:
                await self._playwright.stop()
        except Exception:
            pass
        self._pw_browser = None
        self._pw_context = None
        self._pw_page = None
        self._playwright = None

    # ------------------------------------------------------------------
    # Action dispatcher
    # ------------------------------------------------------------------

    async def execute(self, action: str, params: dict) -> str:
        """Dispatch a browser action by name."""
        actions = {
            "navigate":     self.navigate,
            "search":       self.search,
            "fill_form":    self.fill_form,
            "click":        self.click,
            "extract_text": self.extract_text,
            "screenshot":   self.take_screenshot,
            "manage_tabs":  self.manage_tabs,
            "type_text":    self.type_text,
            "wait_for":     self.wait_for_selector,
            "evaluate":     self.evaluate_js,
        }

        handler = actions.get(action)
        if not handler:
            raise ValueError(
                f"Unknown browser action: '{action}'. "
                f"Available: {list(actions.keys())}"
            )

        # navigate and search handle their own connection (subprocess)
        # all others need Playwright
        if action not in ("navigate", "search"):
            browser = params.get("browser", "edge")
            await self._ensure_playwright(browser)

        return await handler(**params)

    # ------------------------------------------------------------------
    # Playwright-backed actions
    # ------------------------------------------------------------------

    async def fill_form(self, selector: str, value: str, **kwargs) -> str:
        """Fill a form field identified by a CSS selector."""
        await self._pw_page.fill(selector, value)
        return f"Filled '{selector}'"

    async def click(self, selector: str, **kwargs) -> str:
        """Click an element identified by a CSS selector."""
        await self._pw_page.click(selector)
        return f"Clicked '{selector}'"

    async def type_text(self, text: str, selector: str = "", delay: int = 50, **kwargs) -> str:
        """Type text into a selector (or active element if selector is empty)."""
        if selector:
            await self._pw_page.type(selector, text, delay=delay)
        else:
            await self._pw_page.keyboard.type(text, delay=delay)
        return f"Typed: {text}"

    async def extract_text(self, selector: str = "body", **kwargs) -> str:
        """Extract inner text from a CSS selector."""
        text = await self._pw_page.inner_text(selector)
        if len(text) > 5000:
            text = text[:5000] + "... (truncated)"
        return text

    async def take_screenshot(self, path: str = "", full_page: bool = False, **kwargs) -> str:
        """Save a screenshot of the current page."""
        if not path:
            screenshots_dir = os.getenv("SCREENSHOTS_PATH", "./screenshots")
            os.makedirs(screenshots_dir, exist_ok=True)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            path = os.path.join(screenshots_dir, f"browser_{timestamp}.png")
        await self._pw_page.screenshot(path=path, full_page=full_page)
        return f"Screenshot saved to {path}"

    async def manage_tabs(
        self,
        operation: str,
        tab_index: int = 0,
        url: str = "",
        **kwargs,
    ) -> str:
        """List, switch, open, or close browser tabs."""
        pages = self._pw_context.pages

        if operation == "list":
            tabs = [
                {"index": i, "url": p.url, "title": await p.title()}
                for i, p in enumerate(pages)
            ]
            return f"Open tabs: {tabs}"

        if operation == "switch":
            if 0 <= tab_index < len(pages):
                self._pw_page = pages[tab_index]
                await self._pw_page.bring_to_front()
                return f"Switched to tab {tab_index}"
            return f"Invalid tab index: {tab_index}"

        if operation == "new":
            self._pw_page = await self._pw_context.new_page()
            if url:
                await self._pw_page.goto(url)
            return "Opened new tab"

        if operation == "close":
            if 0 <= tab_index < len(pages):
                await pages[tab_index].close()
                remaining = self._pw_context.pages
                self._pw_page = remaining[0] if remaining else None
                return f"Closed tab {tab_index}"
            return f"Invalid tab index: {tab_index}"

        return f"Unknown tab operation: {operation}"

    async def wait_for_selector(self, selector: str, timeout: int = 30000, **kwargs) -> str:
        """Wait until a CSS selector appears on the page."""
        await self._pw_page.wait_for_selector(selector, timeout=timeout)
        return f"Element '{selector}' is now visible"

    async def evaluate_js(self, code: str, **kwargs) -> str:
        """Evaluate JavaScript in the page context and return the result."""
        result = await self._pw_page.evaluate(code)
        return str(result)
