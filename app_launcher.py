import json
import subprocess
import difflib
import webbrowser
import urllib.parse
import re
import os
import time

# Load apps
with open("apps.json", "r", encoding="utf-8-sig") as f:
    apps = json.load(f)

# --- Setups (Macros) ---
SETUPS_FILE = "setups.json"

def load_setups():
    if not os.path.exists(SETUPS_FILE):
        return {}
    try:
        with open(SETUPS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

def save_setups(setups_data):
    with open(SETUPS_FILE, "w", encoding="utf-8") as f:
        json.dump(setups_data, f, indent=4)

setups = load_setups()

def create_setup(name):
    if name in setups:
        ans = input(f"⚠️ Setup '{name}' already exists. Overwrite? (y/n): ")
        if ans.lower() != 'y':
            print("❌ Cancelled.")
            return

    print(f"🛠️ Creating setup: '{name}'")
    print("Enter commands one by one. Type 'done' when finished. (Max 10)")
    
    commands = []
    while len(commands) < 10:
        cmd = input(f"  [{len(commands)+1}/10] > ").strip()
        if cmd.lower() == "done":
            break
        if not cmd:
            continue
        commands.append(cmd)
        
    if not commands:
        print("❌ No commands added. Cancelled.")
        return
        
    setups[name] = commands
    save_setups(setups)
    print(f"✅ Setup '{name}' saved with {len(commands)} commands!")

def run_setup(name):
    if name not in setups:
        print(f"❌ Setup '{name}' not found.")
        return
        
    commands = setups[name]
    print(f"🚀 Running setup: '{name}' ({len(commands)} commands)")
    for i, cmd in enumerate(commands, 1):
        print(f"\n[{i}/{len(commands)}] Executing: {cmd}")
        run_raw_command(cmd)
        if i < len(commands):
            time.sleep(1)
    print(f"\n✅ Setup '{name}' complete!")

# Hardcoded Bookmarks
BOOKMARKS = {
    "bloomberg": "https://bloomberg.com",
    "leetcode": "https://leetcode.com",
    "reddit": "https://reddit.com",
    "github": "https://github.com",
    "gmail": "https://mail.google.com",
    "chatgpt": "https://chat.openai.com",
    "twitter": "https://twitter.com",
    "x": "https://x.com",
    "netflix": "https://netflix.com",
    "amazon": "https://amazon.com",
    "stackoverflow": "https://stackoverflow.com",
    "discord": "https://discord.com"
}

# --- History State ---
command_history = []

def add_to_history(cmd):
    # Store last 20 commands
    command_history.append(cmd)
    if len(command_history) > 20:
        command_history.pop(0)

def show_history():
    if not command_history:
        print("📭 History is empty.")
        return
    print("📜 Command History:")
    for i, cmd in enumerate(command_history, 1):
        print(f"  {i}. {cmd}")

def repeat_command(n):
    if not command_history:
        print("❌ History is empty.")
        return
    if n < 1 or n > len(command_history):
        print(f"❌ Invalid history index. Enter a number between 1 and {len(command_history)}.")
        return
    
    # n is 1-indexed for nth last. n=1 is last, n=2 is second last.
    cmd_to_repeat = command_history[-n]
    print(f"🔄 Repeating: {cmd_to_repeat}")
    
    # Execute the repeated command
    run_raw_command(cmd_to_repeat)

def normalize(text):
    text = text.lower()
    return text.strip()

def find_best_match(user_input):
    user_input = normalize(user_input)
    words = user_input.split()
    remove_words = ["open", "start", "launch", "run"]
    query = " ".join([w for w in words if w not in remove_words])
    
    if not query:
        return None, 0
    
    best_match = None
    best_score = 0

    # 1. Check against App Names and Aliases
    for app_name, data in apps.items():
        names = [app_name]
        if "aliases" in data:
            names.extend(data["aliases"])

        for name in names:
            score = difflib.SequenceMatcher(None, query, name).ratio()
            if score > best_score:
                best_score = score
                best_match = app_name
                
    # 2. Check against Bookmarks (treated like apps for fuzzy matching)
    for site_name in BOOKMARKS.keys():
        score = difflib.SequenceMatcher(None, query, site_name).ratio()
        if score > best_score:
            best_score = score
            best_match = site_name

    return best_match, best_score

def launch_app(app_name):
    # Check if it's a bookmark first
    if app_name in BOOKMARKS:
        url = BOOKMARKS[app_name]
        print(f"🌐 Opening Bookmark: {app_name} ({url})")
        webbrowser.open(url)
        return

    # Otherwise treat as installed app
    app = apps[app_name]
    try:
        if app.get("launch_command"):
            subprocess.Popen(app["launch_command"], shell=True)
        elif app.get("shortcut"):
            subprocess.Popen(app["shortcut"], shell=True)
        else:
            print("No valid launch method found.")
    except Exception as e:
        print("Error launching app:", e)

def suggest_apps(user_input, apps_dict):
    user_input = normalize(user_input)
    words = user_input.split()
    remove_words = ["open", "start", "launch", "run"]
    query = " ".join([w for w in words if w not in remove_words])
    
    if not query:
        return
        
    all_names = list(apps_dict.keys())
    for data in apps_dict.values():
        if "aliases" in data:
            all_names.extend(data["aliases"])
    
    # Add bookmarks to suggestions
    all_names.extend(BOOKMARKS.keys())
            
    suggestions = difflib.get_close_matches(query, all_names, n=3, cutoff=0.4)
    
    if suggestions:
        print("💡 Did you mean:")
        shown = set()
        for s in suggestions:
            if s not in shown:
                print(f"   - {s}")
                shown.add(s)

def launch_web_search(cmd, intent):
    cmd_lower = cmd.lower()
    words = cmd_lower.split()
    
    stop_words = ["open", "start", "launch", "run", "search", "play", "watch", "youtube", "google", "wikipedia", "wiki", "video", "for", "on", "the"]
    query_words = [w for w in words if w not in stop_words]
    query = " ".join(query_words)
    
    if not query:
        if intent == "youtube":
            url = "https://www.youtube.com/"
            site_name = "YouTube"
        elif intent == "wikipedia":
            url = "https://en.wikipedia.org/"
            site_name = "Wikipedia"
        else:
            url = "https://www.google.com/"
            site_name = "Google"
        
        print(f"🌐 Opening {site_name}...")
        webbrowser.open(url)
        return
        
    encoded_query = urllib.parse.quote(query)
    
    if intent == "youtube":
        url = f"https://www.youtube.com/results?search_query={encoded_query}"
        print(f"🌐 Searching YouTube for: '{query}'")
    elif intent == "wikipedia":
        wiki_query = urllib.parse.quote(query.replace(" ", "_"))
        url = f"https://en.wikipedia.org/wiki/{wiki_query}"
        print(f"🌐 Searching Wikipedia for: '{query}'")
    else:
        url = f"https://www.google.com/search?q={encoded_query}"
        print(f"🌐 Searching Google for: '{query}'")
        
    webbrowser.open(url)

def process_command(cmd):
    cmd = cmd.strip()
    if not cmd:
        return

    cmd_lower = cmd.lower()
    words = cmd_lower.split()
    
    # --- Check for Setups (Macros) ---
    remove_words = ["open", "start", "launch", "run", "execute"]
    query = " ".join([w for w in words if w not in remove_words])
    
    if query in setups:
        run_setup(query)
        return
    if cmd_lower in setups:
        run_setup(cmd_lower)
        return

    # 1. Direct Domain Website Intent
    domain_extensions = [".com", ".org", ".net", ".io", ".in"]
    has_domain = False
    domain_match = None
    
    for word in words:
        if any(ext in word for ext in domain_extensions):
            has_domain = True
            domain_match = word
            break
            
    if has_domain:
        domain_match = domain_match.strip('.,/\\!?"\'')
        url = domain_match if domain_match.startswith("http") else f"https://{domain_match}"
        print(f"🌐 Opening website: {domain_match}")
        webbrowser.open(url)
        return

    # 2. Known Web Intents (YouTube / Wiki)
    yt_words = ["youtube", "video", "watch", "ted"]
    wiki_words = ["wiki", "wikipedia"]
    
    if any(w in words for w in yt_words):
        launch_web_search(cmd, "youtube")
        return
    if any(w in words for w in wiki_words):
        launch_web_search(cmd, "wikipedia")
        return

    # 3. Fuzzy App/Bookmark Matching
    match, score = find_best_match(cmd)
    
    has_action = any(w in words for w in remove_words)
    is_multi_word = len(words) > 1
    
    threshold = 0.7
    if is_multi_word and not has_action:
        threshold = 0.85 # Stricter for natural language multi-word queries
        
    if score >= threshold:
        print(f"🚀 Opening: {match} (score: {round(score,2)})")
        launch_app(match)
        return

    # 4. Fallback Search
    if len(words) == 1:
        suggest_apps(cmd, apps)
        print(f"❌ No app found (highest score: {round(score,2)} < {threshold}). Falling back to Google Search...")
        launch_web_search(cmd, "google")
    else:
        print(f"🔍 Treating as search query: '{cmd}'")
        launch_web_search(cmd, "google")

def run_raw_command(raw_cmd):
    # Split by " and " or " & " to handle multiple commands together
    sub_cmds = re.split(r'\s+and\s+|\s+&\s+', raw_cmd, flags=re.IGNORECASE)
    
    for sub_cmd in sub_cmds:
        process_command(sub_cmd)

# 🔥 Main loop
print("--- IntentOS App Launcher Ready ---")
while True:
    try:
        raw_cmd = input(">>> ").strip()
    except (EOFError, KeyboardInterrupt):
        break

    if not raw_cmd:
        continue

    if raw_cmd.lower() in ["exit", "quit"]:
        break

    # Setup/Macro Logic
    cmd_lower = raw_cmd.lower()
    if cmd_lower.startswith("create setup "):
        setup_name = cmd_lower.replace("create setup ", "", 1).strip()
        if setup_name:
            create_setup(setup_name)
        else:
            print("❌ Usage: create setup <name>")
        continue
        
    # History Command Logic
    if cmd_lower == "history":
        show_history()
        continue
        
    if cmd_lower.startswith("repeat"):
        parts = cmd_lower.split()
        if len(parts) == 1:
            # "repeat" -> execute last command
            repeat_command(1)
            continue
        elif len(parts) == 2 and parts[1].isdigit():
            # "repeat n" -> execute nth last command
            n = int(parts[1])
            repeat_command(n)
            continue
            
    # Add to history (only if it's not history/repeat)
    add_to_history(raw_cmd)
    
    # Execute normal command
    run_raw_command(raw_cmd)