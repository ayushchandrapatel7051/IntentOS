"""
OpenClaw Memory — SOUL.md Reader  (v2)
=======================================
Parses SOUL.md by extracting all ```yaml fenced blocks and merging them
into a single structured configuration dictionary.

WHY THIS APPROACH:
  The new SOUL.md uses YAML fenced blocks inside Markdown sections.
  The old parser only handled plain markdown lists (## Macros / - step).
  PyYAML is already in requirements.txt so this costs zero extra dependencies.

WHAT IS PARSED:
  identity             → injected into LLM system prompt as persona
  assistant_profile    → user name, timezone, workspace paths
  communication_style  → personality traits, response format
  preferences          → editor, browser, terminal, directories
  planner_hints        → directive list injected into planner system prompt
  profiles             → named operating modes (coding_mode, meeting_mode …)
  macros               → named multi-step workflows (bypasses LLM)
  safety_rules         → blocked_actions + require_confirmation list
  invocation_policies  → confirmation keywords, global stance

WHAT IS INTENTIONALLY NOT PARSED (future roadmap):
  plugin_architecture, workflow_inheritance, telemetry, runtime_event_system,
  confirmation_state_machine, multi_agent_architecture — these are deferred
  per the architecture analysis. They live in SOUL.md as documentation only.

BACKWARD COMPATIBILITY:
  All legacy methods (get_macros, get_rules, get_preferences, expand_macro,
  get_contact_preference, get_raw_content, get_summary, reload) are preserved
  so no other file needs changes other than planner.py and executor.py.
"""

import re
import os
from pathlib import Path
from typing import Optional

try:
    import yaml
    _YAML_OK = True
except ImportError:
    _YAML_OK = False


# ── Sections we actively parse from SOUL.md ────────────────────────────────
_USEFUL_SECTIONS = {
    "identity",
    "assistant_profile",
    "communication_style",
    "preferences",
    "planner_hints",
    "profiles",
    "macros",
    "safety_rules",
    "invocation_policies",
    "assistant_customization",
}

# ── Advanced sections deferred to future roadmap ───────────────────────────
# We don't skip them entirely — they're extracted but not acted upon yet.
# This means SOUL.md can grow without breaking the loader.
_DEFERRED_SECTIONS = {
    "plugin_architecture",
    "macro_composition",
    "runtime_event_system",
    "confirmation_state_machine",
    "action_permission_matrix",
    "observability",
    "developer_tooling",
    "soul_versioning",
    "automation_sandbox",
    "multi_agent_architecture",
    "memory_sync_hooks",
    "macro_import_export",
    "skill_lifecycle",
    "rollback_policies",
    "workflow_templates_library",
}


