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
🤖 IntentOS > open VS Code and run the dev server
🤖 IntentOS > find all Python files in my project and list the largest ones
```

IntentOS decomposes your intent into a sequence of atomic steps using **Gemini 2.5 Flash**, executes them using a rich skill library, and learns from past runs using **ChromaDB neural memory**.

---

## Features

| Capability | Description |
|---|---|
| 🧠 **Neural Memory (RAG)** | ChromaDB + Sentence Transformers semantic recall of past workflows and failure patterns |
| 🌐 **Browser Control** | Web navigation and DOM extraction via Chrome Extension WebSocket bridge + Playwright |
| 📁 **Universal File Extractor** | Read and extract text from PDF, DOCX, DOC, XLSX, PPTX, EPUB, images (OCR), and any plain-text file — fully local, no API cost |
| 🚀 **App Launcher** | Fuzzy-matched native app launching via `apps.json` |
| 💬 **Messaging** | Send WhatsApp and Telegram messages via desktop automation |
| 💻 **Terminal** | Execute shell commands with live output streaming |
| 👁️ **Screen Vision** | Zero-API-cost local screen analysis via MSS + PyAutoGUI |
| 🔄 **Auto-Recovery** | Detects failures, retries with exponential backoff, and replans using RAG failure memory |
| 📊 **Live Dashboard** | React command center at `localhost:3000` with real-time logs, step chain-of-thought, and memory explorer |

---

## Architecture

```
User (text / voice)
        │
        ▼
  Intent Parser  ──  Gemini 2.5 Flash (Vertex AI)
        │
        ▼
   Pi Engine (Agent Loop)
        │
   ┌────┴────┐
   │ Planner │  →  step-by-step plan
   │Executor │  →  dispatches to skills
   │Recovery │  →  retries & replanning
   └────┬────┘
        │
   ┌────▼──────────────────────────────────┐
   │              Skills Layer             │
   │  browser │ files │ terminal │ apps   │
   │  messaging │ vision │ ai │ extension │
   └───────────────────────────────────────┘
        │
   Neural Memory (ChromaDB RAG + YAML store)
        │
   Dashboard (FastAPI + React + WebSocket)
```

---

## Project Structure

```
IntentOS/
├── agent/                   # Pi Engine — planning, execution, recovery
│   ├── planner.py           # Intent → step plan (Gemini API)
│   ├── executor.py          # Step dispatcher & template resolver
│   ├── rag_executor.py      # RAG memory hooks for executor
│   ├── planner_patch.py     # Plan post-processing (template fixups)
│   └── recovery.py          # Failure detection & retry logic
│
├── skills/                  # Modular skill execution layer
│   ├── files/               # File management + universal text extractor
│   │   ├── file_manager.py  # CRUD, organize, watch
│   │   └── extractor.py     # PDF, DOCX, XLSX, PPTX, OCR, etc.
│   ├── browser/             # Playwright + Chrome Extension bridge
│   ├── terminal/            # Subprocess shell execution
│   ├── apps/                # Native app launcher (apps.json fuzzy match)
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
├── dashboard/
│   ├── backend/             # FastAPI + WebSocket server
│   └── frontend/            # React Vite dashboard
│
├── chrome-extension/        # Manifest V3 Chrome extension (DOM agent)
│   ├── background.js        # WebSocket bridge + tab manager
│   ├── content.js           # DOM extraction & interaction
│   └── manifest.json
│
├── voice/
│   └── stt_client.py        # Sarvam AI speech-to-text client
│
├── main.py                  # Application entry point
├── integration_patch.py     # Runtime patches (RAG + planning rules)
├── scan_apps.py             # App scanner — populates apps.json
├── SOUL.md                  # User-defined macros & behaviour rules
├── .env.example             # Environment variable template
├── requirements.txt         # Python dependencies
└── package.json             # Node.js dependencies (WhatsApp adapter)
```

---

## Quick Start

### Prerequisites

| Requirement | Version | Notes |
|---|---|---|
| Python | 3.10+ | `python --version` |
| Node.js | 18+ | Only needed for WhatsApp messaging |
| Google Cloud | — | Vertex AI project with Gemini API enabled |
| Tesseract | 5.x | Optional — needed for image OCR only |

### Installation

```bash
# 1. Clone the repository
git clone https://github.com/ayushchandrapatel7051/IntentOS.git
cd IntentOS

# 2. Set up environment
cp .env.example .env
# Edit .env — set GCP_PROJECT_ID and GCP_LOCATION

# 3. Authenticate with Google Cloud
gcloud auth application-default login
# OR place your service account key at ./credentials.json

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
| WebSocket | ws://127.0.0.1:8765 | Chrome extension bridge |

---

## Chrome Extension

Load the extension for browser control:

1. Open Chrome → `chrome://extensions`
2. Enable **Developer Mode**
3. Click **Load unpacked** → select the `chrome-extension/` folder
4. The extension icon should appear — click it to connect

---

## SOUL.md — Personalisation

`SOUL.md` lets you define custom macros, shortcuts, and behaviour rules:

```markdown
## Macros
- "start work" → open VS Code, open terminal, run npm run dev
- "standup" → open Notion, open Slack, summarise yesterday's git log

## Rules
- Always confirm before deleting files
- Prefer dark mode apps
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
summarize "C:\Documents\Q4_Report.pdf"
open Chrome and go to gmail.com
send "meeting at 3pm" to team on WhatsApp
find all .log files in Downloads and delete ones older than 7 days
create a Python script that renames all JPEGs by date and save to Desktop
tell me what's in this Excel file "C:\data\sales.xlsx"
```

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
