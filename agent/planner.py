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
# Prompts  (tight, token-efficient)
# ---------------------------------------------------------------------------

# System-level preamble (skills + rules)
SYSTEM_PROMPT = """\
You are IntentOS Planner. Convert user intents into JSON action plans.

SKILLS:
  browser   : navigate(url) | search(query) | fill_form(fields) | click(selector) | extract_text(selector) | screenshot() | manage_tabs(action)
  terminal  : execute(command) | execute_background(command)
  files     : move(src,dst) | copy(src,dst) | rename(src,new_name) | delete(path) | organize_by_type(dir) | list_dir(path) | watch(path)
  apps      : open_app(name, wait_seconds=2) | press_keys(keys=[...]) | type_text(text) | list_apps(filter) | scan_apps()
  messaging : send_message(app, contact, text) | open_chat(app, contact)   [app="whatsapp" or "telegram"]
  vision    : capture_screen() | click_at(x,y) | type_text(text) | press_keys(keys=[...]) | scroll(clicks) | move_mouse(x,y)

RULES:
  - Prefer browser > terminal/apps > vision (vision = last resort)
  - Calendar → browser navigate to calendar.google.com
  - Messaging → messaging skill via desktop app shortcuts, never a bot API
  - Use exact paths, URLs, and names from the intent
  - OS is Windows 11. For terminal commands use PowerShell syntax:
      * Use Move-Item, Copy-Item, Remove-Item, New-Item (NOT mv/cp/rm/mkdir)
      * Paths use backslash: C:\\Users\\$env:USERNAME\\Downloads
      * Expand ~ as $env:USERPROFILE in PowerShell commands
      * Chain commands with ; not &&
      * Create dirs with: New-Item -ItemType Directory -Force -Path <path>
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
    """Pi Engine Planner — Gemini Flash 2.5 backend (google-genai SDK)."""

    def __init__(self, soul_reader: Optional[SoulReader] = None):
        self.api_key     = os.getenv("GEMINI_API_KEY", "")
        self.model_name  = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
        self.soul_reader = soul_reader
        self.client      = None        # non-None = ready

        if _GENAI_OK and self.api_key and "your-gemini" not in self.api_key:
            self.client = genai.Client(api_key=self.api_key)

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
            max_output_tokens=2048,
        )

    def _replan_config(self) -> "genai_types.GenerateContentConfig":
        """Config for replan — no system instruction, prompt is self-contained."""
        return genai_types.GenerateContentConfig(
            system_instruction=self._system_prompt(),
            temperature=0.1,
            max_output_tokens=2048,
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

        response = await asyncio.to_thread(
            self.client.models.generate_content,
            model   = self.model_name,
            contents= self._user_prompt(intent),
            config  = self._gen_config(),
        )
        raw = self._safe_text(response)
        print(f"[Planner] Raw: {raw[:300]}")
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
        response = await asyncio.to_thread(
            self.client.models.generate_content,
            model   = self.model_name,
            contents= prompt,
            config  = self._replan_config(),
        )
        raw = self._safe_text(response)
        return self._parse(raw, f"Recovery: {failed_step.description}")

    async def _refine(self, macro_plan: ActionPlan) -> ActionPlan:
        instructions = " | ".join(s.description for s in macro_plan.steps)
        response = await asyncio.to_thread(
            self.client.models.generate_content,
            model   = self.model_name,
            contents= f"INTENT: {macro_plan.intent}\nMACRO STEPS: {instructions}",
            config  = self._gen_config(),
        )
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
