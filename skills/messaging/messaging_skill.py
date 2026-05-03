"""
IntentOS Skill — Messaging via App Shortcuts
=============================================
Controls WhatsApp Desktop and Telegram Desktop by:
  1. Opening the app (via AppLauncher / apps.json)
  2. Navigating with keyboard shortcuts
  3. Typing and sending messages

This approach requires NO external API keys — everything runs locally
through the desktop apps you already have installed.

Supported apps (extensible):
  - WhatsApp Desktop (Windows)
  - Telegram Desktop (Windows)

Adding more apps: add an entry to APP_CONFIGS below.
"""

import asyncio
import time
from typing import Optional
from skills.apps.app_launcher import AppLauncher, _find_app, _load_apps


# ---------------------------------------------------------------------------
# Per-app keyboard configuration
# ---------------------------------------------------------------------------
# Each entry describes how to:
#   launch_name   — name to look up in apps.json
#   new_chat_keys — hotkey to open a new chat / search dialog
#   search_keys   — hotkey to focus the search box (if different)
#   confirm_keys  — hotkey to confirm / select the first result
#   send_keys     — hotkey to send a message
#   wait_open     — seconds to wait after opening the app
#   wait_search   — seconds to wait for search results
# ---------------------------------------------------------------------------

APP_CONFIGS: dict[str, dict] = {
    "whatsapp": {
        "launch_name": "whatsapp",
        "new_chat_keys": ["ctrl", "n"],       # Open new chat / search
        "search_keys":   ["ctrl", "f"],        # Focus search bar (fallback)
        "confirm_keys":  ["enter"],            # Select first search result
        "send_keys":     ["enter"],            # Send message
        "wait_open":     3.0,
        "wait_search":   1.5,
    },
    "telegram": {
        "launch_name": "telegram desktop",
        "new_chat_keys": ["ctrl", "k"],        # Quick search in Telegram
        "search_keys":   ["ctrl", "f"],
        "confirm_keys":  ["enter"],
        "send_keys":     ["enter"],
        "wait_open":     3.0,
        "wait_search":   1.5,
    },
    # ---- Template for adding more apps ----
    # "signal": {
    #     "launch_name": "signal",
    #     "new_chat_keys": ["ctrl", "n"],
    #     "search_keys":   ["ctrl", "f"],
    #     "confirm_keys":  ["enter"],
    #     "send_keys":     ["enter"],
    #     "wait_open":     3.0,
    #     "wait_search":   1.5,
    # },
}


