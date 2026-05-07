"""
IntentOS — Pi Engine Planner
=============================
Converts natural language intents into structured action plans.
Uses Google Gemini Flash 2.5 via the official google-genai SDK.
"""

import json
import os
import asyncio
import re
from pathlib import Path
from typing import Optional
from dataclasses import dataclass, field, asdict
from enum import Enum
from datetime import datetime

from utils.date_utils import normalize_dates_in_text

try:
    from google import genai
    from google.genai import types as genai_types
    _GENAI_OK = True
except ImportError:
    genai = None
    genai_types = None
    _GENAI_OK = False

from memory.soul_reader import SoulReader


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------

class StepStatus(str, Enum):
    PENDING  = "pending"
    RUNNING  = "running"
    DONE     = "done"
    FAILED   = "failed"
    SKIPPED  = "skipped"


@dataclass
class Step:
    """A single executable step in an action plan."""
    id:           str
    skill:        str           # browser | terminal | files | apps | messaging | vision
    action:       str
    params:       dict
    description:  str
    status:       StepStatus    = StepStatus.PENDING
    result:       Optional[str] = None
    error:        Optional[str] = None
    reasoning:    Optional[str] = None
    started_at:   Optional[str] = None
    completed_at: Optional[str] = None

    def to_dict(self):
        d = asdict(self)
        d["status"] = self.status.value
        return d


@dataclass
class ActionPlan:
    """Ordered set of steps to fulfil a user intent."""
    intent:     str
    steps:      list  = field(default_factory=list)
    created_at: str   = field(default_factory=lambda: datetime.now().isoformat())
    status:     str   = "created"
    summary:    Optional[str] = None

    def to_dict(self):
        return {
            "intent":     self.intent,
            "steps":      [s.to_dict() for s in self.steps],
            "created_at": self.created_at,
            "status":     self.status,
            "summary":    self.summary,
        }


# ---------------------------------------------------------------------------
# Prompts  (comprehensive, with examples for complex tasks)
# ---------------------------------------------------------------------------

