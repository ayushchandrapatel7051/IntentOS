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
             [WebAgent] web_agent(url, task="describe what to do on the page")
  terminal  : execute(command) | execute_background(command)
  files     : move(source,destination) | copy(source,destination) | rename(source,new_name) | delete(path) | organize_by_type(directory) | list_dir(path) | watch(directory) | write_file(path,content) | read_file(path) | create_dir(path)
  apps      : open_app(name, wait_seconds=2) | press_keys(keys=[...]) | type_text(text) | list_apps(filter) | scan_apps()
  messaging : send_message(app, contact, text) | open_chat(app, contact)   [app="whatsapp" or "telegram"]
  vision    : capture_screen() | click_at(x,y) | type_text(text) | press_keys(keys=[...]) | scroll(clicks) | move_mouse(x,y)

WEB AGENT RULES - MANDATORY:
  - For ANY task that involves interacting with a website (filling forms, registering,
    logging in, clicking buttons, submitting data, scraping content, etc.), ALWAYS use:
      extension.web_agent(url="https://...", task="detailed description of what to do")
  - DO NOT output a separate "browser.navigate" step before "web_agent". web_agent handles navigation internally.
  - If the browser is ALREADY on the correct page, use url="" to operate on the active tab.
  - The web_agent automatically: navigates → extracts DOM → decides what to fill/click → executes.
  - NEVER use browser.navigate + browser.click for complex website interactions — use web_agent instead.
  - For simple "just open this URL" tasks, browser.navigate is fine.
  - NEVER use web_agent for Google Apps (YouTube, Gmail, Calendar, Meet). ALWAYS use the dedicated extension commands (e.g. extension.createEvent) because Google DOMs are too complex for web_agent. Calculate dates yourself (e.g. tomorrow = "2026-05-03").

RULES:
  - Prefer browser > terminal/apps > vision (vision = last resort)
  - Calendar: browser.navigate to calendar.google.com
  - Messaging: messaging skill via desktop app shortcuts, never a bot API
  - Use exact paths, URLs, and names from the intent
  - OS is Windows 11. Terminal = PowerShell syntax:
      * Use Move-Item, Copy-Item, Remove-Item, New-Item (NOT mv/cp/rm/mkdir)
      * Paths use backslash: C:\\Users\\$env:USERNAME\\Downloads
      * Expand ~ as $env:USERPROFILE in PowerShell commands
      * Chain commands with ; not &&
      * Create dirs: New-Item -ItemType Directory -Force -Path <path>

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
  - For multi-file operations, generate one step per file.
  - For conditional logic (if X then Y), plan the most likely path.
  - Maximum 15 steps per plan. If more are needed, group related ops.
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
        parts = []
        if self.soul_reader:
            rules = self.soul_reader.get_rules()
            if rules:
                parts.append("CUSTOM RULES:\n" + "\n".join(f"- {r}" for r in rules))
            macros = self.soul_reader.get_macros()
            if macros:
                lines = ["MACROS:"]
                for name, steps in macros.items():
                    lines.append(f"  {name}: " + " | ".join(steps))
                parts.append("\n".join(lines))

        # Inject top installed app names so the LLM knows what's available
        try:
            apps_json = Path(__file__).parent.parent / "apps.json"
            if apps_json.exists():
                import json as _json
                with open(apps_json, "r", encoding="utf-8") as f:
                    app_names = list(_json.load(f).keys())
                # Include a subset of the most relevant apps (keep prompt lean)
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

    def _system_prompt(self) -> str:
        return SYSTEM_PROMPT.format(dynamic=self._dynamic_section())

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

        # Macro short-circuit
        if self.soul_reader:
            macro_steps = self.soul_reader.expand_macro(intent.lower().strip())
            if macro_steps:
                plan = ActionPlan(intent=intent, summary=f"Macro: {intent}")
                for i, text in enumerate(macro_steps, 1):
                    plan.steps.append(Step(
                        id=f"macro_{i}", skill="auto", action="execute",
                        params={"instruction": text}, description=text,
                        reasoning=f"Macro step {i}",
                    ))
                if self.client:
                    return await self._refine(plan)
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
