# Prawdziwe źródła danych (GUS BDL + Eurostat + MF) – plan wdrożenia

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `POST /refresh` pobiera prawdziwe dane (GUS BDL, Eurostat, MF), normalizuje je do jednostek modelu, przechodzi bramki jakości i zapisuje z `synthetic="0"`.

**Architecture:** Trzy klienty implementujące istniejący protokół `SourceClient` (`fetch() -> dict[str, DataFrame]`, błędy jako `SourceError`) + cienka warstwa składania/walidacji zestawu. Reszta (model, symulacja, API, UI) bez zmian poza obsługą załamania strukturalnego PIT w 2025.

**Tech Stack:** Python 3.13, httpx, pandas, openpyxl (XLSX), stdlib `zipfile`; pytest.

**Spec:** `docs/superpowers/specs/2026-10-10-symulator-budzetu-design.md`. **Raport z rozpoznania źródeł** (prawdziwe odpowiedzi, id zmiennych, pułapki): `docs/data-sources-discovery.md` (dodawany w zadaniu 5; do tego czasu: plik w katalogu planów sesji, surowe odpowiedzi w katalogu roboczym sesji – ścieżki w opisach zadań).

## Global Constraints

- Wszystkie kwoty w magazynie w **mld zł**; poziomy indeksów w jednej skali; jedna jednostka na serię (nazwy serii bez zmian: `pkb_real`, `employment`, `wage_nominal`, `cpi`, `consumption_nominal`, `gross_surplus`, `rev_pit`, `rev_cit`, `rev_vat`; dodatkowo `gdp_nominal` jako seria pomocnicza do walidacji).
- Indeks serii: `int` rok (nazwa indeksu `year`), kolumna `value` (`float`) – jak w `Store.load_series`.
- Wartości brakujące **nigdy** nie są zerami: pomijane (BDL: `attrId` ∉ {1,3,9,11,13,20,21,97} → pominąć). Żadnych wartości wymyślonych ani interpolowanych.
- Każdy błąd sieci/parsowania/danych → `SourceError(source, message)` z nazwą źródła (`gus_bdl`, `eurostat`, `mf_execution`); żadnych gołych wyjątków na zewnątrz.
- Pliki z internetu są **niezaufane**: odczyt ZIP/XLSX w pamięci, limity rozmiaru, brak rozpakowywania na dysk po nazwach z archiwum, tylko https i hosty z listy dozwolonych (`bdl.stat.gov.pl`, `ec.europa.eu`, `api.dane.gov.pl`, `www.dane.gov.pl`).
- Testy jednostkowe **bez sieci**, na nagranych prawdziwych odpowiedziach (przycięte fixtures w `backend/tests/fixtures/real/`, opisane nagłówkiem/README jako nagrane prawdziwe dane publiczne z datą pobrania 2026-10-10 – nie `synthetic_*`). Test z siecią tylko pod markerem `live` (domyślnie pomijany).
- BDL: limit anonimowy 1000 żądań/12 h – klient robi ≤ 12 żądań na odświeżenie; opcjonalny nagłówek `X-ClientId` z `BDL_CLIENT_ID`.
- Zależności przypięte `==` (jak w `pyproject.toml`); nowa zależność tylko za wyraźną zgodą w zadaniu.
- Interfejs użytkownika po polsku; zmiany w UI ograniczone do not o załamaniu PIT.

## Review Focus

- BDL zwraca `val: 0.0` z `attrId` oznaczającym brak danych: zero nie może trafić do magazynu (test na nagranej serii 458272, rok 2000).
- Pierwsze/ostatnie lata szeregów łańcuchowanych (CPI, PKB): brak dziury, brak przesunięcia o rok, poziom zakotwiczony w znanej wartości.
- Archiwum ZIP z nieoczekiwaną zawartością (ogromny plik, brak pliku 007, zła etykieta wiersza, układ kolumn jak w innym roku): jawny błąd lub pominięty rok z komunikatem, nigdy zgadywanie komórki.
- Jednostki: błąd rzędu 1000× (mln vs mld) musi zatrzymać odświeżenie na bramce jakości, nie trafić do modelu.
- Załamanie PIT 2025: kalibracja i backtest nie mogą używać lat ≥ 2025 dla `rev_pit`.