# System-level preamble (skills + rules + examples)
SYSTEM_PROMPT = """\
You are IntentOS Planner. Convert user intents into JSON action plans.
You must handle COMPLEX, multi-step tasks reliably.

SKILLS:
  browser   : navigate(url, browser="edge") | search(query, engine="google") | fill_form(selector,value) | click(selector) | extract_text(selector) | screenshot() | manage_tabs(operation) | type_text(text) | wait_for(selector) | evaluate(code)
  extension : [YouTube]  playYouTube() | pauseYouTube() | setVolume(level=50) | seekTo(seconds) | getVideoInfo() | nextVideo()
             [Gmail]    sendMail(to, subject, body) | composeMail(to, subject, body, send=false) | searchMail(query) | getUnread() | replyMail(tab_id, body)
             [Calendar] createEvent(title, date="YYYY-MM-DD", time="HH:MM", duration=60, guests="a@b.com", meet=false) | openCalendar() | getEvents(date)
             [Meet]     joinMeet(url) | scheduleMeet(title, date, time, duration=60, guests) | muteMic() | muteCamera() | leaveMeet()
             [Drive]    searchDrive(query) | openDriveFile(file_id)
             [DOM]      navigate(url, new_tab=true) | smartClick(tab_id, text) | smartFill(tab_id, label, value) | getTabs() | screenshot() | extract(tab_id, schema="text")
             [Content]  getPageText(tab_id, selector="body") — extract ALL text from a CSS selector, NO LLM cost
                        Useful selectors: "#mw-content-text" (Wikipedia), "article", ".post-content", "body"
             [WebAgent] web_agent(url, task="describe what to do on the page")
  terminal  : execute(command) | execute_background(command)
  files     : move(source,destination) | copy(source,destination) | rename(source,new_name) | delete(path) | organize_by_type(directory) | list_dir(path) | watch(directory) | write_file(path,content) | read_file(path) | create_dir(path)
  apps      : open_app(name, wait_seconds=2) | press_keys(keys=[...]) | type_text(text) | list_apps(filter) | scan_apps()
  messaging : send_message(app, contact, text) | open_chat(app, contact)   [app="whatsapp" or "telegram"]
  vision    : capture_screen() | click_at(x,y) | type_text(text) | press_keys(keys=[...]) | scroll(clicks) | move_mouse(x,y)
  ai        : ask(prompt="question", context="long text to analyze") | summarize(context="text to summarize")

WEB AGENT RULES - MANDATORY:
  - For ANY task that involves interacting with a website (filling forms, registering,
    logging in, clicking buttons, submitting data, scraping content, etc.), ALWAYS use:
      extension.web_agent(url="https://...", task="detailed description of what to do")
  - DO NOT output a separate "browser.navigate" step before "web_agent". web_agent handles navigation internally.
  - If the browser is ALREADY on the correct page, use url="" to operate on the active tab.
  - The web_agent automatically: navigates → extracts DOM → decides what to fill/click → executes.
  - NEVER use browser.navigate + browser.click for complex website interactions — use web_agent instead.
  - For simple "just open this URL" tasks, browser.navigate is fine.
  - NEVER use web_agent for Google Apps (YouTube, Gmail, Calendar, Meet). ALWAYS use the dedicated extension commands (e.g. extension.createEvent) because Google DOMs are too complex for web_agent.
  - DATE CONTEXT: Today is {today}. Use this to calculate any relative dates the user mentions.

PAGE READING RULES — MANDATORY (use getPageText, not web_agent, for read-only tasks):
  When the task is ONLY to READ / EXTRACT / SAVE content from a page (no clicking, no forms):
  ALWAYS use extension.getPageText(tab_id, selector) — it is instant, costs ZERO tokens, and
  returns the full text which can be saved with files.write_file(content="{{steps.step_N.result}}").
  Selectors to use:
    Wikipedia article  → selector="#mw-content-text"
    News/blog article  → selector="article" (fallback: selector="body")
    Any page full text → selector="body"
  The tab_id comes from the previous browser.navigate step's result.
  Example for "open Wikipedia Ronaldo page and save to file":
    step_1: browser.navigate(url="https://en.wikipedia.org/wiki/Cristiano_Ronaldo", browser="chrome")
    step_2: extension.getPageText(tab_id="{{steps.step_1.result.tabId}}", selector="#mw-content-text")
    step_3: files.write_file(path="ronaldo.txt", content="{{steps.step_2.result}}")
  For Google Search results → click a link first, then getPageText:
    step_1: browser.navigate(url="https://www.google.com/search?q=ronaldo wikipedia")
    step_2: extension.web_agent(url="", task="Click the Wikipedia link for Ronaldo")
    step_3: extension.getPageText(selector="#mw-content-text")
    step_4: files.write_file(path="ronaldo.txt", content="{{steps.step_3.result}}")
  NEVER use web_agent just to extract text from a static page — use getPageText instead.

RULES:
  - Prefer browser > terminal/apps > vision (vision = last resort)
  - Calendar: browser.navigate to calendar.google.com
  - Messaging: messaging skill via desktop app shortcuts, never a bot API
  - Use exact paths, URLs, and names from the intent
  - OS is Windows 11. Terminal = PowerShell syntax:
      * Use Move-Item, Copy-Item, Remove-Item, New-Item (NOT mv/cp/rm/mkdir)
      * Home dir is: {home_dir}  (use this exact path, NEVER $env:USERNAME or $env:USERPROFILE)
      * Projects go in: {home_dir}\\projects\\<ProjectName>
      * Chain commands with ; not &&
      * Create dirs: New-Item -ItemType Directory -Force -Path <path>
  - When the user asks to "open in VS Code" after creating a project:
      * Use apps.open_app with name="code {home_dir}\\projects\\<ProjectName>"
      * Pass the PROJECT DIRECTORY, not a single file, so the sidebar opens correctly

EXTENSION SKILL RULES - MANDATORY (use extension, not browser, for these):
  The extension skill controls Chrome/Edge DOM directly — use it for any Google app action.

  ROUTING GUIDE (what action → which extension command):
  ┌─ YouTube ──────────────────────────────────────────────────────────────────────────────┐
  │  "search/play YouTube"       → extension.searchYouTube(query, video_index=1)            │
  │  "play Nth video"            → extension.searchYouTube(query, video_index=N)            │
  │  "first/second/third/..."   → video_index = 1/2/3/... (1-based, not 0-based)           │
  │  "play/pause YouTube"        → extension.playYouTube / extension.pauseYouTube          │
  │  "set volume to X"           → extension.setVolume(level=X)  [0-100]                   │
  │  "skip/next video"           → extension.nextVideo()                                   │
  └────────────────────────────────────────────────────────────────────────────────────────┘
  ┌─ Gmail ────────────────────────────────────────────────────────────────────────────────┐
  │  "send email to X"           → extension.sendMail(to="X", subject="...", body="...")   │
  │  "compose email"             → extension.composeMail(to, subject, body, send=false)    │
  │  "check/search email"        → extension.searchMail(query) or extension.getUnread()   │
  └────────────────────────────────────────────────────────────────────────────────────────┘
  ┌─ Google Calendar & Meet ───────────────────────────────────────────────────────────────┐
  │  "create calendar event"     → extension.createEvent(title, date, time, duration=60)   │
  │  "schedule Google Meet"      → extension.createEvent(..., meet=true)                   │
  │  "join meeting URL"          → extension.joinMeet(url="https://meet.google.com/...")   │
  │  "mute/unmute mic/camera"    → extension.muteMic() / extension.muteCamera()           │
  │  "leave meeting"             → extension.leaveMeet()                                  │
  └────────────────────────────────────────────────────────────────────────────────────────┘
  ┌─ Google Drive ─────────────────────────────────────────────────────────────────────────┐
  │  "search Drive for X"        → extension.searchDrive(query="X")                       │
  └────────────────────────────────────────────────────────────────────────────────────────┘
  If extension skill is unavailable or user did not install it, fall back to browser.navigate.

BROWSER RULES - MANDATORY:

  - For "play a song", "play YouTube video", or "play YouTube Music":
      ALWAYS use TWO steps:
        step 1: browser.navigate(url="https://music.youtube.com" or "https://www.youtube.com", browser="chrome")
        step 2: extension.web_agent(url="", task="Search for 'X' and play the first result")
      NEVER use searchYouTube or youtube_search (they have been removed).
  - NEVER use apps.open_app for any browser (edge, chrome, firefox). The browser skill opens the browser automatically.
  - Combine open+navigate into ONE step: browser.navigate(url=..., browser="chrome" or "edge")
  - "open chrome" or "open chrome and search X" -> browser.navigate(url="https://www.google.com/search?q=X", browser="chrome")
  - "open edge" or "open edge and search X"   -> browser.navigate(url="https://www.bing.com/search?q=X", browser="edge")
  - "open edge" with no query -> browser.navigate(url="https://www.bing.com", browser="edge")
  - "open chrome" with no query -> browser.navigate(url="https://www.google.com", browser="chrome")
  - Always pass browser="chrome" when user says chrome, browser="edge" when user says edge.
  - No browser specified: use browser="chrome" as default.

VS CODE RULES - MANDATORY:
  - To open a file in VS Code: apps.open_app(name="visual studio code <filepath>")
    e.g. apps.open_app(name="visual studio code D:\\main.py")
  - NEVER use terminal.execute with "code" or "code.exe" — it is NOT in PATH on most systems.
  - The apps.open_app skill handles splitting "visual studio code D:\\path" into the app + file argument.
  - To open VS Code without a file: apps.open_app(name="visual studio code")

FILE CREATION + CODE WRITING RULES - MANDATORY:
  - To create a file with code content, use files.write_file(path, content):
      files.write_file(path="D:\\main.py", content="print('hello')")
    This is ALWAYS preferred over typing into a text editor.
  - For multi-line code, use \\n inside the content string.
  - If the user says "write code" or "type code" in a file, ALWAYS use files.write_file first,
    then open the file in the editor (VS Code or notepad).
  - The correct order is: 1) write file, 2) open in editor. Never type code character-by-character.

NOTEPAD / TEXT EDITOR RULES:
  - To open a file in Notepad: apps.open_app(name="notepad <filepath>")
  - To create a file with content and open in Notepad:
      1. files.write_file(path="<filepath>", content="<content>")
      2. apps.open_app(name="notepad <filepath>")
  - NEVER put a file path inside apps.open_app name without a known app prefix.
  - If no path specified, save to Desktop by default.

APP OPENING RULES:
  - For any app (VS Code, Notepad, Calculator, etc.), use apps.open_app(name="<app name>").
  - The name is matched against apps.json (case-insensitive, partial match).
  - To open an app with a file argument, concatenate: apps.open_app(name="<app> <filepath>")

COMPLEX TASK GUIDELINES:
  - Break complex tasks into sequential, atomic steps.
  - Each step should do ONE thing. Don't combine unrelated operations.
  - For "create a file, open it, and write code":
      1. files.write_file(path, content)     — create the file with code
      2. apps.open_app(name="vscode <path>") — open in editor
  - For "organize downloads, create a report, and email it":
      1. files.organize_by_type(directory=...)
      2. files.write_file(path=..., content=...) — create report
      3. messaging/browser step to send it
  - For "summarize a file" or "tell me what this file is about":
      1. files.read_file(path=...)
      2. ai.summarize(context="{{steps.step_1.result}}")
  - For multi-file operations, generate one step per file.
  - For conditional logic (if X then Y), plan the most likely path.
  - Maximum 15 steps per plan. If more are needed, group related ops.
PAGE CONTENT EXTRACTION RULES — UPDATED:

# HARD OVERRIDE RULE (CRITICAL)
- If the intent contains words like "extract", "read", "get content", "scrape", "copy text":
  ALWAYS use extension.getPageText
  NEVER use web_agent for these cases (this is a strict rule, not optional)
- If a well-known direct URL exists (e.g., Wikipedia pages), ALWAYS navigate directly.
  DO NOT search Google first.

  When the task is ONLY to read or extract content from a page:
  - ALWAYS use extension.getPageText (NOT web_agent)

  Examples:

  Wikipedia:
    step_1: browser.navigate(url="https://en.wikipedia.org/wiki/Virat_Kohli")
    step_2: extension.getPageText(tab_id="{{steps.step_1.result.tabId}}", selector="#mw-content-text")

  NEVER:
  - use web_agent for static pages
  - say "extract ALL visible text" in web_agent

  web_agent is ONLY for:
  - clicking
  - forms
  - login
  - dynamic interaction

  Example for "create Google Meet and send link on WhatsApp":
    step_1: extension.createEvent(title="Meeting", date="2026-05-04", time="10:00", meet=true)
    step_2: messaging.send_message(app="whatsapp", contact="jaidev", text="Here is the Google Meet link: {{steps.step_1.result.meet_link}}")

PARAM VALUE RULES - MANDATORY:
  - Param values must use ONLY {{steps.step_N.result}} or {{steps.step_N.result.field}} syntax.
  - NEVER write Python code or method calls in param values (.join, .split, .strip, slicing, etc.)
  - NEVER use single-brace templates - always double-brace: {{steps.step_N.result}}
  - To send a Google Meet link: text="Here is the link: {{steps.step_1.result.meet_link}}"
  - To save web content: content="{{steps.step_2.result}}"

BROWSER.EVALUATE RULE — CRITICAL (NEVER use browser.evaluate):
  - NEVER use browser.evaluate(code="window.location.href") or any browser.evaluate action.
  - browser.evaluate runs in a SEPARATE Playwright browser window, NOT in the Chrome tab.
  - It will return a WRONG URL (from a different browser entirely).
  - To get the current YouTube video URL: reference {{steps.step_N.result.video_url}}
    (the executor auto-captures the video URL after YouTube actions).
  - To get YouTube video info: use extension.getVideoInfo()
  - To get the current page URL: use extension.getTabs() and look at tab URLs.
  - NEVER use browser.evaluate for ANY purpose when the extension is available.

YOUTUBE + MESSAGING RULE — MANDATORY:
  - After a YouTube search/play step, the video URL is automatically captured in the step result.
  - To send the YouTube video link: text="Here is the YouTube video: {{steps.step_N.result.video_url}}"
  - Example for "search python on YouTube, play the first video, send its link to X on WhatsApp":
      step_1: browser.navigate(url="https://www.youtube.com", browser="chrome")
      step_2: extension.web_agent(url="", task="Search for 'python' and play the first video result")
      step_3: messaging.send_message(app="whatsapp", contact="X", text="Here is the YouTube video: {{steps.step_2.result.video_url}}")
  - DO NOT add a separate step to get the URL — it is captured automatically.

GIT OPERATIONS RULES — MANDATORY:
  - Each terminal command runs in its own subprocess. `Set-Location` does NOT persist to the next step.
  - NEVER use a standalone `Set-Location <path>` step followed by `git push` or similar.
  - ALWAYS pass the `cwd` parameter to terminal.execute for git commands, OR chain navigation inline:
      CORRECT: terminal.execute(command="git push", cwd="C:\\Users\\codin\\projects\\MyRepo")
      CORRECT: terminal.execute(command="cd C:\\Users\\codin\\projects\\MyRepo; git push")
      WRONG:   terminal.execute(command="Set-Location C:\\path")   <- next step won't be in that dir
  - When cloning a repo and then running git add/commit/push, ALL git steps must use:
      cwd="<clone_target_path>" (the same path used in the git clone command)
  - Never run `git push` or `git commit` without specifying the repo's cwd — it will push IntentOS itself.
  - Example for "clone repo, update README, commit and push":
      step_1: terminal.execute(command="git clone https://github.com/user/repo C:\\Users\\codin\\projects\\repo")
      step_2: files.read_file(path="C:\\Users\\codin\\projects\\repo\\README.md")
      step_3: files.write_file(path="C:\\Users\\codin\\projects\\repo\\README.md", content="...")
      step_4: terminal.execute(command="git add README.md", cwd="C:\\Users\\codin\\projects\\repo")
      step_5: terminal.execute(command="git commit -m 'Updated readme file'", cwd="C:\\Users\\codin\\projects\\repo")
      step_6: terminal.execute(command="git push", cwd="C:\\Users\\codin\\projects\\repo")
  - For git user config errors, chain: terminal.execute(command="git config user.email 'x@x.com'; git config user.name 'x'; git commit -m 'msg'", cwd="<path>")
{dynamic}"""


