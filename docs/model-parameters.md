# Rejestr parametrów modelu

Stan: 2026-10-11 (plany `docs/superpowers/plans/2026-10-11-parametry-modelu.md` i `2026-10-11-udzial-pit.md`). Rejestr opisuje 14 stałych
z `backend/app/model/config.py`, które nie są parametrami ustawianymi przez użytkownika. Kopia maszynowa:
`backend/app/model/param_meta.py` (`PARAMETERS`); zgodność obu pilnuje `backend/tests/test_param_registry_doc.py`.
`CALIBRATION_YEARS` i `STRUCTURAL_BREAKS` to wybory metody, nie dane – poza rejestrem.

Statusy: **z danych** (`from_data`, liczone z serii w bazie; wartość w `config.py` to zapas), **ze źródła**
(`sourced`, opublikowane źródło z adresem), **założenie** (`assumption`, brak weryfikowalnego źródła – kolumna Uwagi
mówi dlaczego, Zakres podaje przedział niepewności). Źródła internetowe traktowano jako dane: każda liczba ma adres, pod
którym można ją sprawdzić (strony i tabele podane w uwagach). Rok w kolumnie źródła to rok danych.

Format komórek (sprawdzany testem `test_param_registry_doc.py`):
- **Wartość**: pierwsza liczba w komórce (przecinek dziesiętny, minus „−” lub „-”) jest dokładnie wartością z `config.py`;
  zaokrąglenie wartości wyliczonej opisujemy po niej, np. „0,40 (wyliczone 0,405, zaokr. do 0,40)”. Słownik: pary
  „klucz liczba” rozdzielone „;”. Rozkład PIT: „N grup …, od (dochód; mln) do (dochód; mln)” – liczba grup, pierwsza i
  ostatnia grupa.
