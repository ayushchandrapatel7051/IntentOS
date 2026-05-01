"""
OpenClaw Skill — Agentic Chrome Extension Bridge v3
====================================================
This is the execution arm of the AI agent for browser DOM tasks.

Flow:
  User input → Planner (Gemini) → Executor → ExtensionBridge.execute()
                                              → WebSocket → background.js
                                              → DOM action in Chrome
                                              → Result → back to agent

Design principles:
  1. Zero extra LLM calls — the agent plans once, the extension executes
  2. Every action returns a meaningful string result the agent can use
  3. Falls back to Playwright if extension is not connected
  4. All action names are normalised (snake_case or camelCase both work)

Supported action groups:
  Core     : get_tabs, switch_tab, close_tab, navigate, get_dom, click,
             fill, screenshot, wait_for, smart_click, smart_fill,
             extract, inject_script
  YouTube  : search_youtube / searchYouTube (query, video_index, autoplay)
             play_youtube / playYouTube
             pause_youtube / pauseYouTube
             set_volume / setVolume (level 0-100)
             seek_to / seekTo (seconds)
             get_video_info / getVideoInfo
             next_video / nextVideo
  Gmail    : compose_mail / composeMail (to, subject, body, send)
             send_mail / sendMail (to, subject, body)
             search_mail / searchMail (query)
             reply_mail / replyMail (tabId, body)
             get_unread / getUnread
  Calendar : create_event / createEvent (title, date, time, duration,
                                          guests, description, meet)
             get_events / getEvents (date)
             open_calendar / openCalendar
  Meet     : join_meet / joinMeet (url)
             schedule_meet / scheduleMeet (title, date, time, duration, guests)
             mute_mic / muteMic
             mute_camera / muteCamera
             leave_meet / leaveMeet
  Drive    : search_drive / searchDrive (query)
             open_drive / openDriveFile (fileId)
"""

import asyncio
import json
import logging
import os
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

try:
    import websockets
    import websockets.server
    _WS_OK = True
except ImportError:
    websockets = None
    _WS_OK = False


# ---------------------------------------------------------------------------
# Chrome launch helper
# ---------------------------------------------------------------------------

_CHROME_PATHS = [
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    str(Path.home() / "AppData" / "Local" / "Google" / "Chrome" / "Application" / "chrome.exe"),
]


def _find_chrome() -> Optional[str]:
    for p in _CHROME_PATHS:
        if Path(p).exists():
            return p
    return None


async def _force_chrome_window(url: str = "about:blank") -> None:
    """
    Unconditionally open a new Chrome window with the given URL.
    Used as a recovery action when the extension reports 'No current window'.
    chrome.exe can run as a background process (for notifications) with ZERO
    visible windows — the tasklist check is unreliable, so we skip it entirely
    and just force a new window via subprocess.
    """
    chrome = _find_chrome()
    if not chrome:
        logger.warning("[ExtensionBridge] Chrome not found -- cannot auto-open window")
        return
    logger.info(f"[ExtensionBridge] Forcing new Chrome window: {url}")
    subprocess.Popen([chrome, "--new-window", url], shell=False)
    # Give Chrome time to create the window and let the extension settle
    await asyncio.sleep(4)


async def _try_subprocess_navigation(command: str, params: dict) -> Optional[str]:
    """
    For commands that simply open a URL, bypass chrome.tabs.create entirely
    and use subprocess instead. This is 100% reliable regardless of Chrome's
    window state.

    Returns the URL that was opened (str), or None if this command should
    still be handled by the extension (DOM manipulation etc).
    """
    chrome = _find_chrome()
    if not chrome:
        return None  # No Chrome found -- fall back to extension

    def _launch(url: str) -> str:
        subprocess.Popen([chrome, url], shell=False)
        return url

    if command == "navigate":
        url = params.get("url", "")
        if url and url != "about:blank":
            await asyncio.to_thread(_launch, url)
            return url
        return None

    if command == "searchYouTube":
        from urllib.parse import quote
        query = params.get("query", "")
        url = f"https://www.youtube.com/results?search_query={quote(query)}"
        await asyncio.to_thread(_launch, url)
        return url

    if command in ("composeMail", "sendMail"):
        to      = params.get("to", "")
        subject = params.get("subject", "") or params.get("su", "")
        body    = params.get("body", "")
        from urllib.parse import quote
        url = (
            f"https://mail.google.com/mail/?view=cm&fs=1"
            f"&to={quote(to)}&su={quote(subject)}&body={quote(body)}"
        )
        await asyncio.to_thread(_launch, url)
        return url

    if command == "searchMail":
        from urllib.parse import quote
        url = f"https://mail.google.com/mail/u/0/#search/{quote(params.get('query', ''))}"
        await asyncio.to_thread(_launch, url)
        return url

    if command == "openCalendar":
        url = "https://calendar.google.com"
        await asyncio.to_thread(_launch, url)
        return url

    if command == "searchDrive":
        from urllib.parse import quote
        url = f"https://drive.google.com/drive/search?q={quote(params.get('query', ''))}"
        await asyncio.to_thread(_launch, url)
        return url

    if command == "openDriveFile":
        file_id = params.get("fileId", "")
        url = f"https://drive.google.com/file/d/{file_id}/view"
        await asyncio.to_thread(_launch, url)
        return url

    if command == "joinMeet":
        url = params.get("url", "")
        if url:
            await asyncio.to_thread(_launch, url)
            return url

    # All other commands (DOM manipulation, YouTube control, etc.) go to extension
    return None


