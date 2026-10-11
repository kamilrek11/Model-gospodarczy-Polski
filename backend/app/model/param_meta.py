"""Metadata registry for the 13 non-user constants of app.model.config.

status: from_data (computed from loaded series), sourced (published source with url),
assumption (no verified source; `note` must say why).
Values stay in config.py; this module only describes them.
"""

from dataclasses import dataclass
from copy import deepcopy
from typing import Literal

from app.model import config

Status = Literal["from_data", "sourced", "assumption"]


@dataclass(frozen=True)
class ParamMeta:
    key: str
    status: Status
    source: str = ""
    year: int | None = None
    url: str = ""
    low: float | None = None
    high: float | None = None
    note: str = ""


def _a(key: str, note: str, low: float | None = None, high: float | None = None) -> ParamMeta:
    return ParamMeta(key=key, status="assumption", note=note, low=low, high=high)


# Sources: full list with the numbers read from them in docs/model-parameters.md.
URL_VAT_GAP = "https://taxation-customs.ec.europa.eu/document/download/b3045343-a25a-4fcf-97c8-b27c413b95ad_en?filename=VAT-GAP-2025-tables.xlsx"
URL_CIT_2021 = "https://api.dane.gov.pl/media/resources/20221219/Infromacja_dotycz%C4%85ca_rozliczenia_podatku_CIT_za_2021_r..pdf"
URL_PIT_2021 = "https://api.dane.gov.pl/media/resources/20230102/INFORMACJA_PIT_za_2021.pdf"
URL_LUMP_2021 = "https://api.dane.gov.pl/media/resources/20221202/Informacja_rycza%C5%82t_za_2021.pdf"
URL_CONSUMPTION = "https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/nama_10_gdp?geo=PL&na_item=P31_S14&unit=CP_MNAC"

_SPLIT_SOURCE = (
    "MF, Informacja dotycząca rozliczenia PIT za 2021 r. (dochód z działalności na skali 43 450 mln zł; PIT-36L "
    "228 957 mln zł) oraz Informacja dotycząca ryczałtu od przychodów ewidencjonowanych za 2021 r. (przychód z "
    f"działalności 89 466 mln zł), dane.gov.pl: {URL_LUMP_2021}"
)
_DERIVED = (
    "Założenie pochodne z MF 2021 + założone R: składniki z MF są źródłowe, ale część ryczałtowa wymaga założonego "
    "PIT_LUMP_REVENUE_TO_INCOME (R = 2,0; MF nie publikuje dochodu ryczałtowców), a dane są sprzed Polskiego Ładu. "
)
_SPLIT_NOTE = _DERIVED + (
    "Podział dochodu z pozarolniczej działalności według formy opodatkowania (trzy udziały sumują się do 1): skala "
    "(razem z wynagrodzeniami), liniowy (pit_flat_rate), ryczałt (pit_lump_rate_default od przychodu). 2021: skala "
    "43,45, liniowy 228,96 mld zł; dochód ryczałtowców = przychód 89,47 mld zł / PIT_LUMP_REVENUE_TO_INCOME (2,0 – "
    "założenie, MF nie publikuje kosztów ryczałtowców) = 44,7 mld zł. Zakres: R od 1,5 do 4 oraz przesunięcie po "
    "Polskim Ładzie (przychód ryczałtowców z działalności 2023: 242,2 mld zł, ×2,7 wobec 2021)."
)

