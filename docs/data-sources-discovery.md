# Rozpoznanie źródeł danych (GUS BDL, Eurostat, MF) – stan na 2026-10-10

Raport z rozpoznania wykonalności; surowe odpowiedzi były zapisane w katalogu roboczym sesji (nie w repozytorium). Fixtures testowe
z nagranych odpowiedzi są w `backend/tests/fixtures/real/`. Wynik pierwszego pełnego odświeżenia na żywo: sekcja
„Uruchomienie na żywo 2026-10-10” (po macierzy MF).


## 1. Summary table

BDL base = `https://bdl.stat.gov.pl/api/v1`. All BDL data URLs below: `/data/by-variable/{id}?format=json&lang=pl&unit-level=0`
(returns only POLSKA, single page). JSON path: `results[0].values[*] -> {year:"YYYY", val:number, attrId:int}`.
Eurostat base = `https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data`, JSON-stat 2.0 (`value` is a sparse dict keyed by flat index, `status` dict for flags; decode with `id`/`size`/`dimension.*.category.index`).

| series | recommended source | request | unit | years | last 3 values | caveats / transformations |
|---|---|---|---|---|---|---|
| pkb_real | BDL var **458431** "dynamika produktu krajowego brutto ogółem, rok poprzedni=100" (subject P3502, GDP constant prices) | `/data/by-variable/458431?format=json&lang=pl&unit-level=0` | index, prev year=100 (measureUnitName "-") | 2000–2024 | 2022: 105.3, 2023: 100.2, 2024: 103.0 (attrId 9 = preliminary) | BDL has NO real GDP level, only growth rates. Chain: level_t = level_{t-1}·val_t/100 anchored at nominal GDP (var **458271**, mln zł, 2000–2024: 3100850 / 3415274 / 3653432) in a base year. Check first year: sister var 458272 (nominal dynamics) has 2000 = `val 0.0, attrId 4` (missing). Alternative with ready level + 2025: Eurostat `nama_10_gdp?geo=PL&na_item=B1GQ&unit=CLV20_MNAC` (2000–2025; 2023: 2666014, 2024: 2752625, 2025: 2857985 mln zł 2020 prices). |
| employment | BDL var **154173** "Przeciętne zatrudnienie wg sekcji – ogółem" (P2836) | `/data/by-variable/154173?...unit-level=0` | etat (FTE avg employment, excl. small units per GUS methodology) | 2005–2024 | 2022: 11032433, 2023: 11041289, 2024: 11038780 | Concept = average paid employment (FTE), not "pracujący". Alternatives: BDL **1632283** BAEL "aktywni zawodowo pracujący" (tys. osób, 2010–2025: 17307 / 17231 / 17241; 1632284 is its precision %); Eurostat `nama_10_pe?geo=PL&na_item=EMP_DC&unit=THS_PER` (2000–2025: 17528.9 / 17420.0 / 17432.03p). For 2000+ coverage Eurostat is the only one. Human choice needed. |
| wage_nominal | BDL var **64428** "Przeciętne miesięczne wynagrodzenia brutto – ogółem" (P2497) | `/data/by-variable/64428?...unit-level=0` | zł/month, nominal, gross | 2002–2025 | 2023: 7595.30, 2024: 8630.27, 2025: 9371.11 | Higher than the headline "gospodarka narodowa" average (2023 headline ≈7155 zł) — BDL regional wage series excludes entities with ≤9 employees (to be confirmed in metadata). Use growth rates, or accept level bias. 2000–2001 missing. |
| cpi | BDL var **217230** "Wskaźnik cen towarów i usług konsumpcyjnych – ogółem" (P2955, COICOP 1999, "dane do 2025r.") | `/data/by-variable/217230?...unit-level=0` | index, prev year=100 (unit "-") | 2003–2025 | 2023: 111.4, 2024: 103.6, 2025: 103.6 | **Not a price level** — growth index. Chain: P_base=100; P_t = P_{t-1}·val_t/100. From 2026 only quarterly COICOP-2018 vars (subject P4635, e.g. 1753083 "1 kwartał / ogółem – okres poprzedni = 100") → series breaks. 2000–2002 missing. Alternative level: Eurostat `prc_hicp_aind?geo=PL&coicop=CP00` unit INX_A_AVG (HICP 2015=100, 2000–2025: 143.5 / 148.7 / 153.7) — HICP≠CPI. |
| consumption_nominal | **NOT in BDL** (variables/search "spożycie" → 0 hits; no national-accounts expenditure subject). Use Eurostat **nama_10_gdp P31_S14** | `nama_10_gdp?format=JSON&lang=EN&geo=PL&na_item=P31_S14&unit=CP_MNAC&sinceTimePeriod=2000` | mln zł, current prices | 2000–2025 | 2023: 1934063, 2024: 2056557, 2025: 2209033 | Unit code is `CP_MNAC` (not CP_MIO_NAC — that returns empty `size` 0). /1000 → mld zł. Requires a new Eurostat client. |
| gross_surplus | BDL var **458419** "nadwyżka operacyjna brutto" (K29 Rachunki regionalne, G549/P3520) | `/data/by-variable/458419?...unit-level=0` | mln zł, current prices | 2000–2023 | 2021: 1279108, 2022: 1553042, 2023: 1676697 | Equals Eurostat B2A3G (GOS + mixed income): 2022 identical (1553042). Lags ~2 years (no 2024). Eurostat `nama_10_gdp na_item=B2A3G unit=CP_MNAC` has 2000–2025 (2023: 1684850 revised, 2024: 1689480, 2025: 1765710). |
| rev_vat | MF "Część tabelaryczna sprawozdania z wykonania budżetu państwa", dane.gov.pl dataset **163** (CC0) | per-year ZIP (see §B) → inner "TOM I" ZIP → file `007- DOCHODY BP ZESTAWIENIE OGÓŁEM.xlsx`, row label "1.1. Podatek od towarów i usług", column "Wykonanie" | tys. zł (cash, state budget) | 2016–2025 parsed (2015 legacy .xls: unsupported) – see "MF – macierz lat" | 2023: 244.27, 2024: 287.68, 2025: 321.65 mld zł | /1e6 → mld zł. Layout differs across years (2024: label col B, plan C, execution D; 2017/2018: label A, plan B, execution C; 2016, 2019–2023, 2025: label A and C, plan D, execution E) → match by label, take execution column. Pre-2015: MF website only. |
| rev_cit | same file, row "1.4. Podatek dochodowy od osób prawnych" | as above | tys. zł | 2016–2025 parsed (2015 unsupported) | 2023: 67.88, 2024: 60.24, 2025: 63.69 mld zł | state-budget share only (JST shares excluded). |
| rev_pit | same file, row "1.5. Podatek dochodowy od osób fizycznych" | as above | tys. zł | 2016–2025 parsed (2015 unsupported) | 2023: 91.67, 2024: 97.60, 2025: **28.75** mld zł | **Structural break 2025**: new JST revenue law moved most PIT to local governments (S1313 D51A also jumps in 2024 Eurostat). State-budget PIT is NOT comparable across 2024/2025 without adjustment. |

