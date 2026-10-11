from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class ParamSpec:
    key: str
    label: str
    tax: str
    unit: str
    default: float
    min: float
    max: float
    step: float
    description: str


def _rate(key, label, tax, default, description, max_=1.0):
    return ParamSpec(key, label, tax, "ułamek", default, 0.0, max_, 0.005, description)


def _amount(key, label, tax, default, description, max_):
    return ParamSpec(key, label, tax, "zł", default, 0.0, max_, 1000.0, description)


PARAMETER_SCHEMA: list[ParamSpec] = [
    _rate("pit_rate_low", "PIT - stawka niższa", "pit", 0.12, "Stawka PIT na skali podatkowej do progu."),
    _rate("pit_rate_high", "PIT - stawka wyższa", "pit", 0.32, "Stawka PIT na skali podatkowej powyżej progu."),
    _amount("pit_threshold", "PIT - próg podatkowy", "pit", 120000, "Dochód roczny, powyżej którego obowiązuje stawka wyższa.", 1_000_000),
    _amount("pit_tax_free", "PIT - kwota wolna", "pit", 30000, "Roczna kwota wolna od podatku.", 200_000),
    _rate("pit_flat_rate", "PIT - podatek liniowy", "pit", 0.19, "Stawka podatku liniowego."),
    _rate("pit_lump_rate_default", "PIT - ryczałt (stawka domyślna)", "pit", 0.12, "Domyślna stawka ryczałtu od przychodów ewidencjonowanych."),
    ParamSpec(
        "pit_state_share_mult", "PIT - udział budżetu państwa (mnożnik względem 2025)", "pit", "mnożnik", 1.0, 0.5, 2.0, 0.05,
        "Mnożnik udziału budżetu państwa w PIT względem 2025 r. (1 = udział z 2025 r.); udział oszacowany z jednego roku. Bez wykonania za 2025 r. mnożnik skaluje PIT liczony według zasad sprzed reformy (zob. Jakość modelu).",
    ),
    _rate("vat_rate_standard", "VAT - stawka podstawowa", "vat", 0.23, "Podstawowa stawka VAT."),
    _rate("vat_rate_reduced1", "VAT - stawka obniżona I", "vat", 0.08, "Pierwsza obniżona stawka VAT."),
    _rate("vat_rate_reduced2", "VAT - stawka obniżona II", "vat", 0.05, "Druga obniżona stawka VAT."),
    _rate("cit_rate", "CIT - stawka podstawowa", "cit", 0.19, "Podstawowa stawka CIT."),
    _rate("cit_rate_small", "CIT - stawka dla małych podatników", "cit", 0.09, "Preferencyjna stawka CIT dla małych podatników."),
]

_BY_KEY = {p.key: p for p in PARAMETER_SCHEMA}


def schema_as_dicts() -> list[dict]:
    return [asdict(p) for p in PARAMETER_SCHEMA]


def defaults() -> dict[str, float]:
    return {p.key: p.default for p in PARAMETER_SCHEMA}


def validate(values: dict) -> dict[str, float]:
    unknown = set(values) - set(_BY_KEY)
    if unknown:
        raise ValueError(f"Nieznany parametr: {', '.join(sorted(unknown))}")
    out = defaults()
    for key, raw in values.items():
        spec = _BY_KEY[key]
        if isinstance(raw, bool) or not isinstance(raw, (int, float)):
            raise ValueError(f"Parametr {key} musi być liczbą")
        if not spec.min <= raw <= spec.max:
            raise ValueError(f"Parametr {key}={raw} poza zakresem [{spec.min}, {spec.max}]")
        out[key] = raw
    return out
