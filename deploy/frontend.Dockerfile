# ============================================================
# ZenFlux Agent - Frontend Dockerfile
# ============================================================
# Vue 3 SPA build → Nginx static serving
#
# Multi-stage: Node.js build → Nginx production

# Stage 1: Build Vue app
FROM node:20-alpine AS builder

WORKDIR /build

# Install dependencies first (layer caching)
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm ci --ignore-scripts 2>/dev/null || npm install

# Copy frontend source
COPY frontend/ .

# Build for web (not Tauri desktop)
# Skip vue-tsc type check for faster/more reliable Docker builds
RUN npx vite build

# Stage 2: Serve with Nginx
FROM nginx:alpine

# Remove default nginx config
RUN rm /etc/nginx/conf.d/default.conf

# Copy custom nginx config
COPY deploy/nginx/default.conf /etc/nginx/conf.d/default.conf

# Copy built frontend
COPY --from=builder /build/dist /usr/share/nginx/html

EXPOSE 80

HEALTHCHECK --interval=30s --timeout=3s --retries=3 \
    CMD wget -qO- http://localhost/ || exit 1

CMD ["nginx", "-g", "daemon off;"]
