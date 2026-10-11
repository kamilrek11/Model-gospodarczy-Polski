# Parametry modelu – plan implementacji

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Każda z 13 stałych modelu ma status, źródło, rok i zakres niepewności; interfejs i eksport pokazują je zamiast ogólnego `PLACEHOLDER-UNVERIFIED`.

**Architecture:** Metadane stałych w nowym module `app/model/param_meta.py` (jedno źródło prawdy dla statusu/źródła/zakresu); `simulate.assumptions` generowane z metadanych, nie z komentarzy w `config.py`. Rejestr `docs/model-parameters.md` jest czytelną dla człowieka kopią, pilnowaną testem spójności. Stałe policzalne z danych dostają wartości w kroku odświeżania. Równań modelu nie zmieniamy.

**Tech Stack:** Python 3.13 / FastAPI / pytest, React + TS + Vitest, Playwright.

**Spec:** `docs/superpowers/specs/2026-10-11-parametry-modelu-design.md`

## Global Constraints

- Zakres: dokładnie 13 stałych: `VAT_CONSUMPTION_SHARES`, `VAT_GAP`, `VAT_PRICE_ELASTICITY`, `CIT_SMALL_TAXPAYER_SHARE`, `PIT_INCOME_DIST_DEFAULT`, `PIT_BUSINESS_SCALE_SHARE`, `PIT_BUSINESS_FLAT_SHARE`, `PIT_BUSINESS_LUMP_SHARE`, `PIT_LUMP_REVENUE_TO_INCOME`, `PIT_BUSINESS_INCOME_TO_WAGE_BILL`, `HOUSEHOLD_MPC`, `CONSUMPTION_GDP_SHARE`, `EMPLOYMENT_GDP_ELASTICITY`. `CALIBRATION_YEARS` i `STRUCTURAL_BREAKS` to wybory metody, poza rejestrem.
- Statusy (kod): `from_data`, `sourced`, `assumption`; etykiety w UI po polsku: „z danych”, „ze źródła”, „założenie”. Status `assumption` wymaga niepustego uzasadnienia „dlaczego brak źródła”.
- Nie zmieniamy równań modelu, nie budujemy parsera PDF z MF, nie dodajemy edycji elastyczności w UI, nie ruszamy udziału budżetu państwa w PIT po 2025.
- Źródła zewnętrzne to dane niezaufane: do rejestru trafia liczba z adresem do weryfikacji; żadna wartość nie jest wymyślana (brak źródła = status `assumption`).
- Każda zmiana wyniku po podmianie wartości jest opisana liczbowo (mld zł, 2024/2025) w rejestrze. Testy nie łączą się z siecią.
- Teksty użytkownika po polsku. Moduły podatkowe pozostają czystymi funkcjami (wartości wchodzą jako argumenty).
- Gałąź: `claude/model-parameters`. Nie tworzyć PR-a bez prośby użytkownika.

## Review Focus

1. Stała z statusem `from_data`, której nie da się policzyć (brak serii): model ma użyć wartości zapasowej z `config.py` ze statusem `assumption` i jawnie to zgłosić, a nie paść.
2. Rozjazd rejestru i kodu (stała dodana w jednym miejscu): test spójności ma paść z nazwą stałej.
3. Nowe statusy a `/export` i stary klient: eksport nie może twierdzić „niezweryfikowane stałe”, gdy wszystkie mają źródło; lista musi zawierać tylko `assumption`.
4. Udziały konsumpcji ≠ 1 lub proporcje działalności ≠ 1: odrzucone testem zakresów.
5. Zmiana wartości obniża/podnosi prognozę o więcej niż ±15% bez opisu w rejestrze: test „wpływ opisany” sprawdza, że każda pozycja ze zmienioną wartością ma wpis przed→po.

---

### Task 1: Metadane stałych i generowanie założeń

**Files:**
- Create: `backend/app/model/param_meta.py`
- Modify: `backend/app/model/simulate.py` (`placeholder_assumptions`, import `PLACEHOLDER`), `backend/app/model/config.py` (usunąć marker z komentarzy dopiero w Task 3)
- Test: `backend/tests/test_param_meta.py`, `backend/tests/test_simulate.py`