class SoulReader:
    """
    Parses SOUL.md to extract structured configuration for:
      - Planner prompt injection (identity, style, hints, prefs)
      - Macro short-circuit execution (bypass LLM for named workflows)
      - Safety validation in Executor (blocked_actions, require_confirmation)
      - Profile/mode management (active mode context)
      - Legacy rule/preference lists (backward compat with old planner)
    """

    def __init__(self, soul_path: str = ""):
        self.soul_path = Path(soul_path or os.getenv("SOUL_MD_PATH", "./SOUL.md"))
        self._raw_content: str = ""
        self._config: dict = {}          # merged YAML config from all blocks
        self._active_mode: str = "default"

        # Legacy flat lists (preserved for backward compat)
        self._macros_legacy: dict = {}   # {name: [step_str, ...]}
        self._rules: list = []
        self._preferences_list: list = []

        if self.soul_path.exists():
            self._parse()

    # ── Parsing ────────────────────────────────────────────────────────────

    def _parse(self):
        """Read SOUL.md, extract all ```yaml blocks, merge into _config."""
        with open(self.soul_path, "r", encoding="utf-8") as f:
            self._raw_content = f.read()

        self._config = {}

        if not _YAML_OK:
            # Fallback: run the old line-by-line parser so the system still works
            print("[SoulReader] PyYAML not available — falling back to legacy parser")
            self._legacy_parse()
            return

        # Extract all ```yaml ... ``` blocks from the markdown
        yaml_blocks = re.findall(
            r"```yaml\s*\n(.*?)```",
            self._raw_content,
            re.DOTALL,
        )

        for block in yaml_blocks:
            try:
                parsed = yaml.safe_load(block)
                if isinstance(parsed, dict):
                    # Merge top-level keys — later blocks win on key collision
                    self._config.update(parsed)
            except yaml.YAMLError:
                # A single malformed block should never crash the whole loader
                pass

        # Build legacy-compatible structures from the parsed config
        self._build_legacy_structures()

    def _build_legacy_structures(self):
        """
        Populate _macros_legacy, _rules, _preferences_list from _config.
        This keeps get_macros() / get_rules() / get_preferences() working
        without any changes to planner.py's existing _dynamic_section().
        We ALSO build enriched data that the new planner injection uses.
        """
        # ── Macros → flat legacy dict ──────────────────────────────────────
        macros_cfg = self._config.get("macros", {})
        if isinstance(macros_cfg, dict):
            for macro_name, macro_data in macros_cfg.items():
                if not isinstance(macro_data, dict):
                    continue
                steps = macro_data.get("steps", [])
                trigger_phrases = macro_data.get("trigger_phrases", [macro_name])
                label = macro_data.get("label", macro_name)
                step_labels = []
                for s in steps:
                    if isinstance(s, dict):
                        lbl = s.get("label") or s.get("description") or str(s.get("action", ""))
                        step_labels.append(lbl)
                # Register under all trigger phrases
                for phrase in trigger_phrases:
                    self._macros_legacy[phrase.lower().strip()] = step_labels
                # Also register under the macro key itself
                self._macros_legacy[macro_name.lower().strip()] = step_labels

        # ── Custom routines from assistant_customization ───────────────────
        customization = self._config.get("assistant_customization", {})
        custom_routines = customization.get("custom_routines", {})
        if isinstance(custom_routines, dict):
            for routine_name, routine_data in custom_routines.items():
                if not isinstance(routine_data, dict):
                    continue
                steps = routine_data.get("steps", [])
                trigger_phrases = routine_data.get("trigger_phrases", [routine_name])
                step_labels = []
                for s in steps:
                    if isinstance(s, dict):
                        lbl = s.get("label") or s.get("description") or str(s.get("action", ""))
                        step_labels.append(lbl)
                for phrase in trigger_phrases:
                    self._macros_legacy[phrase.lower().strip()] = step_labels
                self._macros_legacy[routine_name.lower().strip()] = step_labels

        # ── Safety rules → _rules list ─────────────────────────────────────
        safety = self._config.get("safety_rules", {})
        for blocked in safety.get("blocked_actions", []):
            if isinstance(blocked, dict):
                self._rules.append(f"[SAFETY] Never execute: {blocked.get('pattern', '')} — {blocked.get('reason', '')}")
        for confirm_item in safety.get("require_confirmation", []):
            if isinstance(confirm_item, dict):
                self._rules.append(f"[CONFIRM] Always ask before: {confirm_item.get('action', '')}")

        # ── Preferences → _preferences_list ───────────────────────────────
        prefs = self._config.get("preferences", {})
        messaging = prefs.get("messaging", {})
        if messaging.get("personal_contacts"):
            self._preferences_list.append(f"Prefer {messaging['personal_contacts']} for personal contacts")
        if messaging.get("work_contacts"):
            self._preferences_list.append(f"Prefer {messaging['work_contacts']} for work contacts")
        display = prefs.get("display", {})
        if display.get("dark_mode"):
            self._preferences_list.append("Use dark mode in all applications when possible")

        # ── Communication style messaging rules ────────────────────────────
        comm = self._config.get("communication_style", {})
        for rule in comm.get("messaging_rules", []):
            self._rules.append(f"[COMMUNICATION] {rule}")

    def _legacy_parse(self):
        """
        Old line-by-line markdown parser — used only if PyYAML is missing.
        Preserved verbatim from the original soul_reader.py.
        """
        lines = self._raw_content.split("\n")
        current_section = None
        current_subsection = None
        current_macro_name = None

        for line in lines:
            stripped = line.strip()

            if not stripped or stripped.startswith("#") and stripped.startswith("# "):
                if stripped.startswith("## "):
                    current_section = stripped.lstrip("# ").strip().lower()
                    current_subsection = None
                    current_macro_name = None
                elif stripped.startswith("### "):
                    current_subsection = stripped.lstrip("# ").strip().lower()
                    current_macro_name = None
                    if current_section == "macros":
                        current_macro_name = current_subsection
                        self._macros_legacy[current_macro_name] = []
                continue

            if stripped.startswith("- "):
                item = stripped[2:].strip()
                if current_section == "macros" and current_macro_name:
                    self._macros_legacy[current_macro_name].append(item)
                elif current_section == "rules":
                    if current_subsection == "safety":
                        self._rules.append(f"[SAFETY] {item}")
                    elif current_subsection == "preferences":
                        self._preferences_list.append(item)
                    elif current_subsection == "communication style":
                        self._rules.append(f"[COMMUNICATION] {item}")
                    elif current_subsection == "file organization":
                        self._rules.append(f"[FILES] {item}")
                    else:
                        self._rules.append(item)

    # ── Public API — new structured access ────────────────────────────────

    def get_config(self) -> dict:
        """Full merged config from all YAML blocks in SOUL.md."""
        return self._config

    def get_section(self, key: str) -> dict:
        """Get a specific top-level section dict (returns {} if missing)."""
        return self._config.get(key, {})

    def get_identity(self) -> dict:
        return self._config.get("identity", {})

    def get_communication_style(self) -> dict:
        return self._config.get("communication_style", {})

    def get_preferences(self) -> dict:  # type: ignore[override]  # overrides legacy list method
        """
        Returns the structured preferences dict (not the flat list).
        The legacy flat list is still accessible via get_preferences_list().
        """
        return self._config.get("preferences", {})

    def get_preferences_list(self) -> list:
        """Legacy: returns flat list of preference strings for old callers."""
        return list(self._preferences_list)

    def get_planner_hints(self) -> dict:
        return self._config.get("planner_hints", {})

    def get_profiles(self) -> dict:
        return self._config.get("profiles", {})

    def get_safety_rules(self) -> dict:
        return self._config.get("safety_rules", {})

    def get_invocation_policies(self) -> dict:
        return self._config.get("invocation_policies", {})

    def get_assistant_customization(self) -> dict:
        return self._config.get("assistant_customization", {})

    def get_active_mode(self) -> str:
        return self._active_mode

    def set_active_mode(self, mode_name: str):
        """Called by planner/executor when user activates a profile."""
        self._active_mode = mode_name

    def get_mode_style_override(self) -> dict:
        """
        Returns communication style overrides for the currently active mode.
        Used by the planner to tailor response tone dynamically.
        """
        profiles = self.get_profiles()
        active = profiles.get(self._active_mode, {})
        return active.get("communication_style_override", {})

    def get_macro_details(self, macro_id: str) -> Optional[dict]:
        """Get the full structured YAML dict for a macro by id."""
        macros = self._config.get("macros", {})
        if macro_id in macros:
            return macros[macro_id]
        # Also check custom_routines
        customization = self._config.get("assistant_customization", {})
        custom_routines = customization.get("custom_routines", {})
        return custom_routines.get(macro_id)

    def list_macros(self) -> list:
        """Return list of {id, label, trigger_phrases, description} for all macros."""
        result = []
        macros_cfg = self._config.get("macros", {})
        for macro_id, data in (macros_cfg.items() if isinstance(macros_cfg, dict) else []):
            if isinstance(data, dict):
                result.append({
                    "id": macro_id,
                    "label": data.get("label", macro_id),
                    "description": data.get("description", ""),
                    "trigger_phrases": data.get("trigger_phrases", []),
                    "tags": data.get("tags", []),
                    "icon": data.get("icon", ""),
                })
        customization = self._config.get("assistant_customization", {})
        for routine_id, data in (customization.get("custom_routines", {}).items() if isinstance(customization.get("custom_routines"), dict) else []):
            if isinstance(data, dict):
                result.append({
                    "id": routine_id,
                    "label": data.get("label", routine_id),
                    "description": data.get("description", ""),
                    "trigger_phrases": data.get("trigger_phrases", []),
                    "tags": data.get("tags", []),
                    "icon": data.get("icon", ""),
                })
        return result

    def get_user_name(self) -> str:
        """Convenience: get user's first name from assistant_profile."""
        profile = self._config.get("assistant_profile", {})
        return profile.get("user", {}).get("name", "User")

    def get_workspace(self) -> str:
        """Convenience: get workspace path from preferences or assistant_profile."""
        prefs = self._config.get("preferences", {})
        dirs = prefs.get("directories", {})
        if dirs.get("workspace"):
            return dirs["workspace"]
        profile = self._config.get("assistant_profile", {})
        return profile.get("environment", {}).get("workspace", "~/projects")

    # ── Safety helpers (used by Executor) ─────────────────────────────────

    def is_action_blocked(self, command_or_action: str) -> Optional[str]:
        """
        Check if a command/action string matches any blocked_actions pattern.
        Returns the block reason string if blocked, None if safe.

        WHY: This is a lightweight text-match guard, not a formal policy engine.
        We check the command text against the patterns in safety_rules.blocked_actions.
        A real sandbox (future) would do this at the OS/subprocess level.
        """
        safety = self.get_safety_rules()
        blocked = safety.get("blocked_actions", [])
        command_lower = command_or_action.lower()

        for rule in blocked:
            if not isinstance(rule, dict):
                continue
            pattern = rule.get("pattern", "").lower()
            if not pattern:
                continue
            # Skip credential-in-log rules (those are context-specific)
            if rule.get("context") == "log_output":
                continue
            if pattern in command_lower:
                return rule.get("reason", f"Blocked pattern: {pattern}")
        return None

    def requires_confirmation(self, action_type: str) -> Optional[str]:
        """
        Check if an action type requires user confirmation before execution.
        Returns the confirmation message template if yes, None if not required.

        WHY: Instead of a formal FSM, we do a simple dict lookup. The executor
        emits a WS event and logs the requirement. The frontend can show a modal.
        This is Phase 2's lightweight confirmation gate — simple and reliable.
        """
        safety = self.get_safety_rules()
        confirm_list = safety.get("require_confirmation", [])
        action_lower = action_type.lower()

        for item in confirm_list:
            if not isinstance(item, dict):
                continue
            item_action = item.get("action", "").lower()
            if item_action == action_lower or item_action in action_lower:
                return item.get("message", f"Confirm: {action_type}?")
        return None

    # ── Legacy API (preserved for backward compatibility) ──────────────────

    def get_macros(self) -> dict:
        """Legacy: returns {macro_name: [step_str, ...]} for old planner._dynamic_section."""
        return dict(self._macros_legacy)

    def get_rules(self) -> list:
        """Legacy: returns flat rule strings for old planner._dynamic_section."""
        return list(self._rules)

    def expand_macro(self, intent: str) -> Optional[list]:
        """
        Check if intent matches a macro trigger phrase and return its step labels.

        WHY: This is the macro short-circuit in planner.create_plan(). When a
        macro matches, the LLM is bypassed entirely — execution is deterministic.
        We check trigger_phrases from YAML first (more specific), then fall back
        to fuzzy substring matching on the legacy flat dict.
        """
        intent_lower = intent.lower().strip()

        # First: check against YAML trigger_phrases (precise match)
        macros_cfg = self._config.get("macros", {})
        if isinstance(macros_cfg, dict):
            for macro_id, data in macros_cfg.items():
                if not isinstance(data, dict):
                    continue
                for phrase in data.get("trigger_phrases", []):
                    if phrase.lower().strip() == intent_lower:
                        return [s for s in data.get("steps", []) if isinstance(s, dict)]

        # Second: check custom_routines trigger phrases
        customization = self._config.get("assistant_customization", {})
        custom_routines = customization.get("custom_routines", {})
        if isinstance(custom_routines, dict):
            for routine_id, data in custom_routines.items():
                if not isinstance(data, dict):
                    continue
                for phrase in data.get("trigger_phrases", []):
                    if phrase.lower().strip() == intent_lower:
                        return [s for s in data.get("steps", []) if isinstance(s, dict)]

        # Third: fall back to legacy flat dict fuzzy match
        # Convert legacy string steps into structured mock steps
        def _to_structured(steps_list):
            return [
                {"action": "legacy_text", "label": step, "params": {"instruction": step}}
                if isinstance(step, str) else step
                for step in steps_list
            ]

        if intent_lower in self._macros_legacy:
            return _to_structured(self._macros_legacy[intent_lower])

        for macro_name, steps in self._macros_legacy.items():
            if macro_name in intent_lower or intent_lower in macro_name:
                return _to_structured(steps)

        return None

    def get_contact_preference(self, contact_name: str) -> Optional[str]:
        """Get messaging app preference for a specific contact name."""
        # Try structured contacts first
        customization = self._config.get("assistant_customization", {})
        personal_comm = customization.get("personal_communication", {})
        contacts = personal_comm.get("contacts", {})
        contact_lower = contact_name.lower()
        for name, info in contacts.items():
            if name.lower() == contact_lower and isinstance(info, dict):
                return info.get("preferred_app")

        # Fallback: messaging preferences by category
        prefs = self._config.get("preferences", {})
        messaging = prefs.get("messaging", {})
        # Check if contact is in a known work group
        if contact_lower in ("team", "team group"):
            return messaging.get("work_contacts", "telegram")

        # Legacy flat-list fallback
        for pref in self._preferences_list:
            pref_lower = pref.lower()
            if contact_lower in pref_lower:
                if "whatsapp" in pref_lower:
                    return "whatsapp"
                elif "telegram" in pref_lower:
                    return "telegram"
        return None

    def get_raw_content(self) -> str:
        return self._raw_content

    def reload(self):
        """Hot-reload SOUL.md from disk (e.g. after user edits)."""
        self._config = {}
        self._macros_legacy = {}
        self._rules = []
        self._preferences_list = []
        self._raw_content = ""
        if self.soul_path.exists():
            self._parse()

    def get_summary(self) -> dict:
        """Summary dict used by /api/soul endpoint and startup banner."""
        macros_cfg = self._config.get("macros", {})
        profiles_cfg = self._config.get("profiles", {})
        identity = self.get_identity()
        customization = self._config.get("assistant_customization", {})
        custom_routines = customization.get("custom_routines", {})

        macros_count = len(macros_cfg) + len(custom_routines) if isinstance(macros_cfg, dict) else len(self._macros_legacy)
        profiles_count = len(profiles_cfg) if isinstance(profiles_cfg, dict) else 0

        return {
            "macros_count": macros_count,
            "macros": self.list_macros(),
            "rules_count": len(self._rules),
            "preferences_count": len(self._preferences_list),
            "file_exists": self.soul_path.exists(),
            "yaml_parsed": _YAML_OK and bool(self._config),
            "active_mode": self._active_mode,
            "profiles": list(profiles_cfg.keys()) if isinstance(profiles_cfg, dict) else [],
            "profiles_count": profiles_count,
            "identity": {
                "name": identity.get("name", "OpenClaw"),
                "version": identity.get("version", ""),
                "tagline": identity.get("tagline", ""),
            },
            "user_name": self.get_user_name(),
        }
