# ==========================================
# IntentOS — Dockerfile
# ==========================================
# Multi-stage build:
#   base      — shared Python + Node.js deps
#   py-deps   — installs Python packages
#   node-deps — installs Node packages
#   agent     — production image (main.py)
#   backend   — FastAPI only (headless / API server)
# ==========================================

# ── Stage 1: Base OS + system deps ────────
FROM python:3.11-slim AS base

ARG DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y --no-install-recommends \
        curl \
        gnupg \
        ca-certificates \
        build-essential \
        # Playwright system deps
        libnss3 libnspr4 libatk1.0-0 libatk-bridge2.0-0 \
        libcups2 libdrm2 libdbus-1-3 libxkbcommon0 libxcomposite1 \
        libxdamage1 libxfixes3 libxrandr2 libgbm1 libasound2 \
        # Tesseract OCR (optional — for image text extraction)
        tesseract-ocr \
        tesseract-ocr-eng \
        # Audio support for voice input
        portaudio19-dev \
        # Antiword for legacy .doc files
        antiword \
    && curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user
RUN groupadd --gid 1001 intentos \
    && useradd --uid 1001 --gid intentos --shell /bin/bash --create-home intentos

WORKDIR /app

# ── Stage 2: Python dependency installer ──
FROM base AS py-deps

COPY requirements.txt .

# Step 1: Upgrade pip
RUN pip install --no-cache-dir --upgrade pip

# Step 2: Install CPU-only PyTorch BEFORE everything else.
# This prevents sentence-transformers and chromadb from auto-pulling
# the 1GB+ CUDA build of torch. CPU build is ~180MB instead.
RUN pip install --no-cache-dir \
    torch==2.5.1+cpu \
    torchaudio==2.5.1+cpu \
    --extra-index-url https://download.pytorch.org/whl/cpu

# Step 3: Install remaining requirements (torch already resolved, no CUDA pulled)
RUN pip install --no-cache-dir -r requirements.txt

# Install Playwright browsers
RUN playwright install chromium --with-deps

# ── Stage 3: Node dependency installer ────
FROM base AS node-deps

WORKDIR /app
COPY package.json package-lock.json* ./
RUN npm ci --omit=dev --ignore-scripts

# ── Stage 4: Frontend builder ─────────────
FROM node:20-alpine AS frontend-builder

WORKDIR /app
COPY dashboard/frontend/package.json dashboard/frontend/package-lock.json* ./
RUN npm ci --ignore-scripts

COPY dashboard/frontend/ .
RUN npm run build

# ── Stage 5: Final — full agent image ─────
FROM base AS agent

# Copy Python packages from py-deps stage
COPY --from=py-deps /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=py-deps /usr/local/bin /usr/local/bin

# Copy Node packages
COPY --from=node-deps /app/node_modules /app/node_modules

# Copy pre-built frontend static files
COPY --from=frontend-builder /app/dist /app/dashboard/frontend/dist

# Copy application source
COPY --chown=intentos:intentos . .

# Create required runtime directories
RUN mkdir -p /app/logs /app/screenshots /app/memory/workflows /app/memory/rag \
    && chown -R intentos:intentos /app

USER intentos

HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:${DASHBOARD_PORT:-8000}/api/health || exit 1

EXPOSE 8000

CMD ["python", "main.py"]

# ── Stage 6: Backend-only (API server) ────
FROM agent AS backend

CMD ["uvicorn", "dashboard.backend.main:app", \
     "--host", "0.0.0.0", \
     "--port", "8000", \
     "--workers", "1"]