Eurostat gov_10a_taxag (ESA accrual, unit MIO_NAC), PL, mln zł, 2000–2024:
- `gov_10a_taxag?format=JSON&lang=EN&geo=PL&unit=MIO_NAC&sector=S13&sector=S1311&sector=S1313&na_item=D211&na_item=D51A&na_item=D51B&na_item=D51&sinceTimePeriod=2000`
- D211 VAT, S1311 (= S13): 2022 223395, 2023 249805, 2024 290738
- D51A household income tax, S1311: 70213 / 95239 / 81722; S13: 138019 / 149085 / 183514
- D51B corporate income tax, S1311: 70042 / 68796 / 60956; S13: 85765 / 90989 / 87475
Comparison with MF cash state budget: VAT 2024 287.7 (MF) vs 290.7 (ESA) — close; CIT 2024 60.2 vs 61.0; PIT 2023 91.7 vs 95.2. ESA S1311 = whole central government (incl. funds/agencies), accrual (time-adjusted), and D51A includes items that MF books elsewhere — order of magnitude matches, not identical. Eurostat lacks 2025 until ~Apr 2026+ (latest here: 2024; dataset updated 2026-07-21).

## 2. Real BDL API vs backend/app/data/gus_bdl.py assumptions

1. **National unit name is `"POLSKA"`** (uppercase), id `000000000000`, level 0 (`/units/000000000000` → `{"id":"000000000000","name":"POLSKA","level":0,...,"years":[1995..2026]}`). Code compares with `casefold()` so "Polska" still matches — OK, but matching on `id == "000000000000"` is safer (also e.g. "Kamienica Polska" exists as a gmina; casefold equality avoids it, but id is unambiguous).
2. **Missing values are NOT `null`**: they come as `"val": 0.0` with a non-value `attrId` (e.g. 458272 year 2000: `{"year":"2000","val":0.0,"attrId":4}`; attrId 4 = 'x' "Brak informacji..."). Code only skips `val is None` → would ingest 0.0 as data. Must filter by attrId: value-bearing attrIds per `/attributes`: 1, 3, 9 (preliminary 's'), 11, 13, 20, 21, 97; non-value: 0, 4, 7, 14, 15, 17, 50, 91, 94(?), 98. Safest: treat `attrId in {1,3,9,11,13,20,21,97}` as valid.
3. **Use `unit-level=0`** query param: returns only POLSKA in a single response; the code instead pages through all ~41 territorial units (many requests, rate-limit risk). Also supported: `year=2022&year=2023` (repeatable) to restrict years.
4. **Response shape of /data/by-variable**: top-level keys `totalRecords, links, variableId, measureUnitId, aggregateId, lastUpdate, results` — **no `page`/`pageSize` keys** (they exist on /subjects, /variables, /units). With `unit-level=0` the `links` key is absent entirely. Code handles `links` missing (`or {}`) — OK. Synthetic fixtures include `page`/`pageSize` and "Polska" (title case) — unlike reality.
5. **Pagination**: `links.{first,self,next,last}` (and `prev`); `next` absent on last page; next URLs are absolute and carry `page`/`page-size` — code matches. **Default page-size = 10; max = 100** (`page-size=101` → HTTP 412 with `{"errors":[{"errorResult":"Parametr 'pageSize' może przyjmować jedynie wartości z zakresu <1, 100>.",...}]}`). Code default 100 — OK.
6. **year is a string** ("2024"), val is a number — code's int()/float() fine. Variable level metadata: `measureUnitName` ("mln zł", "zł", "etat", "-" for indexes) is on `/variables/{id}`, not in data response (data only has `measureUnitId`). Code doesn't check units → no validation that the series is mln zł vs index.
7. **Rate limits (anonymous)**: headers `X-Rate-Limit-Limit: 7d`, `X-Rate-Limit-Remaining: ~9990`, `X-Rate-Limit-Reset`. Observed **HTTP 429** on `/units?level=0` after ~30 requests: body `{"errorResult":"Przekroczono limit wywołań API! Maksymalna ilość żądań to 1000 na 12 godz."}`, header **`Retry-After: 3 sek`** (non-numeric! standard parsers fail). Sandbox egress IP may be shared. Registering a free `X-ClientId` header raises limits (per BDL docs; not tested). Code has no retry/backoff and no X-ClientId support; a 429 becomes SourceError.
8. Variables of interest are mostly growth indices ("rok poprzedni=100"), not levels (pkb_real, cpi) → code/config assume level series (config.py:98 note). Needs a chaining transformation step.
9. `/variables/search?name=...` exists; empty result has no `links` key. `/subjects?parent-id=` used for hierarchy; there is **no "Rachunki narodowe" subject** — national-accounts data live under K29 "RACHUNKI REGIONALNE" (with POLSKA aggregate).

