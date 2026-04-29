"""
IntentOS Skill — App Launcher
==============================
Opens Windows applications using the apps.json registry.
Tries AppID (Start Menu UWP/modern apps) first, falls back to .lnk shortcut.

Also provides shortcut-key helpers (press_keys) used by the Messaging skill.
"""

import asyncio
import json
import os
import subprocess
from pathlib import Path
from typing import Optional


# Path to the app registry built by the scanner
APPS_JSON = Path(__file__).parent.parent.parent / "apps.json"


def _load_apps() -> dict:
    """Load the apps registry from apps.json."""
    if not APPS_JSON.exists():
        return {}
    try:
        with open(APPS_JSON, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"[AppLauncher] Failed to load apps.json: {e}")
        return {}


def _find_app(name: str, apps: dict) -> Optional[dict]:
    """
    Find an app entry by name (case-insensitive, partial match).

    Returns the best-matching app dict or None.
    """
    name_lower = name.lower().strip()

    # Exact match first
    if name_lower in apps:
        return apps[name_lower]

    # Starts-with match
    for key in apps:
        if key.startswith(name_lower):
            return apps[key]

    # Contains match
    for key in apps:
        if name_lower in key:
            return apps[key]

    return None


def _launch_via_app_id(app_id: str) -> bool:
    """Launch a UWP / Store app via its AppID using explorer shell."""
    try:
        subprocess.Popen(
            ["explorer.exe", f"shell:appsFolder\\{app_id}"],
            shell=False,
        )
        return True
    except Exception as e:
        print(f"[AppLauncher] AppID launch failed ({app_id}): {e}")
        return False


def _launch_via_shortcut(shortcut_path: str) -> bool:
    """Launch an application from a .lnk shortcut."""
    try:
        os.startfile(shortcut_path)
        return True
    except Exception as e:
        print(f"[AppLauncher] Shortcut launch failed ({shortcut_path}): {e}")
        return False


def _press_keys_sync(keys: list[str], interval: float = 0.05) -> str:
    """
    Simulate a hotkey / shortcut-key sequence using PyAutoGUI.

    `keys` is a list of key names as understood by pyautogui, e.g.:
        ["ctrl", "n"]      → Ctrl+N
        ["alt", "F4"]      → Alt+F4
        ["enter"]          → Enter
    """
    try:
        import pyautogui
        pyautogui.hotkey(*keys, interval=interval)
        return f"Pressed keys: {'+'.join(keys)}"
    except ImportError:
        return "PyAutoGUI not installed — cannot press keys"
    except Exception as e:
        return f"Key press failed: {e}"


def _type_text_sync(text: str, interval: float = 0.03) -> str:
    """Type a string of text character by character."""
    try:
        import pyautogui
        pyautogui.write(text, interval=interval)
        return f"Typed: {text}"
    except ImportError:
        return "PyAutoGUI not installed — cannot type text"
    except Exception as e:
        return f"Type failed: {e}"


class AppLauncher:
    """
    Skill: App Launcher

    Actions:
        open_app    — Open an app by name (looks up apps.json)
        press_keys  — Send a hotkey combination (list of key names)
        type_text   — Type a string of text into the focused window
        list_apps   — Return a filtered list of known app names
        scan_apps   — Re-run the app scanner to refresh apps.json
    """

    async def execute(self, action: str, params: dict) -> str:
        """Dispatch an app-launcher action."""
        handlers = {
            "open_app":   self.open_app,
            "press_keys": self.press_keys,
            "type_text":  self.type_text,
            "list_apps":  self.list_apps,
            "scan_apps":  self.scan_apps,
        }
        handler = handlers.get(action)
        if not handler:
            raise ValueError(
                f"Unknown AppLauncher action: '{action}'. "
                f"Available: {list(handlers.keys())}"
            )
        return await handler(**params)

    # ------------------------------------------------------------------
    # open_app
    # ------------------------------------------------------------------

    async def open_app(self, name: str, wait_seconds: float = 2.0, **kwargs) -> str:
        """
        Open an application by name.

        Args:
            name:         App name to search for in apps.json.
            wait_seconds: Seconds to wait after launching (so the app has time to load).

        Returns:
            Status string.
        """
        apps = _load_apps()
        entry = _find_app(name, apps)

        if not entry:
            raise ValueError(
                f"App '{name}' not found in apps.json. "
                f"Run 'scan_apps' to refresh the registry."
            )

        launched = False

        # 1. Try AppID (UWP / Start Menu)
        if "app_id" in entry:
            launched = await asyncio.to_thread(_launch_via_app_id, entry["app_id"])

        # 2. Fall back to .lnk shortcut
        if not launched and "shortcut" in entry:
            launched = await asyncio.to_thread(_launch_via_shortcut, entry["shortcut"])

        if not launched:
            raise RuntimeError(f"Failed to open '{name}' — no valid launch method found in entry: {entry}")

        # Wait for the app window to appear
        if wait_seconds > 0:
            await asyncio.sleep(wait_seconds)

        return f"Opened '{name}' successfully"

    # ------------------------------------------------------------------
    # press_keys
    # ------------------------------------------------------------------

    async def press_keys(self, keys: list, interval: float = 0.05, **kwargs) -> str:
        """
        Press a hotkey combination.

        Args:
            keys:     List of key names, e.g. ["ctrl", "n"] or ["alt", "F4"].
            interval: Pause between each key press in seconds.

        Returns:
            Status string.
        """
        if not keys:
            raise ValueError("'keys' list cannot be empty")
        return await asyncio.to_thread(_press_keys_sync, [str(k) for k in keys], interval)

    # ------------------------------------------------------------------
    # type_text
    # ------------------------------------------------------------------

    async def type_text(self, text: str, interval: float = 0.03, **kwargs) -> str:
        """
        Type text into the currently focused window.

        Args:
            text:     Text to type.
            interval: Delay between keystrokes in seconds.

        Returns:
            Status string.
        """
        if not text:
            raise ValueError("'text' cannot be empty")
        return await asyncio.to_thread(_type_text_sync, text, interval)

    # ------------------------------------------------------------------
    # list_apps
    # ------------------------------------------------------------------

    async def list_apps(self, filter: str = "", limit: int = 50, **kwargs) -> str:
        """
        List app names from apps.json, optionally filtered by a substring.

        Args:
            filter: Substring to filter app names by (case-insensitive).
            limit:  Maximum number of results to return.

        Returns:
            JSON string of matching app names.
        """
        apps = _load_apps()
        names = list(apps.keys())

        if filter:
            names = [n for n in names if filter.lower() in n]

        names.sort()
        return json.dumps(names[:limit], indent=2)

    # ------------------------------------------------------------------
    # scan_apps
    # ------------------------------------------------------------------

    async def scan_apps(self, **kwargs) -> str:
        """
        Re-run the app scanner script to rebuild apps.json.

        Returns:
            Status string with the number of apps found.
        """
        scanner_path = Path(__file__).parent.parent.parent / "scan_apps.py"
        if not scanner_path.exists():
            raise FileNotFoundError(f"Scanner script not found: {scanner_path}")

        result = await asyncio.to_thread(
            subprocess.check_output,
            ["python", str(scanner_path)],
            text=True,
        )
        return f"App scan complete. {result.strip()}"
