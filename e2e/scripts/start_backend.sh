#!/usr/bin/env bash
# Usage: start_backend.sh <port> <seeded|empty>
# Starts the API on a fresh temporary SQLite db. "seeded" fills it with SYNTHETIC data (never real).
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
"$py" -m uvicorn app.main:app --host 127.0.0.1 --port "$port"