## 3. Unresolved items needing a human decision (ranked)

1. **rev_pit structural break 2025** (state-budget PIT 97.6 → 28.75 mld zł after JST financing reform). Decide: model PIT total (state + JST shares) vs state-budget share only; with MF data you need JST shares from elsewhere for the total. Eurostat S13 D51A gives general-government total (accrual).
2. **Cash state budget (MF, 2015–2025, XLSX in ZIP, label-matched parsing) vs accrual general/central government (Eurostat gov_10a_taxag, clean JSON API, 2000–2024)**. Recommendation for v1: MF dataset 163 for rev_* (it is literally "budżet państwa" and has 2025), with Eurostat S1311 as cross-check/backfill for 2000–2014 marked as different concept. Alternatively, if 2000+ history matters more than concept fidelity, Eurostat only.
3. **consumption_nominal not in BDL** → add a Eurostat client (it would also give pkb_real level, gross_surplus to 2025, employment 2000+). Consider moving all macro to Eurostat nama_10_* for one consistent, longer source.
4. employment concept: FTE avg paid employment (BDL 154173, 2005+) vs BAEL employed persons (2010+) vs national-accounts EMP_DC (Eurostat 2000+).
5. CPI: BDL growth index 2003–2025, annual series ends 2025 (COICOP 2018 switch, quarterly only so far) → chaining + future break; or Eurostat HICP level.
6. wage_nominal: BDL 64428 excludes small firms (level higher than headline); starts 2002.
7. MF XLSX layout drift between years and ZIP naming not stable → enumerate via `https://api.dane.gov.pl/1.4/datasets/163/resources?per_page=50&sort=-data_date` and take `attributes.link`; inner ZIP/folder names differ (2023 has `XLS/` subfolder; 2025 also bundles PDFs). Pre-2015 execution not on dane.gov.pl.
8. BDL X-ClientId registration + 429 handling ("Retry-After: 3 sek").

## B. Budget execution details

- B1 BDL: K27 "FINANSE PUBLICZNE" children are only JST budgets (G195/G197/G199/G201/G423/G425/G497 + archive) — **no state-budget revenue by tax**.
- B2 Eurostat: see table above (works, JSON-stat, codes D211, D51A, D51B, D51; sectors S13, S1311, S1313; unit MIO_NAC).
- B3 MF/dane.gov.pl: dataset 163 "Część tabelaryczna sprawozdań z wykonania budżetu państwa", license CC0 1.0, annual, 11 resources (zip) for 2015–2025 (2025 posted 2026-06-11). Resource links (stable media URLs, but random suffixes, e.g. 2025 `..._O6qXW9j.zip`) — enumerate via API, don't hardcode:
  - 2025 id 2054935 https://api.dane.gov.pl/media/resources/20260611/Sprawozdanie_z_wykonania_bud%C5%BCetu_pa%C5%84stwa_za_2025r_TOM_I_i_II_O6qXW9j.zip
  - 2024 id 72399 https://api.dane.gov.pl/media/resources/20250818/Sprawozdanie_z_wykonania_za_2024_rok_TOM_I_i__II_XLS.zip (6.4 MB)
  - 2023 id 58249 https://api.dane.gov.pl/media/resources/20240604/Sprawozdanie_z_wykonania_bud%C5%BCetu_pa%C5%84stwa_za_2023_rok_TOM_I_i__II_XLS.zip
  - 2022 48622, 2021 38967, 2020 30562, 2019 24153, 2018 17629, 2017 337 (www.dane.gov.pl), 2016 19452, 2015 19451.
  - Parse recipe: outer zip → inner "…TOM I….zip" → file matching `007*DOCHODY BP ZESTAWIENIE OG*.xlsx` (sheet "{YYYY} Załacznik nr 1"; header "w tysiącach zł"; first rows: "DOCHODY OGÓŁEM", "1.1. Podatek od towarów i usług", "1.4. Podatek dochodowy od osób prawnych", "1.5. Podatek dochodowy od osób fizycznych"); take the "Wykonanie" (last numeric) cell in the row; /1e6 → mld zł. Also `005 - ZESTAWIENIE OGÓLNE…xlsx` gives totals (2024 dochody 623239830.6 tys. zł). Zip filenames inside use `#Uxxxx` escapes for Polish chars.
- MF website (mf.gov.pl) itself was not probed further (time/budget); dataset 163 is MF's own publication on the official portal.
- B4 NBP: nothing relevant. Not probed.

## MF – macierz lat

Verified 2026-10-10 against the real resources of dataset 163 (resource list from
`https://api.dane.gov.pl/1.4/datasets/163/resources`, `attributes.link`; year from the title
"… w {YYYY} r."; `data_date` is the publication date). Downloads were sequential, archives read in
memory; 2015/2016/2018 were inspected via HTTP Range requests (only the "TOM I" XLS archive).
Values: column "Wykonanie" (found from the header text in every year — the "last numeric cell"
fallback was **not needed** for any year), unit line " w tysiącach zł" in every sheet, published
with 2 decimals (cells hold formula float noise, e.g. 287683368.91015995 → 287683368.91).
Parsed by `backend/app/data/mf_execution.py` (`find_member` + `extract_revenue`) from the real files.

