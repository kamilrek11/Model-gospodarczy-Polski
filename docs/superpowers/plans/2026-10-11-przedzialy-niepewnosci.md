# Szersze przedziały niepewności – plan implementacji

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Pasma prognoz uwzględniają niepewność kalibracji i parametrów VAR oraz korektę szerokości z backtestu, bez zmiany median.

**Architecture:** Trzy nakładki na próbkowane ścieżki podatków w `simulate()`: (A1) losowy czynnik poziomu z rozrzutu kalibracji, (A2) zaburzenie współczynników VAR w `simulate_levels`, (B) skalowanie odchyleń ścieżek od mediany w logarytmach mnożnikiem `k` z backtestu (zapisanym przy odświeżaniu). `k` liczy czysta funkcja `fit_band_scale` z par (mediana, p10, p90, realizacja).

**Tech Stack:** Python 3.13 / numpy / statsmodels / FastAPI / SQLite; React + TS + Vitest; Playwright.

**Spec:** `docs/superpowers/specs/2026-10-11-przedzialy-niepewnosci-design.md`

## Global Constraints

- Mediany raportowanych podatków nie zmieniają się (test: ≤ 2% dla lat 1–5 na nagranych danych); skalowanie B zachowuje medianę dokładnie (ścieżki skalowane wokół mediany danego roku w logarytmach: `m·(x/m)^k`).
- A1: `exp(σ_cal·z)`, `z~N(0,1)` na ścieżkę, stały w horyzoncie, generator `np.random.default_rng([seed, 11])` (`default_rng()` dla `seed=None`); `σ_cal` = odch. std. `log(rev/moduł)` po latach okna kalibracji, ograniczone do `[CALIBRATION_SIGMA_FLOOR, CALIBRATION_SIGMA_CAP]` = `[0.03, 0.35]`.
- A2: zaburzenie współczynników `N(0, coef_cov)`, generator `default_rng([seed, 13])`; ścieżki z promieniem spektralnym macierzy towarzyszącej ≥ 1 wracają do współczynników bazowych; model bez `coef_cov` działa jak dotąd.
- B: `k ∈ [1, BAND_SCALE_MAX]`, `BAND_SCALE_MAX = 3.0`; `BAND_SCALE_MIN_PAIRS = 8`, poniżej `k = 1` i nota „za mało danych do korekty”; jeden `k` na podatek; zapis w `meta.band_scale` (JSON `{"vat": k, ...}`) w tej samej transakcji co dane; brak klucza = `k = 1`.
- Wspólne liczby losowe: ten sam czynnik A1/A2 w bazie i scenariuszu; scenariusz o identycznych parametrach daje zerową różnicę median.
- Backtest liczy symulacje bez B (surowe pasma) i raportuje pokrycie „bez korekty” oraz „po korekcie (dopasowane do historii – wartość orientacyjna)”.
- Błąd backtestu przy odświeżaniu nie przerywa odświeżenia: `k = 1` i ostrzeżenie.
- Nowe stałe w rejestrze (status `założenie`, marker `PLACEHOLDER-UNVERIFIED`, wiersz w `docs/model-parameters.md`, `param_meta`): `CALIBRATION_SIGMA_FLOOR`, `CALIBRATION_SIGMA_CAP`, `BAND_SCALE_MAX`, `BAND_SCALE_MIN_PAIRS` (łącznie 18 stałych); teksty po polsku; testy offline; test wydajności symulacji mieści się w dotychczasowym budżecie.
- Gałąź `claude/wider-bands`. Bez PR-a bez prośby użytkownika.

## Review Focus

1. Stary zapisany model bez `coef_cov` i stara baza bez `meta.band_scale`: `/simulate`, `/backtest`, `/export` działają, `k = 1`, A2 wyłączone (T3, T4).
2. Mediany po zmianie ≈ przed; pasma szersze (T2–T4).
3. Za mało par backtestu (< 8): `k = 1` z notą, nie błąd (T1, T4).
4. `seed=None`/`0`: oba generatory działają i są deterministyczne dla ustalonego ziarna (T2, T3).
5. Ścieżki z niestabilnymi współczynnikami (≥ 1) nie dają eksplodujących wartości ani NaN (T3).
6. Błąd backtestu/NaN w pasmach podczas odświeżania nie psuje zapisu danych (T4).
7. `σ_cal` przy 1 obserwacji w oknie kalibracji (np. krótka historia) → dolny limit, nie NaN (T2).

