# Udział budżetu państwa w PIT po reformie 2025 – specyfikacja

Data: 2026-10-11. Gałąź: `claude/pit-state-share` (na bazie `claude/model-parameters`, PR #3). Wcześniejsze dokumenty:
`2026-10-10-symulator-budzetu-design.md`, `2026-10-11-parametry-modelu-design.md`, `docs/model-parameters.md`,
`docs/data-sources-discovery.md` (analiza PIT).

## 1. Cel i kontekst
Od 2025 r. budżet państwa zatrzymuje znacznie mniejszą część PIT (reforma finansowania samorządów): wykonanie 2024 = 97,6 mld zł,
2025 = 28,75 mld zł (MF). Model liczy PIT dalej według zasad sprzed reformy, więc prognoza 2025 (ok. 124 mld zł na danych z żywego
przebiegu) jest nieporównywalna z wykonaniem, a wykres pokazuje sztuczny „skok w dół i w górę”. Dziś kalibracja i backtest po prostu
kończą się na 2024 (`config.STRUCTURAL_BREAKS["rev_pit"] = 2025`). Cel: prognoza PIT w budżecie państwa od 2025 r. jest
porównywalna z wykonaniem, z jawnie opisanym i edytowalnym założeniem o udziale budżetu państwa.

Decyzje użytkownika: (1) podejście A – udział jako parametr; (2) udział stały, edytowalny w panelu, z dodatkowym rozrzutem w
symulacji Monte Carlo (uczciwa niepewność jednego punktu kalibracyjnego).

## 2. Model
- PIT w budżecie państwa dla lat ≥ rok załamania (2025) = PIT liczony według obecnego prawa (z kalibracją sprzed reformy) × `s`.
  Lata wcześniejsze: bez zmian (`s = 1`).
- `s = s₀ × m × ε`:
  - `s₀` – bazowy udział, kalibrowany na pierwszym roku po załamaniu: wykonanie `rev_pit` w tym roku ÷ mediana prognozy PIT dla tego
    roku według starych zasad przy parametrach domyślnych (na nagranych danych ≈ 0,23). Przeliczany przy każdej symulacji z
    zapisanych danych (bez nowego pola w bazie).
  - `m` – nowy parametr użytkownika `pit_state_share_mult`: „Udział budżetu państwa w PIT – mnożnik względem 2025” (1 = bez zmian
    względem 2025), zakres 0,5–2, wartość bazowa 1, grupa PIT. Schemat parametrów pozostaje statyczny; efektywny udział `s₀ × m` jest
    pokazany w opisie parametru i w założeniach.
  - `ε` – losowy czynnik na ścieżkę Monte Carlo, lognormalny z odchyleniem logarytmu `σ = 0,2` i medianą 1, stała `PIT_STATE_SHARE_SIGMA`
    w `config.py` (status `założenie`, zakres uzasadniony w rejestrze). Ten sam `ε` dla bazy i scenariusza na danej ścieżce
    (wspólne liczby losowe), więc różnice scenariuszy wynikają z parametrów.
- Brak danych `rev_pit` za rok załamania (lub ≥ 2 lata po załamaniu): `s₀ = 1`, ostrzeżenie w założeniach „PIT liczony według zasad
  sprzed 2025 r.”. Gdy dostępnych jest więcej lat po załamaniu, `s₀` liczone jest z pierwszego roku (ograniczenie opisane w rejestrze;
  rozszerzenie na średnią z kilku lat poza zakresem).
- Backtest: lata ≥ 2025 nadal nie są oceniane (brak wycieku wiedzy o udziale); notka backtestu zaktualizowana.

## 3. Dane, UI, eksport
- Wykres PIT: wykonanie 2025 (28,75) i prognoza od 2026 na jednej skali; nota „zmiana zasad 2025” ma nowy tekst („prognoza uwzględnia
  udział budżetu państwa po reformie, oszacowany z jednego roku – 2025”).
- Panel PIT: suwak `pit_state_share_mult` z opisem „oszacowane z jednego roku (2025)”.
- Zakładka Jakość: wiersz `PIT_STATE_SHARE` (status `kalibracja`, wartość `s₀`, rok 2025, zakres z rozrzutu `σ`) oraz wiersz
  `PIT_STATE_SHARE_SIGMA` (status `założenie`); rejestr `docs/model-parameters.md` i `param_meta` zaktualizowane: rejestr ma
  teraz 14 stałych (dodana `PIT_STATE_SHARE_SIGMA`); `s₀` to wartość wyliczana (jak `CONSUMPTION_GDP_SHARE`), nie stała konfiguracyjna.
- Eksport (CSV/XLSX Metadane): `s₀` i `m` oraz efektywny udział.

## 4. Poza zakresem
Modelowanie przepisów o podziale PIT między poziomy władz; dane o PIT ogółem (wariant C); kalibracja `s₀` z wielu lat po załamaniu;
zmiana skali/ulg PIT.

## 5. Testy
- `s₀` na nagranych danych ≈ 0,23 (tolerancja 0,03); prognoza PIT 2025 z udziałem mieści się w paśmie 80% względem wykonania 2025.
- `m = 2` podwaja medianę PIT od 2025 (tolerancja MC); lata < 2025 bez zmian.
- Brak `rev_pit` za 2025: `s₀ = 1` i jawny komunikat; brak błędu.
- Pasma PIT szersze z `ε` niż bez (σ = 0); baza i scenariusz dzielą `ε` (różnica scenariusza zerowa przy identycznych parametrach).
- Backtest nie używa wykonania ≥ 2025; notki zgodne.
- Rejestr: nowa stała w `config`/`param_meta`/doc spójna (testy spójności); UI: suwak, wiersz Jakość, nota wykresu; e2e.

## 6. Ryzyka
Jeden punkt kalibracyjny: `s₀` zawiera też błąd prognozy modelu dla 2025, nie tylko zmianę podziału; pokazujemy rozrzut i opisujemy
w rejestrze. Zmiana prognoz PIT po 2025 jest duża – wynik „przed → po” podany liczbowo w rejestrze.

## 7. Kryteria ukończenia
Prognoza PIT od 2025 porównywalna z wykonaniem; parametr `m` w UI; `s₀`, `σ` i ostrzeżenie widoczne w Jakości i eksporcie; rejestr i testy
zielone (backend, frontend, e2e); gałąź wypchnięta, bez PR-a do decyzji użytkownika.