---

### Task 1: Klient BDL na prawdziwe API + łańcuchowanie indeksów

**Files:**
- Modify: `backend/app/data/gus_bdl.py`, `backend/app/data/series_map.py`
- Create: `backend/app/data/transform.py`, `backend/tests/fixtures/real/bdl_*.json` (przycięte nagrania), `backend/tests/fixtures/real/README.md`
- Test: `backend/tests/test_gus_bdl_real.py`, `backend/tests/test_transform.py`; usunąć/przepisać przestarzałe testy i `synthetic_bdl_*.json` w `tests/test_data_clients.py`

**Interfaces:**
- Produces: `chain_growth(growth: pd.Series, base_year: int, base_value: float) -> pd.Series` (indeks `int`; `growth` = indeks „rok poprzedni = 100”; poziom w `base_year` = `base_value`; lata po bazie: `L_t = L_{t-1}·g_t/100`; lata przed bazą: `L_{t-1} = L_t·100/g_t`; `base_year` może być `min(index) - 1`, wtedy poziom pierwszego roku = `base_value·g/100`). `GusBdlClient(base_url, http, *, client_id: str | None = None, sleep=time.sleep, max_retries: int = 3)` – `fetch()` zwraca `pkb_real` (mld zł), `employment`, `wage_nominal`, `cpi` (poziom, baza 100 w roku poprzedzającym pierwszy), `gross_surplus` (mld zł), `gdp_nominal` (mld zł).
- `series_map.py`: potwierdzone id – `pkb_growth=458431`, `gdp_nominal=458271` (mln zł), `employment=154173`, `wage_nominal=64428`, `cpi_growth=217230`, `gross_surplus=458419` (mln zł); jednostka krajowa: filtr `unit-level=0` + sprawdzenie `id == "000000000000"` (nazwa „POLSKA”).

- [ ] **Step 1: Testy transform (czerwone)** `test_chain_growth_forward_and_backward`: `g={2022:105.3, 2023:100.2, 2024:103.0}`, `base_year=2023`, `base_value=200.0` → `2023=200.0`, `2024=206.0`, `2022≈199.6007984` (200·100/100.2); `test_chain_growth_base_before_first_year`: `g={2003:101.0, 2004:102.0}`, `base_year=2002`, `base_value=100.0` → `2003=101.0`, `2004=103.02`; `test_chain_growth_rejects_missing_year_gap` (luka w latach → `ValueError`).
- [ ] **Step 2: Testy klienta (czerwone) na nagranych odpowiedziach** (źródło nagrań: katalog roboczy sesji `bdl/data_*_l0.json`, `bdl/data_458272_l0.json`, `bdl/h_*.txt`): `test_values_for_poland_only_with_unit_level_0` (zapytanie zawiera `unit-level=0`; jedyny wynik `POLSKA`/`000000000000`); `test_nominal_gdp_458271_values` (2000=751669 → `751.669`, 2024=3653432 → `3653.432` mld zł); `test_missing_value_attr4_is_dropped` (`val 0.0, attrId 4`, rok 2000 serii 458272 → brak roku 2000); `test_preliminary_attr9_is_kept`; `test_pkb_real_chained_to_nominal_anchor` (poziom w roku bazowym = nominalny PKB w mld; zmiany r/r = indeks/100); `test_cpi_level_chained_base_100`; `test_retry_after_non_numeric_header` (nagłówek `3 sek` → `sleep(3)`, potem sukces); `test_429_after_max_retries_raises_source_error`; `test_page_size_never_above_100`; `test_x_client_id_header_sent`; `test_parse_errors_are_source_errors` (zachować pokrycie z poprzedniej wersji: nienumeryczny `val`, brak `year`, ciało nie-słownik).
- [ ] **Step 3: Implementacja** `chain_growth` w `transform.py`; przepisać `gus_bdl.py` pod prawdziwy kształt (brak `page`/`pageSize` w odpowiedzi danych, `links` opcjonalne, wartości przez whitelistę `attrId`, zmienne po id, normalizacja mln zł → mld zł), retry/backoff (maks. `max_retries`, parsowanie `Retry-After` w formie „N sek” i liczby, górny limit czekania np. 30 s), nagłówek `X-ClientId`. Nagrać przycięte fixtures (po ~5–25 lat każdej serii, w tym rok 2000 serii 458272 z `attrId 4`) do `tests/fixtures/real/` i opisać w README.
- [ ] **Step 4: Uruchomić** `cd backend && .venv/bin/python -m pytest -q` → wszystko zielone (także `-W error::ResourceWarning`).
- [ ] **Step 5: Commit** `feat: GUS BDL client for the real API (unit-level 0, attr filter, retry, chaining)`.