---

### Task 1: Stałe, rejestr i czyste funkcje pasm

**Files:**
- Create: `backend/app/model/bands.py`, `backend/tests/test_bands.py`
- Modify: `backend/app/model/config.py`, `backend/app/model/param_meta.py`, `docs/model-parameters.md`, `README.md` (liczniki stałych), testy spójności rejestru
- Test: `backend/tests/test_bands.py`, `backend/tests/test_param_meta.py`, `backend/tests/test_param_registry_doc.py`

**Interfaces:**
- Produces: `config.CALIBRATION_SIGMA_FLOOR: float = 0.03`, `CALIBRATION_SIGMA_CAP: float = 0.35`, `BAND_SCALE_MAX: float = 3.0`, `BAND_SCALE_MIN_PAIRS: int = 8` (w `param_meta` z zakresami: floor 0.01–0.05, cap 0.2–0.5, max 2–4, min pairs 5–12; notki z uzasadnieniem „brak źródła; ostrożność przy małej próbie”); `bands.fit_band_scale(pairs: Sequence[tuple[float, float, float, float]], target: float = 0.8) -> float` gdzie para = `(median, p10, p90, actual)`; `bands.apply_band_scale(paths: np.ndarray, k: float) -> np.ndarray` (`paths` shape `(n_paths, horizon)`, wynik skalowany wokół mediany kolumny w logarytmach, `k = 1` zwraca kopię bez zmian); `bands.sigma_from_ratios(ratios: Sequence[float]) -> float` (odch. std. `log(ratio)` z limitami; < 2 wartości → `CALIBRATION_SIGMA_FLOOR`).

Algorytm `fit_band_scale`: dla pary z `actual > median` `h = log(p90/median)`, w przeciwnym razie `h = log(median/p10)`, `r = |log(actual/median)|`; para z `h ≤ 1e-9` lub `r == 0`, `median ≤ 0`, `p10 ≤ 0` itp. jest pomijana przy wymaganiu (r = 0 liczy się jako trafiona z `k_i = 0`); `k_i = r/h`; wynik = `target`-kwantyl `k_i` obcięty do `[1, BAND_SCALE_MAX]`; mniej niż `BAND_SCALE_MIN_PAIRS` użytecznych par → `1.0`.

- [ ] **Step 1: Testy** `test_bands.py`: `test_fit_band_scale_known_value` (10 par o k_i = 0.5,…,odp. kwantyl 0.8 dokładnie obliczony ręcznie), `test_fit_band_scale_floor_one` (pary trafione z zapasem → 1.0), `test_fit_band_scale_clamped_to_max`, `test_fit_band_scale_too_few_pairs_returns_one`, `test_fit_band_scale_ignores_degenerate_pairs`; `test_apply_band_scale_preserves_median_exactly` (`np.median` kolumn bez zmian, tolerancja 1e-9), `test_apply_band_scale_widens_quantiles_by_k_in_log_space`, `test_apply_band_scale_k1_identity`; `test_sigma_from_ratios_bounds` (jeden element, identyczne wartości → floor; ogromny rozrzut → cap). Testy spójności rejestru muszą wymagać 4 nowych stałych (padają przed implementacją).
- [ ] **Step 2: Uruchom** `cd backend && .venv/bin/python -m pytest tests/test_bands.py tests/test_param_meta.py tests/test_param_registry_doc.py -q` – FAIL.
- [ ] **Step 3: Implementacja** stałych, `param_meta`, wierszy rejestru (w formacie rejestru; „Wynik przed→po” = puste), `bands.py`, aktualizacji liczników (18 stałych, X założeń) w README/dokumencie/testach.
- [ ] **Step 4: Uruchom** pełny backend `-W error::ResourceWarning` – PASS (regeneracja fixture frontendu: `python -m tests.frontend_fixtures`; `frontend/src/testdata/parameters.json` nie zmienia się).
- [ ] **Step 5: Commit** `feat: band scaling helpers and uncertainty constants`.

### Task 2: Niepewność kalibracji (A1)

**Files:**
- Modify: `backend/app/model/simulate.py` (`_prepare`, `_Context`, `simulate`)
- Test: `backend/tests/test_uncertainty_calibration.py` (nowy)

