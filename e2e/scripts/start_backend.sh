#!/usr/bin/env bash
# Usage: start_backend.sh <port> <seeded|empty>
# Starts the API on a fresh temporary SQLite db. "seeded" fills it with SYNTHETIC data (never real).
# Refresh is disabled (REFRESH_DISABLED=1): the e2e suite makes no real network requests.
set -euo pipefail
port="$1"; mode="$2"
root="$(cd "$(dirname "$0")/../.." && pwd)"
py="$root/backend/.venv/bin/python"; [ -x "$py" ] || py=python3
dir="$(mktemp -d)"
trap 'rm -rf "$dir"' EXIT
db="$dir/budget.db"
cd "$root/backend"
if [ "$mode" = "seeded" ]; then
  SEED_FIXTURES=1 "$py" -m scripts.seed_fixtures --db "$db"
fi
export BUDGET_DB_PATH="$db"
# e2e never touches the real sources: POST /refresh answers 403 on both instances
export REFRESH_DISABLED=1
"$py" -m uvicorn app.main:app --host 127.0.0.1 --port "$port"