| year | resource id | ZIP (MB) | path to the 007 member (outer → nested → member) | format | sheet | rows VAT/CIT/PIT | label col / Wykonanie col | unit | VAT | CIT | PIT (mld zł) |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 2015 | 19451 | 38.4 | `…2015_r.zip.zip` → `1_Tabelaryczne sprawozdanie za 2015 r - Tom I i II.zip` (38.4 MB, stored) → `SPRAWOZDANIE … 2015 ROK - TOM I_XLS.ZIP` → `007- DOCHODY BP ZESTAWIENIE OGÓŁEM (STR. 1.1).XLS` | **legacy .xls (BIFF)** | – | – | – | – | **unsupported** | | |
| 2016 | 19452 | 46.3 | `2016 … TOM I-WERSJA XLS.ZIP` → `007-DOCHODY BP ZESTAWIENIE OGÓŁEM (STR.1.1).XLSX` | xlsx | `Zał 1` | 15/18/19 | A+C / E | w tysiącach zł | 126.58 | 26.38 | 48.23 |
| 2017 | 337 | 6.7 | `2017 … TOM I-WERSJA XLS.ZIP` → `007-DOCHODY BP ZESTAWIENIE OGÓŁEM.xlsx` | xlsx | `ZAŁ 1` | 14/17/18 | A / C | w tysiącach zł | 156.80 | 29.76 | 52.67 |
| 2018 | 17629 | 43.5 | `1a Sprawozdanie za 2018 rok Tom I XLS.zip` → `007-DOCHODY BP ZESTAWIENIE OGÓŁEM.xlsx` | xlsx | `ZAŁ 1` | 14/17/18 | A / C | w tysiącach zł | 174.95 | 34.64 | 59.56 |
| 2019 | 24153 | 14.8 | `1a Sprawozdanie tabelaryczne za 2019 rok Tom I XLS.zip` → `007- DOCHODY BP ZESTAWIENIE OGÓŁEM.xlsx` | xlsx | `Załącznik 1` | 15/18/19 | A+C / E | w tysiącach zł | 180.89 | 39.98 | 65.44 |
| 2020 | 30562 | 11.0 | `1.1 Sprawozdanie 2020 TOM I xls.zip` → `007- DOCHODY BP ZESTAWIENIE OGÓŁEM.xlsx` | xlsx | ` ZaŁącznik 1` | 15/18/19 | A+C / E | w tysiącach zł | 184.55 | 41.29 | 63.80 |
| 2021 | 38967 | 21.8 | `1.1. Sprawozdanie 2021 TOM I xls.zip` → `1.1. Sprawozdanie 2021 TOM I xls/007- DOCHODY BP ZESTAWIENIE OGÓŁEM.xlsx` | xlsx | `2021 Załącznik nr 1` | 14/17/18 | A+C / E | w tysiącach zł | 215.73 | 52.37 | 73.61 |
| 2022 | 48622 | 17.4 | `1.1 Sprawozdanie … 2022 rok Tom I XLS.zip` → `007- DOCHODY BP ZESTAWIENIE OGÓŁEM.xlsx` | xlsx | `2022 Załącznik nr 1` | 14/17/18 | A+C / E | w tysiącach zł | 230.39 | 70.14 | 68.11 |
| 2023 | 58249 | 19.4 | `Sprawozdanie … 2023r. TOM I XLS.zip` → `XLS/007- DOCHODY BP ZESTAWIENIE OGÓŁEM.xlsx` | xlsx | `2023 Załacznik nr 1` | 14/17/18 | A+C / E | w tysiącach zł | 244.27 | 67.88 | 91.67 |
| 2024 | 72399 | 6.4 | `SPRAWOZDANIE Z WYKONANIA ZA 2024 TOM I XLS.zip` → `007- DOCHODY BP ZESTAWIENIE OGÓŁEM.xlsx` | xlsx | `2024 Załacznik nr 1` | 14/17/18 | B / D | w tysiącach zł | 287.68 | 60.24 | 97.60 |
| 2025 | 2054935 | 24.2 | `SPRAWOZDANIE … ZA 2025 TOM I.zip` → `007- DOCHODY BP ZESTAWIENIE OGÓŁEM.xlsx` | xlsx | `2025 Załacznik nr 1` | 14/17/18 | A+C / E | w tysiącach zł | 321.65 | 63.69 | 28.75 |

Exact values (tys. zł, "Wykonanie"): 2016 126584120 / 26381397 / 48232395; 2017 156801210.83 / 29758466.85 / 52668800.67;
2018 174947070.50 / 34640852.72 / 59558738.49; 2019 180891751.05 / 39984712.83 / 65444928.26; 2020 184551929.03 / 41293050.55 / 63797444.20;
2021 215733974.71 / 52373757.92 / 73606199.30; 2022 230390543.92 / 70136602.91 / 68107159.06; 2023 244267385.71 / 67883082.34 / 91665807.67;
2024 287683368.91 / 60239719.55 / 97599844.06; 2025 321646381.78 / 63686737.92 / 28752115.01.

Layouts: three distinct column layouts — (a) short label in A, numbered label in C, plan D, Wykonanie E
(2016, 2019–2023, 2025); (b) label A, plan B, Wykonanie C (2017, 2018); (c) label B, plan C, Wykonanie D (2024).
Header row "Wyszczególnienie | Budżet według ustawy budżetowej | Wykonanie", unit line one row below,
column numbers "1 2 3" two rows below, title "DOCHODY BUDŻETU PAŃSTWA W {YYYY} R." above. One sheet per workbook.
Sanity: VAT 126.6 → 321.6 mld zł, monotone increasing over 2016–2025; CIT/PIT plausible; PIT 2025 shows the known
JST-reform break.