### Task 2: Klient Eurostat (JSON-stat)

**Files:**
- Create: `backend/app/data/eurostat.py`, `backend/tests/fixtures/real/eurostat_*.json`
- Test: `backend/tests/test_eurostat.py`

**Interfaces:**
- Produces: `EurostatClient(http: httpx.Client, *, base_url: str = EUROSTAT_BASE)` implementujący `SourceClient` (`name = "eurostat"`); `fetch()` zwraca `consumption_nominal` (mld zł, `nama_10_gdp`, `na_item=P31_S14`, `unit=CP_MNAC`, `geo=PL`, od 2000) oraz `gross_surplus_eurostat` (mld zł, `B2A3G`, `CP_MNAC`). Funkcja czysta `decode_jsonstat(doc: dict) -> dict[tuple, dict[int, float]]` (dekoder JSON-stat 2.0: rzadki słownik `value` klucz = płaski indeks, wymiary `id`/`size`/`dimension.*.category.index`, flagi w `status`; brak wartości = pominięty rok).
- Wzorzec dekodera: `jsonstat.py` w katalogu roboczym sesji; nagrane odpowiedzi: `eurostat/nama_gdp_PL.json` tamże.

- [ ] **Step 1: Testy (czerwone)** `test_decode_jsonstat_sparse_values_and_flags`; `test_consumption_values` (2023=1934063 mln → `1934.063`, 2024=`2056.557`, 2025=`2209.033` mld zł); `test_gross_surplus_eurostat_2022_matches_bdl` (2022 = `1553.042`); `test_request_uses_cp_mnac_not_cp_mio_nac` (parametr `unit=CP_MNAC`); `test_empty_dataset_raises_source_error` (odpowiedź `size` zawiera 0 – tak odpowiada Eurostat na zły kod jednostki → `SourceError`, nie pusta seria); `test_http_errors_and_malformed_json_are_source_errors`.
- [ ] **Step 2: Implementacja** `decode_jsonstat` i klienta (httpx, timeout, https, bez przekierowań poza hosta Eurostatu); fixtures z `nama_gdp_PL.json` przycięte do kilku lat.
- [ ] **Step 3: Uruchomić** pełny `pytest -q` → zielone.
- [ ] **Step 4: Commit** `feat: Eurostat JSON-stat client for consumption and gross operating surplus`.

### Task 3: Klient MF – wykonanie budżetu państwa (dane.gov.pl, zbiór 163)

**Files:**
- Create: `backend/app/data/mf_execution.py`, `backend/tests/fixtures/real/mf_*.xlsx` (zrekonstruowane z opublikowanych wartości), `backend/tests/test_mf_execution.py`
- Modify: `backend/app/data/execution.py` (usunąć placeholder albo zostawić cienką fasadę do `mf_execution`; usunąć nieużywane `TODO_VERIFY_*`)
- Possibly modify: `backend/pyproject.toml` (+ `xlrd==2.0.1` tylko jeśli lata 2015–2022 są wyłącznie w `.xls` i to blokuje użyteczną historię – decyzja po wypełnieniu macierzy z kroku 1; zgłosić w raporcie)