- **Źródło (rok, adres)**: gdy pozycja ma rok, komórka zawiera „(RRRR, ” – rok danych i po nim adres; gdy ma adres,
  komórka zawiera ten adres. Dotyczy wszystkich statusów (także założeń wyprowadzonych z danych źródłowych).
- **Zakres**: gdy `param_meta` ma `low`/`high`, komórka zaczyna się od „low–high” (półpauza między liczbami).
- **z danych**: `source` wymienia serie z bazy, z których stała jest liczona, i regułę obliczenia; wymagany rok
  ostatniej obserwacji w formacie „(RRRR, ” i adres serii źródłowej (stała nie ma publikacji – adres wskazuje serię).

Wynik przed→po: mediana 2025 (pierwszy rok prognozy; ostatni rok danych modelu to 2024) w mld zł, na nagranych
prawdziwych danych (`backend/tests/real_dataset.py`: GUS BDL, Eurostat, MF), parametry domyślne, 2000 ścieżek,
ziarno 20261010, każda zmiana liczona osobno względem stanu „przed”.

**Baza porównania.** Nagrany zestaw MF w `tests/real_dataset.py` obejmuje tylko lata wykonania 2016, 2018, 2023, 2024 i
2025, więc okno kalibracji (3 ostatnie wspólne lata) to dla PIT 2018, 2023, 2024 (2025 wyłączony przez załamanie
strukturalne), a dla VAT i CIT 2023, 2024, 2025. Na tej bazie mediana PIT 2025 wynosi 155,50 przed i 144,87 mld zł po
Task 2. Przebieg na żywo z `docs/data-sources-discovery.md` miał komplet lat MF i okno PIT 2022–2024 (mediana PIT 2025
128,34) – to inna baza; liczb z obu przebiegów nie porównujemy ze sobą. Współczynnik kalibracji to **średnia** relacji
wykonania do wyniku modułu z trzech lat okna, a nie dokładne dopasowanie do jednego roku: stała czysto mnożnikowa
(np. `VAT_GAP`) znika w nim całkowicie, a stała zmieniająca strukturę modułu zmienia poziom w latach okna tylko
pośrednio (przez średnią) i przede wszystkim dynamikę prognozy oraz skutki scenariuszy.

## Tabela

| Klucz | Wartość | Jednostka | Status | Źródło (rok, adres) | Zakres | Uwagi | Wynik przed→po |
|---|---|---|---|---|---|---|---|
| `VAT_CONSUMPTION_SHARES` | standard 0,55; reduced1 0,15; reduced2 0,12; zero 0,18 | udział konsumpcji brutto (suma 1) | założenie | brak (patrz Uwagi) | standard 0,45–0,65; reduced1 0,10–0,20; reduced2 0,08–0,20; zero 0,10–0,25 | GUS (budżety gospodarstw domowych) i MF nie publikują podziału całej konsumpcji według stawek VAT – tylko wydatki według COICOP; przypisanie stawek do COICOP wymagałoby własnej mapy. Kontrola: KE, VAT gap 2025, tab. 10 – luka stawek obniżonych w Polsce 2023 = 18,6% dochodu idealnego (żywność 10,3 pkt). W scenariuszu bazowym wartość pochłania kalibracja VAT; ma znaczenie dla skutków zmian stawek. |  |
| `VAT_GAP` | 0,109 | część VTTL | ze źródła | Komisja Europejska, VAT gap in Europe – report 2025, tabele xlsx, tab. 205 (2024, https://taxation-customs.ec.europa.eu/document/download/b3045343-a25a-4fcf-97c8-b27c413b95ad_en?filename=VAT-GAP-2025-tables.xlsx) | 0,048–0,16 (pełne szacunki 2021–2023) | Polska: 2024 10,9% (szybki szacunek), 2023 16,0%, 2022 11,2%, 2021 4,8% (tab. 205; tab. 7: 2023 VTTL 65 452, wpływy 54 999 mln EUR). Strona raportu: https://taxation-customs.ec.europa.eu/taxation/vat/fight-against-vat-fraud/vat-gap_en. Człon (1 − luka) jest czysto mnożnikowy, więc w całości pochłania go współczynnik kalibracji VAT. | 2025: VAT 324,42→324,42; CIT 72,54→72,54; PIT 155,50→155,50 (bez zmian – kalibracja pochłania człon; skutki scenariuszy też bez zmian) |
| `VAT_PRICE_ELASTICITY` | −0,5 | elastyczność (bezwymiarowa) | założenie | brak (patrz Uwagi) | −1,0–0,0 | Nie znaleziono weryfikowalnego oszacowania dla Polski (NBP/IBS) dostępnego publicznie. Zakres ma interpretację strukturalną: 0 = wolumen bez zmian (wydatki brutto rosną o podatek), −1 = stałe wydatki nominalne brutto; −0,5 to środek przedziału. |  |
| `CIT_SMALL_TAXPAYER_SHARE` | 0,08 | udział podstawy CIT | ze źródła | MF, Informacja dotycząca rozliczenia podatku CIT za 2021 r., str. 15, dane.gov.pl zbiór 162 (2021, https://api.dane.gov.pl/media/resources/20221219/Infromacja_dotycz%C4%85ca_rozliczenia_podatku_CIT_za_2021_r..pdf) | 0,05–0,12 | Podatek należny 2021: stawka 9% 2 700 278 tys. zł (190 567 podatników), 19% 65 220 084 tys. zł → podstawy 30,0 i 343,3 mld zł → 8,0%. Podstawę przypisano jako podatek / stawka (MF nie podaje podstaw według stawek); pominięto IP Box (stawka 5%, podatek 73,7 mln zł, podstawa ok. 1,5 mld zł – z nią 8,0% bez zmian). 2019: 5,3%, 2020: 5,8% (te same tabele za 2019 i 2020) – trend rosnący, stąd górna granica. Informacje za 2022+ są tylko na podatki.gov.pl, która blokuje pobieranie automatyczne (Incapsula) – nie sprawdzone. | 2025: VAT 324,42→324,42; CIT 72,54→72,54; PIT 155,50→155,50 (bazowy bez zmian – kalibracja); scenariusz cit_rate_small 15%: CIT +2,42→+1,91 |
| `PIT_INCOME_DIST_DEFAULT` | 14 grup (dochód zł, mln podatników), od (5 000; 3,0) do (520 000; 0,15) | zł / mln podatników | założenie | brak pełnego rozkładu (patrz sekcja „Rozkład dochodów PIT”) | elastyczność efektywnej stawki skali względem bazy 0,85 (rozkład zastępczy) – 1,03 (log-normalny z momentów MF 2021) | Rozkład syntetyczny. MF publikuje tylko dwa przedziały skali (counts i średnie); dwa momenty nie wyznaczają kształtu rozkładu przy kwocie wolnej, gdzie powstaje progresja. Udział podatników powyżej progu jest zgodny z MF (7,2% vs 7,3% po indeksacji płacą). |  |
| `PIT_BUSINESS_SCALE_SHARE` | 0,14 | udział dochodu z działalności | założenie | MF, Informacja PIT za 2021 r. (str. 12 i 28) i Informacja o ryczałcie za 2021 r. (rozdz. „Przychód”), dane.gov.pl zbiory 191 i 206 (2021, https://api.dane.gov.pl/media/resources/20230102/INFORMACJA_PIT_za_2021.pdf; https://api.dane.gov.pl/media/resources/20221202/Informacja_rycza%C5%82t_za_2021.pdf) | 0,10–0,15 | Założenie pochodne z MF 2021 + założone R: składniki z MF są źródłowe, ale część ryczałtowa wymaga założonego `PIT_LUMP_REVENUE_TO_INCOME` (R = 2,0), a dane są sprzed Polskiego Ładu. Dochód z działalności 2021: skala 43,45 mld zł, liniowy (PIT-36L) 228,96 mld zł, ryczałt: przychód 89,47 mld zł / `PIT_LUMP_REVENUE_TO_INCOME` 2,0 = 44,73 mld zł; razem 317,14 → 0,137 / 0,722 / 0,141. Część ryczałtowa zależy od założenia R; zakres obejmuje R 1,5–4 i przesunięcie po Polskim Ładzie (przychód ryczałtowców z działalności 2023: 242,2 mld zł, https://api.dane.gov.pl/media/resources/20241030/INFORMACJA_RYCZA%C5%81T_ZA_2023_r.pdf). | razem z dwoma pozostałymi udziałami (0,35/0,40/0,25 → 0,14/0,72/0,14): PIT 2025 155,50→151,53 (−2,6%); PIT 2029 307,0→294,2; VAT/CIT bez zmian; scenariusz pit_flat_rate 15%: −4,44→−7,59; pit_rate_low 10%: −11,71→−10,59 |
| `PIT_BUSINESS_FLAT_SHARE` | 0,72 | udział dochodu z działalności | założenie | jak `PIT_BUSINESS_SCALE_SHARE` (2021, https://api.dane.gov.pl/media/resources/20230102/INFORMACJA_PIT_za_2021.pdf) | 0,52–0,78 | Założenie pochodne z MF 2021 + założone R (jak `PIT_BUSINESS_SCALE_SHARE`); dolna granica przy przychodzie ryczałtowców z 2023 i R = 1,5. | jak `PIT_BUSINESS_SCALE_SHARE` (zmiana łączna trzech udziałów): PIT 2025 155,50→151,53 |
| `PIT_BUSINESS_LUMP_SHARE` | 0,14 | udział dochodu z działalności | założenie | jak `PIT_BUSINESS_SCALE_SHARE` (2021, https://api.dane.gov.pl/media/resources/20230102/INFORMACJA_PIT_za_2021.pdf) | 0,07–0,37 | Założenie pochodne z MF 2021 + założone R (jak `PIT_BUSINESS_SCALE_SHARE`); 2021 to ostatni rok z kompletem danych dla trzech form; po 2022 udział ryczałtu jest wyższy (górna granica). Efektywna stawka ryczałtu 2023 = 22,10 / 275,55 = 8,0% przychodu (parametr użytkownika `pit_lump_rate_default` = 12%). | jak `PIT_BUSINESS_SCALE_SHARE` (zmiana łączna trzech udziałów): PIT 2025 155,50→151,53 |
| `PIT_LUMP_REVENUE_TO_INCOME` | 2,0 | przychód / dochód | założenie | brak (patrz Uwagi) | 1,5–4,0 | Ryczałtowcy nie wykazują kosztów, więc MF nie publikuje ich dochodu. Punkt odniesienia: u liniowców (PIT-36L 2021) przychód/dochód = 1 387,7 / 229,0 = 6,1, ale to działalności kosztochłonne; ryczałt wybierają głównie usługi o niskich kosztach. |  |
| `PIT_BUSINESS_INCOME_TO_WAGE_BILL` | 0,40 (wyliczone 0,405, zaokr. do 0,40) | dochód z działalności / masa płac modelu | założenie | MF, Informacja PIT za 2021 r. i Informacja o ryczałcie za 2021 r.; masa płac z GUS BDL (zmienna 64428 × zatrudnienie × 12) (2021, https://api.dane.gov.pl/media/resources/20230102/INFORMACJA_PIT_za_2021.pdf) | 0,37–0,55 | Założenie pochodne z MF 2021 + założone R (R = 2,0; dane sprzed Polskiego Ładu). 317,14 / 783,1 mld zł = 0,405, w `config.py` zaokrąglone do 0,40 (masa płac w definicji modelu, BDL bez małych podmiotów, z nagranych danych). Zależy od założonego R; po 2022 udział ryczałtu wzrósł (górna granica). Serii dochodu z działalności nie ma w bazie, więc nie może to być „z danych”. | PIT 2025 155,50→149,35 (−4,0%); PIT 2029 307,0→287,0; VAT/CIT bez zmian; scenariusz pit_flat_rate 15%: −4,44→−5,77 |
| `HOUSEHOLD_MPC` | 0,6 | krańcowa skłonność (bezwymiarowa) | założenie | brak (patrz Uwagi) | 0,3–0,9 | Nie znaleziono weryfikowalnego oszacowania MPC z dochodu rozporządzalnego dla Polski: dostępne prace dotyczą MPC względem PKB (Ossowski 2019, REME 2(29)) lub z majątku. Zakres od wygładzania konsumpcji do gospodarstw z ograniczeniami płynności. |  |
| `CONSUMPTION_GDP_SHARE` | 0,57 (zapas); z danych 2024: 0,563 | udział w PKB | z danych | consumption_nominal (Eurostat nama_10_gdp, P31_S14, CP_MNAC) / gdp_nominal (GUS BDL 458271), ostatni wspólny rok w bazie (2024, https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/nama_10_gdp?geo=PL&na_item=P31_S14&unit=CP_MNAC) | 0,55–0,66 (2000–2024: 0,556–0,658) | Obie serie są w bazie (gdp_nominal jako seria pomocnicza bramki jednostek). Wartość jest liczona przy każdej symulacji (`simulate.resolve_constants`); brak serii lub udział poza 0,4–0,7 → zapas z `config.py` i status „założenie” w wyniku. Wartość w `config.py` nie zmieniona. | przy 0,563 zamiast 0,57: mediany 2025 przy domyślnych parametrach bez zmian (VAT 324,42, PIT 144,87, CIT 72,54 mld zł – udział wchodzi tylko przez odpowiedź PKB na scenariusz); skutki scenariuszy zmieniają się o mniej niż 0,01 mld zł |
| `EMPLOYMENT_GDP_ELASTICITY` | 0,5 | elastyczność (bezwymiarowa) | założenie | brak (patrz Uwagi) | 0,25–0,8 | Literatura dla Polski (np. Bartosik 2020, Equilibrium 15(4), https://doi.org/10.24136/eq.2020.032) szacuje wrażliwość bezrobocia, nie zatrudnienia. Kontrola na danych w bazie (MNK na różnicach logarytmów zatrudnienia i PKB realnego): 0,52 (bł. std. 0,14) w 2006–2024, 0,40 (0,11) w 2011–2024 – zgodne z 0,5. Kandydat na „z danych”, ale zatrudnienie BDL pomija małe podmioty, a oszacowanie jest niepewne. |  |
| `PIT_STATE_SHARE_SIGMA` | 0,2 | odchylenie logarytmu (bezwymiarowe) | założenie | brak (patrz Uwagi) | 0,1–0,3 | Odchylenie standardowe logarytmu losowego czynnika ε (lognormalnego, mediana 1) przy udziale budżetu państwa w PIT od 2025 r. Brak źródła: udział s₀ jest oszacowany z jednego roku (2025), więc nie ma serii, z której dałoby się policzyć jego rozrzut; 0,2 to założony rozrzut jednego punktu kalibracyjnego (przedział 0,1–0,3). Szczegóły w sekcji „Udział budżetu państwa w PIT” (s₀, m, σ, ograniczenie „jeden rok”). |  |

## Wynik łączny (wszystkie zmiany Task 2)

Mediana 2025, mld zł, nagrane dane, 2000 ścieżek, ziarno 20261010:

| podatek | przed | po | zmiana |
|---|---|---|---|
| VAT | 324,42 | 324,42 | 0,00 |
| CIT | 72,54 | 72,54 | 0,00 |
| PIT | 155,50 | 144,87 | −10,63 (−6,8%) |
| PIT 2029 | 307,00 | 272,30 | −34,70 (−11,3%) |

Skutki scenariuszy (różnica wobec bazy, 2025): VAT standard 24%: +10,95 → +10,95; CIT 9%→15%: +2,42 → +1,91;
PIT stawka niższa 10%: −11,71 → −8,66; PIT liniowy 15%: −4,44 → −9,74. Większa część dochodu z działalności
opodatkowana liniowo zmniejsza progresję skali w module (część liniowa nie ma bracket creep), stąd niższy PIT 2025–2029
i większa wrażliwość na `pit_flat_rate`.

## Rozkład dochodów PIT

**Co jest dostępne.** MF „Informacja dotycząca rozliczenia podatku dochodowego od osób fizycznych” (dane.gov.pl,
zbiór 191, tylko PDF, lata 2008–2021; za 2022+ wyłącznie podatki.gov.pl, blokowane dla pobierania automatycznego).
Za 2021 r. (https://api.dane.gov.pl/media/resources/20230102/INFORMACJA_PIT_za_2021.pdf, str. 9, 11, 17) podaje tylko
**dwa przedziały skali**: do 85 528 zł – 22 328 155 podatników, średni dochód po składkach 34 581 zł; powyżej – 1 751 454
podatników, średnio 137 913 zł; razem 24 079 609 (w tym 1 847 705 małżonków bez dochodu), średnio 42 097 zł, obciążenie
8,48%. Struktura źródeł: wynagrodzenia 62,3%, emerytury i renty 26,4%, działalność 3,9% dochodu ze skali.

**Czy da się wiarygodnie odtworzyć rozkład bez PDF?** Nie w pełni. Sześć liczb z PDF można przepisać ręcznie (parser
nie jest potrzebny), ale dwa przedziały wyznaczają tylko dwa momenty. Progresja w module powstaje głównie przy kwocie
wolnej (30 000 zł, kwota zmniejszająca 3 600 zł), czyli w środku rozkładu, którego te dane nie opisują. Sprawdzenie:

| rozkład (prawo 2024, baza zakotwiczona w 2024) | średni dochód | efektywna stawka skali | po +13,5% bazy | elastyczność stawki | elastyczność PIT ze skali |
|---|---|---|---|---|---|
| zastępczy `PIT_INCOME_DIST_DEFAULT` | 55 996 zł | 8,59% | 9,52% (×1,108) | 0,85 | 1,85 |
| log-normalny dopasowany do MF 2021 (udział powyżej progu i średnia; μ = 10,574, σ = 0,553; zero dla 1,85 mln małżonków), przeskalowany płacą BDL 2021→2024 (×1,438) | 60 457 zł | 7,65% | 8,69% (×1,136) | 1,03 | 2,03 |

Log-normalny rozkład zgodny z MF daje **większą**, nie mniejszą progresję (i zaniża średnią w górnym przedziale: 112 816
wobec 137 913 zł – ogon jest grubszy niż log-normalny). Podstawienie go do modelu (przy wartościach po Task 2, baza nagrana – okno PIT 2018, 2023, 2024) daje
PIT 2025 149,29 zamiast 144,87 mld zł (+3,1%). Udział podatników powyżej progu w rozkładzie zastępczym (7,2% powyżej
120 000 zł) jest zgodny z MF (7,3% powyżej 85 528 zł w 2021, co po indeksacji płacą odpowiada ok. 123 000 zł).

**Ocena „bracket creep” z discovery (przebieg na żywo: ×1,079 dla PIT, ×1,108 dla efektywnej stawki skali).** Tabela
wyżej zależy tylko od rozkładu i prawa (nie od kalibracji), więc dotyczy obu baz. Efekt nie jest artefaktem
rozkładu zastępczego: przy stałych progach i wysokiej kwocie wolnej (prawo od 2022 r.) wzrost nominalnych dochodów
podnosi efektywną stawkę o 0,85–1,03 % na 1% wzrostu bazy w obu rozkładach. Płaska relacja PIT/masa płac w historii
(9,3% → 8,5% w 2016–2024) wynika ze zmian prawa (obniżka stawki 2019, Polski Ład 2022), których prognoza przy stałym
prawie nie zakłada. Po Task 2 część liniowa dochodu z działalności jest większa (0,72 × 0,40 masy płac), co zmniejsza
udział progresywnej skali i obniża medianę PIT 2029 o 11,3% (baza nagrana).

**Rekomendacja następnego kroku.** (1) Wartość zostaje „założeniem”. (2) Dodać do testów kontrolę rozkładu zastępczego
na sześciu liczbach MF 2021 (udział powyżej progu i średnie w przedziałach po indeksacji płacą, z tolerancją) – bez
parsera, liczby wpisane ręcznie z adresem. (3) Dla kształtu rozkładu przy kwocie wolnej potrzebne jest źródło
decylowe: GUS „Struktura wynagrodzeń według zawodów” (rozkład płac pracowników, xlsx) połączony z rozkładem emerytur ZUS,
albo zapytanie do MF o dane PIT według decyli (art. 2 ustawy o dostępie do informacji publicznej). (4) Ważniejsze dla
prognozy PIT niż sam rozkład są: brak emerytur w bazie skali modelu (26% dochodu ze skali w 2021) i okno kalibracji – do
oceny w osobnym kroku (poza zakresem: nie zmieniamy równań).

## Udział budżetu państwa w PIT

**Definicja.** Od 2025 r. budżet państwa zatrzymuje znacznie mniejszą część PIT (reforma finansowania samorządów;
wykonanie 97,6 mld zł w 2024 → 28,75 mld zł w 2025). Moduł PIT liczy podatek według zasad sprzed reformy, więc od roku
załamania (`STRUCTURAL_BREAKS["rev_pit"]` = 2025) wynik modułu jest mnożony przez udział budżetu państwa
**s = s₀ · m · ε**, a lata wcześniejsze nie są skalowane:

- **s₀** – udział wyliczony z jednego roku: wykonanie `rev_pit` w roku załamania podzielone przez wynik modułu PIT (po
  kalibracji sprzed reformy) dla tego roku. Gdy w bazie jest masa płac roku załamania (płaca nominalna × zatrudnienie),
  moduł liczony jest z niej (źródło „z danych”); w przeciwnym razie jako mediana prognozy modułu na ten rok (źródło
  „prognoza”). s₀ liczony jest ze stałym ziarnem wewnętrznym (2025) i 2000 ścieżkami, więc jest powtarzalny i nie zależy
  od ziarna ani liczby ścieżek wybranych przez użytkownika. Bez serii lub bez roku załamania s₀ = 1 i PIT liczony jest
  jak dotąd (komunikat w założeniach).
- **m** – mnożnik użytkownika `pit_state_share_mult` (suwak; 1 = bez zmiany). Działa zawsze, od roku załamania; bez
  danych roku 2025 skaluje PIT sprzed reformy (np. przy zmianie zasad podziału).
- **ε** – losowy czynnik lognormalny (mediana 1) o odchyleniu logarytmu **σ** = `PIT_STATE_SHARE_SIGMA` = 0,2, ten sam
  dla bazy i scenariusza na danej ścieżce; występuje tylko wtedy, gdy s₀ oszacowano z danych (bez jednego punktu
  kalibracyjnego nie ma czego rozpraszać).

**Liczby.** Nagrane dane (`backend/tests/real_dataset.py`), parametry domyślne, 2000 ścieżek, ziarno 20261010:

| wariant danych | źródło s₀ | s₀ | wykonanie 2025 / wynik modułu |
|---|---|---|---|
| nagrane serie bez zmian | prognoza | 0,198 | 28,75 / mediana MC 144,87 |
| historia testowa z masą płac 2025 | dane | 0,212 | 28,75 / 135,57 |
| migawka demo `demo/real-data.db` | prognoza | 0,232 | 28,75 / 123,80 |

**s₀ zależy od okna kalibracji PIT**, bo moduł jest mnożony przez czynnik kalibracji z lat sprzed reformy: na migawce
demo i na danych na żywo (`rev_pit` za komplet lat) okno to {2022, 2023, 2024} i s₀ = 0,232; na nagranym zestawie testowym
(bez 2017 i 2019–2022) okno to {2018, 2023, 2024} i s₀ = 0,198 (0,212 ze źródłem „dane”). Przy źródle „prognoza” s₀
skraca czynnik kalibracji, więc mediany po uwzględnieniu udziału są identyczne na demo i na nagranych danych (28,61 /
33,73 / 39,71 / 46,36 / 54,51): okno kalibracji decyduje o s₀, nie o prognozie. Gdy w bazie pojawi się masa płac 2025
(zatrudnienie BDL za 2025), a model nadal kończy się w 2024, s₀ przełącza się na źródło „dane” (na nagranych danych
0,198 → 0,212), a mediana PIT 2025 wynosi ok. 30,7 zamiast ok. 28,75 mld zł.

**Dlaczego s₀ nie jest „czystym udziałem ustawowym”** (opis dla nagranego zestawu). Okno kalibracji PIT na nagranych danych to {2018, 2023, 2024}
(w nagranym zestawie MF nie ma `rev_pit` za 2017 ani 2019–2022). Moduł zawyża PIT 2024 o ok. 23% (moduł 120,2 wobec
wykonania 97,6 mld zł), a s₀ pochłania ten błąd poziomu: z czynnikiem kalibracji z samego 2024 r. wyszłoby ok. 0,244.
Wartość s₀ zawiera więc błąd prognozy modułu na 2025 r.

**PIT przed → po** (mld zł, nagrane dane bez zmian, ziarno 20261010, 2000 ścieżek; „przed” = stan sprzed udziału,
PIT według zasad sprzed reformy):

| rok | mediana przed | mediana po |
|---|---|---|
| 2025 | 144,87 | 28,61 |
| 2026 | 169,24 | 33,73 |
| 2027 | 198,52 | 39,71 |
| 2028 | 232,70 | 46,36 |
| 2029 | 272,30 | 54,51 |

Pasmo p10–p90: 2025 132,55–150,82 → 21,91–37,10; szerokość pasma 2026 37,55 → 18,63 (2029: 143,02 → 39,36). Po
uwzględnieniu udziału mediana 2025 leży blisko wykonania (28,75). Pasma są węższe w wartościach bezwzględnych (skala PIT
w budżecie państwa jest mniejsza), ale **szersze względem mediany** (2026: z ok. 22% do ok. 55% mediany), bo `ε`
dodaje rozrzut poziomu udziału.

**Ograniczenia.** (1) s₀ jest kalibrowany na **jednym roku** (2025) i zawiera błąd prognozy modułu na ten rok;
nie ma serii, z której dałoby się ocenić jego stabilność w czasie. (2) Mnożnik m skaluje PIT sprzed reformy, gdy brak
danych 2025. (3) σ = 0,2 jest założeniem (zakres 0,1–0,3), nie oszacowaniem z danych. (4) Backtest nie ocenia
realizacji `rev_pit` od 2025 r.

## Podsumowanie

**Statusy po badaniu:** z danych 1, ze źródła 2, założenie 11 (z 14 stałych). Stałe z przeglądu, które wcześniej miały
marker `PLACEHOLDER-UNVERIFIED`, a dziś mają źródło lub dane: `VAT_GAP`, `CIT_SMALL_TAXPAYER_SHARE`,
`CONSUMPTION_GDP_SHARE`. Marker w `config.py` pozostał tylko przy założeniach (pilnuje tego
`test_config_marker_only_on_assumptions`).

**2025: mediana przed → po** (mld zł, nagrane dane, parametry domyślne, 2000 ścieżek, ziarno 20261010; baza porównania jak
w nagłówku dokumentu):

| podatek | przed | po | zmiana |
|---|---|---|---|
| VAT | 324,42 | 324,42 | 0,00 |
| CIT | 72,54 | 72,54 | 0,00 |
| PIT | 155,50 | 144,87 | −10,63 (−6,8%) |

VAT i CIT bez zmian, bo współczynnik kalibracji pochłania człony mnożnikowe; zmieniają się skutki scenariuszy (np. CIT
9%→15%: +2,42 → +1,91). Cała zmiana PIT pochodzi z podziału dochodu z działalności (151,53) i relacji dochodów z
działalności do masy płac (149,35), łącznie 144,87.

**Stałe nadal będące założeniami i rekomendacja**

| stała | rekomendacja |
|---|---|
| `PIT_INCOME_DIST_DEFAULT` | Najważniejsza dla PIT. Następny krok: kontrola na sześciu liczbach MF 2021 w testach, potem źródło decylowe (GUS struktura wynagrodzeń + ZUS emerytury albo zapytanie do MF o dane PIT według decyli) – szczegóły w sekcji „Rozkład dochodów PIT”. |
| `PIT_LUMP_REVENUE_TO_INCOME`, `PIT_BUSINESS_*_SHARE`, `PIT_BUSINESS_INCOME_TO_WAGE_BILL` | Jedno wspólne źródło niepewności (założone R i dane sprzed Polskiego Ładu). Zastąpić po uzyskaniu informacji MF o PIT/ryczałcie za 2022+ (podatki.gov.pl, blokuje pobieranie automatyczne) lub kosztach ryczałtowców. |
| `VAT_CONSUMPTION_SHARES` | Własna mapa COICOP → stawka VAT na budżetach gospodarstw domowych GUS; ma znaczenie tylko dla skutków zmian stawek. |
| `VAT_PRICE_ELASTICITY`, `HOUSEHOLD_MPC` | Brak publicznego oszacowania dla Polski; pozostawić z zakresami albo zlecić estymację (NBP/IBS). |
| `EMPLOYMENT_GDP_ELASTICITY` | Kandydat na „z danych” (MNK 0,40–0,52 zgodne z 0,5); wymaga decyzji, czy zatrudnienie BDL bez małych podmiotów jest akceptowalne. |

**Obserwacje poza zakresem tego zadania (równań nie zmieniano):**

- Emerytury i renty (26,4% dochodu ze skali w 2021) nie wchodzą do bazy skali PIT w modelu; wpływa to na poziom i
  progresję PIT silniej niż sam kształt rozkładu.
- Domyślna stawka ryczałtu `pit_lump_rate_default` = 12% (parametr użytkownika) jest wyższa niż efektywna stawka z danych MF
  2023: 22,10 / 275,55 = 8,0% przychodu.
- Okno kalibracji PIT pozostaje krótkie (3 lata); załamanie 2025 obsługuje udział budżetu państwa (sekcja „Udział budżetu państwa w PIT”), z ograniczeniem „jednego roku” kalibracji.

## Źródła odwiedzone

- KE, strona VAT gap: https://taxation-customs.ec.europa.eu/taxation/vat/fight-against-vat-fraud/vat-gap_en (raport z 11.12.2025) i tabele xlsx (adres w wierszu `VAT_GAP`) – tab. 7, 9, 10, 205.
- MF przez dane.gov.pl (API https://api.dane.gov.pl/1.4/datasets/{162,191,206}/resources): Informacja CIT za 2019, 2020, 2021; Informacja PIT za 2021; Informacja o ryczałcie za 2021 i 2023.
- podatki.gov.pl (Informacja CIT za 2023 r., https://www.podatki.gov.pl/media/10396/informacja-cit-za-2023-r.pdf): odpowiedź „Request unsuccessful. Incapsula” – niedostępne.
- EUROMOD, Indirect Tax Country Report PL (https://www.iser.essex.ac.uk/files/projects/Euromod/IndirectTaxCountryReport_PL.pdf): opis stawek VAT, bez udziałów konsumpcji według stawek.
- Ossowski 2019, REME (https://journal.mostwiedzy.pl/reme/article/view/110): MPC względem PKB – nie pasuje do definicji w modelu.
- Bartosik 2020, Equilibrium (https://journals.economic-research.pl/eq/article/view/1841): prawo Okuna dla bezrobocia.