# ---------------------------------------------------------------------------
# Action name normalisation
# Converts any case variant → canonical camelCase command for the extension
# ---------------------------------------------------------------------------

_ACTION_MAP = {
    # Core
    "get_tabs":        "getTabs",
    "gettabs":         "getTabs",
    "switch_tab":      "switchTab",
    "switchtab":       "switchTab",
    "close_tab":       "closeTab",
    "closetab":        "closeTab",
    "navigate":        "navigate",
    "get_dom":         "getDom",
    "getdom":          "getDom",
    "click":           "clickElement",
    "click_element":   "clickElement",
    "clickelement":    "clickElement",
    "fill":            "fillInput",
    "fill_input":      "fillInput",
    "fillinput":       "fillInput",
    "screenshot":      "screenshot",
    "wait_for":        "waitForSelector",
    "waitfor":         "waitForSelector",
    "waitforselector": "waitForSelector",
    "smart_click":     "smartClick",
    "smartclick":      "smartClick",
    "smart_fill":      "smartFill",
    "smartfill":       "smartFill",
    "extract":         "extractStructured",
    "extract_structured": "extractStructured",
    "extractstructured":  "extractStructured",
    "inject_script":   "injectScript",
    "injectscript":    "injectScript",

    # YouTube
    "search_youtube":  "searchYouTube",
    "searchyoutube":   "searchYouTube",
    "youtube_search":  "searchYouTube",
    "youtubesearch":   "searchYouTube",
    "play_youtube":    "playYouTube",
    "playyoutube":     "playYouTube",
    "pause_youtube":   "pauseYouTube",
    "pauseyoutube":    "pauseYouTube",
    "set_volume":      "setVolume",
    "setvolume":       "setVolume",
    "seek_to":         "seekTo",
    "seekto":          "seekTo",
    "get_video_info":  "getVideoInfo",
    "getvideoinfo":    "getVideoInfo",
    "next_video":      "nextVideo",
    "nextvideo":       "nextVideo",

    # Gmail
    "compose_mail":    "composeMail",
    "composemail":     "composeMail",
    "send_mail":       "sendMail",
    "sendmail":        "sendMail",
    "search_mail":     "searchMail",
    "searchmail":      "searchMail",
    "reply_mail":      "replyMail",
    "replymail":       "replyMail",
    "get_unread":      "getUnread",
    "getunread":       "getUnread",

    # Google Calendar
    "create_event":    "createEvent",
    "createevent":     "createEvent",
    "get_events":      "getEvents",
    "getevents":       "getEvents",
    "open_calendar":   "openCalendar",
    "opencalendar":    "openCalendar",

    # Google Meet
    "join_meet":       "joinMeet",
    "joinmeet":        "joinMeet",
    "schedule_meet":   "scheduleMeet",
    "schedulemeet":    "scheduleMeet",
    "mute_mic":        "muteMic",
    "mutemic":         "muteMic",
    "mute_camera":     "muteCamera",
    "mutecamera":      "muteCamera",
    "leave_meet":      "leaveMeet",
    "leavemeet":       "leaveMeet",

    # Google Drive
    "search_drive":    "searchDrive",
    "searchdrive":     "searchDrive",
    "open_drive":      "openDriveFile",
    "opendrive":       "openDriveFile",
    "open_drive_file": "openDriveFile",
    "openDriveFile":   "openDriveFile",

    # Agentic web agent DOM commands
    "extract_page":    "extractPage",
    "extractpage":     "extractPage",
    "perform_actions": "performActions",
    "performactions":  "performActions",
}