**Interfaces:**
- Produces: `MfBudgetExecutionClient(http: httpx.Client, cache_dir: str | None, *, years: range | None = None, max_download_bytes: int = 40_000_000, max_member_bytes: int = 30_000_000)` (`name = "mf_execution"`); `fetch()` zwraca `rev_vat`, `rev_cit`, `rev_pit` (mld zł, lata dostępne i obsłużone). Czyste funkcje: `list_resources(http) -> list[Resource(year:int, url:str)]` (API `https://api.dane.gov.pl/1.4/datasets/163/resources`, paginacja, `attributes.link`, rok z tytułu/daty; walidacja hosta i https), `extract_revenue(xlsx_bytes: bytes) -> dict[str, float]` (wiersze po etykiecie: „1.1. Podatek od towarów i usług”, „1.4. Podatek dochodowy od osób prawnych”, „1.5. Podatek dochodowy od osób fizycznych”; kolumna „Wykonanie” wyznaczana z nagłówka lub jako ostatnia liczbowa komórka wiersza – wartości w tys. zł), `find_member(zip_bytes) -> bytes` (zagnieżdżony ZIP → plik pasujący do `007*DOCHODY BP ZESTAWIENIE OG*` bez względu na wielkość liter i kodowanie nazw `#Uxxxx`).
- Dane referencyjne (opublikowane, tys. zł, „Wykonanie”): 2023: VAT 244267385.71, CIT 67883082.34, PIT 91665807.67; 2024: VAT 287683368.91, CIT 60239719.55, PIT 97599844.06; 2025: VAT 321646381.78, CIT 63686737.92, PIT 28752115.01. Pliki wzorcowe: katalog roboczy sesji `danegov/zip2023`, `zip2024`, `zip2025` (`t1/…007…`); zasoby: `danegov/ds163_res.json`.

- [ ] **Step 1: Macierz weryfikacji (rozpoznanie przed kodem)** Dla każdego roku 2015–2025 pobrać ZIP (przez API zasobów, do katalogu poza repo), ustalić: nazwę pliku 007, format (`.xlsx`/`.xls`), arkusz, wiersze 1.1/1.4/1.5, kolumnę „Wykonanie”, sumę kontrolną sensu (VAT 2024 ≈ 287,7 mld). Zapisać macierz w `docs/data-sources-discovery.md` (sekcja „MF – macierz lat”) i w raporcie zadania. Lata, których nie da się wiarygodnie sparsować, mają być **jawnie nieobsłużone** (komunikat), nie zgadywane.
- [ ] **Step 2: Testy (czerwone)** na zrekonstruowanych XLSX odtwarzających układy 2023/2024/2025 (etykieta w kol. A lub A i C; plan/wykonanie w różnych kolumnach; liczby powyżej): `test_extract_revenue_2024_layout`, `test_extract_revenue_2023_and_2025_layout`, `test_values_converted_thousand_zl_to_billion` (np. `287683368.91` tys. → `287.68336891` mld); `test_missing_row_label_raises` (brak wiersza „1.5…” → błąd z nazwą etykiety); `test_find_member_handles_nested_zip_and_escaped_names`; `test_oversized_member_rejected` (nagłówek mówi 500 MB → odrzucone bez odczytu); `test_zip_slip_names_never_touch_disk` (nazwa `../../x` ignorowana); `test_resource_urls_must_be_https_and_allowlisted`; `test_cache_hit_skips_download` (drugi `fetch` nie wykonuje żądań dla lat z cache); `test_year_failure_reports_year_in_source_error_and_other_years_still_returned_policy` (polityka: nieobsłużony rok → pominięty z ostrzeżeniem w `client.warnings`, ale brak jakichkolwiek lat → `SourceError`).
- [ ] **Step 3: Implementacja** wg interfejsów (odczyt w pamięci, `openpyxl` read-only/data-only, limity rozmiaru, timeouty, brak zapisu nazw z archiwum na dysk; cache = JSON z wartościami per rok + identyfikator zasobu/rozmiar, katalog z `BUDGET_CACHE_DIR`).
- [ ] **Step 4: Uruchomić** pełny `pytest -q` → zielone.
- [ ] **Step 5: Commit** `feat: Ministry of Finance state-budget execution client (dane.gov.pl dataset 163)`.

