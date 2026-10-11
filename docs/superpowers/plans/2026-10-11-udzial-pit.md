# Udział budżetu państwa w PIT – plan implementacji

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Prognoza PIT w budżecie państwa od 2025 r. jest porównywalna z wykonaniem dzięki udziałowi `s = s₀ × m × ε` (kalibracja na 2025, mnożnik użytkownika, rozrzut Monte Carlo).

**Architecture:** Udział nakładany jest w `simulate()` po `_scenario()` wyłącznie na raportowany PIT (kanał dochodu rozporządzalnego i drugi obieg liczą nadal PIT „ogółem”). `s₀` liczone jest z zapisanych danych przy każdej symulacji (jak `CONSUMPTION_GDP_SHARE`), `m` to nowy parametr schematu, `ε` losowany osobnym generatorem (wspólne liczby losowe).

**Tech Stack:** Python 3.13 / FastAPI / numpy / pytest; React + TS + Vitest; Playwright.

**Spec:** `docs/superpowers/specs/2026-10-11-udzial-pit-design.md`

## Global Constraints

- Wzór: `s = s₀ × m × ε`; lata ≥ `config.STRUCTURAL_BREAKS["rev_pit"]` (2025); lata wcześniejsze bez zmian.
- `s₀` = wykonanie `rev_pit` w roku załamania ÷ wynik modułu PIT dla tego roku według obecnego prawa (ze współczynnikiem kalibracji sprzed reformy); nie zapisywane w bazie, przeliczane przy każdej symulacji.
- Parametr: klucz `pit_state_share_mult`, etykieta „PIT - udział budżetu państwa (mnożnik względem 2025)”, grupa `pit`, jednostka `mnożnik`, wartość bazowa 1,0, zakres 0,5–2,0, krok 0,05.
- `ε`: lognormalny, mediana 1, odchylenie logarytmu `config.PIT_STATE_SHARE_SIGMA = 0.2` (status `assumption`, 14. stała rejestru); ten sam `ε` dla bazy i scenariusza na ścieżce.
- Brak `rev_pit` za rok załamania i brak sposobu wyliczenia modułu: `s₀ = 1`, bez `ε`, jawne ostrzeżenie; nigdy błąd. `m` działa zawsze dla lat ≥ rok załamania.
- Kanały sprzężenia zwrotnego (`pit_first_law`, `d_pit`, VAT, PKB) nie zmieniają się: udział nakłada się tylko na raportowany PIT.
- Backtest nadal nie ocenia lat ≥ 2025; trening nie używa wykonania ≥ 2025.
- Teksty użytkownika po polsku; brak ruchu sieciowego w testach; nie zmieniamy równań podatkowych, nie dodajemy danych o PIT ogółem.
- Gałąź: `claude/pit-state-share`. Bez PR-a bez prośby użytkownika.

## Review Focus

1. Brak `rev_pit` za 2025 (stary zestaw / synthetic): `s₀ = 1`, brak `ε`, ostrzeżenie w założeniach, symulacja działa (T2).
2. `m = 2` podwaja PIT od 2025 i nie rusza lat wcześniejszych; identyczne parametry bazy i scenariusza dają zerową różnicę mimo `ε` (T2).
3. `seed=None` i `seed=0` nie psują losowania `ε` (T2).
4. Zapisane scenariusze i żądania bez `pit_state_share_mult` nadal przechodzą walidację z domyślną 1,0 (T1).
5. Model, którego ostatni rok ≥ rok załamania (dane makro 2025 dostępne): `s₀` liczone z danych, nie z prognozy (T2).
6. Eksport i zakładka Jakość pokazują wiersz `PIT_STATE_SHARE` ze statusem „kalibracja” i jednoroczną uwagą (T3, T4).

---

### Task 1: Parametr `m` i stała `σ` (schemat + rejestr)

**Files:**
- Modify: `backend/app/model/params.py`, `backend/app/model/config.py`, `backend/app/model/param_meta.py`, `docs/model-parameters.md`
- Test: `backend/tests/test_params.py`, `backend/tests/test_param_meta.py`, `backend/tests/test_param_registry_doc.py`

