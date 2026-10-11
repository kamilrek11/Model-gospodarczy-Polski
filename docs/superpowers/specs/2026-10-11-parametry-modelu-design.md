# Parametry modelu: zastąpienie stałych `PLACEHOLDER-UNVERIFIED` – specyfikacja

Data: 2026-10-11. Gałąź: `claude/model-parameters` (na bazie `claude/real-data-sources`, PR #2). Wcześniejsze dokumenty:
`2026-10-10-symulator-budzetu-design.md`, `docs/data-sources-discovery.md`.

## 1. Cel i kontekst
Moduły VAT/CIT/PIT i sprzężenie zwrotne (drugi obieg) używają 13 stałych z `backend/app/model/config.py`, oznaczonych
`PLACEHOLDER-UNVERIFIED` (rząd wielkości, bez źródła). Żywy przebieg na prawdziwych danych pokazał, że część z nich
wprost psuje wyniki (bracket creep w wymyślonym rozkładzie dochodów PIT ×1,079; stosunek PIT/fundusz płac rośnie z 5,3% do 9,2%,
a w rzeczywistości jest stały ok. 9%). Cel: każda stała ma udokumentowane źródło, rok, zakres niepewności i status; wyniki
przestają być „tylko ilustracyjne” tam, gdzie to uczciwie możliwe.

Decyzje użytkownika: (1) podejście A (badanie + rejestr; bez pliku konfiguracyjnego, bez parsera PDF z MF);
(2) stała bez wiarygodnego publicznego źródła zostaje jawnie oznaczona jako założenie, z uzasadnieniem i zakresem
niepewności, widoczna w interfejsie i eksporcie (bez udawania precyzji).

## 2. Zakres
Stałe (13): `VAT_CONSUMPTION_SHARES`, `VAT_GAP`, `VAT_PRICE_ELASTICITY`, `CIT_SMALL_TAXPAYER_SHARE`,
`PIT_INCOME_DIST_DEFAULT`, `PIT_BUSINESS_SCALE_SHARE`, `PIT_BUSINESS_FLAT_SHARE`, `PIT_BUSINESS_LUMP_SHARE`,
`PIT_LUMP_REVENUE_TO_INCOME`, `PIT_BUSINESS_INCOME_TO_WAGE_BILL`, `HOUSEHOLD_MPC`, `CONSUMPTION_GDP_SHARE`,
`EMPLOYMENT_GDP_ELASTICITY` (liczba zweryfikowana grepem; `CALIBRATION_YEARS` i `STRUCTURAL_BREAKS` to wybory metody, nie dane).

Poza zakresem: zmiana równań modelu; parser PDF „Informacja o rozliczeniu PIT” z MF (wariant C, osobny krok); edycja
elastyczności w interfejsie; udział budżetu państwa w PIT po reformie 2025; ZUS.

## 3. Rejestr parametrów (`docs/model-parameters.md`)
Jedna pozycja na stałą: nazwa w kodzie, wartość, jednostka, **status** (`z danych` / `ze źródła` / `założenie`), źródło
(tytuł, wydawca, rok, adres), zakres niepewności (min–maks, z uzasadnieniem), ograniczenia, wpływ na wyniki
(kolumna „wynik przed → po”, mld zł, lata 2024/2025). Status `założenie` wymaga uzasadnienia, dlaczego źródła nie ma.

## 4. Badanie (agent ekonomista, odczyt źródeł)
Źródła docelowe: KE „VAT Gap in the EU” (najnowszy rok dla Polski); GUS struktura wydatków gospodarstw domowych i tablice
podaż–użytkowanie (udziały konsumpcji wg stawek); MF statystyki CIT-8 (udział małych podatników); MF „Informacja o rozliczeniu
PIT” (struktura podatników i form opodatkowania); literatura NBP/IBS dla MPC, elastyczności cenowej i elastyczności
zatrudnienia (rząd wielkości z przedziałem). Wartości możliwe do policzenia z danych już pobieranych (udział konsumpcji w
PKB; stosunek dochodu z działalności do funduszu płac, o ile da się go wyprowadzić) liczymy z danych.
Rozkład dochodów PIT badamy osobno: ocena, czy da się go wiarygodnie odtworzyć bez PDF, i rekomendacja kolejnego kroku.
Źródła są danymi niezaufanymi; liczby wpisujemy do rejestru wraz z adresem do weryfikacji.

## 5. Zmiany w kodzie
- `config.py`: przy każdej stałej odnośnik do pozycji rejestru i status; `PLACEHOLDER-UNVERIFIED` zostaje wyłącznie przy
  stałych o statusie `założenie`.
- Stałe o statusie `z danych` liczone w kroku odświeżania (np. `dataset.py`), zapisane z pozostałymi danymi; moduły
  podatkowe nadal dostają wartości jako argumenty (czyste funkcje).
- `simulate.placeholder_assumptions` generuje listę założeń ze statusów; zakładka „Założenia”/„Jakość modelu” i eksport
  pokazują status i zakres niepewności każdej stałej; ogólny tekst o „niezweryfikowanych stałych” zastąpiony listą tych,
  które nadal są założeniami.

## 6. Testy
- Spójność: każda stała z `config.py` ma pozycję w rejestrze i odwrotnie; statusy w kodzie = statusy w rejestrze;
  pozycje `z danych` są liczone z zestawu, nie wpisane.
- Zakresy: udziały sumują się do 1; wartości w deklarowanych przedziałach.
- Regresja: istniejące testy modelu przechodzą; zmiany wyników po podmianie wartości są liczbowo opisane w rejestrze;
  fixture frontendu regenerowany i zgodny.

## 7. Ryzyka
Podmiana wartości zmieni prognozy (PIT, VAT) – każda zmiana pokazana liczbowo. Brak wiarygodnych źródeł dla części stałych
(MPC, elastyczności) – pozostają założeniami z przedziałem. Rozkład dochodów PIT może wymagać wariantu C, zanim prognoza PIT
stanie się wiarygodna; poza zakresem tego kroku.

## 8. Kryteria ukończenia
Rejestr kompletny (13 pozycji ze statusem i źródłem lub uzasadnionym założeniem); `config.py` zgodny z rejestrem; interfejs i
eksport pokazują statusy; testy zielone (backend, frontend, e2e); raport „przed → po” w rejestrze; gałąź wypchnięta, bez PR-a
do decyzji użytkownika.