Pitfalls found:
- The 2016 sheet has a second row numbered "1.4." ("1.4. Podatek tonażowy", no execution value) → rows are matched by the full label, never by the "1.x." prefix.
- Archive names without the UTF-8 flag are CP852 (Python shows them as CP437 mojibake, e.g. `OGα¥EM`); `unzip` shows `#Uxxxx` escapes. Matching uses only ASCII parts (`007`, `DOCHODY BP ZESTAWIENIE OG`).
- 2015/2016/2018/2019 bundle large PDF archives next to the XLS ones (2016: 38.8 MB `TOM I_PDF.ZIP`); the client opens only nested archives named "TOM I" (not "TOM II", not "PDF"), at most 10, within a total decompression budget (3 × max_member_bytes) — every real year 2015–2025 keeps the 007 workbook in such an archive.
- Size: 2016 (46.3 MB) and 2018 (43.5 MB) exceed 40 MB → the client's default `max_download_bytes` is 60 MB.
- 2017's `attributes.link` is `https://www.dane.gov.pl/…`, which answers 301 → `https://dane.gov.pl/…` (both allowed hosts).
- 2015: the 007 workbook is legacy `.xls` and sits one archive deeper (outer → `Tom I i II.zip` wrapper of 38.4 MB → `TOM I_XLS.ZIP`). Only one year is `.xls` (2016+ are `.xlsx`), so `xlrd` was **not** added (rule: only if it unlocks ≥ 4 years); resource 19451 is listed as known-unsupported and is not downloaded (a re-published resource gets a new id and is tried again).

## Uruchomienie na żywo 2026-10-10

Pierwsze pełne odświeżenie z prawdziwych źródeł (GUS BDL, Eurostat, MF/dane.gov.pl) przez produkcyjne `refresh(...)`
i klienty z `refresh.get_clients()` (to samo okablowanie co `POST /refresh`), potem `simulate` (parametry domyślne,
horyzont 5) i `backtest` (horyzont 3).

- Data: 2026-10-10, start 21:11 UTC, czas trwania 6 min 31 s (prawie w całości pobieranie archiwów MF).
- Kod: commit `e2e3466` (HEAD gałęzi `claude/real-data-sources`) + nowy skrypt `backend/scripts/live_refresh_report.py`
  z zadania 5 (w drzewie roboczym w chwili uruchomienia; dodany w następnym commicie bez zmian w logice odświeżania).
- Polecenie: `cd backend && .venv/bin/python -m scripts.live_refresh_report --db <scratch>/liverun/live.db --cache-dir <scratch>/live_cache`
  (baza i cache poza repozytorium, `BDL_CLIENT_ID` nieustawiony).
- Ruch: BDL 6 żądań, Eurostat 2 żądania, dane.gov.pl lista zasobów + 10 archiwów ZIP (2016–2025, łącznie ok. 211 MB;
  2015 pominięty bez pobierania). Cache MF po przebiegu: 10 plików JSON (`mf_execution_{2016..2025}.json`, ok. 380 B każdy;
  tylko wartości, bez archiwów).
- Wynik: **kod wyjścia 0, odświeżenie udane, wszystkie bramki jakości przeszły**, zapis z `synthetic="0"`.
- Zgodność z nagraniami: wszystkie wartości na żywo są identyczne z nagranymi fixtures (BDL, Eurostat) i z macierzą MF
  powyżej (2016–2025, co do grosza w tys. zł) – testy offline działają na danych reprezentatywnych.
- Testy `pytest -m live` (3 testy: BDL 458271 2024, Eurostat P31_S14 2024, MF VAT 2024 jednego roku) – zielone.

Raport (dosłownie, wyjście skryptu):