**Interfaces:**
- Produces: `PARAMETER_SCHEMA` zawiera `ParamSpec(key="pit_state_share_mult", label="PIT - udział budżetu państwa (mnożnik względem 2025)", tax="pit", unit="mnożnik", default=1.0, min=0.5, max=2.0, step=0.05, description=<Polski opis: mnożnik udziału budżetu państwa w PIT względem 2025 r.; oszacowane z jednego roku>)`; `defaults()["pit_state_share_mult"] == 1.0`; `config.PIT_STATE_SHARE_SIGMA: float = 0.2`; `param_meta.PARAMETERS["PIT_STATE_SHARE_SIGMA"]` (status `assumption`, low 0.1, high 0.3, notka po polsku z uzasadnieniem „brak źródła; rozrzut jednego punktu kalibracyjnego”) i pozycja w `docs/model-parameters.md` (14. wiersz, kolumny jak pozostałe, „Wynik przed→po” = „—”).

- [ ] **Step 1: Testy.** `test_params.py`: rozszerz `EXPECTED` o `pit_state_share_mult` (długość schematu +1); `test_old_requests_without_the_multiplier_validate_to_default` (`validate({})["pit_state_share_mult"] == 1.0`, także dla żądania z innymi kluczami); `test_multiplier_out_of_range_rejected` (0.4 i 2.1 → `ValueError` z „poza zakresem”). `test_param_meta.py`/`test_param_registry_doc.py`: istniejące testy spójności muszą wymagać nowej stałej (padają przed implementacją).
- [ ] **Step 2: Uruchom** `cd backend && .venv/bin/python -m pytest tests/test_params.py tests/test_param_meta.py tests/test_param_registry_doc.py -q` – FAIL.
- [ ] **Step 3: Implementacja** w wymienionych plikach (schemat parametrów, stała w `config.py` z komentarzem odsyłającym do rejestru i markerem `PLACEHOLDER-UNVERIFIED`, wpis w `param_meta`, wiersz w rejestrze; zaktualizuj licznik stałych w README i w teście markerów, jeśli liczy 13/10).
- [ ] **Step 4: Uruchom** pełny backend `.venv/bin/python -m pytest -q -W error::ResourceWarning` – PASS (regeneracja fixture: `python -m tests.frontend_fixtures`).
- [ ] **Step 5: Commit** `feat: pit_state_share_mult parameter and PIT_STATE_SHARE_SIGMA constant`.

### Task 2: Udział w `simulate()`

**Files:**
- Modify: `backend/app/model/simulate.py`
- Test: `backend/tests/test_simulate.py` (lub nowy `backend/tests/test_pit_state_share.py`)

**Interfaces:**
- Consumes: `config.PIT_STATE_SHARE_SIGMA`, parametr `pit_state_share_mult` z `validate()`.
- Produces: `@dataclass(frozen=True) class StateShare: s0: float; year: int | None; source: Literal["data","forecast","none"]; note: str`; `estimate_state_share(model: MacroModel, history: dict[str, pd.DataFrame], ctx: _Context, years: list[int], pit_base: np.ndarray) -> StateShare`; wiersz założeń `PIT_STATE_SHARE` (status `calibrated` gdy `source != "none"`, inaczej `assumption`; `value=s0`; `year=rok załamania`; `low/high = s0·exp(∓σ)`; notka po polsku z efektywnym udziałem `s0×m` i uwagą „oszacowane z jednego roku”; dla `none`: „PIT liczony według zasad sprzed 2025 r.”). `simulate()` stosuje czynnik do `taxes["pit"]` i `base_taxes["pit"]` przed sumowaniem `total`/`baseline`.

Algorytm `estimate_state_share`: rok załamania `b = STRUCTURAL_BREAKS.get("rev_pit")`; bez `b`, bez modułu PIT w `ctx.enabled` lub bez `rev_pit[b]` w historii → `StateShare(1.0, b, "none", ...)`. Moduł roku `b`: gdy w historii są `wage_nominal` i `employment` za `b` → `ctx.calib["pit"] × _pit(wage·emp, ctx.dist, law)` (`source="data"`); w przeciwnym razie, gdy `b ∈ years` → mediana `pit_base[:, years.index(b)]` (`source="forecast"`); inaczej `none`. `s₀ = rev_b / moduł`; niefinitowe lub ≤ 0 → `none`. Czynnik na ścieżce i roku: `1` dla lat < `b`, inaczej `s₀·m·ε` (baza używa `m = 1`, scenariusz `m` z parametrów); `ε = exp(σ·z)`, `z ~ N(0,1)` o kształcie `(n_paths, 1)` z `np.random.default_rng([seed, 7])` dla `seed` ≠ None, a `np.random.default_rng()` dla None; `ε = 1`, gdy `source == "none"`.

