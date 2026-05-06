<div align="center">

# IntentOS

**An Intent-Based Operating System — control your entire computer with natural language.**

[![Python](https://img.shields.io/badge/Python-3.10%2B-blue?logo=python&logoColor=white)](https://python.org)
[![Node.js](https://img.shields.io/badge/Node.js-18%2B-green?logo=node.js&logoColor=white)](https://nodejs.org)
[![Gemini](https://img.shields.io/badge/Powered%20by-Gemini%202.5%20Flash-orange?logo=google&logoColor=white)](https://ai.google.dev)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Version](https://img.shields.io/badge/version-1.0.0--alpha-blue)](CHANGELOG.md)

</div>

---

## What is IntentOS?

IntentOS is an AI agent that lets you control your entire computer — browser, files, messaging, apps, terminal — using plain English. Instead of clicking through menus, you just say what you want.

```
🤖 IntentOS > summarize "C:\Downloads\report.pdf"
🤖 IntentOS > send "I'll be late" to Rahul on WhatsApp
🤖 IntentOS > open youtube, search python programming and play first video
🤖 IntentOS > find all Python files in my project and list the largest ones
🤖 IntentOS > create a Google Meet for tomorrow at 3pm and send the link to the team
🤖 IntentOS > open Wikipedia page for Virat Kohli and save it to a file
```

IntentOS decomposes your intent into a sequence of atomic steps using **Gemini 2.5 Flash**, executes them using a rich skill library, and learns from past runs using **ChromaDB neural memory**.

---

## Features

| Capability | Description |
|---|---|
| 🧠 **Neural Memory (RAG)** | ChromaDB + Sentence Transformers semantic recall of past workflows and failure patterns |
| 🌐 **Browser Control** | Web navigation and DOM extraction via Chrome Extension WebSocket bridge (MV3) + Playwright |
| 🤖 **Agentic Web Agent** | LLM-guided DOM interaction — fills forms, clicks buttons, submits data on any site automatically |
| 📄 **Direct Page Extraction** | Zero-LLM-cost `getPageText` for reading Wikipedia, articles, blogs — instant and free |
| 📁 **Universal File Extractor** | Read and extract text from PDF, DOCX, DOC, XLSX, PPTX, EPUB, images (OCR), and any plain-text file — fully local |
| 🎬 **YouTube Automation** | Search, play, pause, skip, set volume, capture video URLs — via Chrome extension |
| 📧 **Gmail Integration** | Send, compose, search, and reply to emails directly via extension bridge with verified delivery |
| 📅 **Google Calendar & Meet** | Create events, schedule Google Meet sessions, get calendar events — no manual clicks needed |
| 💾 **Google Drive** | Search and open Drive files via extension commands |
| 🚀 **App Launcher** | Longest-prefix fuzzy-matched native app launching via `apps.json` |
| 💬 **Messaging** | Send WhatsApp and Telegram messages via desktop automation |
| 💻 **Terminal** | Execute PowerShell commands with live output streaming |
| 👁️ **Screen Vision** | Zero-API-cost local screen analysis via MSS + PyAutoGUI |
| 🔄 **Auto-Recovery** | Detects failures, retries with exponential backoff, and replans using RAG failure memory |
| 📅 **Date Normalization** | Converts relative dates ("tomorrow", "next Monday") to ISO dates automatically before planning |
| 🎯 **SOUL.md Macros** | Structured YAML macros bypass the LLM entirely — instant, zero-token-cost named workflows |
| 🛡️ **Safety Guard** | Blocks dangerous commands (rm -rf, format C:) and requires confirmation for destructive ops |
| 📊 **Live Dashboard** | FastAPI + React command center at `localhost:8000` with real-time logs, step chain-of-thought, and memory explorer |

---

## Architecture

```
User (text / voice)
        │
        ▼
  Intent Parser  ──  Gemini 2.5 Flash
        │             ↳ Date normalization (utils/date_utils.py)
        │             ↳ SOUL.md macro short-circuit (zero LLM cost)
        ▼
   Pi Engine (Agent Loop)
        │
   ┌────┴────┐
   │ Planner │  →  step-by-step plan (Gemini API + dynamic SOUL context)
   │Executor │  →  dispatches to skills + template resolution
   │Recovery │  →  retries & replanning via RAG memory
   └────┬────┘
        │
   ┌────▼──────────────────────────────────────────────┐
   │                   Skills Layer                    │
   │  browser │ extension │ files │ terminal │ apps    │
   │  messaging │ vision │ ai │ (auto-routing)         │
   └───────────────────────────────────────────────────┘
        │
   Extension Bridge (WebSocket ws://127.0.0.1:8765)
        ↕  Chrome Extension (Manifest V3)
        │   YouTube │ Gmail │ Calendar │ Meet │ Drive
        │   Web Agent (LLM-guided DOM) │ getPageText
        │
   Neural Memory (ChromaDB RAG + YAML store)
        │
   Dashboard (FastAPI + React + WebSocket)
```

### Smart Extension Routing

The Executor automatically routes browser skill calls to the Chrome Extension when it is connected — no planner change needed. Google domains (YouTube, Gmail, Calendar, Meet, Drive) are always handled by the extension, not raw Playwright, for maximum reliability.

---

## Project Structure

```
IntentOS/
├── agent/                   # Pi Engine — planning, execution, recovery
│   ├── planner.py           # Intent → step plan (Gemini 2.5 Flash)
│   │                        # Dynamic SOUL.md injection, date context, routing rules
│   ├── executor.py          # Step dispatcher, template resolver, smart extension routing
│   ├── rag_executor.py      # RAG memory hooks for executor
│   ├── planner_patch.py     # Plan post-processing (template fixups)
│   └── recovery.py          # Failure detection & retry logic
│
├── skills/                  # Modular skill execution layer
│   ├── files/               # File management + universal text extractor
│   │   ├── file_manager.py  # CRUD, organize, watch, read/write
│   │   └── extractor.py     # PDF, DOCX, XLSX, PPTX, OCR, EPUB, etc.
│   ├── browser/             # Browser automation
│   │   ├── playwright_driver.py   # Playwright CDP bridge
│   │   └── extension_bridge.py    # Chrome Extension WebSocket bridge v3.1
│   │                              # YouTube, Gmail, Calendar, Meet, Drive,
│   │                              # Web Agent (LLM-guided DOM), getPageText
│   ├── terminal/            # PowerShell subprocess execution
│   ├── apps/                # Native app launcher (apps.json, longest-prefix match)
│   ├── messaging/           # WhatsApp / Telegram desktop macros
│   ├── vision/              # MSS screenshot + PyAutoGUI
│   └── ai/                  # LLM reasoning (summarize, ask, analyze)
│
├── memory/                  # Persistence layer
│   ├── rag_store.py         # ChromaDB vector store (workflows + knowledge)
│   ├── store.py             # YAML workflow store
│   ├── soul_reader.py       # SOUL.md macro & rule parser
│   └── workflows/           # Saved workflow YAML files (git-ignored)
│
├── utils/                   # Shared utilities
│   └── date_utils.py        # Relative date normalization (today/tomorrow/next Monday → ISO)
│
├── dashboard/
│   ├── backend/             # FastAPI + WebSocket server (auto port fallback)
│   └── frontend/            # React Vite dashboard
│
├── chrome-extension/        # Manifest V3 Chrome extension (DOM agent)
│   ├── background.js        # WebSocket bridge + tab manager + MV3 service worker
│   ├── content.js           # DOM extraction & interaction
│   ├── popup.html           # Extension popup UI
│   ├── popup.js             # Popup logic
│   └── manifest.json
│
├── voice/
│   └── stt_client.py        # Sarvam AI speech-to-text client
│
├── main.py                  # Application entry point (auto port conflict resolution)
├── integration_patch.py     # Runtime patches (RAG + planning rules)
├── scan_apps.py             # App scanner — populates apps.json
├── SOUL.md                  # User-defined macros, rules & persona (157KB structured YAML)
├── .env.example             # Environment variable template
├── requirements.txt         # Python dependencies (fully audited)
└── package.json             # Node.js dependencies (WhatsApp adapter)
```

---

## Quick Start

### Prerequisites

| Requirement | Version | Notes |
|---|---|---| 
| Python | 3.10+ | `python --version` |
| Node.js | 18+ | Only needed for WhatsApp messaging |
| Google Gemini API | — | API key from [Google AI Studio](https://aistudio.google.com) OR Vertex AI project |
| Tesseract | 5.x | Optional — needed for image OCR only |

### Installation

```bash
# 1. Clone the repository
git clone https://github.com/ayushchandrapatel7051/IntentOS.git
cd IntentOS

# 2. Set up environment
cp .env.example .env
# Edit .env — choose one of the auth options below

# 3a. Auth option A: Gemini API Key (simplest)
#   → Set GEMINI_API_KEY=your-key in .env

# 3b. Auth option B: Vertex AI (enterprise)
#   → Set USE_VERTEX_AI=true, GCP_PROJECT=your-project in .env
#   → Run: gcloud auth application-default login
#   → OR place your service account key at ./credentials.json

# 4. Install Python dependencies
pip install -r requirements.txt

# 5. (Optional) Install Node.js dependencies for WhatsApp
npm install

# 6. (Optional) Install dashboard frontend
cd dashboard/frontend && npm install && cd ../..

# 7. Run IntentOS
python main.py
```

### Access Points

| Service | URL | Description |
|---|---|---|
| REST API | http://127.0.0.1:8000 | FastAPI backend + docs at `/docs` |
| Dashboard | http://127.0.0.1:3000 | React command center (after `npm run frontend`) |
| WebSocket Bridge | ws://127.0.0.1:8765 | Chrome extension bridge |

> **Port auto-fallback**: If port 8000 is busy, IntentOS automatically picks the next available port and prints it in the startup banner.

---

## Chrome Extension Setup

The Chrome extension is required for YouTube, Gmail, Google Calendar, Google Meet, Google Drive, and any web page interaction.

1. Open Chrome → `chrome://extensions`
2. Enable **Developer Mode** (top-right toggle)
3. Click **Load unpacked** → select the `chrome-extension/` folder
4. The extension icon appears in the toolbar — it auto-connects to IntentOS on startup

> The extension uses **Manifest V3** with a persistent WebSocket bridge. It handles MV3 service worker idle-suspend by automatically reconnecting and retrying commands up to 3× with no command loss.

---

## Environment Variables

| Variable | Default | Description |
|---|---|---|
| `GEMINI_API_KEY` | — | Gemini API key (use this OR Vertex AI) |
| `USE_VERTEX_AI` | `false` | Set to `true` to use Vertex AI instead of API key |
| `GCP_PROJECT` | — | Google Cloud project ID (Vertex AI only) |
| `GCP_LOCATION` | `us-central1` | GCP region (Vertex AI only) |
| `GEMINI_MODEL` | `gemini-2.5-flash` | Gemini model to use for planning |
| `EXTENSION_WS_PORT` | `8765` | WebSocket port for Chrome extension bridge |
| `DASHBOARD_HOST` | `127.0.0.1` | Dashboard bind host |
| `DASHBOARD_PORT` | `8000` | Dashboard bind port |
| `SARVAM_API_KEY` | — | Optional: Sarvam AI STT for voice input |
| `CONFIRM_DELETIONS` | `true` | Require confirmation before deleting files |

---

## 🐳 Docker

### Prerequisites

- [Docker Desktop](https://www.docker.com/products/docker-desktop/) installed and running
- `credentials.json` (Google Cloud service account key) placed at the repo root
- `.env` file configured (copy from `.env.example`)

### Setup

```bash
# Enable Vertex AI API on your GCP project (one-time)
gcloud services enable aiplatform.googleapis.com --project=YOUR_PROJECT_ID

# Grant Vertex AI access to your service account (one-time)
gcloud projects add-iam-policy-binding YOUR_PROJECT_ID \
  --member="serviceAccount:YOUR_SA@YOUR_PROJECT_ID.iam.gserviceaccount.com" \
  --role="roles/aiplatform.user"
```

### Running with Docker

```bash
# Start all services (backend + frontend)
docker compose up -d

# Start only the backend
docker compose up -d intentos-backend

# Start only the frontend
docker compose up -d intentos-frontend

# Start with WhatsApp bridge (optional profile)
docker compose --profile whatsapp up -d
```

### Building & Rebuilding

```bash
# Build all images
docker compose build

# Rebuild from scratch after code changes (no cache)
docker compose build --no-cache

# Rebuild and restart in one command
docker compose up -d --build
```

### Logs

```bash
# Live logs for all services
docker compose logs -f

# Live logs for a specific service
docker compose logs -f intentos-backend

# Last 100 lines
docker compose logs --tail=100 intentos-backend
```

### Stopping & Cleanup

```bash
# Stop all containers (keeps volumes)
docker compose down

# Stop and remove volumes (clears memory, logs, screenshots)
docker compose down -v
```

### Volumes

IntentOS uses named Docker volumes to persist data across container restarts:

| Volume | Contents |
|---|---|
| `intentos-memory` | ChromaDB vector store + YAML workflows |
| `intentos-logs` | Agent execution logs |
| `intentos-screenshots` | Screen vision captures |
| `intentos-whatsapp-auth` | WhatsApp session auth (optional) |

---

## SOUL.md — Personalisation

`SOUL.md` lets you define custom macros, shortcuts, behaviour rules, and your personal AI persona. It is a structured YAML document parsed at startup and injected dynamically into every Gemini planning prompt.

```markdown
## Macros
- "start work" → open VS Code, open terminal, run npm run dev
- "standup" → open Notion, open Slack, summarise yesterday's git log

## Rules
- Always confirm before deleting files
- Prefer dark mode apps

## Preferences
editor: visual studio code
browser: chrome
```

**Macro short-circuit**: If you invoke a named SOUL macro, the Planner bypasses Gemini entirely and runs the macro steps directly — zero token cost, instant execution.

---

## Skill Reference

### Browser Skill
```
browser.navigate(url, browser="chrome"|"edge")
browser.search(query, engine="google")
browser.fill_form(selector, value)
browser.click(selector)
browser.extract_text(selector)
browser.screenshot()
```

### Extension Skill (Chrome Extension required)
```
# YouTube
extension.searchYouTube(query, video_index=1)
extension.playYouTube() | pauseYouTube() | nextVideo()
extension.setVolume(level=50) | seekTo(seconds) | getVideoInfo()

# Gmail
extension.sendMail(to, subject, body)
extension.composeMail(to, subject, body, send=false)
extension.searchMail(query) | getUnread()
extension.replyMail(tab_id, body)

# Google Calendar & Meet
extension.createEvent(title, date="YYYY-MM-DD", time="HH:MM", duration=60, meet=false)
extension.getEvents(date) | openCalendar()
extension.joinMeet(url) | muteMic() | muteCamera() | leaveMeet()

# Google Drive
extension.searchDrive(query) | openDriveFile(file_id)

# Page interaction
extension.web_agent(url, task="describe what to do")   # LLM-guided DOM
extension.getPageText(tab_id, selector="body")          # Zero-LLM-cost extraction
```

### Files Skill
```
files.read_file(path)
files.write_file(path, content)
files.move(source, destination) | copy() | rename() | delete()
files.list_dir(path) | organize_by_type(directory) | create_dir(path)
files.watch(directory)
```

### Apps Skill
```
apps.open_app(name)           # e.g. "visual studio code", "notepad C:\file.txt"
apps.list_apps(filter)
apps.scan_apps()
```

### Terminal Skill (PowerShell)
```
terminal.execute(command)
terminal.execute_background(command)
```

### Messaging Skill
```
messaging.send_message(app="whatsapp"|"telegram", contact, text)
messaging.open_chat(app, contact)
```

### AI Skill
```
ai.ask(prompt, context)
ai.summarize(context)
```

---

## Supported File Types (Universal Extractor)

| Category | Extensions |
|---|---|
| Documents | `.pdf` `.docx` `.doc` `.pptx` `.rtf` `.epub` |
| Spreadsheets | `.xlsx` `.xls` `.ods` `.csv` `.tsv` |
| Data / Code | `.json` `.jsonl` `.ipynb` `.py` `.js` `.ts` `.md` `.yaml` and all plain-text |
| Images (OCR) | `.jpg` `.png` `.gif` `.bmp` `.tiff` `.webp` |
| Archives | `.zip` `.tar` `.gz` (lists contents) |

All extraction is **local** — no file contents are sent to any external API.

---

## Example Commands

```
# Documents
summarize "C:\Documents\Q4_Report.pdf"
tell me what's in this Excel file "C:\data\sales.xlsx"

# Web & Browser
open Wikipedia page for Virat Kohli and save it to a file
open Chrome and go to gmail.com
extract all text from the current page and save to notes.txt

# YouTube
search python tutorials on YouTube and play the first video
search lo-fi music on YouTube and play the second result
set YouTube volume to 60

# Gmail & Calendar
send email to john@example.com with subject "Meeting" and body "See you at 3pm"
create a Google Meet for tomorrow at 10am and send the link to Rahul on WhatsApp
check my unread emails

# Files & Terminal
find all .log files in Downloads and delete ones older than 7 days
create a Python script that renames all JPEGs by date and save to Desktop
organize my Downloads folder by file type

# Messaging
send "meeting at 3pm" to team on WhatsApp
open Telegram and message Rahul "I'll be late"

# System
open VS Code and create a new React project in my projects folder
open Calculator
scan my installed apps
```

---

## New Features Since v0.x

### Extension Bridge v3.1
- **3× retry on disconnect**: Commands are never silently dropped when the MV3 service worker restarts
- **Verified delivery**: `sendMail`, `createEvent`, `scheduleMeet` check a `verified` field — unverified actions trigger recovery/replan
- **Tab ID guardrails**: Unresolved `{{template}}` tab IDs are automatically stripped so the extension falls back to the active tab
- **Auto tab tracking**: After `navigate` or `web_agent`, the executor stores the resulting `tabId` in shared context for downstream steps

### Web Agent (LLM-guided DOM)
- Multi-step page interaction using Gemini to decide which DOM elements to click/fill
- Dedicated action verbs: `fill`, `fill_react`, `click`, `enter`, `select`, `scroll`, `navigate`, `extract_text`, `done`
- Smart stop rules: detects YouTube `/watch?v=` URLs and stops automatically
- One-shot social actions (like, follow, retweet) with immediate `done` to prevent loops

### Direct Page Extraction (`getPageText`)
- Zero-LLM-cost text extraction from any CSS selector
- Used for Wikipedia (`#mw-content-text`), articles (`article`), full pages (`body`)
- Returns raw text that downstream steps (write_file, messaging) can use directly
- Server-side HTML fetching via `requests` + `BeautifulSoup` as fast path for static pages

### Date Normalization Utility
- `utils/date_utils.py` converts "tomorrow", "next Monday", "day after tomorrow" → ISO `YYYY-MM-DD`
- Applied automatically to every intent before planning
- Applied to `date` parameters at execution time in the executor

### SOUL.md Structured Macros
- Macros are now full YAML action objects, not just text strings
- Macro short-circuit bypasses Gemini entirely for named workflows
- Supported action types: `open_browser`, `open_editor`, `read_calendar`, `notify_user`

### Auto Port Conflict Resolution
- Dashboard auto-scans ports 8000–8019 and picks the first free one
- Extension bridge (port 8765) kills any stale process holding the port on restart
- Both behaviors are logged in the startup banner

### Safety Layer
- `_validate_action_safety()` blocks dangerous patterns before execution
- Emits `step_blocked` or `confirm_required` WebSocket events for the dashboard
- Driven by `SOUL.md safety_rules` — fully user-configurable

---

## Contributing

Pull requests are welcome. For major changes, open an issue first.

```bash
# Run from repo root
python main.py          # Start the agent
python scan_apps.py     # Regenerate apps.json for your machine
```

---

## License

[MIT](LICENSE) © IntentOS Contributors