```text
Raport odświeżenia na żywo – 2026-10-10 21:11 UTC
  commit: e2e3466
  baza: /tmp/claude-0/-home-user-Model-gospodarczy-Polski/8e7ddd74-c939-5ad7-be8b-d6f9cab8bd80/scratchpad/liverun/live.db
  cache MF: /tmp/claude-0/-home-user-Model-gospodarczy-Polski/8e7ddd74-c939-5ad7-be8b-d6f9cab8bd80/scratchpad/live_cache
  BDL_CLIENT_ID: brak (limit anonimowy)
  symulacja: parametry domyślne, horyzont 5, 2000 ścieżek, seed 20261010

Bramki jakości: OK (wszystkie źródła pobrane, 0 naruszeń; zapisano synthetic=0)
  (b) konsumpcja / PKB nominalny w 2024 r.: 0.563 (zakres 0.4–0.7)
  (d) nadwyżka operacyjna GUS BDL vs Eurostat: 24 wspólnych lat (2000–2023), największa różnica 0.48% w 2023 r. (limit 2%)
Ostrzeżenia źródeł (nie przerywają odświeżenia):
  - mf_execution: 2015: 2015 report: the 007 workbook is a legacy .xls (BIFF) file inside a doubly nested 38 MB archive; .xls is not supported (no xlrd), see docs/data-sources-discovery.md 'MF – macierz lat' (resource 19451, not downloaded)

Serie w magazynie (mld zł; indeksy jako poziomy; zatrudnienie w etatach; płaca w zł/mies.):
  pkb_real             gus_bdl           2001–2024 (24 lat)     ostatnie: 2022: 3408.457, 2023: 3415.274, 2024: 3517.732
  employment           gus_bdl           2005–2024 (20 lat)     ostatnie: 2022: 11032433.000, 2023: 11041289.000, 2024: 11038780.000
  wage_nominal         gus_bdl           2002–2025 (24 lat)     ostatnie: 2023: 7595.300, 2024: 8630.270, 2025: 9371.110
  cpi                  gus_bdl           2003–2025 (23 lat)     ostatnie: 2023: 192.595, 2024: 199.529, 2025: 206.712
  consumption_nominal  eurostat          2000–2025 (26 lat)     ostatnie: 2023: 1934.063, 2024: 2056.557, 2025: 2209.033
  gross_surplus        gus_bdl+eurostat  2000–2025 (26 lat)     ostatnie: 2023: 1676.697, 2024: 1689.480, 2025: 1765.710
  gdp_nominal          gus_bdl           2000–2024 (25 lat)     ostatnie: 2022: 3100.850, 2023: 3415.274, 2024: 3653.432
  rev_vat              mf_execution      2016–2025 (10 lat)     ostatnie: 2023: 244.267, 2024: 287.683, 2025: 321.646
  rev_cit              mf_execution      2016–2025 (10 lat)     ostatnie: 2023: 67.883, 2024: 60.240, 2025: 63.687
  rev_pit              mf_execution      2016–2025 (10 lat)     ostatnie: 2023: 91.666, 2024: 97.600, 2025: 28.752
  wspólne lata makro (pkb_real, employment, wage_nominal, cpi, consumption_nominal): 20 (2005–2024)

Kalibracja (średnia relacja wykonania do wyniku modułu przy obecnym prawie):
  VAT: współczynnik 1.23334, lata 2023, 2024, 2025
  CIT: współczynnik 0.207797, lata 2023, 2024, 2025
  PIT: współczynnik 8.62988e-09, lata 2022, 2023, 2024

Prognoza (mediana, mld zł; parametry domyślne = obecne prawo; horyzont 5 lat od 2025):
  VAT: wykonanie 2022: 230.391, 2023: 244.267, 2024: 287.683
    2025: 324.422 (p10–p90 312.549–348.422; wykonanie 321.646)
    2026: 364.312 (p10–p90 337.979–393.229)
    2027: 395.444 (p10–p90 356.653–437.908)
    2028: 436.478 (p10–p90 383.160–503.437)
    2029: 485.506 (p10–p90 413.461–575.841)
  CIT: wykonanie 2022: 70.137, 2023: 67.883, 2024: 60.240
    2025: 72.537 (p10–p90 70.257–78.390; wykonanie 63.687)
    2026: 82.792 (p10–p90 77.400–89.439)
    2027: 91.142 (p10–p90 82.795–101.413)
    2028: 101.914 (p10–p90 89.528–117.499)
    2029: 114.418 (p10–p90 97.306–136.338)
  PIT: wykonanie 2022: 68.107, 2023: 91.666, 2024: 97.600
    2025: 128.341 (p10–p90 116.514–134.081; wykonanie 28.752)
    2026: 151.921 (p10–p90 133.463–169.951)
    2027: 180.538 (p10–p90 149.896–213.926)
    2028: 214.076 (p10–p90 169.891–269.507)
    2029: 253.383 (p10–p90 192.375–334.529)

Backtest (origins: 5, pominięte: 3; horyzont 3 lata, mediana vs wykonanie):
  VAT: MAPE 10.12%, pokrycie 80% 21%, pokrycie 95% 43%
  CIT: MAPE 28.45%, pokrycie 80% 7%, pokrycie 95% 7%
  PIT: MAPE 14.13%, pokrycie 80% 33%, pokrycie 95% 42%
  uwaga: Backtest liczy lata historyczne przy obecnym prawie podatkowym (domyślne parametry), nie przy prawie obowiązującym w danym roku.
  uwaga: MAPE w procentach; pokrycie jako ułamek realizacji w przedziałach 80% (p10-p90) i 95% (p2,5-p97,5).
  uwaga: Pominięto 3 lat startowych (brak dopasowania modelu) - wyniki opierają się na pozostałych latach.
  uwaga: PIT w budżecie państwa: zmiana zasad podziału od 2025 r. (reforma finansowania JST); kalibracja do 2024; wykonanie 2025 nie jest porównywalne z prognozą przy dotychczasowych zasadach.
  uwaga: Realizacje rev_pit od 2025 r. nie są oceniane w backteście (załamanie strukturalne).

Załamanie PIT 2025:
  wykonanie PIT w budżecie państwa 2024: 97.600, 2025: 28.752 mld zł (-70.5%) – reforma finansowania JST (większy udział JST w PIT)
  kalibracja PIT używa tylko lat < 2025: 2022, 2023, 2024
  backtest nie ocenia realizacji rev_pit od 2025 r.
  prognoza PIT jest liczona według zasad podziału sprzed reformy – nieporównywalna z wykonaniem od 2025 r.
```

Uwagi do raportu:
- „Pominięto 3 lat startowych” w backteście: lata startowe 2016–2018 mają 12–14 wspólnych lat makro (od 2005), a VAR
  wymaga co najmniej 15 obserwacji (`MIN_OBS`); `min_train=12` backtestu jest niższe niż ten próg. Ocenione lata startowe:
  2019–2023 (cele 2020–2025; PIT tylko do 2024).
- Kalibracja VAT i CIT obejmuje rok 2025 (konsumpcja i nadwyżka operacyjna z Eurostatu oraz wykonanie MF są już za 2025),
  choć ostatni rok modelu makro to 2024 (BDL: PKB realny i zatrudnienie kończą się na 2024). Porównanie prognozy 2025 VAT/CIT
  z wykonaniem 2025 nie jest więc testem poza próbą.
- Seria `gross_surplus` = GUS BDL 2000–2023 + Eurostat 2024–2025 (`gus_bdl+eurostat`).

### Wiarygodność prognozy – obserwacje

Analiza (bez zmian w modelu) na bazie z przebiegu na żywo; skrypt analityczny poza repozytorium odtwarza `_prepare`,
`simulate_levels` i moduły podatkowe z tym samym ziarnem (20261010). „Masa płac” = `wage_nominal × employment × 12`
(zł/mies. × etaty; BDL bez małych podmiotów), tylko jako punkt odniesienia – model używa jej w skali względnej.

