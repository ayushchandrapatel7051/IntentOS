# ==========================================
# IntentOS — Frontend Nginx Dockerfile
# ==========================================

# ── Stage 1: Build ────────────────────────
FROM node:20-alpine AS builder

WORKDIR /app

COPY package.json package-lock.json* ./
RUN npm ci --ignore-scripts

COPY . .
RUN npm run build

# ── Stage 2: Serve with nginx ─────────────
FROM nginx:1.27-alpine AS production

RUN rm /etc/nginx/conf.d/default.conf

COPY nginx.conf /etc/nginx/conf.d/default.conf

COPY --from=builder /app/dist /usr/share/nginx/html

EXPOSE 3000

HEALTHCHECK --interval=20s --timeout=5s --retries=3 \
  CMD wget -qO- http://localhost:3000/ | grep -q "html" || exit 1

CMD ["nginx", "-g", "daemon off;"]