# Per-call user message — schema enforced here (Gemini follows user turns more reliably)
USER_PROMPT = """\
INTENT: {intent}

Respond with ONLY this JSON (no markdown, no extra text, keep descriptions short):
{{"summary":"one-line description","steps":[{{"id":"step_1","skill":"<skill>","action":"<action>","params":{{...}},"description":"short","reasoning":"short"}}]}}"""

REPLAN_PROMPT = """\
INTENT: Recovery plan
FAILED STEP: {failed_step}
ERROR: {error}
REMAINING STEPS: {remaining_steps}

Generate a revised plan that works around this failure.
Respond with ONLY this JSON (no markdown, no extra text):
{{"summary":"one-line description","steps":[{{"id":"step_1","skill":"<skill>","action":"<action>","params":{{...}},"description":"what this step does","reasoning":"why"}}]}}"""


# ---------------------------------------------------------------------------
# Planner
# ---------------------------------------------------------------------------

class Planner:
    """Pi Engine Planner — Gemini Flash 2.5 (Vertex AI or API key, via USE_VERTEX_AI in .env)."""

    def __init__(self, soul_reader: Optional[SoulReader] = None):
        self.model_name  = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
        self.soul_reader = soul_reader
        self.client      = None        # non-None = ready

        use_vertex = os.getenv("USE_VERTEX_AI", "false").strip().lower() == "true"

        if not _GENAI_OK:
            print("[Planner] google-genai not installed — offline mode")
            return

        if use_vertex:
            # --- Vertex AI path: service account JSON or ADC ---
            gcp_project  = os.getenv("GCP_PROJECT", "")
            gcp_location = os.getenv("GCP_LOCATION", "us-central1")

            # Auto-point to credentials.json if present and ADC not already set
            if not os.getenv("GOOGLE_APPLICATION_CREDENTIALS"):
                creds_path = Path(__file__).parent.parent / "credentials.json"
                if creds_path.exists():
                    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = str(creds_path)
                    print(f"[Planner] Using service account: {creds_path.name}")

            try:
                self.client = genai.Client(
                    vertexai=True,
                    project=gcp_project,
                    location=gcp_location,
                )
                print(f"[Planner] Auth: Vertex AI ({gcp_project} / {gcp_location})")
            except Exception as e:
                print(f"[Planner] Vertex AI init failed: {e}")
        else:
            # --- Gemini API key path ---
            api_key = os.getenv("GEMINI_API_KEY", "")
            if api_key and "your-gemini" not in api_key:
                self.client = genai.Client(api_key=api_key)
                print("[Planner] Auth: Gemini API key")
            else:
                print("[Planner] GEMINI_API_KEY not set — offline mode")

    # ------------------------------------------------------------------
    # Prompt helpers
    # ------------------------------------------------------------------

    def _dynamic_section(self) -> str:
        """
        Build the dynamic section appended to every Gemini system prompt.

        WHY THIS ORDER:
          1. SOUL persona block first — shapes the LLM's voice and values.
          2. Preferences — gives the LLM concrete defaults (apps, paths).
          3. Planner hints — high-priority planning directives.
          4. Safety rules — hard constraints the LLM must respect.
          5. Macros — named workflows the LLM can reference.
          6. Installed apps — so open_app() params are correct.

        WHAT IS NOT INJECTED:
          plugin_architecture, runtime_event_system, telemetry — these are
          future roadmap items and would bloat the prompt without benefit.
        """
        parts = []

        if self.soul_reader:
            # ── 1. SOUL Identity & Persona ─────────────────────────────────
            soul_persona = self._build_soul_persona_block()
            if soul_persona:
                parts.append(soul_persona)

            # ── 2. Preferences (editor, browser, directories) ──────────────
            prefs_block = self._build_preferences_block()
            if prefs_block:
                parts.append(prefs_block)

            # ── 3. Planner hints (directive list) ──────────────────────────
            hints_block = self._build_planner_hints_block()
            if hints_block:
                parts.append(hints_block)

            # ── 4. Safety rules summary ────────────────────────────────────
            safety_block = self._build_safety_block()
            if safety_block:
                parts.append(safety_block)

            # ── 5. Legacy rules & macros ───────────────────────────────────
            rules = self.soul_reader.get_rules()
            if rules:
                parts.append("CUSTOM RULES:\n" + "\n".join(f"- {r}" for r in rules))

            macros = self.soul_reader.get_macros()
            if macros:
                lines = ["NAMED MACROS (user can trigger these by name):"]
                for name, steps in list(macros.items())[:20]:  # cap at 20 to keep prompt lean
                    step_summary = " | ".join(steps[:4])  # first 4 steps
                    lines.append(f"  '{name}': {step_summary}")
                parts.append("\n".join(lines))

        # ── 6. Installed apps ──────────────────────────────────────────────
        try:
            apps_json = Path(__file__).parent.parent / "apps.json"
            if apps_json.exists():
                import json as _json
                with open(apps_json, "r", encoding="utf-8") as f:
                    app_names = list(_json.load(f).keys())
                relevant = [n for n in app_names if any(kw in n for kw in [
                    "code", "notepad", "terminal", "powershell", "excel", "word",
                    "chrome", "edge", "firefox", "explorer", "calculator", "paint",
                    "outlook", "teams", "steam", "discord", "spotify", "vlc",
                    "whatsapp", "telegram", "signal", "slack",
                ])]
                if relevant:
                    parts.append(
                        "INSTALLED APPS (use these exact names with apps.open_app):\n"
                        + ", ".join(f'"{n}"' for n in sorted(relevant))
                    )
        except Exception:
            pass

        return ("\n" + "\n".join(parts) + "\n") if parts else "\n"

    # ── Soul context builders ──────────────────────────────────────────────

    def _build_soul_persona_block(self) -> str:
        """
        Build the persona/identity block from SOUL.md identity + communication_style.
        Injected as the first item in the system prompt so it shapes everything else.
        """
        sr = self.soul_reader
        identity = sr.get_identity()
        comm = sr.get_communication_style()
        user_name = sr.get_user_name()

        if not identity and not comm:
            return ""

        lines = ["ASSISTANT PERSONA & BEHAVIOR:"]

        # Identity
        name = identity.get("name", "OpenClaw")
        tagline = identity.get("tagline", "")
        if name:
            lines.append(f"  Name: {name}")
        if tagline:
            lines.append(f"  Role: {tagline}")
        if user_name and user_name != "User":
            lines.append(f"  You are speaking with: {user_name}")

        # Personality traits
        personality = comm.get("personality", {})
        if personality:
            primary = personality.get("primary", "")
            secondary = personality.get("secondary", "")
            if primary:
                lines.append(f"  Personality: {primary}, {secondary}".rstrip(", "))

        traits = comm.get("traits", [])
        if traits:
            lines.append("  Traits:")
            for t in traits[:5]:  # cap at 5 to keep prompt concise
                lines.append(f"    - {t}")

        # Response format
        fmt = comm.get("response_format", {})
        if fmt:
            length = fmt.get("default_length", "medium")
            emoji = fmt.get("use_emoji", "sparingly")
            lines.append(f"  Response style: {length} length, emoji {emoji}")

        # Active mode override (e.g. coding_mode → technical and focused)
        mode_override = sr.get_mode_style_override()
        if mode_override:
            tone = mode_override.get("tone", "")
            if tone:
                lines.append(f"  Current mode tone: {tone}")

        # Custom persona from assistant_customization
        customization = sr.get_assistant_customization()
        persona_cfg = customization.get("assistant_personality", {})
        persona_text = persona_cfg.get("persona", "")
        if persona_text and len(persona_text) < 400:
            lines.append(f"  Persona: {persona_text.strip()}")

        return "\n".join(lines)

    def _build_preferences_block(self) -> str:
        """
        Build preferences block from SOUL.md preferences section.
        Gives the LLM concrete defaults so it stops hallucinating app names/paths.
        """
        prefs = self.soul_reader.get_preferences()
        if not prefs or not isinstance(prefs, dict):
            return ""

        lines = ["USER PREFERENCES:"]
        editor = prefs.get("editor", {})
        browser_prefs = prefs.get("browser", {})
        terminal_prefs = prefs.get("terminal", {})
        dirs = prefs.get("directories", {})
        messaging_prefs = prefs.get("messaging", {})

        if editor.get("primary"):
            lines.append(f"  Editor: {editor['primary']}")
        if browser_prefs.get("primary"):
            lines.append(f"  Browser: {browser_prefs['primary']}")
        if terminal_prefs.get("primary"):
            lines.append(f"  Terminal: {terminal_prefs['primary']}")
        if messaging_prefs.get("personal_contacts"):
            lines.append(f"  Personal messaging: {messaging_prefs['personal_contacts']}")
        if messaging_prefs.get("work_contacts"):
            lines.append(f"  Work messaging: {messaging_prefs['work_contacts']}")
        if dirs.get("workspace"):
            lines.append(f"  Workspace: {dirs['workspace']}")
        if dirs.get("downloads"):
            lines.append(f"  Downloads: {dirs['downloads']}")
        if dirs.get("screenshots"):
            lines.append(f"  Screenshots: {dirs['screenshots']}")

        return "\n".join(lines) if len(lines) > 1 else ""

    def _build_planner_hints_block(self) -> str:
        """
        Build planner directives block from SOUL.md planner_hints section.
        These become high-priority instructions for intent resolution and
        execution philosophy. They reduce LLM hallucination of actions.
        """
        hints = self.soul_reader.get_planner_hints()
        if not hints or not isinstance(hints, dict):
            return ""

        lines = ["PLANNING DIRECTIVES (follow these strictly):"]

        # Intent resolution rules
        for rule in hints.get("intent_resolution", [])[:4]:
            lines.append(f"  - {rule}")

        # Execution philosophy (most important 3)
        for rule in hints.get("execution_philosophy", [])[:3]:
            lines.append(f"  - {rule}")

        return "\n".join(lines) if len(lines) > 1 else ""

    def _build_safety_block(self) -> str:
        """
        Build a concise safety rules summary from SOUL.md safety_rules section.
        The executor enforces these programmatically — this injection reminds
        the LLM not to generate plans that violate them in the first place.
        """
        safety = self.soul_reader.get_safety_rules()
        if not safety or not isinstance(safety, dict):
            return ""

        lines = ["SAFETY CONSTRAINTS (non-negotiable):"]

        blocked = safety.get("blocked_actions", [])
        for rule in blocked[:6]:  # top 6 to keep prompt lean
            if isinstance(rule, dict):
                pattern = rule.get("pattern", "")
                reason = rule.get("reason", "")
                lines.append(f"  - NEVER execute '{pattern}' — {reason}")

        confirm_items = safety.get("require_confirmation", [])
        always_confirm = [
            item.get("action", "") for item in confirm_items
            if isinstance(item, dict)
        ]
        if always_confirm:
            lines.append(f"  - Always ask user before: {', '.join(always_confirm[:5])}")

        return "\n".join(lines) if len(lines) > 1 else ""

    def _system_prompt(self) -> str:
        import os as _os
        today = datetime.now().strftime("%Y-%m-%d")
        home_dir = _os.environ.get("USERPROFILE", _os.path.expanduser("~"))
        return SYSTEM_PROMPT.format(
            dynamic=self._dynamic_section(),
            today=today,
            home_dir=home_dir,
        )

    def _user_prompt(self, intent: str) -> str:
        return USER_PROMPT.format(intent=intent)

    # ------------------------------------------------------------------
    # Generation config shared across calls
    # ------------------------------------------------------------------

    def _gen_config(self) -> "genai_types.GenerateContentConfig":
        return genai_types.GenerateContentConfig(
            system_instruction=self._system_prompt(),
            temperature=0.1,
            max_output_tokens=4096,
        )

    def _replan_config(self) -> "genai_types.GenerateContentConfig":
        """Config for replan — no system instruction, prompt is self-contained."""
        return genai_types.GenerateContentConfig(
            system_instruction=self._system_prompt(),
            temperature=0.1,
            max_output_tokens=4096,
        )

    # ------------------------------------------------------------------
    # Safe response text extraction (bypasses SDK .text bug on thinking models)
    # ------------------------------------------------------------------

    @staticmethod
    def _safe_text(response) -> str:
        """
        Extract text from a Gemini response safely.
        Avoids the KeyError('summary') bug that occurs when calling
        response.text on gemini-2.5-flash with thinking enabled.
        Falls back through multiple paths.
        """
        # Path 1: direct .text (works on non-thinking responses)
        try:
            t = response.text
            if t:
                return t
        except Exception:
            pass

        # Path 2: iterate candidates → parts, pick last text part
        try:
            for candidate in response.candidates:
                parts = candidate.content.parts
                # Grab parts that have text (skip thinking parts)
                text_parts = [p.text for p in parts if hasattr(p, "text") and p.text]
                if text_parts:
                    return text_parts[-1]   # last part = actual model output
        except Exception:
            pass

        # Path 3: raw dict access
        try:
            raw = response.model_dump() if hasattr(response, "model_dump") else {}
            text = (
                raw.get("candidates", [{}])[0]
                   .get("content", {})
                   .get("parts", [{}])[-1]
                   .get("text", "")
            )
            if text:
                return text
        except Exception:
            pass

        raise RuntimeError(f"Could not extract text from Gemini response: {response}")

    # ------------------------------------------------------------------
    # JSON parsing
    # ------------------------------------------------------------------

    def _parse(self, text: str, intent: str) -> ActionPlan:
        """Robust JSON parser — handles fences, list wrappers, missing keys."""
        raw = text.strip()

        # Strip markdown fences
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$",          "", raw.strip())

        # Parse JSON
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            # Try to grab the first {...} block
            m = re.search(r"\{.*\}", raw, re.DOTALL)
            if m:
                try:
                    data = json.loads(m.group())
                except json.JSONDecodeError:
                    print(f"[Planner] RAW RESPONSE:\n{raw[:500]}")
                    raise ValueError(f"Gemini returned unparseable JSON: {raw[:200]}")
            else:
                print(f"[Planner] RAW RESPONSE:\n{raw[:500]}")
                raise ValueError(f"No JSON object in Gemini response: {raw[:200]}")

        # Gemini sometimes wraps in a list — unwrap
        if isinstance(data, list):
            data = data[0] if data else {}

        # Must be a dict at this point
        if not isinstance(data, dict):
            print(f"[Planner] RAW RESPONSE:\n{raw[:500]}")
            raise ValueError(f"Expected JSON object, got {type(data).__name__}: {raw[:200]}")

        plan = ActionPlan(intent=intent, summary=data.get("summary", intent))

        for i, s in enumerate(data.get("steps", []), 1):
            if not isinstance(s, dict):
                continue
            skill  = s.get("skill",  "terminal")
            action = s.get("action", "execute")
            plan.steps.append(Step(
                id          = s.get("id", f"step_{i}"),
                skill       = skill,
                action      = action,
                params      = s.get("params", {}),
                description = s.get("description", f"{skill}.{action}"),
                reasoning   = s.get("reasoning", ""),
            ))

        return plan

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def create_plan(self, intent: str) -> ActionPlan:
        """Convert natural language intent → ActionPlan."""

        # Normalize relative dates ("tomorrow", "next Monday") → ISO dates
        intent = normalize_dates_in_text(intent)

        # Macro short-circuit (Phase 3: Structured Macros)
        # Bypasses the LLM entirely. Maps SOUL.md YAML steps directly to Executor skills.
        if self.soul_reader:
            macro_steps = self.soul_reader.expand_macro(intent.lower().strip())
            if macro_steps:
                plan = ActionPlan(intent=intent, summary=f"Macro: {intent}")
                for i, step_def in enumerate(macro_steps, 1):
                    # step_def is now a full dict from YAML
                    action_type = step_def.get("action", "execute").lower()
                    label = step_def.get("label") or step_def.get("description") or f"Macro step {i}"
                    
                    # ── Map YAML structural actions to Executor skills ──
                    skill = "terminal"
                    action_name = "execute"
                    params = {}

                    if action_type == "open_browser":
                        skill = "browser"
                        action_name = "navigate"
                        params = {"url": step_def.get("target", "https://google.com")}
                    elif action_type == "open_editor":
                        skill = "apps"
                        action_name = "open_app"
                        target = step_def.get("target", "vscode")
                        if target.lower() == "vscode":
                            target = "code"
                        project = step_def.get("project", "")
                        params = {"name": f"{target} {project}".strip()}
                    elif action_type == "read_calendar":
                        skill = "extension"
                        action_name = "get_events"
                        params = {"date": step_def.get("range", "today")}
                    elif action_type == "notify_user":
                        skill = "terminal"
                        action_name = "execute"
                        # Simple echo for now; dashboard reads stdout
                        # PowerShell requires single quotes to be escaped as ''
                        msg = step_def.get("message", "Notification").replace("'", "''")
                        params = {"command": f"echo '{msg}'"}
                    elif action_type == "legacy_text":
                        # Fallback for old markdown strings
                        skill = "auto"
                        action_name = "execute"
                        params = {"instruction": step_def.get("params", {}).get("instruction", "")}
                    else:
                        # Fallback: assume terminal command if no mapping
                        skill = "terminal"
                        action_name = "execute"
                        params = {"command": step_def.get("command", "")}

                    plan.steps.append(Step(
                        id=step_def.get("id", f"macro_{i}"),
                        skill=skill,
                        action=action_name,
                        params=params,
                        description=label,
                        reasoning=f"Structured SOUL.md macro step ({action_type})",
                    ))

                # BYPASS LLM entirely for pure YAML macros!
                # If we have legacy text steps, we still have to refine them.
                has_legacy = any(s.skill == "auto" for s in plan.steps)
                if has_legacy and self.client:
                    print(f"[Planner] Refining legacy text macro: {intent}")
                    return await self._refine(plan)
                
                print(f"[Planner] Bypassing LLM for structured macro: {intent}")
                return plan

        if not self.client:
            return self._fallback(intent)

        try:
            response = await asyncio.wait_for(
                asyncio.to_thread(
                    self.client.models.generate_content,
                    model   = self.model_name,
                    contents= self._user_prompt(intent),
                    config  = self._gen_config(),
                ),
                timeout=30.0,
            )
        except asyncio.TimeoutError:
            raise RuntimeError(
                "Gemini API timed out after 30s. "
                "Check your credentials.json permissions and GCP_PROJECT in .env."
            )
        raw = self._safe_text(response)
        print(f"[Planner] Raw: {raw[:1000]}")
        return self._parse(raw, intent)

    async def replan(
        self,
        failed_step: Step,
        error: str,
        remaining_steps: list,
        screenshot_analysis: str = "",
    ) -> ActionPlan:
        """Generate a recovery plan when a step fails."""
        if not self.client:
            return self._fallback(f"Retry: {failed_step.description}")

        prompt = REPLAN_PROMPT.format(
            failed_step     = json.dumps(failed_step.to_dict()),
            error           = error,
            remaining_steps = json.dumps([s.to_dict() for s in remaining_steps]),
        )
        try:
            response = await asyncio.wait_for(
                asyncio.to_thread(
                    self.client.models.generate_content,
                    model   = self.model_name,
                    contents= prompt,
                    config  = self._replan_config(),
                ),
                timeout=30.0,
            )
        except asyncio.TimeoutError:
            raise RuntimeError("Gemini API timed out during replan.")
        raw = self._safe_text(response)
        return self._parse(raw, f"Recovery: {failed_step.description}")

    async def _refine(self, macro_plan: ActionPlan) -> ActionPlan:
        instructions = " | ".join(s.description for s in macro_plan.steps)
        try:
            response = await asyncio.wait_for(
                asyncio.to_thread(
                    self.client.models.generate_content,
                    model   = self.model_name,
                    contents= f"INTENT: {macro_plan.intent}\nMACRO STEPS: {instructions}",
                    config  = self._gen_config(),
                ),
                timeout=30.0,
            )
        except asyncio.TimeoutError:
            raise RuntimeError("Gemini API timed out during macro refinement.")
        raw = self._safe_text(response)
        return self._parse(raw, macro_plan.intent)

    def _fallback(self, intent: str) -> ActionPlan:
        plan = ActionPlan(intent=intent, summary=f"Offline fallback: {intent}")
        plan.steps.append(Step(
            id="fallback_1", skill="terminal", action="execute",
            params={"command": f"echo \"IntentOS (offline): {intent}\""},
            description="Echo intent — Gemini API not configured",
            reasoning="GEMINI_API_KEY not set in .env",
        ))
        return plan
