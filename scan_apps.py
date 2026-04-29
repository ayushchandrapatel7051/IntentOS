"""
IntentOS — App Scanner
=======================
Scans installed Windows apps (Start Menu UWP AppIDs + .lnk shortcuts)
and saves them to apps.json for the AppLauncher skill to use.

Run manually:
    python scan_apps.py

Or trigger from within IntentOS:
    "scan apps"  →  AppLauncher.scan_apps()
"""

import os
import json
import subprocess
from pathlib import Path


def get_startapps() -> dict:
    """Get AppIDs using PowerShell (UWP + Store apps)."""
    apps = {}
    try:
        output = subprocess.check_output(
            ["powershell", "-Command", "Get-StartApps | ConvertTo-Json"],
            text=True,
        )
        data = json.loads(output)

        # PowerShell returns a single dict when there is only one result
        if isinstance(data, dict):
            data = [data]

        for app in data:
            name = app["Name"].lower()
            apps[name] = {"app_id": app["AppID"]}

    except Exception as e:
        print(f"[Scanner] Failed to fetch StartApps: {e}")

    return apps


def get_startmenu_shortcuts() -> dict:
    """Scan Start Menu folders for .lnk shortcut files."""
    apps = {}

    start_paths = [
        os.path.join(os.environ["APPDATA"], r"Microsoft\Windows\Start Menu\Programs"),
        r"C:\ProgramData\Microsoft\Windows\Start Menu\Programs",
    ]

    for base in start_paths:
        if not os.path.isdir(base):
            continue
        for root, _dirs, files in os.walk(base):
            for file in files:
                if file.endswith(".lnk"):
                    name = file.replace(".lnk", "").lower()
                    full_path = os.path.join(root, file)
                    apps[name] = {"shortcut": full_path}

    return apps


def merge_apps(app_ids: dict, shortcuts: dict) -> dict:
    """Merge both sources, combining data for the same app name."""
    merged = {}
    for name in set(app_ids) | set(shortcuts):
        merged[name] = {}
        if name in app_ids:
            merged[name]["app_id"] = app_ids[name]["app_id"]
        if name in shortcuts:
            merged[name]["shortcut"] = shortcuts[name]["shortcut"]
    return merged


def main():
    print("Scanning system apps...")

    app_ids = get_startapps()
    shortcuts = get_startmenu_shortcuts()
    merged = merge_apps(app_ids, shortcuts)

    output_path = Path(__file__).parent / "apps.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(merged, f, indent=4)

    print(f"Found {len(merged)} apps. Saved to {output_path}")
    return len(merged)


if __name__ == "__main__":
    main()
