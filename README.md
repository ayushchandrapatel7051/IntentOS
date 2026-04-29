# 🐾 OpenClaw

## Intent-Based Operating System

> Control your entire computer with natural language.

**Version:** 1.0.0-alpha | **License:** MIT | **Runtime:** Node.js 22 + Python 3.11+

---

## Overview

OpenClaw is an intent-based operating system layer that lets you control your entire computer — browser, terminal, messaging, files, and calendar — using plain English, Hindi, or Hinglish commands. Instead of manually clicking through apps, you simply state what you want and OpenClaw's AI agent loop figures out how to do it.

It combines the reasoning power of **Claude API** with OpenClaw's **Pi Engine** agent loop, **Sarvam AI**'s Indian-language speech recognition, and a rich set of automation tools — all surfaced through a live **Command Center Dashboard**.

## Key Capabilities

| Capability | Description |
|---|---|
| 🌐 **Browser Control** | Search, research, fill forms, manage Gmail & Google Calendar via Chrome Extension + Playwright/CDP |
| 💬 **Messaging** | Send/receive WhatsApp and Telegram messages; vision fallback when APIs are unavailable |
| 💻 **Terminal Control** | Execute shell commands in a sandboxed Docker environment |
| 📁 **File Management** | Move, rename, delete, organise files; auto-watch directories with watchdog |
| 👁️ **Screen Vision** | Screenshot → Claude Vision API → PyAutoGUI click/type for any UI |
| 🧠 **Memory & Learning** | Persist workflows in YAML store; load macros & rules from SOUL.md |
| 🔄 **Failure Recovery** | Auto-detect errors, retry with exponential backoff, replan with Claude |
| 📊 **Command Center** | Real-time execution tracking with logs and AI reasoning via WebSocket |
| 🎤 **Voice Input** | Hindi, Hinglish, and Indian language voice commands via Sarvam AI |
| 📅 **Calendar & Push** | Google Calendar integration with proactive reminders via APScheduler |
| 🎥 **Meeting Co-Pilot** | Transcribe meetings and generate structured minutes with Claude |

## Quick Start

### Prerequisites
- Node.js 22+
- Python 3.11+
- Docker (optional, for sandboxed terminal)
- API Keys: Anthropic (Claude), Sarvam AI, Google Calendar OAuth 2.0

### Installation

```bash
# 1. Clone
git clone https://github.com/your-org/openclaw.git
cd openclaw

# 2. Install Python dependencies
pip install -r requirements.txt

# 3. Install Node.js dependencies
npm install

# 4. Install dashboard frontend
cd dashboard/frontend && npm install && cd ../..

# 5. Configure environment
cp .env.example .env
# Edit .env with your API keys

# 6. Start OpenClaw
python main.py
```

### Open the Dashboard
Navigate to **http://localhost:8000** for the API, or run the frontend dev server:

```bash
cd dashboard/frontend
npm run dev
```

Dashboard will be available at **http://localhost:5173**

## Architecture

```
User (Voice / Text) → Sarvam AI STT + Intent Parser (Claude API)
                    → Pi Engine (Agent Loop & Reasoning)
                    → Skills: Browser | Terminal | Messaging | Files | Vision
                    → Memory Store (YAML / SOUL.md) + Failure Recovery
                    → Command Center Dashboard (FastAPI + React + WebSocket)
```

## Project Structure

```
IntentOS/
├── agent/               # Pi Engine agent loop
│   ├── planner.py       # Intent → step decomposition (Claude API)
│   ├── executor.py      # Step execution dispatcher
│   └── recovery.py      # Failure detection and retry
├── skills/              # Skill Execution Layer
│   ├── browser/         # Playwright + Chrome Extension bridge
│   ├── messaging/       # WhatsApp (Node.js) + Telegram (Python)
│   ├── terminal/        # Sandboxed shell execution
│   ├── files/           # File management + watchdog
│   └── vision/          # Screenshot + Claude Vision + PyAutoGUI
├── memory/              # YAML store + SOUL.md reader
├── dashboard/
│   ├── backend/         # FastAPI + WebSocket server
│   └── frontend/        # React Command Center UI
├── voice/               # Sarvam AI STT integration
├── calendar/            # Google Calendar + APScheduler
├── meeting/             # Audio capture + meeting minutes
├── chrome-extension/    # Manifest V3 Chrome extension
├── SOUL.md              # User macros & behaviour rules
├── main.py              # Application entry point
└── docker-compose.yml   # Containerized deployment
```

## SOUL.md

Your personal behaviour file. Define macros and rules in plain English:

```markdown
## Macros
### start my day
- Open Gmail in Chrome
- Check Google Calendar for today's events
- Open VS Code with the last active project

## Rules
### Safety
- Always ask before deleting files permanently
- Do not run any git push without my confirmation
```

## Example Commands

| Command | What Happens |
|---|---|
| `"Send I'll be late to Rahul"` | Opens WhatsApp → finds Rahul → sends message |
| `"Organise my downloads"` | Groups by type → renames by date → deletes duplicates |
| `"Research AI agents"` | Opens Chrome → searches → opens top results → summarises |
| `"Kal ki meeting cancel karo"` | Hindi STT → parses intent → cancels calendar event |
| `"Start backend work"` | Opens VS Code → runs dev server → opens localhost |
| `"What's on today?"` | Fetches calendar → formats summary → sends to WhatsApp |

## Security

- Terminal commands run in Docker containers by default
- File deletion always prompts for confirmation
- Messaging sessions are stored locally only
- Dashboard is bound to localhost by default
- Git push requires explicit confirmation

## License

MIT License. See [LICENSE](LICENSE) for details.

---

**Built with** OpenClaw Pi Engine + Claude API + Sarvam AI