def _normalise(action: str) -> str:
    """Convert any action name variant to the canonical camelCase extension command."""
    # Try exact match first (handles already-correct camelCase from planner)
    if action in _ACTION_MAP.values():
        return action
    key = re.sub(r'[-\s]', '_', action).lower()
    return _ACTION_MAP.get(key, action)


# ---------------------------------------------------------------------------
# Extension Bridge
# ---------------------------------------------------------------------------

class ExtensionBridge:
    """
    Agentic bridge: receives action+params from the Executor,
    forwards them to the Chrome extension via WebSocket,
    and returns a result string for the agent to use.

    Connection lifecycle:
      - start_server() is called once at main.py startup
      - The Chrome extension connects automatically when Chrome is open
      - If disconnected, execute() raises ConnectionError with a helpful message
    """

    def __init__(self, port: int = 8765):
        self.port = port
        self.server = None
        self.extension_ws = None
        self._response_futures: dict = {}
        self._message_id = 0
        self._is_connected = False

    # ------------------------------------------------------------------
    # Server lifecycle
    # ------------------------------------------------------------------

    async def start_server(self):
        """Start the WebSocket server. Called once at startup by main.py."""
        if not _WS_OK:
            raise ImportError(
                "websockets not installed — run: pip install websockets"
            )
        # ping_interval=None is CRITICAL for Chrome MV3 service workers.
        # MV3 workers get suspended after ~30s inactivity; if the server
        # sends a ping while suspended, the worker can't respond and
        # websockets closes the connection immediately.
        self.server = await websockets.serve(
            self._handle_connection,
            "127.0.0.1",
            self.port,
            ping_interval=None,
            ping_timeout=None,
            close_timeout=10,
        )
        logger.info(f"[ExtensionBridge] WebSocket server on ws://127.0.0.1:{self.port}")

    async def stop_server(self):
        if self.server:
            self.server.close()
            await self.server.wait_closed()

    @property
    def is_connected(self) -> bool:
        return self._is_connected and self.extension_ws is not None

    # ------------------------------------------------------------------
    # WebSocket handler
    # ------------------------------------------------------------------

    async def _handle_connection(self, websocket):
        was_connected = self._is_connected
        self.extension_ws = websocket
        self._is_connected = True
        if not was_connected:
            logger.debug("[ExtensionBridge] ✓ Chrome extension connected")
        try:
            async for raw in websocket:
                try:
                    data = json.loads(raw)
                except json.JSONDecodeError:
                    continue

                msg_id = data.get("id")
                if msg_id and msg_id in self._response_futures:
                    fut = self._response_futures[msg_id]
                    if not fut.done():
                        fut.set_result(data)
                else:
                    event_type = data.get("type", "event")
                    logger.debug(f"[ExtensionBridge] Extension event: {event_type}")
        except websockets.ConnectionClosed:
            pass  # Normal close — don't spam
        except Exception as e:
            logger.error(f"[ExtensionBridge] Connection error: {type(e).__name__}: {e}")
        finally:
            self.extension_ws = None
            self._is_connected = False
            # Only log if no immediate reconnect (MV3 workers reconnect within ~1s)
            logger.debug("[ExtensionBridge] WebSocket handler exited")

    # ------------------------------------------------------------------
    # Internal send/receive
    # ------------------------------------------------------------------

    async def _send(
        self,
        command: str,
        params: dict = None,
        timeout: float = 30.0,
    ) -> dict:
        """Send a command to the extension and await its response."""
        if not self.is_connected:
            raise ConnectionError(
                "Chrome extension is not connected to IntentOS. "
                "Please: 1) Open Chrome, 2) Install the OpenClaw extension from "
                "chrome://extensions/ → Load Unpacked → IntentOS/chrome-extension/, "
                "3) Reload this page."
            )

        self._message_id += 1
        msg_id = str(self._message_id)

        fut = asyncio.get_event_loop().create_future()
        self._response_futures[msg_id] = fut

        payload = json.dumps({
            "id":      msg_id,
            "command": command,
            "params":  params or {},
        })

        try:
            await self.extension_ws.send(payload)
        except Exception as e:
            self._response_futures.pop(msg_id, None)
            raise ConnectionError(f"Failed to send to extension: {e}")

        try:
            response = await asyncio.wait_for(fut, timeout=timeout)
        finally:
            self._response_futures.pop(msg_id, None)

        if response.get("success") is False:
            error = response.get("error", "Unknown extension error")
            raise RuntimeError(f"Extension error: {error}")

        return response

    # ------------------------------------------------------------------
    # Main entry point — called by Executor
    # ------------------------------------------------------------------

    async def execute(self, action: str, params: dict) -> str:
        """
        Dispatch an action from the AI agent to the Chrome extension.

        The Executor calls this as:  skill_handler.execute(step.action, step.params)

        Accepts both snake_case (from planner) and camelCase action names.
        Returns a human-readable result string for the agent to log/use.
        """
        # Normalise action name to camelCase extension command
        command = _normalise(action)

        logger.info(f"[ExtensionBridge] {action} -> {command}({json.dumps(params)})")

        # Remap param keys that the planner might use differently
        params = _remap_params(command, params)

        # Subprocess-first navigation: open URLs via subprocess (always works),
        # then query extension for the resulting tabId. This completely avoids
        # chrome.tabs.create "No current window" errors.
        subprocess_result = await _try_subprocess_navigation(command, params)
        if subprocess_result is not None:
            # Wait for extension to connect if Chrome was just launched cold
            for _ in range(16):
                if self.is_connected:
                    break
                await asyncio.sleep(0.5)
            await asyncio.sleep(1) # Give Chrome a moment to finalize tab url
            try:
                tabs_data = await self._send("getTabs", {})
                tabs = tabs_data.get("tabs", [])
                target_url = subprocess_result
                matched = None
                for tab in reversed(tabs):
                    tab_url = tab.get("url", "")
                    if target_url and (
                        target_url.rstrip("/") in tab_url
                        or tab_url.startswith(target_url.split("?")[0])
                    ):
                        matched = tab
                        break
                if matched is None and tabs:
                    matched = tabs[-1]
                tab_id = matched["id"] if matched else None
                return _format_result(command, {"tabId": tab_id, "url": target_url})
            except Exception:
                return _format_result(command, {"tabId": None, "url": subprocess_result})

        # Extension-based commands (DOM manipulation, non-navigation)
        last_err: Exception = None
        for attempt in range(2):
            try:
                result = await self._send(command, params)
                result.pop("id", None)
                result.pop("success", None)
                return _format_result(command, result)
            except RuntimeError as e:
                last_err = e
                if "No current window" in str(e) and attempt == 0:
                    target_url = params.get("url", "about:blank") or "about:blank"
                    print(f"  [ExtensionBridge] No window -- opening Chrome and retrying '{command}'...")
                    await _force_chrome_window(target_url)
                else:
                    raise

        raise last_err