PARAMETERS: dict[str, ParamMeta] = {
    m.key: m
    for m in (
        _a(
            "VAT_CONSUMPTION_SHARES",
            "Udziały nominalnej konsumcji prywatnej (brutto) według stawek VAT: standard -> vat_rate_standard, "
            "reduced1 -> vat_rate_reduced1, reduced2 -> vat_rate_reduced2, zero -> 0%/zwolnione. Założenie: brak "
            "publikacji GUS/MF z podziałem całej konsumpcji gospodarstw domowych według stawek (budżety gospodarstw "
            "domowych podają wydatki według COICOP, nie według stawek; przypisanie stawek do COICOP wymagałoby "
            "własnej mapy). Kontrola: KE (VAT gap 2025, tab. 10) – luka stawek obniżonych w Polsce 2023 to 18,6% "
            "dochodu idealnego, z czego żywność 10,3 pkt.",
        ),
        ParamMeta(
            key="VAT_GAP",
            status="sourced",
            source="Komisja Europejska, VAT gap in Europe – report 2025, tabele (xlsx), tab. 205: Polska",
            year=2024,
            url=URL_VAT_GAP,
            low=0.048,
            high=0.16,
            note="Luka w ściągalności VAT jako część VTTL: 2024 (szybki szacunek KE) 10,9%; pełne szacunki 2021 4,8%, "
            "2022 11,2%, 2023 16,0%. Człon jest czysto mnożnikowy i w całości pochłania go współczynnik kalibracji VAT "
            "– zmiana wartości nie zmienia prognoz ani skutków scenariuszy.",
        ),
        _a(
            "VAT_PRICE_ELASTICITY",
            "Elastyczność realnego popytu konsumpcyjnego względem ceny brutto (pełne przeniesienie VAT na ceny). "
            "Założenie: nie znaleziono weryfikowalnego oszacowania dla Polski (NBP/IBS) dostępnego bez logowania. "
            "Zakres ma interpretację strukturalną: 0 = wolumen bez zmian (wydatki brutto rosną o podatek), -1 = stałe "
            "wydatki nominalne brutto (wolumen spada proporcjonalnie do ceny); -0,5 to środek.",
            low=-1.0,
            high=0.0,
        ),
        ParamMeta(
            key="CIT_SMALL_TAXPAYER_SHARE",
            status="sourced",
            source="MF, Informacja dotycząca rozliczenia podatku CIT za 2021 r. (dane.gov.pl, zbiór 162), str. 15",
            year=2021,
            url=URL_CIT_2021,
            low=0.05,
            high=0.12,
            note="Udział podstawy CIT opodatkowanej stawką 9% (mali podatnicy). 2021: podatek 9% 2 700 278 tys. zł, "
            "19% 65 220 084 tys. zł -> podstawy 30,0 i 343,3 mld zł -> 8,0% (podstawa = podatek / stawka; pominięto IP Box: "
            "podstawa ok. 1,5 mld zł, bez wpływu na 8,0%). 2019: 5,3%, 2020: 5,8% (rosnący trend). "
            "Informacje za 2022+ są tylko na podatki.gov.pl (strona blokuje pobieranie automatyczne).",
        ),
        _a(
            "PIT_INCOME_DIST_DEFAULT",
            "Rozkład dochodów podatników na skali: (średni roczny dochód w zł, liczba podatników w mln) w grupie. "
            "Założenie: rozkład syntetyczny. MF publikuje tylko dwa przedziały skali (Informacja PIT za 2021: "
            "22,33 mln podatników do 85 528 zł, średnio 34 581 zł; 1,75 mln powyżej, średnio 137 913 zł); dwa momenty "
            "nie wyznaczają kształtu rozkładu w pobliżu kwoty wolnej, gdzie powstaje progresja. Zastępczy rozkład jest "
            "zgodny z udziałem podatników powyżej progu (7,2% vs 7,3% po indeksacji płacą). Patrz sekcja "
            "„Rozkład dochodów PIT” w docs/model-parameters.md.",
        ),
        ParamMeta(key="PIT_BUSINESS_SCALE_SHARE", status="assumption", source=_SPLIT_SOURCE, year=2021, url=URL_PIT_2021, low=0.10, high=0.15, note=_SPLIT_NOTE),
        ParamMeta(key="PIT_BUSINESS_FLAT_SHARE", status="assumption", source=_SPLIT_SOURCE, year=2021, url=URL_PIT_2021, low=0.52, high=0.78, note=_SPLIT_NOTE),
        ParamMeta(key="PIT_BUSINESS_LUMP_SHARE", status="assumption", source=_SPLIT_SOURCE, year=2021, url=URL_PIT_2021, low=0.07, high=0.37, note=_SPLIT_NOTE),
        _a(
            "PIT_LUMP_REVENUE_TO_INCOME",
            "Relacja przychodu (podstawa ryczałtu) do dochodu ryczałtowców. Założenie: ryczałtowcy nie wykazują kosztów, "
            "więc MF nie publikuje ich dochodu. Punkt odniesienia: u podatników liniowych (PIT-36L, 2021) przychód / "
            "dochód = 1 387,7 / 229,0 = 6,1, ale to działalności kosztochłonne; ryczałt wybierają głównie usługi o "
            "niskich kosztach. Zakres 1,5–4.",
            low=1.5,
            high=4.0,
        ),
        ParamMeta(
            key="PIT_BUSINESS_INCOME_TO_WAGE_BILL",
            status="assumption",
            source="MF, Informacja PIT za 2021 r. i Informacja o ryczałcie za 2021 r. (dane.gov.pl, zbiory 191 i 206); "
            "masa płac modelu z GUS BDL (zmienna 64428 × zatrudnienie × 12)",
            year=2021,
            url=URL_PIT_2021,
            low=0.37,
            high=0.55,
            note=_DERIVED + "Dochód z pozarolniczej działalności (skala 43,45 + liniowy 228,96 + ryczałt 89,47/2,0 = 317,1 mld zł) "
            "do masy płac w definicji modelu (2021: 783,1 mld zł) = 0,405, zaokrąglone do 0,40. Po 2022 r. udział ryczałtu wzrósł, stąd górna granica zakresu. Serii dochodu "
            "z działalności nie ma w bazie, więc stała nie może mieć statusu „z danych”.",
        ),
        _a(
            "HOUSEHOLD_MPC",
            "Krańcowa skłonność do konsumpcji z dochodu rozporządzalnego: zmiana PIT o dT (mld zł) zmienia konsumpcję "
            "nominalną o -HOUSEHOLD_MPC × dT. Założenie: nie znaleziono weryfikowalnego oszacowania MPC z dochodu "
            "rozporządzalnego dla Polski (dostępne prace dotyczą MPC względem PKB lub z majątku). Zakres 0,3–0,9 "
            "(od szybkiej reakcji gospodarstw z ograniczeniami płynności do wygładzania konsumpcji).",
            low=0.3,
            high=0.9,
        ),
        ParamMeta(
            key="CONSUMPTION_GDP_SHARE",
            status="from_data",
            source="consumption_nominal (Eurostat nama_10_gdp, P31_S14, CP_MNAC) / gdp_nominal (GUS BDL, zmienna 458271), "
            "ostatni wspólny rok w bazie",
            year=2024,
            url=URL_CONSUMPTION,
            low=0.55,
            high=0.66,
            note="Udział konsumpcji gospodarstw domowych w PKB: zmiana realnej konsumpcji o x zmienia realny PKB o "
            "CONSUMPTION_GDP_SHARE × x. Liczona z danych (2024: 0,563; zakres 2000–2024: 0,556–0,658); wartość w "
            "config.py (0,57) to tylko zapas, gdy brak serii.",
        ),
        _a(
            "EMPLOYMENT_GDP_ELASTICITY",
            "Elastyczność zatrudnienia względem realnego PKB (krótki okres, typ Okuna). Założenie: literatura dla Polski "
            "(np. Bartosik 2020, Equilibrium 15(4)) podaje wrażliwość bezrobocia, nie zatrudnienia. Kontrola na danych "
            "w bazie (MNK na różnicach logarytmów zatrudnienia i PKB realnego): 0,52 (bł. std. 0,14) dla 2006–2024, "
            "0,40 (0,11) dla 2011–2024 – zgodne z 0,5.",
            low=0.25,
            high=0.8,
        ),
    )
}


def assumption_rows() -> list[dict]:
    """One row per registered constant: current config value plus its metadata."""
    rows: list[dict] = []
    for key, m in PARAMETERS.items():
        value = deepcopy(getattr(config, key))
        rows.append({
            "key": key,
            "value": [list(r) for r in value] if isinstance(value, tuple) else value,
            "status": m.status,
            "note": m.note,
            "source": m.source,
            "year": m.year,
            "url": m.url,
            "low": m.low,
            "high": m.high,
        })
    return rows
