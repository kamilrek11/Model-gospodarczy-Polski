# Symulator wpływów do budżetu państwa – plan wdrożenia v1

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Działająca wersja v1 aplikacji: PIT, CIT, VAT + blok makro, symulacja na żywo, wykresy, scenariusze, eksport.

**Architecture:** Backend FastAPI z estymacją modelu offline (po `POST /refresh`) i symulacją Monte Carlo w `POST /simulate`; dane i współczynniki w SQLite. Frontend React/TS generuje formularz ze schematu `GET /parameters`. Całość w kontenerach Docker.

**Tech Stack:** Python 3.11+, FastAPI, pandas, numpy, statsmodels, httpx, pytest; React + TypeScript + Vite, Recharts, Vitest, Playwright; Docker Compose.

**Spec:** `docs/superpowers/specs/2026-10-10-symulator-budzetu-design.md`

## Global Constraints

- Horyzont prognozy: roczny, 1–5 lat. Pasma niepewności: 80% i 95% z Monte Carlo.
- Odświeżanie danych wyłącznie na żądanie (`POST /refresh`); częściowy sukces nie nadpisuje ostatniego dobrego stanu.
- Brak danych dla modułu → moduł wyłączony z komunikatem; nigdy zmyślone wartości.
- Interfejs po polsku, motyw jasny i ciemny; paleta odporna na daltonizm; tabela danych jako alternatywa wykresów.
- Debounce symulacji 300 ms, anulowanie starszych żądań (AbortController).
- Scenariusze w localStorage + eksport/import JSON; brak kont. Eksport CSV/XLSX (backend), PNG/PDF (przeglądarka).
- Wartości domyślne parametrów = obecne prawo; kwoty w mld zł, stawki jako ułamki (0.23).
- Identyfikatory serii BDL/MF/Eurostat ustala się z realnego API (host `bdl.stat.gov.pl` był zablokowany w środowisku); do tego czasu testy używają zapisanych fixtures.

## Review Focus

- Pusta baza (przed pierwszym `/refresh`): `/simulate` zwraca 409 z komunikatem „brak danych", UI pokazuje stan pusty z przyciskiem odświeżenia.
- Ekstremalne parametry (stawka 0 lub 1, próg PIT = 0, kwota wolna > progu): wynik skończony, nieujemny wpływ, bez NaN.
- Awaria jednego źródła przy `/refresh`: poprzedni zestaw zostaje, status zawiera nazwę źródła i błąd.
- Krótka historia serii (< 15 obserwacji): estymacja zwraca jawny błąd z liczbą obserwacji, nie model.
- Scenariusz z importu JSON o starszym schemacie lub nieznanych kluczach: odrzucony z komunikatem, bez wyjątku w UI.

---

## File Structure

```
backend/pyproject.toml
backend/app/main.py                 FastAPI, routery
backend/app/store.py                SQLite: serie, współczynniki, metadane
backend/app/data/base.py            interfejs SourceClient
backend/app/data/gus_bdl.py         klient BDL
backend/app/data/execution.py       wykonanie budżetu (MF/ZUS/Eurostat)
backend/app/model/params.py         schemat parametrów + domyślne
backend/app/model/taxes/{vat,cit,pit}.py
backend/app/model/macro.py          estymacja VAR/ECM
backend/app/model/simulate.py       Monte Carlo
backend/app/model/backtest.py
backend/app/api/{parameters,simulate,history,refresh,backtest,export}.py
backend/tests/…  backend/tests/fixtures/…
frontend/src/{api,state,components,charts,scenarios}/…
docker-compose.yml, backend/Dockerfile, frontend/Dockerfile
```

---

### Task 1: Szkielet backendu i magazyn danych

**Files:** Create `backend/pyproject.toml`, `backend/app/main.py`, `backend/app/store.py`; Test `backend/tests/test_store.py`

