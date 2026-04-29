"""
OpenClaw Memory — SOUL.md Reader
===================================
Parses the user's SOUL.md behaviour file to extract macros, rules,
and preferences that customize agent behavior.
"""

import re
import os
from pathlib import Path
from typing import Optional


class SoulReader:
    """
    Parses SOUL.md to extract:
    - Macros: named sequences of actions (e.g., "start my day" → list of steps)
    - Rules: behavioral constraints (e.g., "always ask before deleting")
    - Preferences: per-contact or per-action preferences
    """

    def __init__(self, soul_path: str = ""):
        self.soul_path = Path(soul_path or os.getenv("SOUL_MD_PATH", "./SOUL.md"))
        self._macros = {}
        self._rules = []
        self._preferences = []
        self._raw_content = ""

        if self.soul_path.exists():
            self._parse()

    def _parse(self):
        """Parse the SOUL.md file."""
        with open(self.soul_path, "r", encoding="utf-8") as f:
            self._raw_content = f.read()

        lines = self._raw_content.split("\n")
        current_section = None
        current_subsection = None
        current_macro_name = None

        for line in lines:
            stripped = line.strip()

            # Skip empty lines and comments
            if not stripped or stripped.startswith("#") and stripped.startswith("# "):
                # Check for section headers
                if stripped.startswith("## "):
                    current_section = stripped.lstrip("# ").strip().lower()
                    current_subsection = None
                    current_macro_name = None
                elif stripped.startswith("### "):
                    current_subsection = stripped.lstrip("# ").strip().lower()
                    current_macro_name = None

                    # If we're in the macros section, this is a macro name
                    if current_section == "macros":
                        current_macro_name = current_subsection
                        self._macros[current_macro_name] = []
                continue

            # Parse list items
            if stripped.startswith("- "):
                item = stripped[2:].strip()

                if current_section == "macros" and current_macro_name:
                    self._macros[current_macro_name].append(item)
                elif current_section == "rules":
                    if current_subsection == "safety":
                        self._rules.append(f"[SAFETY] {item}")
                    elif current_subsection == "preferences":
                        self._preferences.append(item)
                    elif current_subsection == "communication style":
                        self._rules.append(f"[COMMUNICATION] {item}")
                    elif current_subsection == "file organization":
                        self._rules.append(f"[FILES] {item}")
                    else:
                        self._rules.append(item)

    def get_macros(self) -> dict:
        """Get all macros as {name: [step_list]}."""
        return dict(self._macros)

    def get_rules(self) -> list:
        """Get all behavioral rules."""
        return list(self._rules)

    def get_preferences(self) -> list:
        """Get all user preferences."""
        return list(self._preferences)

    def expand_macro(self, intent: str) -> Optional[list]:
        """
        Check if an intent matches a macro and return its steps.
        
        Args:
            intent: User intent to check against macros
            
        Returns:
            List of steps if a macro matches, None otherwise
        """
        intent_lower = intent.lower().strip()
        
        # Direct match
        if intent_lower in self._macros:
            return self._macros[intent_lower]

        # Fuzzy match — check if intent contains or is contained by a macro name
        for macro_name, steps in self._macros.items():
            if macro_name in intent_lower or intent_lower in macro_name:
                return steps

        return None

    def get_contact_preference(self, contact_name: str) -> Optional[str]:
        """
        Get messaging preference for a specific contact.
        
        Args:
            contact_name: Name of the contact
            
        Returns:
            Preferred messaging platform, or None
        """
        contact_lower = contact_name.lower()
        for pref in self._preferences:
            pref_lower = pref.lower()
            if contact_lower in pref_lower:
                if "whatsapp" in pref_lower:
                    return "whatsapp"
                elif "telegram" in pref_lower:
                    return "telegram"
        return None

    def get_raw_content(self) -> str:
        """Get the raw SOUL.md content for inclusion in AI prompts."""
        return self._raw_content

    def reload(self):
        """Reload SOUL.md from disk (e.g., after user edits)."""
        self._macros = {}
        self._rules = []
        self._preferences = []
        self._raw_content = ""
        if self.soul_path.exists():
            self._parse()

    def get_summary(self) -> dict:
        """Get a summary of what's configured in SOUL.md."""
        return {
            "macros_count": len(self._macros),
            "macros": list(self._macros.keys()),
            "rules_count": len(self._rules),
            "preferences_count": len(self._preferences),
            "file_exists": self.soul_path.exists(),
        }
