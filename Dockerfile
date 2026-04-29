# ==========================================
# OpenClaw Multi-Stage Dockerfile
# ==========================================

# --- Base Stage: Python + Node.js ---
FROM python:3.11-slim AS base

# Install Node.js 22
RUN apt-get update && apt-get install -y curl gnupg && \
    curl -fsSL https://deb.nodesource.com/setup_22.x | bash - && \
    apt-get install -y nodejs && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install Playwright browsers
RUN playwright install chromium --with-deps

# Install Node.js dependencies
COPY package.json package-lock.json* ./
RUN npm install --production

# Copy source code
COPY . .

# --- Backend Target ---
FROM base AS backend
EXPOSE 8000
CMD ["uvicorn", "dashboard.backend.main:app", "--host", "0.0.0.0", "--port", "8000"]

# --- WhatsApp Target ---
FROM base AS whatsapp
EXPOSE 3001
CMD ["node", "skills/messaging/whatsapp_adapter.js"]

# --- Agent Target (full system) ---
FROM base AS agent
CMD ["python", "main.py"]
