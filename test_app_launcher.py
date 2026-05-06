"""
Test script to verify if the agent can open apps in apps.json
Supports batch testing (5 apps at a time to avoid lag)
"""

import asyncio
import json
import sys
from pathlib import Path
from skills.apps.app_launcher import AppLauncher


async def test_batch_apps(batch_num=1, batch_size=5):
    """Test opening a batch of apps from apps.json"""
    
    # Load apps.json
    apps_json_path = Path(__file__).parent / "apps.json"
    
    if not apps_json_path.exists():
        print("ERROR: apps.json not found!")
        return 1
    
    with open(apps_json_path, "r", encoding="utf-8") as f:
        apps = json.load(f)
    
    total_apps = len(apps)
    start_idx = (batch_num - 1) * batch_size
    end_idx = start_idx + batch_size
    
    if start_idx >= total_apps:
        print(f"ERROR: Batch {batch_num} is out of range!")
        print(f"Total apps: {total_apps}, total batches: {(total_apps + batch_size - 1) // batch_size}")
        return 1
    
    sorted_apps = sorted(apps.keys())
    batch_apps = sorted_apps[start_idx:end_idx]
    
    print(f"\n{'='*80}")
    print(f"BATCH {batch_num} — Testing {len(batch_apps)} apps (Total: {total_apps})")
    print(f"Apps {start_idx + 1} to {min(end_idx, total_apps)} of {total_apps}")
    print(f"{'='*80}\n")
    
    launcher = AppLauncher()
    results = {
        "success": [],
        "failed": [],
        "skipped": []
    }
    
    for i, app_name in enumerate(batch_apps, start=start_idx + 1):
        app_entry = apps[app_name]
        print(f"[{i:3d}/{total_apps}] Testing: {app_name}")
        print(f"        Entry: {app_entry}")
        
        try:
            # Open app with minimal wait time for testing
            result = await launcher.open_app(app_name, wait_seconds=0.5)
            print(f"        ✓ SUCCESS: {result}")
            results["success"].append(app_name)
        except ValueError as e:
            if "not found" in str(e).lower():
                print(f"        ⊘ SKIPPED: {e}")
                results["skipped"].append((app_name, str(e)))
            else:
                print(f"        ✗ FAILED: {e}")
                results["failed"].append((app_name, str(e)))
        except RuntimeError as e:
            print(f"        ✗ FAILED (Runtime): {e}")
            results["failed"].append((app_name, str(e)))
        except Exception as e:
            print(f"        ✗ FAILED (Exception): {e}")
            results["failed"].append((app_name, str(e)))
        
        print()
    
    # Summary
    print(f"\n{'='*80}")
    print("BATCH SUMMARY")
    print(f"{'='*80}")
    print(f"✓ Success:  {len(results['success'])}/{len(batch_apps)}")
    print(f"✗ Failed:   {len(results['failed'])}/{len(batch_apps)}")
    print(f"⊘ Skipped:  {len(results['skipped'])}/{len(batch_apps)}")
    
    if results["success"]:
        print(f"\nSuccessfully opened:")
        for app in results["success"]:
            print(f"  ✓ {app}")
    
    if results["failed"]:
        print(f"\nFailed to open:")
        for app, error in results["failed"]:
            print(f"  ✗ {app}: {error}")
    
    if results["skipped"]:
        print(f"\nSkipped (not found):")
        for app, error in results["skipped"]:
            print(f"  ⊘ {app}: {error}")
    
    # Next batch info
    next_batch = batch_num + 1
    total_batches = (total_apps + batch_size - 1) // batch_size
    if next_batch <= total_batches:
        print(f"\n→ Next batch: python test_app_launcher.py {next_batch}")
    else:
        print(f"\n✓ All {total_batches} batches completed!")
    
    print(f"\n{'='*80}\n")
    
    # Return exit code based on failures
    return 0 if len(results["failed"]) == 0 else 1


if __name__ == "__main__":
    batch_num = 1
    if len(sys.argv) > 1:
        try:
            batch_num = int(sys.argv[1])
        except ValueError:
            print("Usage: python test_app_launcher.py [batch_number]")
            print("Example: python test_app_launcher.py 1")
            sys.exit(1)
    
    exit_code = asyncio.run(test_batch_apps(batch_num=batch_num, batch_size=5))
    sys.exit(exit_code)