**Interfaces:**
- Consumes: `bands.sigma_from_ratios`, stałe z T1.
- Produces: `_Context.sigma_cal: dict[str, float]` (podatek → σ); w `simulate()` czynnik `exp(σ_cal·z)` per podatek i ścieżka (kształt `(n_paths, 1)`, ten sam dla bazy i scenariusza), nakładany na `taxes[t]` i `base_taxes[t]` po `_scenario` i po udziale PIT, przed sumowaniem `total`; wiersze założeń `calibration_sigma.<podatek>` (status `calibrated`, wartość σ, notka po polsku: „rozrzut relacji wykonania do modułu w oknie kalibracji (lata …), z limitami”).

- [ ] **Step 1: Testy** (na `tests.real_dataset`): `test_sigma_cal_per_tax_in_bounds` (σ ∈ [0.03, 0.35] dla VAT/CIT/PIT; wiersze założeń obecne), `test_calibration_noise_widens_bands` (p10–p90 szersze niż przy `monkeypatch` σ=0 o co najmniej 10% dla każdego podatku), `test_medians_unchanged_by_calibration_noise` (≤ 2% względem σ=0), `test_identical_params_zero_difference`, `test_seed_none_and_zero_work`, `test_single_observation_window_uses_floor` (historia z 1 rokiem kalibracji → σ = floor, brak NaN).
- [ ] **Step 2: Uruchom** – FAIL.
- [ ] **Step 3: Implementacja:** `_prepare` zapisuje roczne relacje `rev/moduł` (już liczone do współczynnika) i wylicza σ per podatek; `simulate` losuje czynniki osobnym generatorem `np.random.default_rng([seed, 11])` (dla `None` – `default_rng()`), jeden `z` na podatek i ścieżkę; wiersze założeń dołączone przed ujednoliceniem kształtu.
- [ ] **Step 4: Uruchom** pełny backend – PASS; zregeneruj fixture frontendu.
- [ ] **Step 5: Commit** `feat: calibration uncertainty in the forecast bands`.

### Task 3: Niepewność parametrów VAR (A2)

**Files:**
- Modify: `backend/app/model/macro.py` (`MacroModel`, `fit_macro`, `to_dict`/`from_dict`), `backend/app/model/simulate.py` (`simulate_levels`, `simulate`)
- Test: `backend/tests/test_macro.py`, `backend/tests/test_uncertainty_var.py` (nowy)

**Interfaces:**
- Produces: `MacroModel.coef_cov: np.ndarray | None` (macierz `(P, P)`, `P = k·(1 + k·lags)`; w kolejności `vec(coefs)` dopasowanej do wektoryzacji kolumnami macierzy `coefs` o kształcie `(1+k·lags, k)` – implementer ustala zgodność z `statsmodels` `res.cov_params()` i dokumentuje w teście); `to_dict` zapisuje klucz `coef_cov` (lista list) tylko gdy nie `None`, `from_dict` toleruje brak klucza; `simulate_levels(model, horizon, n_paths, rng, coef_rng: np.random.Generator | None = None)`: przy `coef_rng` i `model.coef_cov` losuje zaburzenia współczynników na ścieżkę, sprawdza promień spektralny macierzy towarzyszącej (≥ 1 → współczynniki bazowe), liczy kroki z współczynnikami per ścieżka; `simulate()` przekazuje `np.random.default_rng([seed, 13])` (`default_rng()` dla `None`).

- [ ] **Step 1: Testy:** `test_fit_macro_stores_symmetric_psd_cov_with_right_shape`; `test_model_roundtrip_with_and_without_cov` (stary słownik bez klucza → `coef_cov is None`); `test_old_model_simulates_without_param_uncertainty` (wynik identyczny jak przed zmianą dla modelu bez `coef_cov` przy tym samym ziarnie – regresja na stałych liczbach z fixture); `test_param_uncertainty_widens_macro_and_tax_bands` (nowy model: p10–p90 PKB i podatków szersze niż z `coef_rng=None`); `test_medians_close_with_param_uncertainty` (≤ 2%); `test_unstable_draws_fall_back_to_base` (monkeypatch kowariancji o ogromnej skali → brak NaN/inf, wartości w rozsądnym zakresie, część ścieżek identyczna z bazową); `test_seed_none_and_deterministic_with_seed`; `test_model_version_changes_when_cov_added`.
- [ ] **Step 2: Uruchom** – FAIL.
- [ ] **Step 3: Implementacja** (`res.cov_params()`; wektoryzowane obliczenie kroków z `np.einsum`; sprawdzenie stabilności z `np.linalg.eigvals` macierzy towarzyszącej bez stałej, wektoryzowane lub w pętli po unikalnych ścieżkach – wybór wykonawcy, byle mieścił się w budżecie czasu).
- [ ] **Step 4: Uruchom** pełny backend (+ test wydajności) – PASS; zregeneruj fixture frontendu.
- [ ] **Step 5: Commit** `feat: VAR parameter uncertainty in the macro paths`.