### Task 4: Składanie zestawu, bramki jakości, załamanie PIT, domyślne klienty

**Files:**
- Create: `backend/app/data/dataset.py` (składanie + walidacja)
- Modify: `backend/app/api/refresh.py` (domyślna fabryka `get_clients()` z prawdziwymi klientami; użycie `dataset`), `backend/app/model/config.py` (`STRUCTURAL_BREAKS`), `backend/app/model/simulate.py` (kalibracja i nota o załamaniu), `backend/app/model/backtest.py` (cele ≥ rok załamania pomijane dla danej serii + nota), `frontend/src/components/QualityTab.tsx` (jeśli założenia/noty wymagają renderowania nowej noty – tylko jeśli konieczne)
- Test: `backend/tests/test_dataset.py`, uzupełnienia `test_refresh.py`, `test_simulate.py`, `test_backtest_export.py`

**Interfaces:**
- Consumes: wyniki klientów z zadań 1–3.
- Produces: `assemble(results: dict[str, pd.DataFrame]) -> dict[str, tuple[str, pd.DataFrame]]` (nazwa serii → (źródło, dane); `gross_surplus` = BDL, uzupełnione latami po ostatnim roku BDL z `gross_surplus_eurostat`; zapisuje źródło per seria); `validate_dataset(series: dict[str, pd.DataFrame]) -> list[str]` (lista naruszeń; pusta = OK): (a) ≥ 15 ciągłych lat wspólnych dla 5 zmiennych makro; (b) `consumption_nominal / gdp_nominal` w [0,4; 0,7] w ostatnim wspólnym roku; (c) ostatnia wartość `rev_vat` ∈ [100; 500], `rev_cit` ∈ [20; 150], `rev_pit` ∈ [10; 200] mld zł; (d) nakładające się lata `gross_surplus` BDL vs Eurostat różnią się o ≤ 2%; (e) brak NaN/ujemnych kwot. `STRUCTURAL_BREAKS: dict[str, int] = {"rev_pit": 2025}`; `calibration_years(series_name, years) -> list[int]` ucina lata ≥ rok załamania.
- Wymaganie: naruszenie bramki → `refresh` kończy się błędem źródła `"dataset"` z listą naruszeń, **bez zapisu** (zachowuje ostatni dobry stan); sukces → atomowy `save_snapshot` jak dotąd, `synthetic="0"`.

- [ ] **Step 1: Testy (czerwone)** `test_assemble_extends_gross_surplus_from_eurostat_after_bdl_last_year` (BDL do 2023, Eurostat do 2025 → seria do 2025, lata ≤ 2023 z BDL); `test_validate_flags_thousand_fold_unit_error` (konsumpcja ×1000 → naruszenie (b)); `test_validate_flags_wrong_vat_scale`; `test_validate_requires_15_contiguous_macro_years`; `test_validate_gross_surplus_sources_disagree`; `test_refresh_with_failed_gate_keeps_previous_state_and_names_violations`; `test_refresh_success_writes_synthetic_zero_and_all_series_with_sources`; `test_default_get_clients_builds_real_clients` (bez sieci: tylko typy i konfiguracja z env); `test_calibration_ignores_pit_years_from_2025` (PIT 2025=28.75 nie wpływa na współczynnik kalibracji); `test_backtest_skips_pit_targets_from_break_year_and_notes_it`; `test_assumptions_contain_pit_break_note`.
- [ ] **Step 2: Implementacja** `dataset.py`, `STRUCTURAL_BREAKS` i użycie w `simulate.py` (okno kalibracji) oraz `backtest.py`; nota (po polsku) w liście założeń/notatkach backtestu: „PIT w budżecie państwa: zmiana zasad podziału od 2025 (reforma finansowania JST); kalibracja do 2024; wykonanie 2025 nie jest porównywalne z prognozą przy dotychczasowych zasadach”.
- [ ] **Step 3: Uruchomić** backend `pytest -q` (także z `-W error::ResourceWarning`), frontend `npx vitest run` i `npx tsc --noEmit` jeśli ruszano frontend.
- [ ] **Step 4: Commit** `feat: assemble real datasets with quality gates and the 2025 PIT structural break`.