- [ ] **Step 1: Testy** (na `tests.real_dataset`/`assemble(real_results())` i syntetycznej historii): `test_s0_from_recorded_data_is_about_0_23` (tolerancja 0,03; `source` w {"data","forecast"}); `test_pit_2025_median_close_to_realised` (mediana PIT 2025 mieści się w paśmie p10–p90 i w ±15% wykonania 28,75); `test_multiplier_scales_pit_from_break_only` (m=2 → PIT 2025+ ≈ 2× mediany m=1, tolerancja 2%; lata < 2025 jeśli występują – bez zmian; VAT/CIT bez zmian); `test_identical_params_give_zero_difference` (`res.taxes["pit"]["median"]` równe baseline przy `params={}`); `test_epsilon_widens_pit_bands` (szerokość p10–p90 PIT > szerokość z `σ=0` przez monkeypatch configu); `test_missing_rev_2025_falls_back_to_old_rules` (historia bez roku 2025: `s0 == 1`, wiersz `PIT_STATE_SHARE` status `assumption` z „sprzed 2025”, brak wyjątku, `ε` wyłączony – pasma jak przed zmianą); `test_seed_none_runs` i `test_seed_zero_is_deterministic`; `test_state_share_row_has_year_range_and_note` (rok 2025, `low < value < high`, notka zawiera „jednego roku”); `test_data_source_when_model_year_is_2025` (historia z makro za 2025 → `source == "data"`).
- [ ] **Step 2: Uruchom** testy z kroku 1 – FAIL.
- [ ] **Step 3: Implementacja** w `simulate.py` zgodnie z Interfaces; kanały sprzężenia bez zmian (czynnik po `_scenario`); `PIT_STATE_SHARE` dołączone do listy założeń przed ujednoliceniem kształtu wierszy.
- [ ] **Step 4: Uruchom** pełny backend (+ `-W error::ResourceWarning`) – PASS; zregeneruj fixture frontendu.
- [ ] **Step 5: Commit** `feat: state-budget PIT share (calibrated on 2025, user multiplier, Monte Carlo spread)`.

### Task 3: Backtest, notki i eksport

**Files:**
- Modify: `backend/app/model/simulate.py` (`BREAK_NOTES`, notka `STRUCTURAL_BREAKS`), `backend/app/model/backtest.py` (notka), `backend/app/api/export.py` (metadane)
- Test: `backend/tests/test_backtest_export.py`, `backend/tests/test_export_provenance.py`, `backend/tests/test_simulate.py`

**Interfaces:**
- Consumes: wiersz `PIT_STATE_SHARE` z T2.
- Produces: `BREAK_NOTES["rev_pit"]` – „PIT w budżecie państwa: zmiana zasad podziału od 2025 r. (reforma finansowania JST); prognoza uwzględnia udział budżetu państwa po reformie, oszacowany z jednego roku (2025); wykonanie 2025 służy do kalibracji udziału, nie do oceny backtestu.”; eksport: wiersz Metadane `pit_udzial_budzetu` = „<s₀ z 3 miejscami>; mnożnik <m>; efektywny <s₀·m>; <rok>” (przez `safe()`).

- [ ] **Step 1: Testy:** `test_backtest_does_not_score_or_train_on_2025_pit` (cele PIT ≥ 2025 pominięte, `train` obcięty przed 2025 → `s0 == 1` w symulacjach backtestu); `test_backtest_note_mentions_share`; `test_export_contains_pit_share_metadata` (CSV i XLSX; wartość nie zaczyna się od `=+-@`); `test_export_without_share_row_still_works` (stary `result` bez `PIT_STATE_SHARE`).
- [ ] **Step 2: Uruchom** – FAIL.
- [ ] **Step 3: Implementacja** (teksty, wiersz eksportu z walidacją typów i długości jak dla pozostałych pól).
- [ ] **Step 4: Uruchom** pełny backend – PASS; zregeneruj fixture.
- [ ] **Step 5: Commit** `feat: break notes, backtest and export carry the PIT share`.

### Task 4: Interfejs (suwak, wykres, Jakość, e2e)

**Files:**
- Modify: `frontend/src/charts/data.ts` (`breakNote`), `frontend/src/components/QualityTab.tsx` (jeśli potrzebne dla wiersza), `frontend/src/components/ParameterPanel.tsx` (jednostka `mnożnik`), `e2e/budget.spec.ts`
- Test: `frontend/src/charts/charts.test.tsx`, `frontend/src/components/ParameterPanel.test.tsx`, `frontend/src/components/QualityTab.test.tsx`

