import pandas as pd


def chain_growth(growth: pd.Series, base_year: int, base_value: float) -> pd.Series:
    """Turn a "previous year = 100" index into a level series.

    The level in `base_year` equals `base_value`; later years: L_t = L_{t-1}*g_t/100;
    earlier years: L_{t-1} = L_t*100/g_t. `base_year` may also be min(index) - 1 (the base
    is then not part of the result). The output is indexed by the years of `growth`.
    """
    years = [int(y) for y in growth.index]
    if not years:
        raise ValueError("empty growth series")
    years_sorted = sorted(years)
    if years_sorted != list(range(years_sorted[0], years_sorted[-1] + 1)):
        raise ValueError("growth series has gaps in years")
    first, last = years_sorted[0], years_sorted[-1]
    if not first - 1 <= base_year <= last:
        raise ValueError(f"base year {base_year} outside {first - 1}..{last}")
    g = {int(y): float(v) for y, v in growth.items()}
    if any(v <= 0 for v in g.values()):
        raise ValueError("growth index must be positive")
    level = {base_year: float(base_value)}
    for t in range(base_year + 1, last + 1):
        level[t] = level[t - 1] * g[t] / 100.0
    for t in range(base_year, first, -1):
        level[t - 1] = level[t] * 100.0 / g[t]
    out = pd.Series({y: level[y] for y in years_sorted}, dtype="float64")
    out.index = pd.Index(years_sorted, dtype="int64", name="year")
    return out
