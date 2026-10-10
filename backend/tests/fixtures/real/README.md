# Real BDL recordings

Recorded public data from bdl.stat.gov.pl (GUS BDL API v1) on 2026-10-10,
query `/data/by-variable/{id}?format=json&lang=pl&unit-level=0`.
These are NOT synthetic: values are exactly as returned by the API
(the responses are small, so they are stored complete, only renamed).
`bdl_458272_*` contains year 2000 with `val 0.0, attrId 4` (missing value marker).

# Real Eurostat recordings

Recorded public data from the Eurostat dissemination API (JSON-stat 2.0) on 2026-10-10,
base `https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data`.
These are real responses, not synthetic. Each response is a single small series (about 4 KB),
so they are stored complete (the only change is the file name); nothing was edited.

- `eurostat_nama_10_gdp_P31_S14_CP_MNAC.json`:
  `nama_10_gdp?format=JSON&lang=EN&geo=PL&na_item=P31_S14&unit=CP_MNAC&sinceTimePeriod=2000` (2000-2025, mln zl).
- `eurostat_nama_10_gdp_B2A3G_CP_MNAC.json`: same query with `na_item=B2A3G`.
- `eurostat_nama_10_gdp_invalid_unit_CP_MIO_NAC.json`: same as the first with the invalid
  `unit=CP_MIO_NAC`; Eurostat answers HTTP 200 with `size` `[1,0,1,1,26]` and empty `value`.
- `eurostat_nama_pe_EMP_DC_flags.json`: `nama_pe?geo=PL&na_item=EMP_DC&unit=THS_PER&sinceTimePeriod=2000`,
  used only because it carries real `status` flags (`b` break, `p` provisional).
- `eurostat_nama_10_gdp_multi_series.json`: `nama_10_gdp?geo=PL&na_item=B1GQ,B2A3G,P31_S14,D1&unit=CP_MNAC,CLV20_MNAC&sinceTimePeriod=2000`
  (6 non-empty series; D1/B2A3G/P31_S14 have no CLV20_MNAC values), used to check the multi-series decoding and the "single series expected" error.
Test variants with missing values are derived in the tests by deleting keys from these recordings.