**Interfaces:**
- Produces: `class Store(path: str)` z metodami `save_series(name: str, source: str, df: pd.DataFrame) -> None`, `load_series(name: str) -> pd.DataFrame` (indeks = rok `int`, kolumna `value`), `save_model(payload: dict) -> None`, `load_model() -> dict | None`, `set_meta(key: str, value: str) -> None`, `get_meta(key: str) -> str | None`. `GET /health` → `{"status": "ok"}`.

- [ ] **Step 1:** Test `test_save_and_load_series_roundtrip`: zapis serii `pkb` i odczyt zwraca identyczny DataFrame; `test_load_model_empty_returns_none`.
- [ ] **Step 2:** Uruchom `cd backend && pytest tests/test_store.py -v` → FAIL (brak modułu).
- [ ] **Step 3:** Zaimplementuj `Store` (sqlite3, tabele `series`, `model`, `meta`) i `GET /health`.
- [ ] **Step 4:** `pytest tests/test_store.py -v` → PASS.
- [ ] **Step 5:** `git add backend && git commit -m "feat: backend skeleton and sqlite store"`

### Task 2: Schemat parametrów (v1)

**Files:** Create `backend/app/model/params.py`, `backend/app/api/parameters.py`; Test `backend/tests/test_params.py`

**Interfaces:**
- Produces: `PARAMETER_SCHEMA: list[ParamSpec]` (`ParamSpec`: `key, label, tax, unit, default, min, max, step, description`); `defaults() -> dict[str, float]`; `validate(values: dict) -> dict[str, float]` (brakujące klucze → domyślne, nieznany klucz lub wartość poza zakresem → `ValueError`). `GET /parameters` zwraca schemat.
- Klucze v1: PIT `pit_rate_low` 0.12, `pit_rate_high` 0.32, `pit_threshold` 120000, `pit_tax_free` 30000, `pit_flat_rate` 0.19, `pit_lump_rate_default` 0.12; VAT `vat_rate_standard` 0.23, `vat_rate_reduced1` 0.08, `vat_rate_reduced2` 0.05; CIT `cit_rate` 0.19, `cit_rate_small` 0.09.

- [ ] **Step 1:** Testy: `test_defaults_match_current_law` (wartości powyżej), `test_validate_rejects_unknown_key`, `test_validate_rejects_out_of_range`, `test_get_parameters_endpoint_lists_all_keys`.
- [ ] **Step 2:** `pytest tests/test_params.py -v` → FAIL.
- [ ] **Step 3:** Implementuj `params.py` i router `/parameters`.
- [ ] **Step 4:** `pytest tests/test_params.py -v` → PASS.
- [ ] **Step 5:** Commit `feat: parameter schema`.

### Task 3: Moduły podatkowe VAT, CIT, PIT

**Files:** Create `backend/app/model/taxes/{vat,cit,pit}.py`; Test `backend/tests/test_taxes.py`

**Interfaces:**
- Consumes: `defaults()` z Task 2.
- Produces: czyste funkcje `vat_revenue(consumption: np.ndarray, shares: dict[str, float], p: dict, gap: float, elasticity: float, base_p: dict) -> np.ndarray`, `cit_revenue(gross_surplus: np.ndarray, small_share: float, p: dict, calib: float) -> np.ndarray`, `pit_revenue(wage_bill: np.ndarray, business_income: np.ndarray, income_dist: IncomeDist, p: dict, calib: float) -> np.ndarray` (wszystko w mld zł, wektor po latach/ścieżkach). `consumption_feedback(vat_before, vat_after, elasticity) -> float` – względna zmiana konsumpcji dla bloku makro.

