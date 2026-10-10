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

> **Uwaga – `POST /api/refresh` działa bez uwierzytelniania**, a nginx wystawia go razem z resztą `/api` na porcie 8080.
> Każdy, kto ma dostęp do frontendu, może wielokrotnie uruchamiać odświeżanie (zapytania do BDL – limit anonimowy
> 1000 / 12 h – i do ok. 210 MB pobrań z dane.gov.pl przy pustym cache). Ostatni dobry stan danych jest chroniony, ale dla
> każdej instancji dostępnej spoza zaufanej sieci ustaw `REFRESH_DISABLED=1` (Compose przekazuje zmienną do backendu,
> domyślnie `0` = odświeżanie włączone):
>
> ```bash
> REFRESH_DISABLED=1 docker compose up -d --build
> ```

> Stan weryfikacji: w środowisku, w którym powstał kod, nie działał demon Dockera, więc lokalnie sprawdzono tylko
> `docker compose config`. Build obrazów, `docker compose up --wait`, `nginx -t` i test dymny (SPA oraz proxy `/api`)
> uruchamia i przechodzi workflow CI (zadanie „Docker" w `.github/workflows/ci.yml`) na runnerze GitHub Actions.

### Lokalnie (dev)

```bash
# backend
cd backend && python -m venv .venv
# zależności przypięte w pyproject.toml (projekt nie jest instalowalnym pakietem): runtime + grupa dev (pytest)
.venv/bin/pip install $(.venv/bin/python -c "import tomllib;p=tomllib.load(open('pyproject.toml','rb'))['project'];print(' '.join(p['dependencies']+p['optional-dependencies']['dev']))")
.venv/bin/python -m uvicorn app.main:app --port 8000      # baza: $BUDGET_DB_PATH (domyślnie backend/var/budget.db)
# frontend (proxy /api -> localhost:8000)
cd frontend && npm ci && npm run dev
```

Testy: `cd backend && .venv/bin/python -m pytest`, `cd frontend && npx vitest run && npx tsc --noEmit`.

Zmienne środowiskowe i źródła danych: sekcja [Prawdziwe dane](#prawdziwe-dane).

### Dane syntetyczne (fixtures) - OSTRZEŻENIE

Do uruchomienia aplikacji bez sieci (demo, testy e2e) można zasiać bazę danymi syntetycznymi:

```bash
cd backend && SEED_FIXTURES=1 .venv/bin/python -m scripts.seed_fixtures --db /sciezka/do/demo.db
BUDGET_DB_PATH=/sciezka/do/demo.db .venv/bin/python -m uvicorn app.main:app
```

**Dane z tego skryptu są SYNTETYCZNE (wymyślone, deterministyczne) i nie mogą być nigdy przedstawiane jako prawdziwe dane
GUS/MF/ZUS/Eurostat.** Skrypt odmawia działania bez `SEED_FIXTURES=1` i bez jawnego `--db`, a także gdy rozwiązana ścieżka (realpath) wskazuje
domyślną bazę aplikacji lub `$BUDGET_DB_PATH`, albo gdy plik już istnieje i nie jest oznaczony jako syntetyczny
(`meta.synthetic = "1"`); zapisuje w bazie `meta.synthetic = "1"` i wypisuje ostrzeżenie.
API (`/simulate`, `/history`, `/refresh/status`) zwraca `synthetic: true`, a interfejs pokazuje wtedy stały baner
„DANE SYNTETYCZNE – nie są to dane GUS/MF"; znacznik trafia też do eksportów (CSV/XLSX: blok/arkusz „Metadane", PNG: stopka,
PDF: notka). Udane odświeżenie z prawdziwych źródeł zapisuje `meta.synthetic = "0"` w tej samej transakcji co dane.

### Testy end-to-end (Playwright)

```bash
cd e2e && npm ci && npm test      # buduje frontend, startuje 2 backendy (zasiane / puste) i 2 serwery podglądu
```

Testy uruchamiają backend na tymczasowej bazie z danymi syntetycznymi oraz drugi, z pustą bazą (stan pusty); oba z
`REFRESH_DISABLED=1` (bez ruchu sieciowego do źródeł danych). Jeśli przeglądarka
Playwrighta nie jest pobrana, wskaż Chromium: `PW_CHROMIUM_PATH=/ścieżka/do/chrome npm test`.

## Prawdziwe dane

`POST /refresh` (przycisk „Odśwież dane”) pobiera prawdziwe dane publiczne, sprawdza je bramkami jakości i dopiero wtedy
zapisuje je w bazie (jedna transakcja, `meta.synthetic = "0"`); błąd źródła lub naruszenie bramki nie nadpisuje ostatniego
dobrego stanu. Źródła (szczegóły, identyfikatory i pułapki: `docs/data-sources-discovery.md`):

| seria | źródło | jednostka w bazie |
|---|---|---|
| `pkb_real` | GUS BDL 458431 (dynamika PKB, r/r) łańcuchowana do nominalnego PKB 458271 w ostatnim ostatecznym roku | mld zł (ceny stałe roku bazowego) |
| `gdp_nominal` (pomocnicza, kontrola jednostek) | GUS BDL 458271 | mld zł |
| `employment` | GUS BDL 154173 (przeciętne zatrudnienie, etaty) | etaty |
| `wage_nominal` | GUS BDL 64428 (przeciętne miesięczne wynagrodzenie brutto) | zł/mies. |
| `cpi` | GUS BDL 217230 (CPI r/r) łańcuchowany, 100 = rok przed pierwszym | indeks |
| `consumption_nominal` | Eurostat `nama_10_gdp` P31_S14, `CP_MNAC` (nie ma jej w BDL) | mld zł |
| `gross_surplus` | GUS BDL 458419, lata po ostatnim roku BDL z Eurostatu `nama_10_gdp` B2A3G | mld zł |
| `rev_vat`, `rev_cit`, `rev_pit` | MF, sprawozdania z wykonania budżetu państwa (dane.gov.pl, zbiór 163), plik 007, kolumna „Wykonanie” – kasowo, budżet państwa | mld zł |

Bramki jakości (`backend/app/data/dataset.py`): ≥ 15 ciągłych wspólnych lat zmiennych makro; konsumpcja / PKB nominalny
w [0,4; 0,7] (wyłapuje błąd mln/mld); ostatnie wpływy VAT/CIT/PIT w wiarygodnych przedziałach; nadwyżka operacyjna GUS i
Eurostatu zgodna co do 2% w latach wspólnych; brak NaN i wartości ujemnych; serie wpływów nie kończą się wcześniej niż
już zapisane (poza danymi syntetycznymi).

Zmienne środowiskowe backendu:

- `BDL_CLIENT_ID` – opcjonalny klucz API GUS BDL (nagłówek `X-ClientId`, wyższy limit niż anonimowe 1000 zapytań / 12 h;
  jedno odświeżenie to 6 zapytań do BDL).
- `BUDGET_CACHE_DIR` – katalog cache sprawozdań MF (tylko odczytane wartości per rok jako JSON, bez archiwów ZIP); domyślnie
  `<katalog bazy>/cache`, pusta wartość wyłącza cache. W Docker Compose: `/data/cache` w wolumenie.
- `REFRESH_DISABLED=1` (także `true`/`yes`, bez względu na wielkość liter) – wyłącza odświeżanie (`POST /refresh` → 403
  „odświeżanie wyłączone w tej instancji”, `/refresh/status` zwraca `disabled: true`); używane przez testy e2e, które nie
  łączą się z prawdziwymi źródłami, i zalecane dla każdej wystawionej instancji (endpoint nie ma uwierzytelniania).

**Pierwsze odświeżenie pobiera ok. 210 MB** (10 rocznych archiwów ZIP MF 2016–2025, w większości PDF-y dołączone przez MF;
trwało ok. 6,5 min) – kolejne korzystają z cache i robią tylko 8 zapytań do BDL/Eurostatu plus listę zasobów dane.gov.pl.
Ostrzeżenia źródeł (np. nieobsługiwany rok 2015 MF) są widoczne w `/refresh/status` i w interfejsie, ale nie przerywają odświeżenia.
Natomiast rok MF od 2016 r., którego nie udało się pobrać (błąd sieci, przekroczony czas, 5xx, limit rozmiaru) i którego
nie ma w cache, jest błędem źródła: odświeżenie kończy się stanem `failed`, a zapisane dane pozostają bez zmian.

Dowód na żywo (wymaga sieci; nie dotyka bazy aplikacji):

```bash
cd backend
# raport: prawdziwe odświeżenie do NOWEJ bazy, symulacja z parametrami domyślnymi, backtest; kod wyjścia 0 = bramki przeszły
.venv/bin/python -m scripts.live_refresh_report --db /tmp/live.db [--cache-dir /tmp/mf-cache]
# testy dymne na żywo (małe zapytania: PKB 2024 z BDL, konsumpcja 2024 z Eurostatu, VAT 2024 z MF – jeden rok)
.venv/bin/python -m pytest -m live -q
```

Skrypt odmawia pracy, gdy `--db` wskazuje istniejący plik albo bazę aplikacji (domyślną lub `$BUDGET_DB_PATH`).
Zwykłe `pytest -q` pomija testy `live` (`addopts = -m "not live"` w `pyproject.toml`); w CI uruchamia je osobne zadanie
`live-sources`, dostępne wyłącznie ręcznie (`workflow_dispatch`). Wynik pierwszego uruchomienia na żywo (2026-10-10) z
liczbami: `docs/data-sources-discovery.md`, sekcja „Uruchomienie na żywo 2026-10-10”.

## Znane ograniczenia i otwarte kwestie

- **Źródła danych są prawdziwe i zweryfikowane na żywo** (2026-10-10: GUS BDL, Eurostat, MF/dane.gov.pl; wartości zgodne z
  nagraniami i opublikowanymi sprawozdaniami). Niezweryfikowany pozostaje **model**:
  - **14 stałych modelu oznaczonych `PLACEHOLDER-UNVERIFIED`** w `backend/app/model/config.py` (lista także w zakładce
    „Jakość” i w eksportach): udziały konsumpcji wg stawek VAT, luka VAT, elastyczność cenowa konsumpcji, udział małych
    podatników CIT, rozkład dochodów PIT, podział dochodów z działalności (skala/liniowy/ryczałt) i relacja przychodu do
    dochodu ryczałtowców, relacja dochodów z działalności do masy płac, krańcowa skłonność do konsumpcji, udział konsumpcji
    w PKB, elastyczność zatrudnienia względem PKB. Wymagają weryfikacji przez ekonomistę.
  - **Rozkład dochodów PIT** jest zastępczy; dane MF („Informacja dotycząca rozliczenia PIT”, dane.gov.pl zbiór 191) są tylko
    w PDF (do 2021 r.). Na danych na żywo rozkład zastępczy daje silną progresję („bracket creep”): elastyczność części skali
    PIT względem bazy ≈ 1,85, mediana PIT 2025 128 mld zł przy 97,6 mld zł wykonania 2024 (szczegóły w raporcie z rozpoznania,
    „Wiarygodność prognozy – obserwacje”). Prognozy PIT traktować jako ilustracyjne.
  - Mediany VAR dla 2025 są wyraźnie powyżej wykonania (płace, CPI, konsumpcja) – szok 2022–2024 w krótkiej próbie;
    backtest (MAPE VAT ~10%, CIT ~28%, PIT ~14%, pokrycie pasm 80% poniżej nominalnego) pokazuje za wąskie pasma.
- **Załamanie PIT 2025**: od 2025 r. budżet państwa zatrzymuje znacznie mniejszą część PIT (reforma finansowania JST;
  97,6 → 28,75 mld zł). Kalibracja i backtest PIT używają tylko lat do 2024; prognoza PIT jest liczona według zasad sprzed
  reformy i nie jest porównywalna z wykonaniem od 2025 r. Decyzja (PIT ogółem vs udział budżetu państwa) pozostaje otwarta.
- **MF 2015 nieobsługiwany**: sprawozdanie za 2015 ma plik 007 w starym formacie `.xls` (dodatkowo podwójnie zagnieżdżony),
  bez `xlrd` – rok jest pomijany z ostrzeżeniem. Wpływy dostępne od 2016 r.; lat sprzed 2015 nie ma na dane.gov.pl.
- **Kasowo vs memoriałowo**: wpływy MF to kasowe wykonanie budżetu państwa (udział budżetu państwa, bez udziałów JST);
  dane makro (Eurostat, rachunki narodowe) są memoriałowe. Porównania z ESA (np. Eurostat `gov_10a_taxag`) dają ten sam rząd
  wielkości, ale nie identyczne liczby.
- Kalibracja VAT i CIT może obejmować rok po ostatnim roku modelu makro (konsumpcja i nadwyżka z Eurostatu są o rok dłuższe
  niż PKB realny i zatrudnienie z BDL), więc porównanie prognozy tego roku z wykonaniem nie jest testem poza próbą.
- Pojęcia serii: zatrudnienie i płaca z BDL nie obejmują małych podmiotów (płaca wyższa od średniej „w gospodarce
  narodowej”); od 2026 r. GUS publikuje CPI w klasyfikacji COICOP 2018 (seria roczna 217230 kończy się na 2025 r.).
- **ZUS / składki nie są objęte** (brak maszynowo czytelnego źródła; wariant: Eurostat `gov_10a_taxag` D61).
- Otwarte kwestie ze specyfikacji (§8): definicja „budżet państwa” vs sektor finansów publicznych, okres kalibracji, finalny
  zestaw zmiennych makro i elastyczności (do ustalenia z analitykiem ekonomicznym), docelowy hosting (projekt jest kontenerowy).
- Dane syntetyczne (`scripts.seed_fixtures`) nadal są dostępne do demo i testów e2e; są zawsze oznaczone (`synthetic: true`,
  baner, eksporty) i zastępowane przy pierwszym udanym odświeżeniu z prawdziwych źródeł.
