"""
Fast validation test to check if each app entry is valid
Tests the app launcher logic without actually opening windows
"""

import json
from pathlib import Path
import re
import os


def _expand_ps_vars(s: str) -> str:
    """Expand PowerShell-style $env:VAR variables in a string."""
    def _replace(m):
        return os.environ.get(m.group(1), m.group(0))
    return re.sub(r'\$env:(\w+)', _replace, s)


def validate_app_entry(app_name: str, app_entry: dict) -> tuple[str, bool, str]:
    """
    Validate an app entry to check if it has valid launch parameters.
    Returns: (app_name, is_valid, reason)
    """
    
    if not isinstance(app_entry, dict):
        return app_name, False, "Entry is not a dictionary"
    
    has_app_id = "app_id" in app_entry
    has_shortcut = "shortcut" in app_entry
    
    if not has_app_id and not has_shortcut:
        return app_name, False, "No app_id or shortcut defined"
    
    # Check if shortcut exists (if defined)
    if has_shortcut:
        shortcut_path = _expand_ps_vars(app_entry["shortcut"])
        if not Path(shortcut_path).exists():
            if has_app_id:
                return app_name, True, f"Has app_id (shortcut missing: {shortcut_path})"
            else:
                return app_name, False, f"Shortcut not found: {shortcut_path}"
    
    if has_app_id:
        app_id = app_entry["app_id"]
        # Basic validation of app_id format
        if isinstance(app_id, str) and len(app_id) > 0:
            return app_name, True, f"Valid (app_id: {app_id[:50]}...)"
        else:
            return app_name, False, "Invalid app_id format"
    
    return app_name, True, "Valid (shortcut exists)"


def main():
    """Validate all apps in apps.json"""
    
    apps_json_path = Path(__file__).parent / "apps.json"
    
    if not apps_json_path.exists():
        print("ERROR: apps.json not found!")
        return 1
    
    with open(apps_json_path, "r", encoding="utf-8") as f:
        apps = json.load(f)
    
    print(f"\n{'='*100}")
    print(f"Validating {len(apps)} app entries from apps.json")
    print(f"{'='*100}\n")
    
    valid_apps = []
    invalid_apps = []
    partial_apps = []
    
    for i, (app_name, app_entry) in enumerate(sorted(apps.items()), 1):
        app_name_display, is_valid, reason = validate_app_entry(app_name, app_entry)
        
        status = "✓" if is_valid else "✗"
        print(f"[{i:3d}/{len(apps)}] {status} {app_name}")
        print(f"            {reason}")
        
        if is_valid:
            if "missing" in reason.lower():
                partial_apps.append(app_name)
            else:
                valid_apps.append(app_name)
        else:
            invalid_apps.append((app_name, reason))
        print()
    
    # Summary
    print(f"\n{'='*100}")
    print("VALIDATION SUMMARY")
    print(f"{'='*100}")
    print(f"✓ Fully Valid:        {len(valid_apps)}/{len(apps)} ({100*len(valid_apps)//len(apps)}%)")
    print(f"◐ Partial Valid:      {len(partial_apps)}/{len(apps)} ({100*len(partial_apps)//len(apps)}%)")
    print(f"✗ Invalid:            {len(invalid_apps)}/{len(apps)} ({100*len(invalid_apps)//len(apps)}%)")
    
    if invalid_apps:
        print(f"\nInvalid apps ({len(invalid_apps)}):")
        for app, reason in sorted(invalid_apps)[:20]:  # Show first 20
            print(f"  ✗ {app}: {reason}")
        if len(invalid_apps) > 20:
            print(f"  ... and {len(invalid_apps)-20} more")
    
    if partial_apps:
        print(f"\nPartially valid apps with missing shortcuts ({len(partial_apps)}):")
        for app in sorted(partial_apps)[:20]:  # Show first 20
            print(f"  ◐ {app} (has fallback app_id)")
        if len(partial_apps) > 20:
            print(f"  ... and {len(partial_apps)-20} more")
    
    print(f"\n{'='*100}\n")
    
    # Return exit code based on invalid apps (not partial)
    return 0 if len(invalid_apps) == 0 else 1


if __name__ == "__main__":
    exit(main())