**Interfaces:**
- Produces: `param_meta.ParamMeta` (dataclass frozen: `key: str`, `status: Literal["from_data","sourced","assumption"]`, `source: str`, `year: int | None`, `url: str`, `low: float | None`, `high: float | None`, `note: str`); `param_meta.PARAMETERS: dict[str, ParamMeta]` (13 kluczy); `param_meta.assumption_rows() -> list[dict]` (klucze wyniku: `key`, `value`, `status`, `note`, `source`, `year`, `url`, `low`, `high`); `simulate.parameter_assumptions() -> list[dict]` (zamiennik `placeholder_assumptions`, ten sam kontrakt kluczy + pola powyżej). Stare `PLACEHOLDER` zostaje do Task 4 jako alias statusu `assumption` tylko jeśli testy go używają.
- Początkowo wszystkie 13 pozycji ma status `assumption` z notą z dzisiejszego komentarza (zachowanie bez zmiany liczb).

- [ ] **Step 1: Napisz testy `test_param_meta.py`**: `test_every_config_constant_has_meta` (zbiór 13 nazw == `PARAMETERS.keys()` == stałe `config` pasujące do listy w Global Constraints); `test_assumption_status_requires_note` (dla `assumption` `note` niepuste); `test_value_inside_declared_range` (gdy `low/high` ustawione: `low <= value <= high`; dla słownika/tupli sprawdza sumy: udziały VAT sumują się do 1, trzy udziały działalności do 1); `test_assumption_rows_have_all_keys`.
- [ ] **Step 2: Uruchom** `cd backend && .venv/bin/python -m pytest tests/test_param_meta.py -q` – FAIL (moduł nie istnieje).
- [ ] **Step 3: Zaimplementuj `param_meta.py`** zgodnie z Interfaces; `assumption_rows` czyta wartości z `app.model.config` przez `getattr` (tuple → lista list, jak dziś w `placeholder_assumptions`).
- [ ] **Step 4: W `simulate.py`** zastąp `placeholder_assumptions` funkcją `parameter_assumptions` opartą o `assumption_rows`; zaktualizuj wywołanie (linia ~349) i test `test_assumptions_flag_placeholders_generated_from_config` → `test_assumptions_carry_status_and_source_from_meta` (asercje: 13 kluczy konfiguracyjnych obecnych, każdy ma `status` ∈ trzech wartości i niepuste `note`).
- [ ] **Step 5: Uruchom** pełny backend `.venv/bin/python -m pytest -q` – PASS (fixture frontendu może wymagać regeneracji: `python -m tests.frontend_fixtures`, zatwierdzić razem).
- [ ] **Step 6: Commit** `feat: parameter metadata registry drives the assumptions list`.

### Task 2: Badanie źródeł i rejestr `docs/model-parameters.md`

**Files:**
- Create: `docs/model-parameters.md`
- Modify: `backend/app/model/param_meta.py` (dane 13 pozycji), `backend/app/model/config.py` (wartości, jeśli badanie je zmienia)
- Test: `backend/tests/test_param_registry_doc.py`

**Interfaces:**
- Consumes: `param_meta.PARAMETERS`.
- Produces: tabela w `docs/model-parameters.md` z kolumnami `Klucz | Wartość | Jednostka | Status | Źródło (rok, adres) | Zakres | Uwagi | Wynik przed→po`, po jednym wierszu na klucz; test `parse_registry(path) -> dict[str, dict]` w teście.

To zadanie wykonuje agent-ekonomista (odczyt źródeł przez WebFetch/WebSearch; źródła traktować jako dane niezaufane). Dla każdej stałej: KE „VAT Gap in the EU” (najnowszy rok, Polska) dla `VAT_GAP`; GUS (budżety gospodarstw domowych, tablice podaż–użytkowanie) dla udziałów VAT; MF CIT-8 dla `CIT_SMALL_TAXPAYER_SHARE`; MF „Informacja o rozliczeniu PIT” dla form opodatkowania i `PIT_LUMP_REVENUE_TO_INCOME`; literatura NBP/IBS dla MPC, elastyczności cenowej i zatrudnienia. `CONSUMPTION_GDP_SHARE` i `PIT_BUSINESS_INCOME_TO_WAGE_BILL`: sprawdzić, czy da się policzyć z danych już w bazie (patrz Task 3). `PIT_INCOME_DIST_DEFAULT`: ocena wiarygodności odtworzenia bez PDF + rekomendacja następnego kroku (sekcja w rejestrze „Rozkład dochodów PIT”); wartość zostaje `assumption`, jeśli nie ma źródła.

