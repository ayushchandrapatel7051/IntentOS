"""
IntentOS — Date Normalization Utilities
========================================
Converts relative date expressions (today, tomorrow, next Monday, etc.)
into concrete ISO-format dates (YYYY-MM-DD) so the planner and executor
always work with deterministic date values.
"""

import re
from datetime import datetime, timedelta


def normalize_date(date_str: str) -> str:
    """
    Parses a relative date string (e.g., 'today', 'tomorrow', 'next Monday')
    and returns an ISO format date string (YYYY-MM-DD).
    If it's already an ISO date or cannot be parsed, returns the original.
    """
    if not date_str or not isinstance(date_str, str):
        return date_str

    lower_date = date_str.lower().strip()
    now = datetime.now()

    if lower_date == "today":
        return now.strftime("%Y-%m-%d")
    elif lower_date == "tomorrow":
        return (now + timedelta(days=1)).strftime("%Y-%m-%d")
    elif lower_date == "yesterday":
        return (now - timedelta(days=1)).strftime("%Y-%m-%d")
    elif lower_date.startswith("next "):
        day_name = lower_date.split("next ")[1].strip()
        days_of_week = [
            "monday", "tuesday", "wednesday", "thursday",
            "friday", "saturday", "sunday",
        ]
        if day_name in days_of_week:
            target_day = days_of_week.index(day_name)
            current_day = now.weekday()
            days_ahead = target_day - current_day
            if days_ahead <= 0:  # Target day already happened this week
                days_ahead += 7
            return (now + timedelta(days=days_ahead)).strftime("%Y-%m-%d")

    return date_str


# Regex that matches relative date tokens inside natural language text
_RELATIVE_DATE_PATTERNS = [
    # "next Monday", "next friday", etc.
    (re.compile(r'\bnext\s+(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b', re.IGNORECASE),
     lambda m: normalize_date(m.group(0))),
    # "day after tomorrow"
    (re.compile(r'\bday\s+after\s+tomorrow\b', re.IGNORECASE),
     lambda m: (datetime.now() + timedelta(days=2)).strftime("%Y-%m-%d")),
    # "tomorrow", "today", "yesterday" (standalone words)
    (re.compile(r'\b(tomorrow|today|yesterday)\b', re.IGNORECASE),
     lambda m: normalize_date(m.group(0))),
]


def normalize_dates_in_text(text: str) -> str:
    """
    Scans natural language text for relative date expressions and replaces
    them with concrete ISO dates.

    Examples:
        "schedule meeting for tomorrow"   → "schedule meeting for 2026-05-07"
        "remind me next friday"           → "remind me 2026-05-08"
    """
    if not text or not isinstance(text, str):
        return text

    result = text
    for pattern, replacer in _RELATIVE_DATE_PATTERNS:
        result = pattern.sub(replacer, result)
    return result