### Task 4: Korekta z backtestu (B), zapis i zastosowanie

**Files:**
- Modify: `backend/app/model/backtest.py`, `backend/app/model/simulate.py` (parametr `band_scale`), `backend/app/api/simulate.py`, `backend/app/api/backtest.py`, `backend/app/api/refresh.py`, `backend/app/store.py` (bez zmian schematu: `meta`)
- Test: `backend/tests/test_backtest_export.py`, `backend/tests/test_refresh.py`, `backend/tests/test_band_scale.py` (nowy)

**Interfaces:**
- Consumes: `bands.fit_band_scale`, `bands.apply_band_scale`.
- Produces: `simulate(..., band_scale: dict[str, float] | None = None)` – po A1 i udziale PIT skaluje ścieżki każdego podatku `apply_band_scale(paths, k)` przed sumowaniem `total` (baza i scenariusz tym samym `k`); wiersze założeń `band_scale.<podatek>` (status `calibrated`, wartość `k`, notka „dopasowane do historii backtestu; wartość orientacyjna”); `BacktestResult` zyskuje `band_scale: dict[str, float]`, `coverage80_scaled: dict[str, float]`, `coverage95_scaled`, `n_pairs: dict[str, int]` w `to_dict`; `backtest()` zbiera pary `(median, p10, p90, actual)` i liczy `k` przez `fit_band_scale`, pokrycie „po korekcie” wylicza analitycznie z par (bez ponownej symulacji); noty: „Pokrycie po korekcie jest dopasowane do tej samej historii – wartość orientacyjna.” oraz „Za mało danych do korekty pasm: <podatek>” gdy `k` wymuszone na 1 z braku par; `refresh()` po `fit_macro` liczy `backtest(data)` (dane z `series`), zapisuje `meta["band_scale"] = json.dumps(...)` w `save_snapshot` i dodaje ostrzeżenie `"backtest: ..."` oraz `k = 1`, gdy backtest rzuci wyjątek; `api/simulate.py` i `api/backtest.py` czytają `meta.band_scale` (brak lub błędny JSON → `None`).

- [ ] **Step 1: Testy:** `test_band_scale_applied_widens_and_keeps_medians`; `test_backtest_reports_raw_and_scaled_coverage` (po A: coverage80 raw > dzisiejsze 0,21/0,07/0,25 – wartości z `tests/real_dataset.py`; scaled ∈ [0.65, 0.95] tam, gdzie `n_pairs ≥ 8`, inaczej `k = 1` i nota); `test_backtest_runs_without_band_scale` (nie używa zapisanego `k` do własnej oceny); `test_refresh_stores_band_scale_in_the_same_transaction` (po `refresh` meta zawiera JSON; awaria zapisu = brak częściowego stanu); `test_refresh_survives_backtest_failure` (monkeypatch `backtest` rzucający wyjątek → odświeżenie kończy się sukcesem, `k = 1`, ostrzeżenie); `test_old_store_without_band_scale_uses_one` (API `/simulate` i `/backtest` 200); `test_simulate_api_applies_stored_band_scale` (zapisane `k = 2` → pasma szersze niż `k = 1` przy równych medianach).
- [ ] **Step 2: Uruchom** – FAIL.
- [ ] **Step 3: Implementacja** zgodnie z Interfaces; `refresh()` używa tych samych `series` co zapis, żeby `k` odpowiadało zapisanym danym.
- [ ] **Step 4: Uruchom** pełny backend (+ `-W error::ResourceWarning`), regeneracja fixture – PASS.
- [ ] **Step 5: Commit** `feat: backtest band scaling stored at refresh and applied to the bands`.