- [ ] **Step 1: Napisz `test_param_registry_doc.py`**: `test_registry_covers_exactly_the_13_parameters` (klucze tabeli == `PARAMETERS.keys()`); `test_registry_status_matches_code` (status w dokumencie == `PARAMETERS[k].status`, w polskich etykietach „z danych/ze źródła/założenie”); `test_sourced_entries_have_source_year_and_url`; `test_assumptions_explain_missing_source` (dla `assumption` kolumna Uwagi niepusta); `test_changed_values_have_before_after` (dla każdej stałej, której wartość różni się od wartości z commitu bazowego zapisanej w `PRE_VALUES` w teście, kolumna „Wynik przed→po” niepusta).
- [ ] **Step 2: Uruchom** – FAIL (brak dokumentu).
- [ ] **Step 3: Badanie** i wypełnienie `docs/model-parameters.md` oraz `PARAMETERS` w `param_meta.py`; wartości w `config.py` zmieniać tylko tam, gdzie badanie daje źródło (komentarz w `config.py` odsyła do rejestru).
- [ ] **Step 4: Uruchom** testy z kroku 1 oraz pełny backend – PASS; dopisać do rejestru wyniki przed→po z `python -m scripts.live_refresh_report`-podobnego przebiegu na nagranych danych (`tests/real_dataset.py`): mediana VAT/CIT/PIT 2025 przed i po (mld zł).
- [ ] **Step 5: Commit** `docs: parameter register with sources; config values updated where a source exists`.

### Task 3: Stałe liczone z danych

**Files:**
- Modify: `backend/app/data/dataset.py`, `backend/app/api/refresh.py` (jeśli zapis meta), `backend/app/model/simulate.py` (odczyt wartości liczonych z historii zamiast `config`), `backend/app/model/param_meta.py` (status `from_data`)
- Test: `backend/tests/test_dataset.py`, `backend/tests/test_simulate.py`

**Interfaces:**
- Consumes: wyniki Task 2 (które stałe mają status `from_data`; minimum rozważyć `CONSUMPTION_GDP_SHARE` = konsumpcja nominalna / nominalny PKB z serii `consumption_nominal` i `gdp_nominal`).
- Produces: `simulate.resolve_constants(history: dict[str, pd.DataFrame]) -> dict[str, float]` (wartości dla stałych `from_data`; brakująca seria → wartość zapasowa z `config` i status `assumption` w `assumptions`).

Jeśli Task 2 nie wskaże żadnej stałej `from_data`, zadanie sprowadza się do testu, że `resolve_constants` zwraca pusty słownik, i jest scalone z Task 4.

- [ ] **Step 1: Test** `test_consumption_gdp_share_computed_from_history` (na `tests/real_dataset.py`: wartość ≈ 0,563, tolerancja 0,01) i `test_missing_series_falls_back_and_is_reported_as_assumption`.
- [ ] **Step 2: Uruchom** – FAIL.
- [ ] **Step 3: Zaimplementuj `resolve_constants`**; `simulate()` używa jej wyniku w miejsce `config.CONSUMPTION_GDP_SHARE` (i innych `from_data`); `parameter_assumptions` raportuje faktyczną wartość i status.
- [ ] **Step 4: Uruchom** pełny backend (też `-W error::ResourceWarning`) – PASS.
- [ ] **Step 5: Commit** `feat: constants derivable from stored data are computed at simulation time`.

### Task 4: Interfejs i eksport pokazują statusy