### Task 5: Dowód na żywo i dokumentacja

**Files:**
- Create: `backend/tests/test_live_sources.py` (`@pytest.mark.live`), `backend/scripts/live_refresh_report.py`, `docs/data-sources-discovery.md` (przeniesiony raport z rozpoznania + macierz MF + wyniki uruchomienia na żywo)
- Modify: `backend/pyproject.toml` (marker `live`, domyślnie pominięty: `addopts = -m "not live"`), `.github/workflows/ci.yml` (osobny job `live-sources` wyłącznie dla `workflow_dispatch`), `README.md` (sekcja „Prawdziwe dane”, zmienne `BDL_CLIENT_ID`, `BUDGET_CACHE_DIR`), lista założeń w `config.py` (usunąć stare `PLACEHOLDER` dla jednostki konsumpcji: `CONSUMPTION_SERIES_TO_MLD_ZL` zastąpione normalizacją w klientach)

**Interfaces:**
- `live_refresh_report.py --db <tmp.db>` uruchamia prawdziwe odświeżenie przez `refresh(...)` do podanej (nowej) bazy, potem `simulate` z parametrami domyślnymi i `backtest`, i wypisuje raport tekstowy (lata dostępne dla każdej serii, ostatnie wartości, współczynniki kalibracji, mediany prognoz VAT/CIT/PIT na 5 lat, MAPE i pokrycie z backtestu, naruszenia bramek). Odmawia pracy na ścieżce domyślnej aplikacji.

- [ ] **Step 1: Test `live` (domyślnie pominięty)**: `test_live_bdl_gdp_nominal_2024`, `test_live_eurostat_consumption_2024`, `test_live_mf_vat_2024` (wartości w rzędach wielkości z raportu), uruchamiany ręcznie `pytest -m live`.
- [ ] **Step 2: Skrypt raportu i uruchomienie na żywo** do tymczasowej bazy; wynik (liczby) wkleić do `docs/data-sources-discovery.md` i do raportu zadania; jeśli bramka jakości zatrzyma zestaw – to znalezisko, nie powód do osłabiania bramki: opisać dokładnie.
- [ ] **Step 3: Dokumentacja i CI** (job `live-sources` tylko `workflow_dispatch`, `-m live`); zwykłe `pytest -q` nadal pomija testy `live`.
- [ ] **Step 4: Uruchomić** pełne zestawy (backend, frontend, e2e lokalnie jak dotąd) → zielone.
- [ ] **Step 5: Commit** `docs: real data sources, live smoke tests and the live refresh report`.

---

## Self-Review

- Pokrycie decyzji użytkownika: wpływy z MF gotówkowo (zad. 3), makro GUS-first z Eurostatem dla konsumpcji (zad. 1–2; uzupełnienie nadwyżki operacyjnej Eurostatem – jawne odstępstwo, zad. 4), osobna gałąź/PR (poza planem: proces).
- Załamanie PIT 2025 obsłużone w kalibracji i backteście (zad. 4); prognoza po 2025 pozostaje „zasady sprzed reformy” – otwarta decyzja.
- Niezweryfikowane po tej pracy nadal: 14 stałych modelu (zakres ekonomisty), rozkład dochodów PIT (tylko PDF do 2021).
