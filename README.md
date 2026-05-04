# 🐾 OpenClaw (IntentOS)

## Intent-Based Operating System

> Control your entire computer with natural language.

**Version:** 1.0.0-alpha | **License:** MIT | **Runtime:** Node.js 22 + Python 3.9+

---

## Overview

OpenClaw is an intent-based operating system layer that lets you control your entire computer — browser, terminal, messaging, files, applications, and calendar — using plain English commands. Instead of manually clicking through apps, you simply state what you want and OpenClaw's AI agent loop figures out how to execute it.

It combines the blazing fast reasoning power of **Google Gemini 2.5 Flash** with OpenClaw's **Pi Engine** agent loop, **ChromaDB Semantic Memory**, and a rich set of automation tools — all surfaced through a live **React Command Center Dashboard**.

## Key Capabilities

| Capability | Description |
|---|---|
| 🧠 **Neural Memory (RAG)** | ChromaDB + Sentence Transformers semantic memory for past workflow retrieval, knowledge storing, and failure pattern avoidance |
| 🌐 **Browser Control** | Intelligent web navigation and deterministic content extraction via Chrome Extension WebSocket Bridge + Playwright |
| 🚀 **App Launcher** | Lightning fast native desktop app launching with intelligent fuzzy-matching via `apps.json` |
| 💬 **Messaging** | Send WhatsApp and Telegram messages via desktop app automation |
| 💻 **Terminal Control** | Execute shell commands and manipulate the system natively via subprocess |
| 📁 **File Management** | Move, rename, delete, organise files; **Universal Text Extractor** for reading PDFs, DOCX, Images (OCR), and more; auto-watch directories with watchdog |
| 👁️ **Screen Vision** | Zero-API-cost local screen automation using MSS screenshots + PyAutoGUI |
| 🔄 **Failure Recovery** | Auto-detect errors, retry with exponential backoff, and replan using past RAG failure contexts |
| 📊 **Command Center** | Real-time React dashboard with Live Logs, Chain-of-Thought reasoning, and Neural Memory Explorer |

## Quick Start

### Prerequisites
- Node.js 22+
- Python 3.9+
- API Keys: Google Cloud Platform (Vertex AI Gemini API credentials)

### Installation

```bash
# 1. Clone
git clone https://github.com/ayushchandrapatel7051/IntentOS.git
cd IntentOS

# 2. Install Python dependencies
pip install -r requirements.txt
pip install chromadb sentence-transformers

# 3. Install Node.js dependencies
npm install

# 4. Install dashboard frontend
cd dashboard/frontend && npm install && cd ../..

# 5. Configure environment
cp .env.example .env
# Edit .env with your GCP details (PROJECT_ID, LOCATION) and authenticate:
# gcloud auth application-default login

# 6. Start OpenClaw
python main.py
```

### Open the Dashboard
Navigate to **http://localhost:8000** for the FastAPI backend, or run the frontend dev server:

```bash
cd dashboard/frontend
npm run dev
```

Dashboard will be available at **http://localhost:5173**

## Architecture

```
User (Voice / Text) → Intent Parser (Gemini 2.5 Flash)
                    → Pi Engine (Agent Loop & Reasoning)
                    → Skills: Browser | Terminal | Messaging | Files | Apps | Vision
                    → Neural Memory (ChromaDB RAG + YAML store)
                    → Command Center Dashboard (FastAPI + React + WebSocket)
```

## Project Structure

```text
IntentOS/
├── agent/               # Pi Engine agent loop
│   ├── planner.py       # Intent → step decomposition (Gemini API)
│   ├── executor.py      # Step execution dispatcher
│   ├── rag_executor.py  # RAG memory execution augmentations
│   └── recovery.py      # Failure detection and retry
├── skills/              # Skill Execution Layer
│   ├── browser/         # Chrome Extension WebSocket bridge + Playwright
│   ├── messaging/       # WhatsApp / Telegram desktop macro routing
│   ├── terminal/        # PowerShell / Shell execution
│   ├── apps/            # Longest-prefix app launcher matching
│   ├── files/           # File management
│   └── vision/          # Screenshot + PyAutoGUI
├── memory/              # ChromaDB RAG Semantic Store + YAML workflows
├── dashboard/
│   ├── backend/         # FastAPI + WebSocket server
│   └── frontend/        # React Command Center UI + Memory Explorer
├── chrome-extension/    # Manifest V3 Chrome extension (DOM Agent)
├── main.py              # Application entry point
├── integration_patch.py # Dynamic startup patcher for RAG & Planning rules
└── SOUL.md              # User macros & behaviour rules
```

## Example Commands

| Command | What Happens |
|---|---|
| `"Send I'll be late to Rahul"` | Opens WhatsApp → finds Rahul → sends message |
| `"Create a google meet link for May 4 and send it to Jaidev"` | Triggers browser skill → creates event → copies link → routes to WhatsApp |
| `"Extract the main introduction of Virat Kohli from Wikipedia"` | Navigates to Wikipedia → executes deterministic DOM text extraction → returns content |
| `"Start backend work"` | Uses App Launcher to open VS Code → runs dev server |
| `"Summarize the financial_report.pdf"` | Reads the PDF using Universal Text Extractor → LLM summarizes the content |
| `"What's on today?"` | Fetches calendar → formats summary → sends to WhatsApp |

## Security

- File deletion always prompts for confirmation in the CLI / Dashboard
- Messaging sessions are stored locally only
- Execution is strictly bounded to the configured local skills
- Terminal operations are continuously logged via WebSockets

## License

MIT License. See [LICENSE](LICENSE) for details.

---

**Built with** OpenClaw Pi Engine + Google Gemini 2.5 Flash + ChromaDB
