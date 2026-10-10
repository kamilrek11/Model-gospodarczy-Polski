# Symulator wpływów do budżetu państwa Polski – specyfikacja projektu

Data: 2026-10-10 · Status: do przeglądu przez użytkownika

## 1. Cel i odbiorcy
Aplikacja webowa dla ekspertów/analityków, która na podstawie bieżących i historycznych wskaźników prognozuje wpływy do
budżetu państwa. Użytkownik steruje parametrami podatkowymi (PIT, CIT, VAT itd.) i widzi skutek na wykresach:
(1) prognoza vs. wykonanie, (2) cały budżet z podziałem na rodzaje wpływów. Priorytet: wierność modelu i jawność założeń.

## 2. Zakres
**Docelowo:** PIT, CIT, VAT, akcyzy i podatek od gier, składki ZUS/NFZ/FUS, wpływy pozostałe i niepodatkowe.

**Etapy:**
- **v1:** PIT, CIT, VAT + blok makro + pełny przepływ (dane, model, UI, scenariusze, eksport).
- **v2:** akcyzy/gry, składki, pozostałe i niepodatkowe; ulgi PIT, przesuwanie towarów między stawkami VAT, estoński CIT
  (zależnie od dostępności danych mikro).

**Parametry regulowane (docelowo):**
- PIT: stawki skali (12%/32%) i próg, kwota wolna/zmniejszająca, podatek liniowy 19% i ryczałt, ulgi (rodzinna, IKZE, B+R).
- VAT: stawki 23/8/5/0%, przesuwanie towarów między stawkami.
- CIT: stawki 19%/9% (mali podatnicy), estoński CIT.

## 3. Decyzje
| Obszar | Decyzja |
|---|---|
| Dane | GUS BDL (makro) + MF/ZUS/Eurostat (wykonanie budżetu); odświeżanie na żądanie (przycisk) |
| Horyzont | Roczny, 1–5 lat |
| Model | Dynamiczny, uproszczony model makro zredukowany (VAR/ECM) + moduły podatkowe, efekty drugiej rundy |
| Niepewność | Pasma 80% i 95% z symulacji Monte Carlo |
| Stos | Python (FastAPI, pandas, statsmodels, numpy) + React/TypeScript |
| Architektura | Estymacja offline po „Odśwież dane", symulacja Monte Carlo w API na żywo (debounce 300 ms) |
| Scenariusze | Zapis i porównanie obok siebie; localStorage + eksport/import JSON; bez kont |
| Eksport | Dane CSV/XLSX, wykresy PNG/PDF |
| UI | Polski, motyw jasny i ciemny, panel parametrów po lewej, wykresy po prawej |
| Hosting | Nieokreślony → kontenery (Docker), przenośne |

## 4. Architektura i warstwa danych
```
frontend/ (React+TS)   UI, wykresy, scenariusze w localStorage
backend/api/           FastAPI: /parameters /simulate /history /refresh /backtest /export
backend/data/          klienci źródeł: gus_bdl, mf, zus, eurostat
backend/model/         makro (VAR/ECM), taxes/{pit,cit,vat}, simulate (Monte Carlo)
backend/store/         SQLite: serie czasowe, współczynniki modelu, metadane odświeżenia
```
Przepływ:
1. `POST /refresh` uruchamia zadanie w tle: pobranie serii (GUS: PKB, zatrudnienie, płace, CPI, konsumpcja; MF/ZUS/Eurostat:
   wykonanie budżetu), zapis z datą i źródłem, estymacja bloku makro i zapis współczynników oraz reszt. Częściowy
   sukces nie nadpisuje ostatniego dobrego stanu.
2. `POST /simulate` wczytuje zapisane współczynniki i liczy ścieżki Monte Carlo (numpy, wektorowo).
3. `/export` generuje CSV/XLSX; wykresy PNG/PDF powstają w przeglądarce.

Błędy: niedostępne źródło → praca na ostatnim zestawie z widoczną datą. Brak danych dla modułu → moduł wyłączony z
komunikatem, bez zmyślonych wartości.

Testy: klienci źródeł na nagranych odpowiedziach (fixtures), testy jednostkowe modułów podatkowych na znanych liczbach,
backtest modelu.

