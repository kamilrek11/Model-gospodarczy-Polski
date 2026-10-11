#!/usr/bin/env bash
# Startuje aplikację na zatwierdzonej migawce PRAWDZIWYCH danych (GUS BDL + Eurostat + MF, demo/real-data.db).
# Działa lokalnie i w GitHub Codespaces:   bash scripts/demo-real-data.sh
# Odświeżanie jest wyłączone (migawka jest tylko do podglądu; POST /refresh zwraca 403).
# Zmienne: API_PORT (domyślnie 8000), WEB_PORT (domyślnie 5173).
set -euo pipefail
root="$(cd "$(dirname "$0")/.." && pwd)"
API_PORT="${API_PORT:-8000}"
WEB_PORT="${WEB_PORT:-5173}"

fail() { echo "BŁĄD: $*" >&2; exit 1; }

port_busy() { (exec 3<>"/dev/tcp/127.0.0.1/$1") 2>/dev/null; }
port_busy "$API_PORT" && fail "port $API_PORT jest zajęty (działa tam inny backend z inną bazą, przez co aplikacja pokazałaby \"Brak danych źródłowych\"). Zatrzymaj go albo uruchom z innym portem: API_PORT=8010 bash scripts/demo-real-data.sh"
port_busy "$WEB_PORT" && fail "port $WEB_PORT jest zajęty. Zatrzymaj proces albo ustaw inny: WEB_PORT=5174 bash scripts/demo-real-data.sh"

# zawsze świeża kopia migawki w nowym katalogu (stary plik nigdy nie jest użyty ponownie)
work="$(mktemp -d)"
cp "$root/demo/real-data.db" "$work/real-data.db"

cd "$root/backend"
if [ ! -x .venv/bin/python ]; then
  python3 -m venv .venv
  .venv/bin/pip install -q $(.venv/bin/python -c "import tomllib;p=tomllib.load(open('pyproject.toml','rb'))['project'];print(' '.join(p['dependencies']+p['optional-dependencies']['dev']))")
fi
BUDGET_DB_PATH="$work/real-data.db" REFRESH_DISABLED=1 .venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port "$API_PORT" >"$work/backend.log" 2>&1 &
api=$!
trap 'kill $api 2>/dev/null || true; rm -rf "$work"' EXIT

for _ in $(seq 1 60); do
  curl -fs "http://127.0.0.1:$API_PORT/health" >/dev/null 2>&1 && break
  kill -0 "$api" 2>/dev/null || { cat "$work/backend.log" >&2; fail "backend nie wystartował"; }
  sleep 0.5
done
curl -fs "http://127.0.0.1:$API_PORT/health" >/dev/null || fail "backend nie odpowiada na /health"

hist="$(curl -s "http://127.0.0.1:$API_PORT/history" || true)"
python3 - "$hist" <<'PY' || fail "backend nie zwrócił prawdziwych danych (sprawdź $work/backend.log)"
import json, sys
d = json.loads(sys.argv[1])
assert d.get("synthetic") is False, "dane oznaczone jako syntetyczne"
assert d, "pusta historia"
PY

cd "$root/frontend"
[ -d node_modules ] || npm ci --silent
echo "Backend OK (/history zwraca prawdziwe dane). Aplikacja: http://localhost:$WEB_PORT  (w Codespaces otwórz przekierowany port $WEB_PORT)"
# Codespaces serwuje aplikację pod *.app.github.dev; Vite blokuje nieznane nagłówki Host, dopóki nie są dozwolone.
API_TARGET="http://127.0.0.1:$API_PORT" __VITE_ADDITIONAL_SERVER_ALLOWED_HOSTS=".app.github.dev" npx vite --host 0.0.0.0 --port "$WEB_PORT" --strictPort