**PIT.** Współczynnik kalibracji 8,63·10⁻⁹ (moduł liczy w jednostkach „zł/mies. × etaty”, więc liczba sama w sobie nie ma
interpretacji), lata 2022, 2023, 2024 (2025 wyłączony przez załamanie). Relacja wykonanie/moduł w tych latach:
8,51 / 9,34 / 8,04 (×10⁻⁹); w 2016 była 15,20 i spada monotonicznie (z wyjątkiem 2023).

| rok | masa płac (mld zł/rok) | PIT wykonanie | PIT / masa płac (wykonanie) | efektywna stawka skali w module (rozkład zastępczy) | PIT modelu / masa płac (po kalibracji) |
|---|---|---|---|---|---|
| 2016 | 521,1 | 48,23 | 9,26% | 3,59% | 5,26% |
| 2017 | 565,7 | 52,67 | 9,31% | 4,03% | 5,59% |
| 2018 | 615,3 | 59,56 | 9,68% | 4,51% | 5,97% |
| 2019 | 671,5 | 65,44 | 9,75% | 5,06% | 6,40% |
| 2020 | 709,3 | 63,80 | 9,00% | 5,39% | 6,66% |
| 2021 | 783,1 | 73,61 | 9,40% | 5,97% | 7,11% |
| 2022 | 887,8 | 68,11 | 7,67% | 6,82% | 7,78% |
| 2023 | 1006,3 | 91,67 | 9,11% | 7,63% | 8,42% |
| 2024 | 1143,2 | 97,60 | 8,54% | 8,59% | 9,16% |

Rozkład skoku mediany PIT 2025 (128,34) względem wykonania 2024 (97,60) – ×1,315 (+31,5%):
1. **Okno kalibracji ×1,073**: współczynnik to średnia z 2022–2024, a relacja w 2024 jest najniższa z trzech, więc model już
   w 2024 daje 104,8 zamiast 97,6 mld zł (+7,3%). Rok 2022 (obniżka PIT w połowie roku) i 2023 podnoszą średnią.
2. **Wzrost bazy ×1,135**: mediana VAR dla 2025 – płaca nominalna +11,1%, zatrudnienie +1,6%. Wykonanie 2025 w BDL: płaca
   +8,6% (zatrudnienia za 2025 brak). VAR (1 opóźnienie) przenosi wysoki wzrost płac z 2024 (+13,6%) na 2025.
3. **Progresja w rozkładzie zastępczym („bracket creep”) ×1,079**: efektywna stawka skali rośnie z 8,59% do 9,52% (mediana)
   przy +13,5% bazy. Elastyczność efektywnej stawki względem bazy w punkcie zakotwiczenia = 0,85, czyli elastyczność części
   skali PIT względem bazy ≈ 1,85 (część liniowa/ryczałt: 0,034 na jednostkę masy płac, część skali: 0,093). W kolejnych latach
   stawka rośnie dalej (10,4% / 11,3% / 12,3% / 13,3% w 2026–2029), stąd mediana 253 mld zł w 2029 (×2,6 względem 2024).
   W danych historycznych (przy zmieniającym się prawie) relacja PIT/masa płac jest płaska (9,3% → 8,5%), a moduł przy obecnym
   prawie podwaja efektywną stawkę między 2016 a 2024 – spadająca relacja wykonanie/moduł (15,2 → 8,0) to ten sam efekt.

Kontrfakty: przy faktycznej płacy 2025 (+8,58%) i zatrudnieniu 2024 PIT 2025 = 119,4 (+22,3%); dodatkowo z relacją kalibracji
tylko z 2024 – 111,2 (+14,0%). Nawet wtedy wzrost PIT jest ~1,6× wzrostu bazy, co wynika z rozkładu zastępczego
(`PIT_INCOME_DIST_DEFAULT`, PLACEHOLDER-UNVERIFIED: 3 mln podatników z dochodem 5 tys. zł, duża masa w pobliżu kwoty wolnej
30 tys. zł) i stałych progów. Część progresji jest realna (progi w Polsce nie są indeksowane), ale jej skala w modelu nie jest
zweryfikowana – rozkład z danych MF (tylko PDF do 2021) jest warunkiem wiarygodnej prognozy PIT.

**VAT.** Współczynnik 1,2333 (lata 2023–2025; relacje wykonanie/moduł 1,135 / 1,257 / 1,308). Mediana 2025 = 324,4 vs
wykonanie 2025 = 321,6 (−0,9%) – trafienie przypadkowe: VAR daje medianę konsumpcji nominalnej +14,9% w 2025, a Eurostat
pokazuje +7,4%; przy faktycznej konsumpcji 2025 model dałby 303,2 (−5,7%), bo współczynnik (średnia trzech lat) jest niższy od
relacji 2025. Względem wykonania 2024: ×1,128 = poziom kalibracji 0,981 × wzrost konsumpcji 1,149. Moduł VAT jest liniowy
w konsumpcji (brak progresji).

**CIT.** Współczynnik 0,2078 (lata 2023–2025; relacje 0,225 / 0,198 / 0,200). Mediana 2025 = 72,5 vs wykonanie 2025 = 63,7
(+13,9%). Względem 2024: ×1,204 = poziom kalibracji 1,049 × wzrost nadwyżki 1,148. Nadwyżka w projekcji rośnie jak nominalny
PKB z VAR (mediana 2025: realny PKB +6,6%, CPI +8,5% → +14,8%), a faktycznie: nadwyżka (Eurostat) +4,5%, CPI (BDL) +3,6%.
Przy faktycznej nadwyżce 2025 model dałby 66,0 (+3,7%).

