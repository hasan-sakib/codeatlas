# syntax=docker/dockerfile:1
#
# Three stages: deps (npm ci only — reused as-is by the dev Compose
# overlay, which bind-mounts source over this stage and runs `next dev`),
# builder (full production build), runtime (the pruned standalone
# server only — no node_modules, no source, no build tooling).

FROM node:22-slim AS deps
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci

FROM node:22-slim AS builder
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY . .
RUN npm run build

FROM node:22-slim AS runtime

RUN groupadd --system app && useradd --system --gid app --create-home app

WORKDIR /app
ENV NODE_ENV=production \
    PORT=3000 \
    HOSTNAME=0.0.0.0

COPY --from=builder /app/public ./public
COPY --from=builder --chown=app:app /app/.next/standalone ./
COPY --from=builder --chown=app:app /app/.next/static ./.next/static

USER app

EXPOSE 3000

CMD ["node", "server.js"]
