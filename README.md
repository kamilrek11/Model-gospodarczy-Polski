# Symulator wpływów budżetowych (PIT / CIT / VAT)

Symulator wpływów z podatków PIT, CIT i VAT w budżecie państwa: blok makro (VAR), moduły podatkowe, symulacja Monte Carlo
z pasmami niepewności, scenariusze, eksport. Projekt: `docs/superpowers/specs/2026-10-10-symulator-budzetu-design.md`.

## Uruchomienie

### Docker Compose

```bash
docker compose up -d --build     # frontend: http://localhost:8080 (jedyny opublikowany port)
```

Backend nie jest wystawiony na zewnątrz; nginx we frontendzie proxuje `/api/*` do `backend:8000` (bez prefiksu `/api`).
Baza SQLite leży w nazwanym wolumenie `budget-data` (`/data/budget.db`). Healthcheck backendu: `GET /health`.

> Stan weryfikacji: pliki Dockerfile/compose przeszły `docker compose config`, ale w środowisku, w którym powstały,
> nie działał demon Dockera - obrazów nie zbudowano, a `docker compose up` NIE był uruchamiany.

### Lokalnie (dev)

```bash
# backend
cd backend && python -m venv .venv && .venv/bin/pip install -e . 2>/dev/null || .venv/bin/pip install fastapi uvicorn pandas numpy statsmodels httpx openpyxl pytest
.venv/bin/python -m uvicorn app.main:app --port 8000      # baza: $BUDGET_DB_PATH (domyślnie backend/var/budget.db)
# frontend (proxy /api -> localhost:8000)
cd frontend && npm ci && npm run dev
```

Testy: `cd backend && .venv/bin/python -m pytest`, `cd frontend && npx vitest run && npx tsc --noEmit`.

### Dane syntetyczne (fixtures) - OSTRZEŻENIE

Prawdziwe źródła danych nie są jeszcze podłączone (patrz niżej), więc do uruchomienia aplikacji offline i do testów e2e służy:

```bash
cd backend && SEED_FIXTURES=1 .venv/bin/python -m scripts.seed_fixtures --db /sciezka/do/demo.db
BUDGET_DB_PATH=/sciezka/do/demo.db .venv/bin/python -m uvicorn app.main:app
```

**Dane z tego skryptu są SYNTETYCZNE (wymyślone, deterministyczne) i nie mogą być nigdy przedstawiane jako prawdziwe dane
GUS/MF/ZUS/Eurostat.** Skrypt odmawia działania bez `SEED_FIXTURES=1` i bez jawnego `--db` (nigdy nie dotyka domyślnej bazy),
zapisuje w bazie `meta.synthetic = "1"` i wypisuje ostrzeżenie.

### Testy end-to-end (Playwright)

```bash
cd e2e && npm ci && npm test      # buduje frontend, startuje 2 backendy (zasiane / puste) i 2 serwery podglądu
```

Testy uruchamiają backend na tymczasowej bazie z danymi syntetycznymi oraz drugi, z pustą bazą (stan pusty). Jeśli przeglądarka
Playwrighta nie jest pobrana, wskaż Chromium: `PW_CHROMIUM_PATH=/ścieżka/do/chrome npm test`.

## Znane ograniczenia i otwarte kwestie

- **Identyfikatory serii GUS (BDL) / MF / ZUS / Eurostat w `backend/app/data/series_map.py` są `PLACEHOLDER-UNVERIFIED`**
  (środowisko deweloperskie nie miało dostępu do tych hostów). Dlatego `POST /refresh` względem prawdziwych źródeł kończy się
  błędem `series not mapped` z czytelnym komunikatem, dopóki identyfikatory nie zostaną potwierdzone. Do tego czasu aplikacja
  działa tylko na danych zasianych (syntetycznych) lub na wcześniej poprawnie pobranych.
- Otwarte kwestie ze specyfikacji (§8):
  - dostępność i warunki API: BDL (GUS), MF, ZUS, Eurostat; konieczne odblokowanie hostów, aby ustalić realne serie;
  - dokładna definicja „budżet państwa" vs sektor finansów publicznych (wpływ na składki ZUS/NFZ/FUS);
  - okres kalibracji, finalny zestaw zmiennych makro i elastyczności (do ustalenia z analitykiem ekonomicznym po weryfikacji danych);
  - docelowy hosting (projekt jest kontenerowy).
