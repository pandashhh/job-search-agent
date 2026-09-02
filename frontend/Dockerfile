# syntax=docker/dockerfile:1.7

# ============================================================
# Frontend-Image: React + Vite → nginx
# ============================================================
#
# Multi-Stage: dieselbe Idee wie beim Backend — Node/npm und der ganze
# node_modules-Ballast bleiben in Stage 1, das finale Image ist nur ein
# schlanker nginx, der die kompilierten Vite-Assets ausliefert.
#
# nginx darf hier bewusst Alpine sein — keine Python-Kompilierungsprobleme
# wie beim Backend, nginx-alpine ist die offizielle empfohlene Variante.

# ---------- Stage 1: build ----------
FROM node:20-slim AS build

WORKDIR /app

# package.json + lock zuerst, damit der npm-Layer-Cache nur invalidiert
# wird, wenn sich die Dependencies wirklich ändern (nicht bei jedem
# Source-File-Change).
COPY package.json package-lock.json ./
# npm ci statt install: strikt an package-lock.json, reproduzierbarer
# Build, keine "silent"-Updates von Sub-Deps.
RUN npm ci

# Restlicher Source-Code + Vite-Build. Erzeugt /app/dist mit statischen
# Assets (index.html, JS-Bundles, CSS). tsc -b + vite build laufen über
# das build-Script in package.json.
COPY . .
RUN npm run build

# ---------- Stage 2: runtime ----------
FROM nginx:alpine AS runtime

# Nur das fertige dist/ übernehmen — kein node_modules, kein tsc, kein
# Vite. Das nginx-Default-html-Verzeichnis wird ersetzt.
COPY --from=build /app/dist /usr/share/nginx/html

# Default-Port des nginx-Images. docker-compose mappt das Host-seitig
# auf 5173 (siehe docker-compose.yml).
EXPOSE 80