- [ ] **Step 1:** Testy z liczbami: `test_vat_standard_rate_up_increases_revenue` (przy elastyczności 0 wpływ rośnie proporcjonalnie), `test_vat_elasticity_dampens_increase` (z elastycznością −0.5 wzrost mniejszy niż liniowy, nadal dodatni), `test_cit_zero_rate_zero_revenue`, `test_pit_threshold_zero_all_taxed_high` (próg 0 → cała baza po stawce wyższej, minus kwota zmniejszająca), `test_pit_tax_free_above_threshold_nonnegative`, `test_modules_finite_for_extreme_params` (stawki 0 i 1).
- [ ] **Step 2:** `pytest tests/test_taxes.py -v` → FAIL.
- [ ] **Step 3:** Implementuj trzy moduły. `IncomeDist`: dataclass z kwantylami dochodu i liczbą podatników, wczytywana z danych MF; PIT liczy podatek per przedział rozkładu.
- [ ] **Step 4:** `pytest tests/test_taxes.py -v` → PASS.
- [ ] **Step 5:** Commit `feat: VAT, CIT, PIT revenue modules`.

### Task 4: Klienci źródeł danych

**Files:** Create `backend/app/data/{base,gus_bdl,execution}.py`; Test `backend/tests/test_data_clients.py`; Fixtures `backend/tests/fixtures/*.json`

**Interfaces:**
- Produces: `class SourceClient(Protocol)`: `name: str`, `fetch() -> dict[str, pd.DataFrame]` (nazwa serii → DataFrame rok/value), rzuca `SourceError(source: str, message: str)`. Implementacje `GusBdlClient(base_url, http: httpx.Client)` (serie: `pkb_real`, `employment`, `wage_nominal`, `cpi`, `consumption_nominal`, `gross_surplus`) i `ExecutionClient` (serie: `rev_pit`, `rev_cit`, `rev_vat` w mld zł). Mapowanie nazw serii → identyfikatory BDL/MF w `backend/app/data/series_map.py` ustalone z realnym API.

- [ ] **Step 1:** Testy na fixtures (httpx MockTransport): `test_gus_client_parses_series`, `test_gus_client_raises_source_error_on_http_500`, `test_gus_client_paginates`.
- [ ] **Step 2:** `pytest tests/test_data_clients.py -v` → FAIL.
- [ ] **Step 3:** Implementuj klientów; zweryfikuj identyfikatory na żywym API (wymaga odblokowania hostów) i zapisz fixtures z realnych odpowiedzi.
- [ ] **Step 4:** `pytest tests/test_data_clients.py -v` → PASS.
- [ ] **Step 5:** Commit `feat: GUS BDL and budget execution clients`.

### Task 5: Odświeżanie danych i estymacja bloku makro

**Files:** Create `backend/app/model/macro.py`, `backend/app/api/refresh.py`; Test `backend/tests/test_macro.py`, `backend/tests/test_refresh.py`

**Interfaces:**
- Consumes: `Store`, `SourceClient`.
- Produces: `fit_macro(data: pd.DataFrame, lags: int = 1) -> MacroModel` (`coefs`, `resid`, `last_obs`, `n_obs`); `MacroModel.to_dict()/from_dict()`; rzuca `InsufficientData(n_obs: int, required: int = 15)`. `refresh(store, clients) -> RefreshResult` (`ok: bool`, `errors: dict[str, str]`, `updated_at`). `POST /refresh` startuje zadanie w tle, `GET /refresh/status` → `{state, errors, updated_at}`.

- [ ] **Step 1:** Testy: `test_fit_macro_recovers_known_var_coefficients` (dane syntetyczne VAR(1)), `test_fit_macro_raises_on_short_history` (n=10), `test_refresh_keeps_previous_state_when_a_source_fails`, `test_refresh_status_reports_failed_source_name`.
- [ ] **Step 2:** `pytest tests/test_macro.py tests/test_refresh.py -v` → FAIL.
- [ ] **Step 3:** Implementuj `fit_macro` (statsmodels VAR na logarytmicznych przyrostach) i orkiestrację odświeżenia: zapis do `Store` dopiero po sukcesie estymacji.
- [ ] **Step 4:** Uruchom testy → PASS.
- [ ] **Step 5:** Commit `feat: macro estimation and refresh`.

### Task 6: Symulacja Monte Carlo i `/simulate`

