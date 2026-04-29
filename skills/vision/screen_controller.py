"""
IntentOS Skill — Screen Controller
=====================================
Screenshot capture + PyAutoGUI mouse/keyboard simulation.

Claude Vision is intentionally disabled to keep costs low.
Use this skill as a fallback when browser/terminal automation isn't possible.

When you need vision analysis later, re-enable analyze_screenshot()
and set CLAUDE_VISION_MODEL in .env.
"""

import asyncio
import os
from datetime import datetime
from typing import Optional, Tuple
from pathlib import Path


class ScreenController:
    """
    Screen control using:
    - MSS for fast screenshot capture
    - PyAutoGUI for mouse/keyboard simulation

    Vision (Claude) analysis is disabled — re-enable later if needed.
    """

    def __init__(self):
        self.screenshots_dir = os.getenv("SCREENSHOTS_PATH", "./screenshots")
        os.makedirs(self.screenshots_dir, exist_ok=True)

    async def execute(self, action: str, params: dict) -> str:
        """Dispatch a vision / input action."""
        actions = {
            "capture_screen": self._async_capture,
            "click_at":       self._async_click,
            "type_text":      self._async_type,
            "press_keys":     self._async_press_keys,
            "scroll":         self._async_scroll,
            "move_mouse":     self._async_move,
        }
        handler = actions.get(action)
        if not handler:
            raise ValueError(
                f"Unknown screen action: '{action}'. "
                f"Available: {list(actions.keys())}"
            )
        return await handler(**params)

    # ------------------------------------------------------------------
    # Capture
    # ------------------------------------------------------------------

    async def _async_capture(self, monitor: int = 0, **kwargs) -> str:
        path = await asyncio.to_thread(self._capture_sync, monitor)
        return f"Screenshot saved: {path}" if path else "Screenshot capture failed"

    def _capture_sync(self, monitor: int = 0) -> Optional[str]:
        try:
            import mss
            from PIL import Image

            with mss.mss() as sct:
                mon = sct.monitors[monitor]
                screenshot = sct.grab(mon)
                img = Image.frombytes("RGB", screenshot.size, screenshot.bgra, "raw", "BGRX")
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                path = os.path.join(self.screenshots_dir, f"screen_{timestamp}.png")
                img.save(path)
                return path
        except ImportError:
            print("[Screen] MSS or Pillow not installed")
            return None
        except Exception as e:
            print(f"[Screen] Screenshot failed: {e}")
            return None

    # ------------------------------------------------------------------
    # Click
    # ------------------------------------------------------------------

    async def _async_click(self, x: int, y: int, button: str = "left", **kwargs) -> str:
        return await asyncio.to_thread(self._click_sync, x, y, button)

    def _click_sync(self, x: int, y: int, button: str = "left") -> str:
        try:
            import pyautogui
            pyautogui.click(x, y, button=button)
            return f"Clicked {button} at ({x}, {y})"
        except ImportError:
            return "PyAutoGUI not installed"
        except Exception as e:
            return f"Click failed: {e}"

    # ------------------------------------------------------------------
    # Type
    # ------------------------------------------------------------------

    async def _async_type(self, text: str, interval: float = 0.03, **kwargs) -> str:
        return await asyncio.to_thread(self._type_sync, text, interval)

    def _type_sync(self, text: str, interval: float = 0.03) -> str:
        try:
            import pyautogui
            pyautogui.write(text, interval=interval)
            return f"Typed {len(text)} characters"
        except ImportError:
            return "PyAutoGUI not installed"
        except Exception as e:
            return f"Type failed: {e}"

    # ------------------------------------------------------------------
    # Press keys / hotkeys
    # ------------------------------------------------------------------

    async def _async_press_keys(self, keys: list, interval: float = 0.05, **kwargs) -> str:
        return await asyncio.to_thread(self._press_keys_sync, [str(k) for k in keys], interval)

    def _press_keys_sync(self, keys: list, interval: float = 0.05) -> str:
        try:
            import pyautogui
            pyautogui.hotkey(*keys, interval=interval)
            return f"Pressed: {'+'.join(keys)}"
        except ImportError:
            return "PyAutoGUI not installed"
        except Exception as e:
            return f"Key press failed: {e}"

    # ------------------------------------------------------------------
    # Scroll
    # ------------------------------------------------------------------

    async def _async_scroll(self, clicks: int = 3, x: int = None, y: int = None, **kwargs) -> str:
        return await asyncio.to_thread(self._scroll_sync, clicks, x, y)

    def _scroll_sync(self, clicks: int, x: Optional[int], y: Optional[int]) -> str:
        try:
            import pyautogui
            if x is not None and y is not None:
                pyautogui.scroll(clicks, x=x, y=y)
            else:
                pyautogui.scroll(clicks)
            direction = "up" if clicks > 0 else "down"
            return f"Scrolled {direction} {abs(clicks)} clicks"
        except ImportError:
            return "PyAutoGUI not installed"
        except Exception as e:
            return f"Scroll failed: {e}"

    # ------------------------------------------------------------------
    # Move mouse
    # ------------------------------------------------------------------

    async def _async_move(self, x: int, y: int, duration: float = 0.2, **kwargs) -> str:
        return await asyncio.to_thread(self._move_sync, x, y, duration)

    def _move_sync(self, x: int, y: int, duration: float = 0.2) -> str:
        try:
            import pyautogui
            pyautogui.moveTo(x, y, duration=duration)
            return f"Mouse moved to ({x}, {y})"
        except ImportError:
            return "PyAutoGUI not installed"
        except Exception as e:
            return f"Move failed: {e}"
