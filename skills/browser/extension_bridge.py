"""
OpenClaw Skill — Chrome Extension Bridge
==========================================
Communicates with the OpenClaw Chrome Extension via WebSocket
for tab management, DOM interaction, and navigation commands.
"""

import asyncio
import json
import os
from typing import Optional

try:
    import websockets
except ImportError:
    websockets = None


class ExtensionBridge:
    """
    Bridge between the Python agent and the Chrome Extension.
    
    Runs a local WebSocket server that the extension connects to.
    The extension exposes tab management, DOM interaction, and
    navigation commands that the agent can invoke.
    """

    def __init__(self, port: int = 8765):
        self.port = port
        self.server = None
        self.extension_ws = None
        self._response_futures = {}
        self._message_id = 0

    async def start_server(self):
        """Start the WebSocket server for extension communication."""
        if not websockets:
            raise ImportError("websockets package not installed")

        self.server = await websockets.serve(
            self._handle_connection,
            "127.0.0.1",
            self.port,
        )
        print(f"[ExtensionBridge] WebSocket server listening on ws://127.0.0.1:{self.port}")

    async def stop_server(self):
        """Stop the WebSocket server."""
        if self.server:
            self.server.close()
            await self.server.wait_closed()

    async def _handle_connection(self, websocket, path=""):
        """Handle incoming WebSocket connection from the extension."""
        print("[ExtensionBridge] Chrome extension connected")
        self.extension_ws = websocket
        try:
            async for message in websocket:
                data = json.loads(message)
                msg_id = data.get("id")

                if msg_id and msg_id in self._response_futures:
                    # This is a response to a request we sent
                    self._response_futures[msg_id].set_result(data)
                else:
                    # This is an unsolicited event from the extension
                    await self._handle_extension_event(data)
        except Exception as e:
            print(f"[ExtensionBridge] Connection closed: {e}")
        finally:
            self.extension_ws = None

    async def _handle_extension_event(self, data: dict):
        """Handle events pushed from the extension (e.g., tab changes)."""
        event_type = data.get("type", "unknown")
        print(f"[ExtensionBridge] Extension event: {event_type}")

    async def _send_command(self, command: str, params: dict = None, timeout: float = 30.0) -> dict:
        """Send a command to the extension and wait for the response."""
        if not self.extension_ws:
            raise ConnectionError("Chrome extension not connected")

        self._message_id += 1
        msg_id = str(self._message_id)

        message = {
            "id": msg_id,
            "command": command,
            "params": params or {},
        }

        future = asyncio.get_event_loop().create_future()
        self._response_futures[msg_id] = future

        await self.extension_ws.send(json.dumps(message))

        try:
            response = await asyncio.wait_for(future, timeout=timeout)
            return response
        finally:
            self._response_futures.pop(msg_id, None)

    # --- Public API ---

    async def execute(self, action: str, params: dict) -> str:
        """Dispatch an action by name."""
        actions = {
            "get_tabs": self.get_tabs,
            "switch_tab": self.switch_tab,
            "close_tab": self.close_tab,
            "inject_script": self.inject_script,
            "get_dom": self.get_dom_content,
            "click_element": self.click_element,
            "fill_input": self.fill_input,
        }

        handler = actions.get(action)
        if not handler:
            raise ValueError(f"Unknown extension action: {action}")

        return await handler(**params)

    async def get_tabs(self, **kwargs) -> str:
        """Get a list of all open tabs."""
        response = await self._send_command("getTabs")
        return json.dumps(response.get("tabs", []))

    async def switch_tab(self, tab_id: int, **kwargs) -> str:
        """Switch to a specific tab."""
        response = await self._send_command("switchTab", {"tabId": tab_id})
        return f"Switched to tab {tab_id}"

    async def close_tab(self, tab_id: int, **kwargs) -> str:
        """Close a specific tab."""
        response = await self._send_command("closeTab", {"tabId": tab_id})
        return f"Closed tab {tab_id}"

    async def inject_script(self, tab_id: int, code: str, **kwargs) -> str:
        """Inject and execute JavaScript in a tab."""
        response = await self._send_command("injectScript", {
            "tabId": tab_id,
            "code": code,
        })
        return str(response.get("result", ""))

    async def get_dom_content(self, tab_id: int, selector: str = "body", **kwargs) -> str:
        """Get DOM content from a tab."""
        response = await self._send_command("getDom", {
            "tabId": tab_id,
            "selector": selector,
        })
        text = response.get("content", "")
        if len(text) > 5000:
            text = text[:5000] + "... (truncated)"
        return text

    async def click_element(self, tab_id: int, selector: str, **kwargs) -> str:
        """Click an element in a tab."""
        response = await self._send_command("clickElement", {
            "tabId": tab_id,
            "selector": selector,
        })
        return f"Clicked '{selector}' in tab {tab_id}"

    async def fill_input(self, tab_id: int, selector: str, value: str, **kwargs) -> str:
        """Fill an input element in a tab."""
        response = await self._send_command("fillInput", {
            "tabId": tab_id,
            "selector": selector,
            "value": value,
        })
        return f"Filled '{selector}' with value in tab {tab_id}"