**Interfaces:**
- Consumes: parametr `pit_state_share_mult` ze schematu (`unit: "mnożnik"`), wiersz `PIT_STATE_SHARE`, nowy `BREAK_NOTES`.
- Produces: `breakNote("pit", year)` = „Od {year} r. budżet państwa zatrzymuje znacznie mniejszą część PIT (reforma finansowania JST); prognoza uwzględnia udział budżetu państwa po reformie, oszacowany z jednego roku ({year}).”

- [ ] **Step 1: Testy:** `charts.test.tsx`: nowy tekst `breakNote`; `ParameterPanel.test.tsx`: suwak „PIT - udział budżetu państwa (mnożnik względem 2025)” renderuje jednostkę „mnożnik”, wartość 1, zakres 0,5–2, zmiana na 1,5 wywołuje `onChange` z 1.5 (bez przeliczania na %); `QualityTab.test.tsx`: wiersz `PIT_STATE_SHARE` pokazuje badge „kalibracja”, rok i uwagę z „jednego roku”; e2e: po zmianie suwaka na 1,5 metryka „Zmiana vs baza” dla PIT jest dodatnia, a wykres PIT zawiera notę o udziale (seed syntetyczny: mnożnik działa, ostrzeżenie o braku danych w zakładce Jakość).
- [ ] **Step 2: Uruchom** `cd frontend && npx vitest run` – FAIL.
- [ ] **Step 3: Implementacja** (jednostka nie-ułamkowa już obsługiwana ogólnie – zweryfikuj formatowanie; `breakNote`; ewentualnie opis w panelu).
- [ ] **Step 4: Uruchom** `npx vitest run && npx tsc --noEmit && npm run build` oraz `cd e2e && npm test` – PASS.
- [ ] **Step 5: Commit** `feat: PIT share slider, chart note and quality row`.

### Task 5: Rejestr, README i raport przed→po

**Files:**
- Modify: `docs/model-parameters.md`, `README.md`, `docs/data-sources-discovery.md` (jedno zdanie o nowym podejściu do PIT 2025)
- Test: `backend/tests/test_param_registry_doc.py`

**Interfaces:** Consumes: wszystko z T1–T4.

- [ ] **Step 1: Test** `test_registry_documents_the_pit_share_decision`: rejestr zawiera sekcję „Udział budżetu państwa w PIT” z `s₀`, `m`, `σ` i ograniczeniem „jeden rok”.
- [ ] **Step 2: Uruchom** – FAIL.
- [ ] **Step 3: Dokumentacja:** sekcja w rejestrze (definicja, `s₀ ≈ 0,23` z nagranych danych, tabela „mediana PIT 2025–2029 przed → po” policzona na `tests/real_dataset.py` z seedem 20261010 i 2000 ścieżek; szerokość pasma p10–p90 przed → po; zastrzeżenie, że `s₀` zawiera błąd prognozy 2025); README: zdanie o parametrze i aktualna lista otwartych kwestii (usuń „prognoza PIT po 2025 liczy według starych zasad”).
- [ ] **Step 4: Pełna weryfikacja:** backend (`-W error::ResourceWarning`), frontend, e2e; testy live pominięte bez `RUN_LIVE=1`; zaktualizuj migawkę `demo/real-data.db` tylko jeśli kontrakt bazy się zmienił (nie powinien).
- [ ] **Step 5: Commit** i `git push -u origin claude/pit-state-share`.

---

## Self-review

- **Pokrycie specyfikacji:** §2 model → T1, T2; §2 backtest → T3; §3 UI/eksport/rejestr → T3, T4, T5; §5 testy → w każdym zadaniu; §7 kryteria → T5.
- **Spójność nazw:** `pit_state_share_mult`, `PIT_STATE_SHARE`, `PIT_STATE_SHARE_SIGMA`, `StateShare`, `estimate_state_share`, `BREAK_NOTES["rev_pit"]`, `breakNote` użyte jednolicie.
- **Proporcja:** plan opisuje decyzje i testy; algorytm podany tylko tam, gdzie sygnatury go nie determinują.
- **Rozstrzygnięcie przy niejasności:** `ε` tylko gdy `s₀` oszacowano z danych (bez jednego punktu kalibracyjnego nie ma czego rozpraszać); `m` działa zawsze dla lat ≥ rok załamania.
