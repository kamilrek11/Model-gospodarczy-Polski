#!/usr/bin/env bash
# Starts the app on the committed snapshot of REAL data (GUS BDL + Eurostat + MF, demo/real-data.db).
# Works locally and in GitHub Codespaces:   bash scripts/demo-real-data.sh
# Refresh is disabled (the snapshot is read-only demo data; POST /refresh answers 403).
set -euo pipefail
root="$(cd "$(dirname "$0")/.." && pwd)"
work="${TMPDIR:-/tmp}/budget-demo"
mkdir -p "$work"
cp -n "$root/demo/real-data.db" "$work/real-data.db" 2>/dev/null || true

cd "$root/backend"
if [ ! -x .venv/bin/python ]; then
  python3 -m venv .venv
  .venv/bin/pip install -q $(.venv/bin/python -c "import tomllib;p=tomllib.load(open('pyproject.toml','rb'))['project'];print(' '.join(p['dependencies']+p['optional-dependencies']['dev']))")
fi
BUDGET_DB_PATH="$work/real-data.db" REFRESH_DISABLED=1 .venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 &
api=$!
trap 'kill $api 2>/dev/null || true' EXIT

cd "$root/frontend"
[ -d node_modules ] || npm ci --silent
echo "Aplikacja: http://localhost:5173  (w Codespaces otwórz przekierowany port 5173)"
# Codespaces serves the app under *.app.github.dev; Vite blocks unknown Host headers unless allowed.
__VITE_ADDITIONAL_SERVER_ALLOWED_HOSTS=".app.github.dev" npx vite --host 0.0.0.0 --port 5173
