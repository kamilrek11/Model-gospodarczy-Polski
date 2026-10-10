#!/usr/bin/env bash
# Usage: start_frontend.sh <port> <api-port>  -- serves the built SPA (run `npm run build:app` first).
set -euo pipefail
root="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$root/frontend"
API_TARGET="http://127.0.0.1:$2" exec npx vite preview --host 127.0.0.1 --port "$1" --strictPort