## 5. Silnik ekonomiczny
**Blok makro (VAR/ECM, dane roczne):** realny PKB, zatrudnienie, przeciętne wynagrodzenie nominalne, CPI, konsumpcja
prywatna nominalna. Mała próba → 1–2 opóźnienia, ewentualnie ECM; zmienne zewnętrzne jako egzogeniczne ścieżki bazowe.
Przedziały będą szerokie i aplikacja pokazuje to wprost.

**Moduły podatkowe:**
- VAT: baza ≈ konsumpcja nominalna wg udziałów stawek × stawka × (1 − luka VAT); zmiana stawki przez elastyczność cenową
  popytu wraca do konsumpcji (druga runda).
- CIT: baza ≈ nadwyżka operacyjna brutto × udział płatników CIT; stawki 19%/9%; osobna ścieżka estońskiego CIT (v2).
- PIT: baza ≈ fundusz wynagrodzeń i dochody z działalności; skala, próg, kwota wolna, liniowy 19%, ryczałt. Zmiany
  progów wymagają rozkładu dochodów z danych MF o strukturze podatników.
- Efekty drugiej rundy: podatek → dochód/ceny → konsumpcja i zatrudnienie → baza → wpływy, domknięte w jednym kroku symulacji.

**Kalibracja i walidacja:** współczynnik kalibracyjny per moduł odtwarza wykonanie z ostatnich lat i jest jawnie
pokazany jako założenie. Backtest rolling-origin (estymacja do T, prognoza T+1..T+3; MAPE, pokrycie przedziałów).
Elastyczności z literatury w jednym pliku konfiguracji z cytowanym źródłem, możliwe do nadpisania w UI.

**Ryzyko:** ulgi PIT, przesuwanie towarów między stawkami VAT i estoński CIT wymagają danych mikro; bez nich moduł
pokazuje niepewność albo jest wyłączony.

## 6. API
- `GET /parameters` – schemat parametrów (domyślne = obecne prawo, zakresy, jednostki, opisy); UI generuje z niego formularz.
- `POST /simulate` – parametry → ścieżki per podatek (mediana, pasma 80/95%, 1–5 lat), baza, suma, wskaźniki makro,
  `model_version`, data danych.
- `GET /history` – wykonanie historyczne per rodzaj wpływu.
- `POST /refresh`, `GET /refresh/status` – odświeżenie w tle z postępem i błędami źródeł.
- `GET /backtest` – metryki jakości.
- `POST /export` – CSV/XLSX wyników i parametrów scenariusza.

## 7. Interfejs
- Układ: panel parametrów (lewo) + wykresy (prawo). Pasek górny: nazwa scenariusza, motyw, „Odśwież dane" z datą
  aktualizacji, eksport.
- Parametry: sekcje zwijane per podatek, pole liczbowe + suwak, jednostka, wartość bazowa, znacznik odchylenia od
  obecnego prawa, „Przywróć", opisy w tooltipach.
- Wykres 1: linie wykonania (ciągła) i prognozy (przerywana) z pasmami 80/95%, wybór podatku, zmiana względem bazy
  (mld zł i %).
- Wykres 2: słupki skumulowane po latach wg rodzajów wpływów, klikalna legenda.
- Scenariusze: zapis nazwany (localStorage), eksport/import JSON, widok porównania obok siebie i tabela różnic.
- Zakładka „Jakość modelu": backtest, lista założeń i elastyczności.
- Stany: szkielet ładowania, baner błędu źródła z datą ostatniego dobrego zestawu, moduł wyłączony z uzasadnieniem.
- Dostępność: paleta odporna na daltonizm, tabela danych jako alternatywa, obsługa klawiatury; język polski.
- Wydajność: debounce 300 ms, anulowanie starszych żądań (AbortController), cache klienta.

## 8. Otwarte kwestie
- Dostępność i warunki API: BDL (GUS), MF, ZUS, Eurostat. Sieć środowiska deweloperskiego blokowała `bdl.stat.gov.pl`;
  wymagane dodanie hostów do dozwolonych domen, zanim sprawdzimy realne serie.
- Dokładna definicja „budżet państwa" vs sektor finansów publicznych (wpływ na składki ZUS/NFZ/FUS).
- Okres kalibracji, finalny zestaw zmiennych makro i elastyczności (do ustalenia z analitykiem ekonomicznym po
  weryfikacji danych).
- Docelowy hosting (projektujemy kontenerowo).
