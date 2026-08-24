# Multi-stage build: Node builds the static bundle, nginx serves it.
# Matches docker-compose.yml's expectation: `build: { context: ./web, args:
# { VITE_API_BASE_URL } }`, exposing 5173 (architecture.md §3).
#
# Base images are pinned to exact tags (ADR-007) — no `:latest`, no bare
# `node`/`nginx`.

FROM node:22.20.0-slim AS build
WORKDIR /app

# Install dependencies first so this layer is cache-friendly across builds
# that only touch application code.
COPY package.json package-lock.json ./
RUN npm ci

COPY . .

# Baked into the static bundle at build time (Vite env vars are compile-time,
# not runtime) — set via docker-compose.yml's build.args.
ARG VITE_API_BASE_URL=http://localhost:8000
ENV VITE_API_BASE_URL=${VITE_API_BASE_URL}

RUN npm run build

FROM nginx:1.27.4-alpine AS runtime
COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 5173

HEALTHCHECK --interval=5s --timeout=3s --retries=20 \
  CMD wget -qO- http://localhost:5173/ >/dev/null 2>&1 || exit 1
