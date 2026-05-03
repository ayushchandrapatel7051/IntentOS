"""
OpenClaw Skill — Agentic Chrome Extension Bridge v3.1
====================================================
Fixes in v3.1:
  - _send() retries up to 3× on disconnect — no mid-execution command loss
  - execute() propagates verified=False as a raised VerificationError so
    the Executor can treat unverified Gmail/Calendar saves as real failures
  - _format_result() surfaces verified status and meetLink in result strings
  - composeMail / createEvent return verified field checked by executor
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

WEB_AGENT_LLM_TIMEOUT = 25.0
WEB_AGENT_MAX_ELEMENTS = 60
WEB_AGENT_MAX_TASK_CHARS = 800
WEB_AGENT_MAX_PAGE_TEXT_CHARS = 350

try:
    import websockets
    import websockets.server
    _WS_OK = True
except ImportError:
    websockets = None
    _WS_OK = False


# ---------------------------------------------------------------------------
# Custom exception for unverified actions
# ---------------------------------------------------------------------------

class VerificationError(RuntimeError):
    """Raised when the extension completes an action but cannot verify success."""
    pass


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
    chrome = _find_chrome()
    if not chrome:
        logger.warning("[ExtensionBridge] Chrome not found -- cannot auto-open window")
        return
    logger.info(f"[ExtensionBridge] Forcing new Chrome window: {url}")
    subprocess.Popen([chrome, "--new-window", url], shell=False)
    await asyncio.sleep(4)


async def _try_subprocess_navigation(command: str, params: dict) -> Optional[str]:
    chrome = _find_chrome()
    if not chrome:
        return None

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
        if params.get("autoplay", True):
            return None
        from urllib.parse import quote
        query = params.get("query", "")
        url = f"https://www.youtube.com/results?search_query={quote(query)}"
        await asyncio.to_thread(_launch, url)
        return url

    # NOTE: composeMail / sendMail are intentionally NOT handled here.
    # They must travel through the extension WebSocket path so that
    # background.js can click Send and verify "Message sent" confirmation.
    # Returning early here would open the compose window but never send.

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

    return None


# ---------------------------------------------------------------------------
# Action name normalisation
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

    # Direct content extraction (no LLM)
    "get_page_text":   "getPageText",
    "getpagetext":     "getPageText",
    "page_text":       "getPageText",
    "pagetext":        "getPageText",
    "extract_text":    "getPageText",   # allow planner to use extract_text as action name
    "extracttext":     "getPageText",
}


def _normalise(action: str) -> str:
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
        if not _WS_OK:
            raise ImportError("websockets not installed — run: pip install websockets")
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
            pass
        except Exception as e:
            logger.error(f"[ExtensionBridge] Connection error: {type(e).__name__}: {e}")
        finally:
            if self.extension_ws is websocket:
                disconnect_error = ConnectionError("Chrome extension disconnected before responding")
                for fut in list(self._response_futures.values()):
                    if not fut.done():
                        fut.set_exception(disconnect_error)
                self._response_futures.clear()
                self.extension_ws = None
                self._is_connected = False
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
        """
        Send a command to the extension and await its response.

        Retries up to 3× on disconnect, waiting for MV3 service worker to
        reconnect between attempts. A command is NEVER silently dropped —
        if all retries fail, a ConnectionError is raised so the caller can
        handle it explicitly.
        """
        MAX_ATTEMPTS = 3
        last_err: Exception = None

        for attempt in range(MAX_ATTEMPTS):
            # Wait for connection (handles MV3 idle suspend)
            if not self.is_connected:
                logger.debug(
                    f"[ExtensionBridge] '{command}' attempt {attempt+1}: "
                    f"not connected, waiting up to 5s..."
                )
                for _ in range(10):
                    if self.is_connected:
                        break
                    await asyncio.sleep(0.5)
                if not self.is_connected:
                    last_err = ConnectionError(
                        "Chrome extension is not connected to IntentOS. "
                        "Please: 1) Open Chrome, 2) Install the OpenClaw extension from "
                        "chrome://extensions/ → Load Unpacked → IntentOS/chrome-extension/, "
                        "3) Reload this page."
                    )
                    if attempt < MAX_ATTEMPTS - 1:
                        await asyncio.sleep(1)
                        continue
                    raise last_err

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
                response = await asyncio.wait_for(fut, timeout=timeout)
                # Extension reported a logical failure (success=false)
                if response.get("success") is False:
                    error = response.get("error", "Unknown extension error")
                    raise RuntimeError(f"Extension error: {error}")
                return response

            except (ConnectionError, websockets.ConnectionClosed) as e:
                last_err = e
                self._response_futures.pop(msg_id, None)
                if attempt < MAX_ATTEMPTS - 1:
                    logger.warning(
                        f"[ExtensionBridge] '{command}' disconnected on attempt "
                        f"{attempt+1}/{MAX_ATTEMPTS}, retrying in 1s..."
                    )
                    await asyncio.sleep(1)
                    # Wait up to 3s for MV3 worker to reconnect
                    for _ in range(6):
                        if self.is_connected:
                            break
                        await asyncio.sleep(0.5)
                    continue
                raise ConnectionError(
                    f"Chrome extension disconnected during '{command}' "
                    f"after {MAX_ATTEMPTS} attempts: {e}"
                ) from e

            except asyncio.TimeoutError as e:
                self._response_futures.pop(msg_id, None)
                raise TimeoutError(
                    f"Extension command '{command}' timed out after {timeout:.0f}s"
                ) from e

            finally:
                self._response_futures.pop(msg_id, None)

        # Should never reach here, but be explicit
        raise last_err or RuntimeError(f"'{command}' failed after {MAX_ATTEMPTS} attempts")

    # ------------------------------------------------------------------
    # Main entry point — called by Executor
    # ------------------------------------------------------------------

    async def execute(self, action: str, params: dict) -> str:
        """
        Dispatch an action from the AI agent to the Chrome extension.

        Raises VerificationError for commands where the extension explicitly
        reports verified=False (e.g. Gmail send not confirmed, Calendar event
        save not detected). The Executor treats this as a step failure.
        """
        command = _normalise(action)
        logger.info(f"[ExtensionBridge] {action} -> {command}({json.dumps(params)})")

        params = _remap_params(command, params)

        # Subprocess-first navigation
        subprocess_result = await _try_subprocess_navigation(command, params)
        if subprocess_result is not None:
            for _ in range(16):
                if self.is_connected:
                    break
                await asyncio.sleep(0.5)
            await asyncio.sleep(1)
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

        # Extension-based commands
        last_err: Exception = None
        for attempt in range(2):
            try:
                result = await self._send(command, params)
                result.pop("id", None)

                # ── Verified field check ────────────────────────────────
                # Commands that mutate state (send mail, save event) include
                # verified=True/False. Treat verified=False as a hard failure
                # so the Executor retries or flags the step.
                verified = result.get("verified")
                success  = result.get("success", True)

                # Commands that MUST be verified before we return success
                MUST_VERIFY = {"composeMail", "sendMail", "createEvent", "scheduleMeet"}

                if command in MUST_VERIFY and verified is False:
                    status = result.get("status", "unknown")
                    error  = result.get("error", f"Action completed but could not be verified (status={status})")
                    raise VerificationError(
                        f"[{command}] Verification failed: {error}"
                    )

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
# Param remapping
# ---------------------------------------------------------------------------

def _remap_params(command: str, params: dict) -> dict:
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

    if "tabId" in out:
        try:
            tid = int(out["tabId"])
            if tid <= 0:
                del out["tabId"]
        except (TypeError, ValueError):
            del out["tabId"]
    return out


# ---------------------------------------------------------------------------
# Result formatting
# ---------------------------------------------------------------------------

def _format_result(command: str, result: dict) -> str:
    if not result:
        return f"[extension] {command} completed"

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

    if command in ("composeMail", "sendMail"):
        status   = result.get("status", "")
        verified = result.get("verified", False)
        attempt  = result.get("attempt", "")
        if status == "sent" and verified:
            return (
                f"[Gmail] ✓ Email sent and verified"
                f" (attempt {attempt}) — to={result.get('to')} subject={result.get('subject')}"
            )
        return f"[Gmail] Compose window opened (to={result.get('to','')})"

    if command in ("createEvent", "scheduleMeet"):
        status   = result.get("status", "event_form_opened")
        verified = result.get("verified", False)
        # Support both field names (meetLink from v3.1, meet_link from v3)
        meet_link = result.get("meetLink") or result.get("meet_link") or ""
        base = (
            f"[Calendar] {status} — "
            f"'{result.get('title','New Event')}' on {result.get('date','')} {result.get('time','')}"
        )
        if verified:
            base += " ✓ verified"
        if meet_link:
            base += f" | meet_link={meet_link}"
        return base

    if command == "joinMeet":
        return f"[Meet] Join attempted for: {result.get('url','')}"

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

    if command == "getPageText":
        text = result.get("text", "")
        sel  = result.get("selector", "body")
        length = result.get("length", len(text))
        # Return the raw text so downstream steps (write_file, messaging) get the content
        if text:
            return text
        return f"[getPageText] No text found for selector '{sel}'"

    if command == "performActions":
        r = result
        return f"[WebAgent] Performed {r.get('performed',0)}/{r.get('total',0)} actions"

    return json.dumps(result, indent=2) if result else f"[extension] {command} completed"


def _shorten(value, limit: int) -> str:
    text = "" if value is None else str(value)
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) <= limit:
        return text
    if limit <= 3:
        return text[:limit]
    return text[: limit - 3].rstrip() + "..."


def _format_web_element(el: dict, index: int) -> str:
    parts = [f"[{index}]", _shorten(el.get("tag", "?"), 16)]
    if el.get("type"):
        parts.append(f'type="{_shorten(el["type"], 24)}"')
    parts.append(f'selector="{_shorten(el.get("selector", ""), 140)}"')
    if el.get("label"):
        parts.append(f'label="{_shorten(el["label"], 80)}"')
    if el.get("placeholder"):
        parts.append(f'placeholder="{_shorten(el["placeholder"], 80)}"')
    if el.get("required"):
        parts.append("required=true")
    if el.get("options"):
        opts = ", ".join(
            f'{_shorten(o.get("value", ""), 24)}={_shorten(o.get("text", ""), 36)}'
            for o in el["options"][:5]
        )
        parts.append(f"options=[{opts}]")
    value = el.get("value")
    if value and el.get("type") not in ("password", "hidden"):
        parts.append(f'value="{_shorten(value, 50)}"')
    if el.get("href"):
        parts.append(f'href="{_shorten(el["href"], 100)}"')
    return " ".join(parts)


def _parse_actions(raw_text: str) -> list:
    raw = raw_text.strip()
    raw = re.sub(r"^```(?:json)?\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw.strip())
    try:
        actions = json.loads(raw)
    except json.JSONDecodeError:
        match = re.search(r"\[.*\]", raw, re.DOTALL)
        if not match:
            raise
        actions = json.loads(match.group())
    return actions if isinstance(actions, list) else [actions]


def _youtube_search_request(task: str) -> Optional[dict]:
    text = task or ""
    lower = text.lower()
    if "search" not in lower or "play" not in lower:
        return None
    if "youtube" not in lower and "video" not in lower:
        return None

    quoted = re.search(r"['\"]([^'\"]+)['\"]", text)
    if quoted:
        query = quoted.group(1).strip()
    else:
        query_match = re.search(
            r"search\s+(?:for\s+)?(.+?)(?:\s+and\s+play|\s+play\s+the|\s+on\s+youtube|$)",
            text,
            re.IGNORECASE,
        )
        query = query_match.group(1).strip(" .") if query_match else ""

    if not query:
        return None

    ordinals = {
        "first": 1, "1st": 1,
        "second": 2, "2nd": 2,
        "third": 3, "3rd": 3,
        "fourth": 4, "4th": 4,
        "fifth": 5, "5th": 5,
    }
    index = 1
    for word, value in ordinals.items():
        if re.search(rf"\b{re.escape(word)}\b", lower):
            index = value
            break
    digit = re.search(r"\b(\d+)(?:st|nd|rd|th)?\s+(?:video|result)\b", lower)
    if digit:
        index = max(1, int(digit.group(1)))

    return {"query": query, "videoIndex": index, "autoplay": True}


# ---------------------------------------------------------------------------
# Agentic Web Interaction Loop
# ---------------------------------------------------------------------------

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
- {"action":"extract_text"}  ← NO selector needed. Captures ALL visible text from the current page. Use when task says "extract content", "read page", "save page text", "get article text", etc.
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


async def run_web_agent(bridge: "ExtensionBridge", task: str, url: str = None,
                        tab_id: int = None,
                        gemini_client=None, model_name: str = "gemini-2.5-flash",
                        max_iterations: int = 5) -> str:
    if not bridge.is_connected:
        raise ConnectionError("Chrome extension not connected")

    if not gemini_client:
        raise RuntimeError("Gemini client required for web_agent — check your .env auth config")

    try:
        from google.genai import types as genai_types
    except ImportError:
        raise ImportError("google-genai not installed")

    youtube_request = _youtube_search_request(task)
    if youtube_request:
        result = await bridge._send("searchYouTube", youtube_request, timeout=45)
        result.pop("id", None)
        result.pop("success", None)
        if result.get("warning") or result.get("playing") is False:
            raise RuntimeError(_format_result("searchYouTube", result))
        return "[WebAgent] Completed via YouTube shortcut:\n" + _format_result("searchYouTube", result)

    results_log = []
    last_actions_str = ""
    consecutive_scroll_only = 0
    done_actions = []
    completed = False
    made_progress = False
    failure_reason = ""

    if tab_id:
        results_log.append(f"Using existing tab {tab_id}")
        try:
            await bridge._send("switchTab", {"tabId": tab_id})
        except Exception:
            pass
        await asyncio.sleep(5)
        made_progress = True
    elif url and not url.endswith("=") and "..." not in url and url != "https://":
        nav_result = await bridge._send("navigate", {"url": url, "newTab": False})
        tab_id = nav_result.get("tabId")
        results_log.append(f"Navigated to {url}")
        await asyncio.sleep(5)
        made_progress = True

    for iteration in range(max_iterations):
        print(f"  [WebAgent] Iteration {iteration + 1}: extracting page elements...")
        page_data = await bridge._send("extractPage", {"tabId": tab_id}, timeout=25)
        page_data.pop("id", None)
        page_data.pop("success", None)

        elements = page_data.get("elements", [])[:WEB_AGENT_MAX_ELEMENTS]
        page_url = page_data.get("url", "")
        page_title = page_data.get("title", "")
        page_text = _shorten(page_data.get("pageText", ""), WEB_AGENT_MAX_PAGE_TEXT_CHARS)

        if not elements:
            failure_reason = "No interactive elements found on page"
            results_log.append(failure_reason)
            break

        el_lines = [_format_web_element(el, i) for i, el in enumerate(elements)]
        elements_text = "\n".join(el_lines)

        user_msg = (
            f"TASK: {_shorten(task, WEB_AGENT_MAX_TASK_CHARS)}\n\n"
            f"PAGE URL: {page_url}\n"
            f"PAGE TITLE: {_shorten(page_title, 160)}\n\n"
            f"VISIBLE TEXT:\n{page_text}\n\n"
            f"INTERACTIVE ELEMENTS:\n{elements_text}"
        )

        print(f"  [WebAgent] Sending {len(elements)} elements to LLM...")

        try:
            response = await asyncio.wait_for(
                asyncio.to_thread(
                    gemini_client.models.generate_content,
                    model=model_name,
                    contents=user_msg,
                    config=genai_types.GenerateContentConfig(
                        system_instruction=_WEB_AGENT_PROMPT,
                        temperature=0.1,
                        max_output_tokens=768,
                    ),
                ),
                timeout=WEB_AGENT_LLM_TIMEOUT,
            )
            raw_text = ""
            try:
                raw_text = response.text
            except Exception:
                for c in response.candidates:
                    for p in c.content.parts:
                        if hasattr(p, "text") and p.text:
                            raw_text = p.text
                            break

        except asyncio.TimeoutError:
            failure_reason = f"LLM call timed out after {WEB_AGENT_LLM_TIMEOUT:.0f}s"
            results_log.append(failure_reason)
            break
        except Exception as e:
            failure_reason = f"LLM call failed: {e}"
            results_log.append(failure_reason)
            break

        try:
            actions = _parse_actions(raw_text)
        except json.JSONDecodeError:
            failure_reason = f"LLM returned invalid JSON: {raw_text[:200]}"
            results_log.append(failure_reason)
            break

        actions = [a for a in actions if isinstance(a, dict)]
        if not actions:
            failure_reason = "LLM returned no usable actions"
            results_log.append(failure_reason)
            break

        current_actions_str = json.dumps(actions, sort_keys=True)
        if current_actions_str == last_actions_str:
            failure_reason = "Detected action loop (same actions as last step)."
            results_log.append(failure_reason)
            print("  [WebAgent] Detected action loop. Stopping.")
            break
        last_actions_str = current_actions_str

        done_actions   = [a for a in actions if a.get("action") == "done"]
        nav_actions    = [a for a in actions if a.get("action") == "navigate"]
        dom_actions    = [a for a in actions if a.get("action") in (
            "fill", "fill_react", "click", "enter", "select", "check", "scroll",
            "extract_text",  # special no-selector action to capture full page text
        )]

        non_scroll = [a for a in actions if a.get("action") not in ("scroll", "done")]
        if not non_scroll and not done_actions:
            consecutive_scroll_only += 1
            if consecutive_scroll_only >= 2:
                failure_reason = "Stalled: agent only scrolled with no progress."
                results_log.append(failure_reason)
                print("  [WebAgent] Scroll-only stall detected. Stopping.")
                break
        else:
            consecutive_scroll_only = 0

        if nav_actions:
            new_url = nav_actions[0].get("url", "")
            if new_url:
                nav_result = await bridge._send("navigate", {"url": new_url, "newTab": False})
                tab_id = nav_result.get("tabId")
                made_progress = True
                results_log.append(f"Navigated to {new_url}")
                await asyncio.sleep(5)
                continue

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
            if performed:
                made_progress = True
            results_log.append(f"Executed {performed}/{total} actions")
            print(f"  [WebAgent] Executed {performed}/{total} actions")

            for r in exec_result.get("results", []):
                if r.get("ok"):
                    action_desc = f"{r['action']}({r['selector']}"
                    if r.get("value"):
                        action_desc += f", \"{r['value']}\""
                    action_desc += ")"
                    results_log.append(f"  ✓ {action_desc}")
                else:
                    results_log.append(f"  ✗ {r['action']}({r['selector']}): {r.get('error')}")


            if total and performed < total:
                failure_reason = f"Only performed {performed}/{total} DOM actions"
                break

            await asyncio.sleep(3)

        # Handle extract_text if performed
        extracted_text = None
        for r in exec_result.get("results", []):
            if r.get("action") == "extract_text" and r.get("ok") and r.get("text"):
                extracted_text = r["text"]
                results_log.append(f"  ✓ extract_text: captured {len(extracted_text)} chars")
                break

        if done_actions:
            msg = done_actions[0].get("message", "Task completed")
            completed = True
            results_log.append(f"✓ {msg}")
            print(f"  [WebAgent] Done: {msg}")
            if extracted_text:
                return extracted_text
            break

        if extracted_text:
            return extracted_text

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
                completed = True
                results_log.append(f"  ✓ Video playing: {current_title}")
                print(f"  [WebAgent] Auto-done: landed on watch page — {current_title}")
                break
            if is_one_shot_task and had_successful_click:
                completed = True
                results_log.append(f"  ✓ One-shot action completed (auto-done)")
                print(f"  [WebAgent] Auto-done: one-shot social action completed")
                break
        except Exception:
            if is_one_shot_task and had_successful_click:
                completed = True
                results_log.append(f"  ✓ One-shot action completed (auto-done)")
                print(f"  [WebAgent] Auto-done: one-shot social action completed")
                break

        if not dom_actions and not nav_actions and not done_actions:
            failure_reason = "No executable actions returned by LLM"
            results_log.append(failure_reason)
            break
    else:
        iteration = max_iterations - 1


    summary = "\n".join(results_log)
    if completed:
        return f"[WebAgent] Completed in {iteration + 1} iteration(s):\n{summary}"
    if failure_reason:
        raise RuntimeError(f"[WebAgent] Stopped in iteration {iteration + 1}: {failure_reason}\n{summary}")
    if made_progress:
        raise RuntimeError(f"[WebAgent] Reached iteration limit before completion:\n{summary}")
    raise RuntimeError(f"[WebAgent] Stopped without completing the task:\n{summary}")