**Files:** Create `backend/app/model/simulate.py`, `backend/app/api/simulate.py`; Test `backend/tests/test_simulate.py`

**Interfaces:**
- Consumes: `MacroModel`, moduły podatkowe, `validate`.
- Produces: `simulate(model: MacroModel, history: dict[str, pd.DataFrame], params: dict, horizon: int = 5, n_paths: int = 2000, seed: int | None = None) -> SimResult` z polami per podatek: `median, p10, p90, p2_5, p97_5` (długość `horizon`), plus `baseline` (obecne prawo), `total`, `macro`. `POST /simulate` → JSON `{taxes: {...}, total: {...}, macro: {...}, model_version, data_updated_at}`; 409 gdy brak modelu.

- [ ] **Step 1:** Testy: `test_default_params_equal_baseline`, `test_higher_vat_raises_vat_median_and_dampens_consumption`, `test_bands_are_ordered` (p2_5 ≤ p10 ≤ median ≤ p90 ≤ p97_5), `test_seed_reproducible`, `test_simulate_endpoint_409_without_model`, `test_simulate_runs_under_200ms` (n_paths=2000, horyzont 5).
- [ ] **Step 2:** Uruchom → FAIL.
- [ ] **Step 3:** Implementuj wektorową symulację (bootstrap reszt VAR, jedno przejście per rok, sprzężenie zwrotne `consumption_feedback`).
- [ ] **Step 4:** Uruchom → PASS.
- [ ] **Step 5:** Commit `feat: monte carlo simulation endpoint`.

### Task 7: Historia, backtest, eksport

**Files:** Create `backend/app/model/backtest.py`, `backend/app/api/{history,backtest,export}.py`; Test `backend/tests/test_backtest_export.py`

**Interfaces:**
- Produces: `backtest(data, horizon: int = 3, min_train: int = 12) -> BacktestResult` (`mape: dict[tax, float]`, `coverage80/95: dict[tax, float]`); `GET /history` → `{tax: [{year, value}]}`; `GET /backtest`; `POST /export?format=csv|xlsx` z ciałem `{params, result}` → plik.

- [ ] **Step 1:** Testy: `test_backtest_perfect_series_zero_mape`, `test_backtest_coverage_between_0_and_1`, `test_export_csv_contains_params_and_years`, `test_export_xlsx_has_two_sheets` (wyniki, parametry).
- [ ] **Step 2:** Uruchom → FAIL.
- [ ] **Step 3:** Implementuj (rolling-origin; eksport przez openpyxl).
- [ ] **Step 4:** Uruchom → PASS.
- [ ] **Step 5:** Commit `feat: history, backtest and export`.

### Task 8: Szkielet frontendu, panel parametrów, klient API

**Files:** Create `frontend/` (Vite React TS), `src/api/client.ts`, `src/components/ParameterPanel.tsx`, `src/state/useSimulation.ts`; Test `src/components/ParameterPanel.test.tsx`, `src/state/useSimulation.test.ts`

**Interfaces:**
- Consumes: `GET /parameters`, `POST /simulate`.
- Produces: `useSimulation(params): {result, loading, error}` (debounce 300 ms, AbortController anuluje poprzednie żądanie); `<ParameterPanel schema values onChange onReset/>` z sekcjami zwijanymi per podatek, polem + suwakiem, znacznikiem odchylenia od bazy i „Przywróć".

- [ ] **Step 1:** Testy (Vitest + Testing Library): `renders one section per tax from schema`, `marks parameter deviating from default`, `reset restores default`, `useSimulation debounces 300ms and aborts previous request` (fake timers).
- [ ] **Step 2:** `cd frontend && npx vitest run` → FAIL.
- [ ] **Step 3:** Implementuj; pola poza zakresem odrzucane z komunikatem po polsku.
- [ ] **Step 4:** Uruchom → PASS.
- [ ] **Step 5:** Commit `feat: frontend shell and parameter panel`.

### Task 9: Wykresy i stany