# ---------------------------------------------------------------------------
# Param remapping — normalise planner output to extension expectations
# ---------------------------------------------------------------------------

def _remap_params(command: str, params: dict) -> dict:
    """
    Normalise param names the planner might generate in various forms.
    e.g.  video_index → videoIndex,  tab_id → tabId, etc.

    Also sanitises tab_id=0 / tab_id≤0 — the extension's chrome.tabs.get(0)
    throws "No matching signature", so we remove invalid tab IDs and let
    the extension fall back to the active tab via resolveTabId().
    """
    mapping = {
        "video_index":   "videoIndex",
        "tab_id":        "tabId",
        "new_tab":       "newTab",
        "auto_play":     "autoplay",
        "file_id":       "fileId",
    }
    out = {}
    for k, v in params.items():
        mapped_key = mapping.get(k, k)
        out[mapped_key] = v

    # Remove invalid tabId values (0, negative, None, "0", etc.)
    if "tabId" in out:
        try:
            tid = int(out["tabId"])
            if tid <= 0:
                del out["tabId"]
        except (TypeError, ValueError):
            del out["tabId"]  # String like "last" — remove; resolveTabId handles it
    return out


# ---------------------------------------------------------------------------
# Result formatting — make results readable for the agent's log
# ---------------------------------------------------------------------------