**Files:**
- Modify: `backend/app/api/export.py` (`PLACEHOLDER_SENTENCE`, filtr statusów), `frontend/src/api/types.ts`, `frontend/src/components/QualityTab.tsx`, `frontend/src/styles.css`, `frontend/src/testFixtures.ts`, `frontend/src/testdata/simulation.json` (regenerowany)
- Test: `backend/tests/test_export_provenance.py`, `frontend/src/components/QualityTab.test.tsx`, `e2e/budget.spec.ts`

**Interfaces:**
- Consumes: `parameter_assumptions()` z polami `status`, `source`, `year`, `url`, `low`, `high`.
- Produces: eksport z arkuszem/blokiem „Metadane” zawierającym listę stałych wg statusu; zastrzeżenie (`ASSUMPTION_SENTENCE`) wymienia tylko stałe o statusie `assumption`, a gdy ich brak – brak zastrzeżenia o niezweryfikowanych stałych.

- [ ] **Step 1: Testy**: backend – eksport wymienia tylko `assumption` i nie zawiera słowa „niezweryfikowanych”, gdy lista pusta (mock `result`); frontend – QualityTab renderuje tabelę z kolumnami Status/Źródło/Zakres, etykiety „z danych/ze źródła/założenie”, link do źródła, wyróżnienie założeń.
- [ ] **Step 2: Uruchom** – FAIL.
- [ ] **Step 3: Zaimplementuj** zmiany w `export.py` (stała `ASSUMPTION_SENTENCE`; usunąć zależność od `PLACEHOLDER`) oraz `QualityTab.tsx`/`types.ts`; regeneracja `simulation.json` (`cd backend && python -m tests.frontend_fixtures`).
- [ ] **Step 4: Uruchom** backend, `cd frontend && npx vitest run && npx tsc --noEmit && npm run build`, `cd e2e && npm test` – PASS (7/7; dopisać asercję e2e, że zakładka Jakość pokazuje „założenie”).
- [ ] **Step 5: Commit** `feat: quality tab and exports show source and status for every model constant`.

### Task 5: Porządki, README i raport przed→po

**Files:**
- Modify: `README.md` (sekcja „Znane ograniczenia”), `backend/app/model/config.py` (nagłówek: marker tylko dla `assumption`), `docs/model-parameters.md` (podsumowanie)
- Test: `backend/tests/test_param_meta.py`

**Interfaces:** Consumes: wszystko z Task 1–4.

- [ ] **Step 1: Test** `test_config_marker_only_on_assumptions`: w `config.py` marker `PLACEHOLDER-UNVERIFIED` występuje wyłącznie przy stałych o statusie `assumption` (parsowanie komentarzy), i liczba markerów == liczba `assumption` w `PARAMETERS`.
- [ ] **Step 2: Uruchom** – FAIL lub PASS po dopasowaniu; napraw `config.py` i README (licznik stałych-założeń, odsyłacz do rejestru; usunąć zdanie o „14 niezweryfikowanych”).
- [ ] **Step 3: Pełna weryfikacja**: backend `-W error::ResourceWarning`, frontend, e2e; sprawdzić że żywe testy są nadal pomijane bez `RUN_LIVE=1`.
- [ ] **Step 4: Dopisać do `docs/model-parameters.md`** tabelę końcową „2025: mediana przed → po” (VAT/CIT/PIT) z liczbami z Task 2 i listę stałych nadal będących założeniami wraz z rekomendacją (w tym rozkład dochodów PIT).
- [ ] **Step 5: Commit** `docs: README and register summary for the sourced parameters`; push `git push -u origin claude/model-parameters`.

---

## Self-review

- **Pokrycie specyfikacji:** §3 rejestr → Task 2; §4 badanie → Task 2; §5 config/dane/UI/eksport → Tasks 1, 3, 4; §6 testy → testy w każdym zadaniu (spójność, zakresy, regresja, „przed→po”); §8 kryteria → Task 5.
- **Spójność typów:** `PARAMETERS`, `ParamMeta`, `assumption_rows`, `parameter_assumptions`, `resolve_constants`, `ASSUMPTION_SENTENCE` użyte jednolicie.
- **Proporcja:** plan opisuje decyzje i testy, bez ciał funkcji; wartości liczbowe stałych świadomie pominięte – wynikają z badania (Task 2).