**Files:** Create `src/charts/{ForecastVsActual,BudgetStack}.tsx`, `src/components/{StatusBanner,EmptyState,DataTable}.tsx`; Test `src/charts/charts.test.tsx`

**Interfaces:**
- Consumes: wynik `/simulate`, `/history`.
- Produces: `<ForecastVsActual tax history sim/>` (linia ciągła = wykonanie, przerywana = prognoza, pasma 80/95%, metryka zmiany vs baza w mld zł i %); `<BudgetStack sim history/>` (słupki skumulowane po latach, klikalna legenda); `<DataTable/>` jako alternatywa tekstowa; paleta odporna na daltonizm w `src/charts/palette.ts`.

- [ ] **Step 1:** Testy: `ForecastVsActual shows change vs baseline in mld zł and %`, `BudgetStack legend toggles series`, `EmptyState shown on 409 with refresh button`, `StatusBanner shows last good data date on source error`.
- [ ] **Step 2:** Uruchom → FAIL.
- [ ] **Step 3:** Implementuj (Recharts).
- [ ] **Step 4:** Uruchom → PASS.
- [ ] **Step 5:** Commit `feat: charts and states`.

### Task 10: Scenariusze, eksport, motyw, zakładka jakości

**Files:** Create `src/scenarios/{store,compare}.ts`, `src/components/{ScenarioBar,CompareView,QualityTab,ThemeToggle}.tsx`; Test `src/scenarios/scenarios.test.ts`

**Interfaces:**
- Produces: `saveScenario(name, params)`, `listScenarios()`, `exportScenarios(): string`, `importScenarios(json: string): {ok: true} | {ok: false, error: string}` (schema version `1`, nieznane klucze/wersja → `ok: false`); `compare(a, b): DiffRow[]`. Eksport PNG/PDF wykresów z przeglądarki; CSV/XLSX przez `POST /export`.

- [ ] **Step 1:** Testy: `save and list roundtrip`, `import rejects older schema version`, `import rejects unknown parameter keys`, `compare returns per-tax differences`, `localStorage failure does not throw`.
- [ ] **Step 2:** Uruchom → FAIL.
- [ ] **Step 3:** Implementuj, w tym przełącznik motywu i zakładkę „Jakość modelu" (backtest + lista założeń).
- [ ] **Step 4:** Uruchom → PASS.
- [ ] **Step 5:** Commit `feat: scenarios, export, theme, quality tab`.

### Task 11: Kontenery i test end-to-end

**Files:** Create `backend/Dockerfile`, `frontend/Dockerfile`, `docker-compose.yml`, `e2e/budget.spec.ts`, `README.md`

- [ ] **Step 1:** Test Playwright `e2e/budget.spec.ts`: po starcie z załadowanymi fixtures zmiana `vat_rate_standard` na 0.25 aktualizuje wykres i wskaźnik zmiany; zapis scenariusza i widok porównania; stan pusty przed odświeżeniem.
- [ ] **Step 2:** `docker compose up -d && npx playwright test` → FAIL (brak kontenerów).
- [ ] **Step 3:** Dodaj Dockerfile'e, compose (backend, frontend, wolumen SQLite) i README z uruchomieniem.
- [ ] **Step 4:** `docker compose up -d && npx playwright test` → PASS.
- [ ] **Step 5:** Commit `feat: containers and e2e`.

---

## Self-Review

- Pokrycie spec: dane (T4–5), model i moduły (T3, T5–6), niepewność (T6), API (T2, T5–7), UI i stany (T8–10), scenariusze/eksport/motyw (T7, T10), kontenery (T11). Etap v2 celowo poza planem.
- Spójność typów: `Store`, `MacroModel`, `SimResult`, `validate`, `defaults` użyte spójnie między zadaniami.
- Zależność zewnętrzna: T4 wymaga odblokowania hostów (BDL/MF/ZUS/Eurostat), aby ustalić identyfikatory serii; reszta pracuje na fixtures.