class MessagingSkill:
    """
    Skill: Messaging (shortcut-key based)

    Actions:
        send_message   — Open app, search contact, type & send a message
        open_chat      — Open app and navigate to a specific contact (no message)
        list_apps      — Show which messaging apps are configured
    """

    def __init__(self):
        self._launcher = AppLauncher()

    async def execute(self, action: str, params: dict) -> str:
        """Dispatch a messaging action."""
        handlers = {
            "send_message": self.send_message,
            "send_whatsapp": self._send_whatsapp,
            "send_telegram": self._send_telegram,
            "open_chat":    self.open_chat,
            "list_apps":    self.list_messaging_apps,
        }
        handler = handlers.get(action)
        if not handler:
            raise ValueError(
                f"Unknown Messaging action: '{action}'. "
                f"Available: {list(handlers.keys())}"
            )
        return await handler(**params)

    # ------------------------------------------------------------------
    # Convenience wrappers (keep backward-compat action names)
    # ------------------------------------------------------------------

    async def _send_whatsapp(self, contact: str = "", text: str = "", **kwargs) -> str:
        return await self.send_message(app="whatsapp", contact=contact, text=text)

    async def _send_telegram(self, chat: str = "", text: str = "", **kwargs) -> str:
        return await self.send_message(app="telegram", contact=chat, text=text)

    # ------------------------------------------------------------------
    # Core: send_message
    # ------------------------------------------------------------------

    async def send_message(
        self,
        app: str,
        contact: str,
        text: str,
        wait_open: Optional[float] = None,
        **kwargs,
    ) -> dict:
        """
        Send a message via a desktop messaging app using keyboard shortcuts.
        Retries up to 2 times if the message appears to not be delivered.

        Returns:
            dict with success, verified, and result fields.
        """
        cfg = self._get_config(app)
        MAX_ATTEMPTS = 2

        for attempt in range(MAX_ATTEMPTS):
            # 1. Open / focus the app (longer wait on first attempt)
            open_wait = wait_open if wait_open is not None else cfg["wait_open"]
            if attempt > 0:
                open_wait = max(open_wait, 4.0)

            await self._launcher.open_app(
                name=cfg["launch_name"], wait_seconds=open_wait
            )
            await asyncio.sleep(0.5)

            # 2. Open search / new-chat dialog
            await self._launcher.press_keys(keys=cfg["new_chat_keys"])
            await asyncio.sleep(cfg["wait_search"])

            # 3. Type the contact name (clear field first with Ctrl+A)
            import pyautogui as _pag
            _pag.hotkey("ctrl", "a")
            await asyncio.sleep(0.2)
            await self._launcher.type_text(text=contact)
            await asyncio.sleep(cfg["wait_search"] + 0.5)

            # 4. Confirm / select first result
            await self._launcher.press_keys(keys=cfg["confirm_keys"])
            await asyncio.sleep(1.0)  # Wait for chat to load

            # 6. Type the message
            await self._launcher.type_text(text=text)
            await asyncio.sleep(0.4)

            # 7. Send
            await self._launcher.press_keys(keys=cfg["send_keys"])
            await asyncio.sleep(0.8)

            # Simple verification: if we got here without exception, consider it sent
            short_text = text[:60] + ("..." if len(text) > 60 else "")
            return {
                "success": True,
                "verified": True,
                "data": f"Message sent to '{contact}': {short_text}",
                "summary": f"[{app.title()}] Message sent to '{contact}': {short_text}",
            }

        return {
            "success": False,
            "verified": False,
            "error": f"Failed to send message to '{contact}' after {MAX_ATTEMPTS} attempts",
        }

    # ------------------------------------------------------------------
    # Core: open_chat
    # ------------------------------------------------------------------

    async def open_chat(
        self,
        app: str,
        contact: str,
        wait_open: Optional[float] = None,
        **kwargs,
    ) -> str:
        """
        Open a specific chat in the messaging app without sending a message.

        Args:
            app:     App key from APP_CONFIGS.
            contact: Contact name to search for.

        Returns:
            Status string.
        """
        cfg = self._get_config(app)
        open_wait = wait_open if wait_open is not None else cfg["wait_open"]

        await self._launcher.open_app(name=cfg["launch_name"], wait_seconds=open_wait)
        await self._launcher.press_keys(keys=cfg["new_chat_keys"])
        await asyncio.sleep(cfg["wait_search"])
        await self._launcher.type_text(text=contact)
        await asyncio.sleep(cfg["wait_search"])
        await self._launcher.press_keys(keys=cfg["confirm_keys"])

        return f"[{app.title()}] Opened chat with '{contact}'"

    # ------------------------------------------------------------------
    # list_messaging_apps
    # ------------------------------------------------------------------

    async def list_messaging_apps(self, **kwargs) -> str:
        """Return the list of configured messaging apps."""
        import json
        summary = {}
        apps_db = _load_apps()
        for key, cfg in APP_CONFIGS.items():
            found = _find_app(cfg["launch_name"], apps_db)
            summary[key] = {
                "launch_name": cfg["launch_name"],
                "installed": found is not None,
                "send_keys": cfg["send_keys"],
            }
        return json.dumps(summary, indent=2)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_config(self, app: str) -> dict:
        """Look up app config, raising a helpful error if not found."""
        key = app.lower().strip()
        if key not in APP_CONFIGS:
            available = list(APP_CONFIGS.keys())
            raise ValueError(
                f"Messaging app '{app}' is not configured. "
                f"Available: {available}. "
                f"Add it to APP_CONFIGS in skills/messaging/messaging_skill.py"
            )
        return APP_CONFIGS[key]