**Wspólny czynnik.** Mediana VAR dla 2025 jest wyraźnie powyżej średnich z próby 2005–2024 (płaca +6,7%, CPI +3,4%,
konsumpcja +6,5%, PKB realny +3,7% rocznie) i powyżej wykonania 2025 – szok płacowo-cenowy 2022–2024 ciągnie ścieżki w górę.
Dla VAT i CIT to główne źródło odchylenia; dla PIT nakłada się na progresję rozkładu zastępczego i okno kalibracji. Backtest
(MAPE: VAT 10,1%, CIT 28,5%, PIT 14,1%; pokrycie 80%: 21% / 7% / 33%) potwierdza, że pasma niepewności są za wąskie.
Wnioski dla ekonomisty (poza zakresem tego zadania): rozkład dochodów PIT z danych MF, okno kalibracji (np. tylko ostatni rok
lub ważenie), specyfikacja VAR (liczba opóźnień, okres próby), szerokość pasm.

## C. PIT income distribution
dane.gov.pl dataset **191** "Informacje dotyczące rozliczenia podatku dochodowego od osób fizycznych" — 14 resources, **PDF only**, years 2008–2021 (e.g. 2021: https://api.dane.gov.pl/media/resources/20230102/INFORMACJA_PIT_za_2021.pdf). Contains the taxpayers-by-bracket tables, but not machine-readable (PDF table extraction needed). Sister dataset 162 (CIT) notes "Począwszy od 2022 r. informacje publikowane są wyłącznie na stronie podatki.gov.pl" — likely same for PIT (podatki.gov.pl page fetched but returned a 955-byte shell; formats there unverified).

## D. ZUS
dane.gov.pl dataset 158 (FUS/FEP/FRD plan execution incl. budget part 73) has a single HTML resource from 2015 — not usable. Financial statements datasets (19, 226, 235) are old (2012–2014). psz.zus.pl (Portal Statystyczny ZUS) and zus.pl respond HTTP 200 but no API was verified. For v2, Eurostat gov_10a_taxag D61 (net social contributions, S1314 social security funds) is the clean machine-readable fallback; ZUS-specific cash revenue would need ZUS annual "Informacja o wykonaniu planu finansowego FUS" (PDF/XLSX) — unverified.

## 4. Raw evidence (saved files under SCRATCH)

- bdl/h_subjects.txt — headers: `X-Rate-Limit-Limit: 7d`, `X-Rate-Limit-Remaining: 9998`
- bdl/subjects_root.json, sub_K29.json, sub_K15.json, sub_K4.json, sub_K40.json, sub_K27.json, sub_G543/G541/G549/G405/G479/G403.json
- bdl/var_P3502.json: `{"id":458431,"subjectId":"P3502","n1":"dynamika produktu krajowego brutto ogółem, rok poprzedni=100","level":3,"measureUnitId":1,"measureUnitName":"-"}`
- bdl/var_P3498.json (458271 "produkt krajowy brutto ogółem" mln zł), var_P3520.json (458419 mln zł), var_P2955.json (217230 "ogółem" "-"), var_P2497.json (64428 zł), var_P2836.json (154173 etat), var_P4089.json (1632283 tys. osób), var_P4283*.json (monthly employment, 756 vars), var_64428.json (`"years":[2002,…,2025]`)
- bdl/data_458271_l0.json: `{"totalRecords":1,"variableId":458271,"measureUnitId":6,"aggregateId":1,"lastUpdate":null,"results":[{"id":"000000000000","name":"POLSKA","values":[{"year":"2000","val":751669,"attrId":1},…,{"year":"2024","val":3653432,"attrId":9}]}]}`
- bdl/data_458431_l0.json, data_458419_l0.json, data_217230_l0.json, data_64428_l0.json, data_154173_l0.json, data_1632283_l0.json, data_458272_l0.json (`{"year":"2000","val":0.0,"attrId":4}`)
- bdl/data_458271_all_ps5.json — pagination: `"links":{"first":…,"self":…,"next":"…&page=1","last":"…&page=8"}`, totalRecords 41, includes MAKROREGION/REGION/województwa
- bdl/data_ps101.json — HTTP 412 page-size error; data_ps_default.json — default 10 per page
- bdl/attributes.json — attrId dictionary
- bdl/units_l0.json, units_l0_retry.json, h_units.txt — HTTP 429, `Retry-After: 3 sek`, "Maksymalna ilość żądań to 1000 na 12 godz."
- bdl/unit_000000000000.json, units_search.json
- bdl/vsearch_spozycie.json (0 results), vsearch_pracujacy.json, vsearch_konsump.json
- eurostat/taxag_PL_S1311_all.json (na_item code list), taxag_PL_sel.json (values above), nama_gdp_PL.json, nama_gdp_PL_units.json (unit code list), hicp_aind_PL.json, nama_pe_PL.json
- danegov/search_wykonanie.json, ds163.json, ds163_res.json
- danegov/zip2024/ (sprawozdanie_2024.zip, outer/, t1/005…, t1/007…), zip2025/ (s.zip, outer/, t1/007…), zip2023/ (s.zip, outer/, t1/XLS/007…)
  - 2024 007 excerpt: `['1.1. Podatek od towarów i usług', 293500000, 287683368.91]`, `['1.4. Podatek dochodowy od osób prawnych', 58556935, 60239719.55]`, `['1.5. Podatek dochodowy od osób fizycznych', 97745431, 97599844.06]` (plan, wykonanie; tys. zł)
  - 2025: VAT E14 321646381.78, CIT E17 63686737.92, PIT E18 28752115.01; 2023: VAT 244267385.71, CIT 67883082.34, PIT 91665807.67
- jsonstat.py (SCRATCH root) — helper script used to decode JSON-stat.
- PIT (dataset 191) and ZUS (dataset 158) metadata were read to stdout only (not saved, due to plan mode).