def _format_result(command: str, result: dict) -> str:
    """Convert the extension's JSON response into a clean agent-readable string."""
    if not result:
        return f"[extension] {command} completed"

    # Command-specific formatting
    if command == "searchYouTube":
        if result.get("title"):
            return f"[YouTube] Playing #{result.get('videoIndex',1)}: \"{result['title']}\""
        if result.get("warning"):
            return f"[YouTube] Warning: {result['warning']}"
        if result.get("url"):
            return f"[YouTube] Opened search results: {result['url']}"
        return f"[YouTube] Searched for: {result.get('searched','')}"

    if command in ("playYouTube", "pauseYouTube", "nextVideo"):
        return f"[YouTube] {command.replace('YouTube','').replace('Next','Next track ')} done"

    if command == "setVolume":
        return f"[YouTube] Volume set to {result.get('volume')}%"

    if command == "getVideoInfo":
        v = result
        mins = int((v.get('currentTime') or 0) // 60)
        secs = int((v.get('currentTime') or 0) % 60)
        return (
            f"[YouTube] {v.get('title','?')} — "
            f"{'paused' if v.get('paused') else 'playing'} "
            f"at {mins}:{secs:02d}"
        )

    if command == "composeMail":
        status = result.get("status", "")
        if status == "sent":
            return f"[Gmail] Email sent to {result.get('to')} — subject: {result.get('subject')}"
        return f"[Gmail] Compose window opened (to={result.get('to','')})"

    if command == "createEvent":
        status = result.get("status", "event_form_opened")
        return (
            f"[Calendar] {status} — "
            f"'{result.get('title','New Event')}' on {result.get('date','')} {result.get('time','')}"
        )

    if command == "joinMeet":
        return f"[Meet] Join attempted for: {result.get('url','')}"

    if command == "scheduleMeet":
        return (
            f"[Meet] Meet event form opened — "
            f"'{result.get('title','')}' on {result.get('date','')}"
        )

    if command == "getTabs":
        tabs = result.get("tabs", [])
        lines = "\n".join(f"  [{t['id']}] {t['title']} — {t['url']}" for t in tabs)
        return f"[Tabs] {len(tabs)} open tabs:\n{lines}"

    if command == "screenshot":
        return f"[Screenshot] Captured (data URL length: {len(result.get('screenshot',''))} chars)"

    if command in ("clickElement", "smartClick"):
        return f"[Click] Clicked: {result.get('clicked','')}"

    if command in ("fillInput", "smartFill"):
        return f"[Fill] Filled: {result.get('filled','')}"

    if command == "getDom":
        content = result.get("content", "")
        return f"[DOM] Extracted {len(content)} chars:\n{content[:500]}{'...' if len(content) > 500 else ''}"

    if command == "extractStructured":
        data = result.get("data")
        if isinstance(data, list):
            return f"[Extract] {len(data)} items:\n" + json.dumps(data[:10], indent=2)
        return f"[Extract] {str(data)[:500]}"

    if command == "performActions":
        r = result
        return f"[WebAgent] Performed {r.get('performed',0)}/{r.get('total',0)} actions"

    # Generic fallback
    return json.dumps(result, indent=2) if result else f"[extension] {command} completed"


# ---------------------------------------------------------------------------
# Agentic Web Interaction Loop
# ---------------------------------------------------------------------------
# This is the "brain" of DOM interaction on arbitrary websites.
# Cost: 1 LLM call per page state (typically ~500 input tokens, ~300 output).

_WEB_AGENT_PROMPT = """You are a browser automation agent. You are given:
1. The user's TASK (what they want to accomplish)
2. The current PAGE URL and TITLE
3. A list of INTERACTIVE ELEMENTS on the page (inputs, buttons, links, selects)

Your job: decide the MINIMUM set of DOM actions needed to accomplish the task, then STOP.

Output a JSON array of actions. Each action is one of:
- {"action":"fill", "selector":"CSS_SELECTOR", "value":"TEXT_TO_TYPE"}
- {"action":"fill_react", "selector":"CSS_SELECTOR", "value":"TEXT_TO_TYPE"}  ← React/SPA inputs (ChatGPT, Notion)
- {"action":"click", "selector":"CSS_SELECTOR"}
- {"action":"enter", "selector":"CSS_SELECTOR"}  ← press Enter on an input (use for search bars)
- {"action":"select", "selector":"CSS_SELECTOR", "value":"OPTION_VALUE"}
- {"action":"check", "selector":"CSS_SELECTOR", "value":true}
- {"action":"scroll", "selector":"CSS_SELECTOR"}  ← only when element is NOT in list yet
- {"action":"navigate", "url":"URL"}  ← navigate to a different page
- {"action":"done", "message":"WHAT_WAS_ACCOMPLISHED"}  ← TASK IS COMPLETE, STOP NOW

CRITICAL RULES — read carefully:
1. Use ONLY selectors from the elements list. Never invent selectors.
2. Output ONLY the JSON array. No markdown, no explanation, no comments.
3. ALWAYS include {"action":"done",...} in the SAME array as the final action — never rely on a next iteration to stop.

DONE DETECTION — return [{"action":"done",...}] immediately when:
- The PAGE URL contains "/watch?v=" or "music.youtube.com/watch" → video is playing, STOP NOW.
- You are on a YouTube video page for ANY reason — do NOT click Back, do NOT navigate away, STOP.
- A success/confirmation message is visible on the page.
- The task has already been completed (e.g., email sent, form submitted, message typed and sent).

ONE-SHOT ACTIONS — do these ONCE then stop immediately:
These actions must ALWAYS include "done" in the same JSON array right after the click:
  - Like / Heart a post → [scroll_if_needed, click(like_button), done("Liked the post")]
  - Follow / Unfollow → [click(follow_button), done("Followed the user")]
  - Retweet / Share → [click(retweet_button), done("Retweeted the post")]
  - Bookmark / Save → [click(bookmark_button), done("Bookmarked the post")]
  - Subscribe / Unsubscribe → [click(subscribe_button), done("Subscribed")]
  - Upvote / Downvote → [click(vote_button), done("Voted")]
*** After ONE successful click on a like/follow/retweet/subscribe button → STOP. Do NOT repeat. ***

SEARCH BAR RULES:
- For YouTube, Google, YouTube Music: use "fill" then "enter" on the SAME input selector.
- Do NOT use "fill" then "click(#button)" — search bars need Enter, not a button click.
- Example: [{"action":"fill","selector":"input[name='search_query']","value":"kaho na kaho"}, {"action":"enter","selector":"input[name='search_query']"}]

CHATGPT / CHAT APP RULES (chat.openai.com, chatgpt.com):
- STEP 1: "fill_react" on the textarea/input selector from the elements list.
- STEP 2: "enter" on the EXACT SAME selector — this sends the message.
- STEP 3: Include "done" in the SAME JSON array — do not wait for AI response.
- *** NEVER click any button to send *** — NEVER use "click" on a submit/send button.
- *** NEVER invent selectors *** like "#composer-submit-button" — only use selectors from the list.
- Correct pattern: [fill_react(selector, text), enter(selector), done(message)]

REACT/SPA RULES:
- For ChatGPT, Google Docs, Notion, Slack: use "fill_react" for text inputs.
- After "fill_react", ALWAYS use "enter" on the same selector — NEVER click a submit button.

GENERAL RULES:
- If the search box is visible: fill it directly, do NOT scroll first.
- Only scroll if the target element is genuinely absent from the elements list.
- For forms: fill all required fields, then click submit or use "enter".
- After clicking a video/link that opens a new page: return [{"action":"done","message":"..."}].
- Do NOT keep clicking once the task is accomplished. Stop immediately.
"""


async def run_web_agent(bridge: ExtensionBridge, task: str, url: str = None,
                        tab_id: int = None,
                        gemini_client=None, model_name: str = "gemini-2.5-flash",
                        max_iterations: int = 5) -> str:
    """
    Run the agentic web interaction loop.

    1. Navigate to URL (if provided and no tab_id given)
    2. Extract page elements via extension
    3. Send elements + task to Gemini → get actions
    4. Execute actions via extension
    5. If page changes, repeat from step 2

    Args:
        bridge: connected ExtensionBridge instance
        task: what the user wants to accomplish
        url: optional URL to navigate to first (ignored if tab_id is given)
        tab_id: optional specific tab to operate on (from a prior navigate step)
        gemini_client: google.genai.Client instance (from Planner)
        model_name: Gemini model to use
        max_iterations: max pages to interact with (safety limit)

    Returns:
        Summary string of what was accomplished
    """
    if not bridge.is_connected:
        raise ConnectionError("Chrome extension not connected")

    if not gemini_client:
        raise RuntimeError("Gemini client required for web_agent — check your .env auth config")

    # Import genai types
    try:
        from google.genai import types as genai_types
    except ImportError:
        raise ImportError("google-genai not installed")

    results_log = []
    last_actions_str = ""
    consecutive_scroll_only = 0  # stall detection: too many scroll-only rounds
    done_actions = []  # initialise here so stall-detection can reference it
    last_page_url = ""

    # Step 1: Navigate if URL given and no specific tab_id was provided
    if tab_id:
        # We already have a tab from the prior navigate step — switch to it
        results_log.append(f"Using existing tab {tab_id}")
        try:
            await bridge._send("switchTab", {"tabId": tab_id})
        except Exception:
            pass  # Non-fatal; the tab might already be active
        # Give the tab 5 s to finish loading before we extract elements
        await asyncio.sleep(5)
    elif url and not url.endswith("=") and "..." not in url and url != "https://":
        nav_result = await bridge._send("navigate", {"url": url, "newTab": False})
        tab_id = nav_result.get("tabId")
        results_log.append(f"Navigated to {url}")
        # Wait for complex SPAs (YouTube Music, ChatGPT) to fully render
        await asyncio.sleep(5)

    for iteration in range(max_iterations):
        # Step 2: Extract page elements
        print(f"  [WebAgent] Iteration {iteration + 1}: extracting page elements...")
        page_data = await bridge._send("extractPage", {"tabId": tab_id}, timeout=15)
        page_data.pop("id", None)
        page_data.pop("success", None)

        elements = page_data.get("elements", [])
        page_url = page_data.get("url", "")
        page_title = page_data.get("title", "")
        page_text = page_data.get("pageText", "")[:500]

        if not elements:
            results_log.append("No interactive elements found on page")
            break

        # Step 3: Build compact element list for LLM
        el_lines = []
        for i, el in enumerate(elements):
            parts = [f"[{i}]", el.get("tag", "?")]
            if el.get("type"):
                parts.append(f'type="{el["type"]}"')
            parts.append(f'selector="{el.get("selector","")}"')
            if el.get("label"):
                parts.append(f'label="{el["label"]}"')
            if el.get("placeholder"):
                parts.append(f'placeholder="{el["placeholder"]}"')
            if el.get("required"):
                parts.append("REQUIRED")
            if el.get("options"):
                opts = ", ".join(f'{o["value"]}={o["text"]}' for o in el["options"][:10])
                parts.append(f"options=[{opts}]")
            if el.get("value"):
                parts.append(f'value="{el["value"]}"')
            if el.get("href"):
                parts.append(f'href="{el["href"]}"')
            el_lines.append(" ".join(parts))

        elements_text = "\n".join(el_lines)

        user_msg = (
            f"TASK: {task}\n\n"
            f"PAGE URL: {page_url}\n"
            f"PAGE TITLE: {page_title}\n\n"
            f"VISIBLE TEXT (first 500 chars):\n{page_text}\n\n"
            f"INTERACTIVE ELEMENTS:\n{elements_text}"
        )

        print(f"  [WebAgent] Sending {len(elements)} elements to LLM...")

        # Step 4: Call Gemini for action plan (1 LLM call)
        try:
            response = gemini_client.models.generate_content(
                model=model_name,
                contents=user_msg,
                config=genai_types.GenerateContentConfig(
                    system_instruction=_WEB_AGENT_PROMPT,
                    temperature=0.1,
                    max_output_tokens=8192,
                ),
            )
            # Extract text safely
            raw_text = ""
            try:
                raw_text = response.text
            except Exception:
                for c in response.candidates:
                    for p in c.content.parts:
                        if hasattr(p, "text") and p.text:
                            raw_text = p.text
                            break

        except Exception as e:
            results_log.append(f"LLM call failed: {e}")
            break

        # Parse actions JSON
        raw_text = raw_text.strip()
        # Strip markdown code fences if present
        if raw_text.startswith("```"):
            raw_text = "\n".join(raw_text.split("\n")[1:])
        if raw_text.endswith("```"):
            raw_text = raw_text[:-3]
        raw_text = raw_text.strip()

        try:
            actions = json.loads(raw_text)
        except json.JSONDecodeError:
            results_log.append(f"LLM returned invalid JSON: {raw_text[:200]}")
            break

        if not isinstance(actions, list):
            actions = [actions]

        # Loop protection: identical actions
        current_actions_str = json.dumps(actions, sort_keys=True)
        if current_actions_str == last_actions_str:
            results_log.append("Detected action loop (same actions as last step). Stopping.")
            print("  [WebAgent] Detected action loop. Stopping.")
            break
        last_actions_str = current_actions_str

        # Split action types up front
        done_actions   = [a for a in actions if a.get("action") == "done"]
        nav_actions    = [a for a in actions if a.get("action") == "navigate"]
        dom_actions    = [a for a in actions if a.get("action") in (
            "fill", "fill_react", "click", "enter", "select", "check", "scroll"
        )]

        # Stall detection: if every non-done action this round is just "scroll"
        non_scroll = [a for a in actions if a.get("action") not in ("scroll", "done")]
        if not non_scroll and not done_actions:
            consecutive_scroll_only += 1
            if consecutive_scroll_only >= 2:
                results_log.append("Stalled: agent only scrolling with no progress. Stopping.")
                print("  [WebAgent] Scroll-only stall detected. Stopping.")
                break
        else:
            consecutive_scroll_only = 0

        # Handle navigate action (goes to a new URL, then restart the loop)
        if nav_actions:
            new_url = nav_actions[0].get("url", "")
            if new_url:
                nav_result = await bridge._send("navigate", {"url": new_url, "newTab": False})
                tab_id = nav_result.get("tabId")
                results_log.append(f"Navigated to {new_url}")
                await asyncio.sleep(5)  # wait for page to load
                continue

        # ── Step 5: Execute DOM actions FIRST, then honor done ──────────
        # IMPORTANT: done_actions are processed AFTER DOM actions so that
        # [fill_react(input, text), enter(input), done("sent")] works correctly
        # — the fill and enter happen before we stop the loop.
        exec_result = {"performed": 0, "total": 0, "results": []}
        if dom_actions:
            print(f"  [WebAgent] Executing {len(dom_actions)} actions...")
            exec_result = await bridge._send("performActions", {
                "tabId": tab_id,
                "actions": dom_actions,
            }, timeout=30)
            exec_result.pop("id", None)
            exec_result.pop("success", None)

            performed = exec_result.get("performed", 0)
            total = exec_result.get("total", len(dom_actions))
            results_log.append(f"Executed {performed}/{total} actions")
            print(f"  [WebAgent] Executed {performed}/{total} actions")

            # Log individual results
            for r in exec_result.get("results", []):
                if r.get("ok"):
                    action_desc = f"{r['action']}({r['selector']}"
                    if r.get("value"):
                        action_desc += f", \"{r['value']}\""
                    action_desc += ")"
                    results_log.append(f"  ✓ {action_desc}")
                else:
                    results_log.append(f"  ✗ {r['action']}({r['selector']}): {r.get('error')}")

            # Wait for page to update after actions
            await asyncio.sleep(3)

        # ── Now honor done (LLM signals task is complete after its actions) ──
        if done_actions:
            msg = done_actions[0].get("message", "Task completed")
            results_log.append(f"✓ {msg}")
            print(f"  [WebAgent] Done: {msg}")
            break

        # ── Auto-done detection ───────────────────────────────────────────
        # 1. YouTube watch page → video is playing, always stop.
        # 2. One-shot social action (like/follow/retweet) + successful click → stop.
        _ONE_SHOT_KEYWORDS = (
            "like", "heart", "follow", "retweet", "share",
            "bookmark", "save", "subscribe", "upvote", "vote",
        )
        task_lower = task.lower()
        is_one_shot_task = any(kw in task_lower for kw in _ONE_SHOT_KEYWORDS)
        had_successful_click = any(
            r.get("ok") and r.get("action") == "click"
            for r in exec_result.get("results", [])
        )

        try:
            post_data = await bridge._send("extractPage", {"tabId": tab_id}, timeout=10)
            current_url = post_data.get("url", "")
            current_title = post_data.get("title", "")
            _DONE_URL_PATTERNS = ("/watch?v=", "music.youtube.com/watch", "/v/")
            if any(p in current_url for p in _DONE_URL_PATTERNS):
                results_log.append(f"  ✓ Video playing: {current_title}")
                print(f"  [WebAgent] Auto-done: landed on watch page — {current_title}")
                break
            if is_one_shot_task and had_successful_click:
                results_log.append(f"  ✓ One-shot action completed (auto-done)")
                print(f"  [WebAgent] Auto-done: one-shot social action completed")
                break
        except Exception:
            # Non-fatal — but still apply one-shot auto-done without URL check
            if is_one_shot_task and had_successful_click:
                results_log.append(f"  ✓ One-shot action completed (auto-done)")
                print(f"  [WebAgent] Auto-done: one-shot social action completed")
                break

        if not dom_actions and not nav_actions and not done_actions:
            results_log.append("No executable actions returned by LLM")
            break
    else:
        iteration = max_iterations - 1  # loop completed without break

    summary = "\n".join(results_log)
    return f"[WebAgent] Completed in {iteration + 1} iteration(s):\n{summary}"