### Task 5: Interfejs, eksport, dokumentacja i migawka demo

**Files:**
- Modify: `frontend/src/components/QualityTab.tsx`, `frontend/src/api/types.ts`, `frontend/src/testdata/*.json`, `backend/app/api/export.py`, `docs/model-parameters.md`, `README.md`, `demo/real-data.db`
- Create: `backend/scripts/rebuild_demo_snapshot.py`
- Test: `frontend/src/components/QualityTab.test.tsx`, `backend/tests/test_backtest_export.py`, `backend/tests/test_demo_snapshot.py`, `e2e/budget.spec.ts`

**Interfaces:**
- Consumes: pola backtestu z T4 (`coverage80_scaled`, `band_scale`, `n_pairs`), wiersze założeń `band_scale.<podatek>`, `calibration_sigma.<podatek>`.
- Produces: tabela backtestu w zakładce Jakość z kolumnami „Pokrycie 80% (bez korekty)” i „Pokrycie 80% (po korekcie, orientacyjne)” oraz kolumną `k`; metadane eksportu `pasma_k` = `"<podatek> <k>; …"` (bezpieczne przez `safe()`, walidacja typów); skrypt `rebuild_demo_snapshot.py --db demo/real-data.db` odtwarza model i `band_scale` z zapisanych serii bez sieci (`fit_macro` → `backtest` → `save_snapshot` z zachowaniem `updated_at`/`synthetic=0`), odmawia pracy na bazie z `synthetic=1`.

- [ ] **Step 1: Testy:** QualityTab renderuje obie kolumny pokrycia i `k` (liczby z fixture), notę „dopasowane do historii”; eksport zawiera `pasma_k` i nie psuje starych wyników bez pola (`test_export_without_band_scale_still_works`); `test_demo_snapshot` rozszerzony: po przebudowie `/simulate` zwraca wiersze `band_scale.*` i `calibration_sigma.*`, a mediana PIT 2025 nadal ≈ 28,6 (±5%); e2e: zakładka Jakość pokazuje kolumnę „po korekcie”.
- [ ] **Step 2: Uruchom** – FAIL.
- [ ] **Step 3: Implementacja** UI/eksportu; napisanie i uruchomienie `rebuild_demo_snapshot.py` na migawce (commit zaktualizowanego `demo/real-data.db`); dokumentacja: sekcja „Niepewność prognoz” w rejestrze (opis A1, A2, B, tabela „pokrycie 80% przed → po A → po A+B” zmierzona na `tests/real_dataset.py` i na migawce, jawne ograniczenia: mała próba, korekta dopasowana do historii, wymagane odświeżenie danych), README (jedno zdanie + zaktualizowane otwarte kwestie).
- [ ] **Step 4: Pełna weryfikacja:** backend `-W error::ResourceWarning`, frontend `vitest/tsc/build`, `cd e2e && npm test`, testy live pominięte bez `RUN_LIVE=1`.
- [ ] **Step 5: Commit** i `git push -u origin claude/wider-bands`.

---

## Self-review

- **Pokrycie specyfikacji:** §2.1 → T2; §2.2 → T3; §2.3 → T1 (funkcje), T4 (zastosowanie, zapis); §3 UI/eksport/dok. → T5 (+ rejestr w T1); §5 testy (a)–(j) → rozłożone w T1–T5; §7 kryteria → T5.
- **Spójność nazw:** `fit_band_scale`, `apply_band_scale`, `sigma_from_ratios`, `coef_cov`, `band_scale` (parametr i klucz `meta`), `coverage80_scaled`, `calibration_sigma.<podatek>`, `band_scale.<podatek>`, generatory `[seed, 11]` i `[seed, 13]` użyte jednolicie.
- **Rozstrzygnięcia przy niejasności:** skalowanie B na ścieżkach (nie na kwantylach), więc `total` pozostaje spójny z sumą skalowanych ścieżek; `k` wyznaczane analitycznie z par jako kwantyl 0,8 z `|log(a/m)|/h`; backtest przy odświeżaniu nie może przerwać zapisu danych; migawka demo przebudowywana offline.
- **Proporcja:** plan opisuje decyzje, sygnatury i testy; algorytm podany tylko dla `fit_band_scale`.
