# Node 22 per package.json's engines (">=22.19.0") and architecture.md §8.
# Pinned to the same exact tag web/Dockerfile uses (ADR-007) — no `:latest`,
# no bare `node`.

FROM node:22.20.0-slim AS build
WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci

COPY tsconfig.json tsconfig.build.json ./
COPY src ./src
RUN npm run build

FROM node:22.20.0-slim AS runtime
WORKDIR /app
ENV NODE_ENV=production

COPY package.json package-lock.json ./
RUN npm ci --omit=dev

COPY --from=build /app/dist ./dist
COPY models.ollama.json .
COPY .pi ./.pi

# Non-root user (architecture.md §8.5's containment posture). The node:*
# base image already ships a uid-1000 "node" user — reuse it rather than
# useradd a second one. session.ts writes .pi/agent/models.json and
# .pi/agent/auth.json per turn, and SessionManager writes .pi/sessions/
# (the latter is also a Compose volume mount) — both need to be writable
# by this user, not just readable.
RUN mkdir -p .pi/agent .pi/sessions \
    && chown -R node:node /app
USER node

EXPOSE 8100

HEALTHCHECK --interval=5s --timeout=5s --retries=20 \
    CMD node -e "fetch('http://localhost:8100/healthz').then(r=>process.exit(r.ok?0:1)).catch(()=>process.exit(1))" || exit 1

CMD ["node", "dist/server.js"]
