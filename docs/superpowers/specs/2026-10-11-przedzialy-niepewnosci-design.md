# Szersze przedziały niepewności – specyfikacja

Data: 2026-10-11. Gałąź: `claude/wider-bands` (na bazie `claude/pit-state-share`, PR #4). Wcześniejsze dokumenty:
`2026-10-10-symulator-budzetu-design.md`, `2026-10-11-parametry-modelu-design.md`, `2026-10-11-udzial-pit-design.md`,
`docs/model-parameters.md`.

## 1. Cel i kontekst
Backtest na prawdziwych danych pokazuje, że pasma są za wąskie: pokrycie przedziału 80% wynosi 21% (VAT), 7% (CIT), 25% (PIT)
przy MAPE 10% / 28% / 14%. Przyczyna: pasma biorą się wyłącznie z bootstrapu reszt VAR (`simulate_levels` w
`backend/app/model/simulate.py`); moduły podatkowe są deterministyczne, współczynnik kalibracji (średnia z `CALIBRATION_YEARS` = 3
lat) jest traktowany jako pewny, parametry VAR również. Cel: pasma, które uczciwie pokrywają zbliżoną do deklarowanej część
realizacji (pokrycie 80% w backteście w granicach ok. 0,65–0,95), przy **niezmienionych medianach**, z jawnym opisem
ograniczeń (mała próba: do ok. 5 punktów startowych, horyzont 3 lata, 10 lat przychodów).

Decyzja użytkownika: podejście **C** – najpierw źródła niepewności z modelu (A), potem korekta szerokości z backtestu (B) tylko
tam, gdzie A nie wystarcza.

## 2. Model

### 2.1 Niepewność kalibracji (A1)
Dla każdego włączonego podatku na ścieżkę losowany czynnik `exp(σ_cal·z)`, `z ~ N(0,1)`, mediana 1, stały dla całego horyzontu
(błąd poziomu jest trwały), nakładany na raportowany podatek po `_scenario` (podobnie jak udział PIT). `σ_cal` = odchylenie
standardowe `log(rev / moduł)` po latach okna kalibracji (te same lata, co współczynnik kalibracji), ograniczone do
`[CALIBRATION_SIGMA_FLOOR, CALIBRATION_SIGMA_CAP]` = `[0,03; 0,35]` (stałe `config`, status `założenie`: trzy obserwacje nie mogą
dać ani zerowego, ani absurdalnego rozrzutu). Wspólne liczby losowe: ten sam czynnik w bazie i scenariuszu; osobny generator
(`np.random.default_rng([seed, 11])`, dla `seed=None` – `default_rng()`).

### 2.2 Niepewność parametrów VAR (A2)
`MacroModel` zapisuje macierz kowariancji współczynników (`cov_params` z `statsmodels`, nowe opcjonalne pole `coef_cov`
w `to_dict`/`from_dict`); `model_version` się zmienia, więc stare zapisane modele działają jak dotąd (bez A2), a po aktualizacji
kodu odświeżenie danych dopisuje pole. Na ścieżkę losowane jest zaburzenie współczynników z `N(0, coef_cov)` (osobny generator
`default_rng([seed, 13])`); ścieżki, dla których macierz towarzysząca ma promień spektralny ≥ 1, wracają do współczynników
bazowych. Zaburzenie jest symetryczne, więc mediany zostają zbliżone (test: dryf ≤ 2%).

### 2.3 Korekta z backtestu (B)
Po A backtest liczy dla każdego podatku mnożnik `k ∈ [1, BAND_SCALE_MAX]` (`BAND_SCALE_MAX = 3`, stała `config`, `założenie`)
skalujący odchylenia kwantyli raportowanych pasm (p10/p90 oraz p2,5/p97,5) od mediany w przestrzeni logarytmów tak, aby empiryczne
pokrycie 80% w backteście zbliżyło się do 80% (najmniejsze `k` na siatce o kroku 0,05, dające pokrycie ≥ 0,8, w granicach `K`).
Wymagane minimum ocenionych par (origin, horyzont): `BAND_SCALE_MIN_PAIRS = 8`; poniżej `k = 1` i nota „za mało danych do
korekty”. `k` liczone jest przy odświeżaniu danych (backtest trwa kilka sekund) i zapisywane w bazie (`meta.band_scale`, JSON
`{podatek: k}`, w tej samej transakcji co dane); `simulate` stosuje `k` do pasm, a wiersz założeń `band_scale.<podatek>`
(status `calibrated`) pokazuje wartość. Jeden `k` na podatek (bez rozbicia na horyzonty) – ogranicza przeuczenie na małej próbie.
Backtest pokazuje oba pokrycia: bez korekty i po korekcie, z notą „po korekcie – dopasowane do historii, wartość orientacyjna”.
Backtest wewnętrznie liczy symulacje z A (bez B), żeby korekta nie wpływała na własny pomiar.

## 3. Interfejs, eksport, dokumentacja
- Zakładka Jakość: tabela backtestu z pokryciem przed/po korekcie (Polskie etykiety), wiersze założeń `band_scale.<podatek>`
  (status `kalibracja`); nowe stałe `CALIBRATION_SIGMA_FLOOR`, `CALIBRATION_SIGMA_CAP`, `BAND_SCALE_MAX`,
  `BAND_SCALE_MIN_PAIRS` w rejestrze (`param_meta`, `docs/model-parameters.md`, status `założenie`, uzasadnienie i zakres).
- Wykresy bez zmian poza szerszymi pasmami; opis pasm na wykresie nie obiecuje deklarowanego pokrycia, tylko „przedział
  prognozy (p10–p90), po korekcie z backtestu” gdy `k > 1`.
- Eksport (metadane): `k` per podatek i informacja, czy A2 był aktywny.
- Rejestr i README: sekcja „Niepewność prognoz” z tabelą pokrycia przed → po (A, A+B), jawnym ograniczeniem małej próby i
  informacją, że B jest dopasowaniem do historii.

## 4. Poza zakresem
Zmiana median i równań; niepewność prawa (stawki) i parametrów użytkownika; osobne `k` per horyzont; modele zmiennej wariancji;
niepewność udziału PIT (już w `ε`); automatyczne ponowne liczenie `k` poza odświeżaniem danych.

## 5. Testy
(a) mediany po zmianie ≈ przed (≤ 2% dla VAT/CIT/PIT, lata 1–5) na nagranych danych; (b) pasma p10–p90 szersze niż przed dla
każdego podatku; (c) wspólne liczby losowe: scenariusz o identycznych parametrach daje zerową różnicę median; (d) determinizm
przy ustalonym ziarnie, działanie przy `seed=None`; (e) stary model bez `coef_cov` działa (bez A2), nowy model serializuje się
i wczytuje; (f) pokrycie 80% w backteście po A rośnie względem 21% / 7% / 25% i po A+B mieści się w 0,65–0,95 tam, gdzie
`k` jest policzone; przy za małej próbie `k = 1` z notą; (g) `k` zapisane atomowo z danymi, brak `k` w bazie = `k = 1`;
(h) czas symulacji mieści się w budżecie istniejącego testu wydajności; (i) rejestr/UI/eksport/e2e; (j) backtest nie używa
wyników B do własnej oceny.

## 6. Ryzyka
Mała próba: korekta B jest częściowo dopasowaniem do historii i nie gwarantuje pokrycia poza próbą (opisane wprost). Zmiana formatu
zapisanego modelu wymaga odświeżenia danych (stare modele nadal działają). Szersze pasma mogą wyglądać „mniej imponująco” – to
zamierzone. Dryf median w A2 przy mocno skorelowanych współczynnikach – pilnowany testem (a).

## 7. Kryteria ukończenia
Pasma uwzględniają niepewność kalibracji i parametrów VAR; korekta `k` liczona przy odświeżeniu, zapisywana i stosowana; backtest
raportuje pokrycie przed/po; mediany bez zmian (≤ 2%); rejestr, UI, eksport i README zaktualizowane; testy zielone (backend,
frontend, e2e); gałąź wypchnięta, bez PR-a do decyzji użytkownika.
