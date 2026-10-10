"""Ministry of Finance state-budget execution (dane.gov.pl dataset 163), verified 2026-10-10.

Each year is one ZIP ("Część tabelaryczna sprawozdania z wykonania budżetu państwa") that holds a
"TOM I" ZIP with the workbook "007- DOCHODY BP ZESTAWIENIE OGÓŁEM.xlsx". The rows
"1.1. Podatek od towarów i usług", "1.4. Podatek dochodowy od osób prawnych" and
"1.5. Podatek dochodowy od osób fizycznych" give, in the column "Wykonanie", the cash revenue of
the state budget in tys. zł (published with 2 decimals). Year matrix and layouts:
docs/data-sources-discovery.md, section "MF – macierz lat" (2016-2025 supported; 2015 is a legacy
.xls workbook and stays unsupported).

Cache: parsed values per year (or an "unsupported" verdict for the exact published file) as JSON,
keyed by resource id + size and a fingerprint of CACHE_VERSION and the active limits (bump rule at
CACHE_VERSION).

Everything downloaded is untrusted: archives are read in memory only (member names are never used
as paths), sizes are capped while streaming and while decompressing, only https links on the
dane.gov.pl hosts are fetched (also after redirects) and workbooks are read with openpyxl in
read-only/data-only mode with a row cap (cached values, no formula evaluation).
"""

import io
import json
import math
import os
import re
import tempfile
import time
import unicodedata
import zipfile
import zlib
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

import httpx
import openpyxl
import pandas as pd

from app.data.base import SourceError, to_frame
from app.data.gus_bdl import GusBdlClient
from app.data.series_map import MF_DATASET_ID, MF_EXECUTION_ROWS

SOURCE = "mf_execution"
RESOURCES_URL = f"https://api.dane.gov.pl/1.4/datasets/{MF_DATASET_ID}/resources"
ALLOWED_HOSTS = frozenset({"api.dane.gov.pl", "www.dane.gov.pl", "dane.gov.pl"})
CACHE_ENV = "BUDGET_CACHE_DIR"  # read by the wiring (refresh.get_clients); passed in as cache_dir

PER_PAGE = 50
MAX_PAGES = 20
MAX_REDIRECTS = 5
LIST_TIMEOUT = httpx.Timeout(30.0, connect=10.0)
DOWNLOAD_TIMEOUT = httpx.Timeout(60.0, connect=10.0)
CHUNK = 1 << 20

MAX_NESTING = 2  # ZIPs opened inside the downloaded one (2015 wraps "TOM I" once more)
MAX_ARCHIVES = 10  # nested archives opened per find_member call (real reports: 1, 2015: 2)
MAX_MEMBERS = 5000  # per archive (the largest real "TOM I" has ~190)
XLSX_MAX_UNCOMPRESSED = 50_000_000  # sum of the workbook's own parts (real: ~60 KB)
MAX_SHEETS = 10
MAX_ROWS = 500  # real sheets have <= 63 rows
MAX_COLS = 40

UNIT_TEXT = "w tysiącach zł"
EXECUTION_HEADER = "wykonanie"
PLAUSIBLE_MAX_THOUSAND_ZL = 2e9  # 2000 mld zł: anything above is a unit/layout error
OLE2_MAGIC = bytes.fromhex("d0cf11e0a1b11ae1")
# Bump CACHE_VERSION whenever parsing changes in a way that could change a value or turn an
# "unsupported" verdict into a supported one (labels, column rules, rounding, member matching, the
# descent rule). The active limits are part of the cache fingerprint automatically.
CACHE_VERSION = 2
# Listed years from this one on must be obtained (downloaded or cached); a non-"unsupported" failure
# of such a year (network error, timeout, 5xx, size limit) fails the whole fetch, so a transient
# problem never shortens the stored revenue series. Earlier years (2015: legacy .xls) only warn.
FIRST_EXPECTED_YEAR = 2016

# Resources verified on 2026-10-10 to be unparseable by this client; skipped without downloading
# (a re-published resource gets a new id and is tried again).
KNOWN_UNSUPPORTED_RESOURCES = {
    "19451": "2015 report: the 007 workbook is a legacy .xls (BIFF) file inside a doubly nested "
    "38 MB archive; .xls is not supported (no xlrd), see docs/data-sources-discovery.md 'MF – macierz lat'",
}

_ESCAPE = re.compile(r"#U([0-9A-Fa-f]{4})")
_TOM_I = re.compile(r"TOM[\s_-]*I(?![IV])")
_TITLE_YEAR = re.compile(r"\b(\d{4})\s*r\b", re.IGNORECASE)
_SHEET_YEAR = re.compile(r"dochody budżetu państwa w (\d{4})")


def _err(message: str) -> SourceError:
    return SourceError(SOURCE, message)


def _norm(text: str) -> str:
    return " ".join(unicodedata.normalize("NFC", text).split()).casefold()


@dataclass(frozen=True)
class Resource:
    year: int
    url: str
    id: str = ""
    size: int | None = None


def _url_problem(url: str) -> str | None:
    try:
        parts = urlsplit(url)
        port = parts.port
    except ValueError:
        return f"unparseable URL {url!r}"
    if parts.scheme != "https":
        return f"not https: {url!r}"
    if (parts.hostname or "").lower() not in ALLOWED_HOSTS:
        return f"host {parts.hostname!r} not allowed"
    if port not in (None, 443) or parts.username or parts.password:
        return f"port/credentials not allowed in {url!r}"
    return None


def _get_json(http: httpx.Client, url: str, params: dict, *, sleep, max_retries: int) -> object:
    for attempt in range(max_retries + 1):
        try:
            r = http.get(url, params=params, timeout=LIST_TIMEOUT, follow_redirects=False)
        except httpx.HTTPError as e:
            raise _err(f"request failed for {url}: {e}") from e
        if _url_problem(str(r.url)):
            raise _err(f"response from unexpected location {r.url.host!r}")
        if r.status_code == 429 or r.status_code >= 500:
            if attempt < max_retries:
                sleep(GusBdlClient._wait_seconds(r, attempt))
                continue
            raise _err(f"HTTP {r.status_code} for {url} after {attempt + 1} attempts")
        if 300 <= r.status_code < 400:
            raise _err(f"HTTP {r.status_code} redirect for {url} (not followed)")
        if r.status_code >= 400:
            raise _err(f"HTTP {r.status_code} for {url}")
        try:
            return r.json()
        except ValueError as e:
            raise _err(f"invalid JSON from {url}: {e}") from e
    raise _err(f"retries exhausted for {url}")  # pragma: no cover


def list_resources(
    http: httpx.Client,
    *,
    warnings: list[str] | None = None,
    sleep=time.sleep,
    max_retries: int = 3,
) -> list[Resource]:
    """All dataset-163 resources with a year in the title and an allowed https `attributes.link`.

    Rejected links and titles without a year are skipped (reason appended to `warnings`).
    The year comes from the title ("… w 2024 r."); `data_date` is the publication date (the
    following year), so it is not used for the year.
    """
    warn = warnings if warnings is not None else []
    out: list[Resource] = []
    seen = 0
    for page in range(1, MAX_PAGES + 1):
        body = _get_json(http, RESOURCES_URL, {"page": page, "per_page": PER_PAGE}, sleep=sleep, max_retries=max_retries)
        try:
            items = body["data"]
            count = int(body["meta"]["count"])
            if not isinstance(items, list):
                raise TypeError("`data` is not a list")
            for item in items:
                rid = str(item["id"])
                attrs = item["attributes"]
                title, link = attrs.get("title") or "", attrs.get("link")
                size = attrs.get("file_size")
                size = int(size) if isinstance(size, (int, float)) and not isinstance(size, bool) else None
                m = _TITLE_YEAR.search(title)
                if not m:
                    warn.append(f"resource {rid} skipped: no year in title {title!r}")
                    continue
                year = int(m.group(1))
                problem = _url_problem(link) if isinstance(link, str) else "no link"
                if problem:
                    warn.append(f"resource {rid} ({year}) rejected: {problem}")
                    continue
                out.append(Resource(year=year, url=link, id=rid, size=size))
        except (KeyError, TypeError, ValueError, AttributeError) as e:
            raise _err(f"malformed resource list (page {page}): {e!r}") from e
        seen += len(items)
        if not items or seen >= count:
            return out
    raise _err(f"resource list longer than {MAX_PAGES} pages")


# --- archives --------------------------------------------------------------------------------


def _member_name(info: zipfile.ZipInfo) -> str:
    """Display/matching name: legacy (non-UTF-8) names are CP852, `#Uxxxx` escapes decoded."""
    name = info.filename
    if not info.flag_bits & 0x800:
        try:
            name = name.encode("cp437").decode("cp852")
        except (UnicodeEncodeError, UnicodeDecodeError):
            pass
    name = _ESCAPE.sub(lambda m: chr(int(m.group(1), 16)), name)
    return unicodedata.normalize("NFC", name)


def _unsafe_name(raw: str) -> bool:
    parts = re.split(r"[\\/]", raw)
    return raw.startswith(("/", "\\")) or ".." in parts or (len(raw) > 1 and raw[1] == ":")


def _is_007(name: str) -> bool:
    base = " ".join(re.split(r"[\\/]", name)[-1].upper().split())
    return re.match(r"007(?!\d)", base) is not None and "DOCHODY BP ZESTAWIENIE OG" in base


def _open_zip(data: bytes, max_members: int) -> zipfile.ZipFile:
    try:
        zf = zipfile.ZipFile(io.BytesIO(data))
    except (zipfile.BadZipFile, zipfile.LargeZipFile, ValueError, OSError, EOFError) as e:
        raise _err(f"not a valid ZIP archive: {e}") from e
    if len(zf.infolist()) > max_members:
        zf.close()
        raise _limit(f"archive has more than {max_members} members")
    return zf


class LimitExceeded(SourceError):
    """A failure caused by a configured size/count limit (depends on the limits, never cached)."""


def _limit(message: str) -> LimitExceeded:
    return LimitExceeded(SOURCE, message)


class _Budget:
    """Decompressed bytes still allowed for one find_member call (all levels together)."""

    def __init__(self, total: int):
        self.total = total
        self.left = total

    def take(self, n: int) -> None:
        self.left -= n
        if self.left < 0:
            raise _limit(f"decompression budget of {self.total} bytes exceeded (max_total_decompressed_bytes)")


def _read_member(zf: zipfile.ZipFile, info: zipfile.ZipInfo, limit: int, budget: _Budget | None = None) -> bytes:
    name = _member_name(info)
    if info.file_size > limit:
        raise _limit(f"member {name!r} declares {info.file_size} bytes (limit {limit})")
    if budget is not None and info.file_size > budget.left:
        raise _limit(f"member {name!r} ({info.file_size} bytes) does not fit the remaining decompression budget "
                     f"({budget.left} of {budget.total} bytes, max_total_decompressed_bytes)")
    buf = bytearray()
    try:
        with zf.open(info) as f:
            while chunk := f.read(CHUNK):
                buf += chunk
                if budget is not None:
                    budget.take(len(chunk))
                if len(buf) > limit:
                    raise _limit(f"member {name!r} exceeds {limit} bytes while reading")
    except SourceError:
        raise
    except (zipfile.BadZipFile, RuntimeError, NotImplementedError, zlib.error, EOFError, OSError, ValueError) as e:
        raise _err(f"cannot read member {name!r}: {e}") from e
    return bytes(buf)


def find_member(
    zip_bytes: bytes,
    *,
    max_member_bytes: int = 30_000_000,
    max_depth: int = MAX_NESTING,
    max_members: int = MAX_MEMBERS,
    max_total_decompressed_bytes: int | None = None,
    max_archives: int = MAX_ARCHIVES,
) -> bytes:
    """Bytes of the single `007*DOCHODY BP ZESTAWIENIE OG*` member (case-insensitive, `#Uxxxx`
    and CP852 names decoded), searched in the archive and in nested ZIPs up to `max_depth` levels.

    Descent rule: only nested archives whose (decoded) name contains "TOM I" (not "TOM II") and not
    "PDF" are opened — every real report 2015-2025 keeps the 007 workbook in such an archive
    ("…TOM I XLS.zip", "…TOM I-WERSJA XLS.ZIP", "…ZA 2025 TOM I.zip"; 2015 adds the wrapper
    "…Tom I i II.zip"). At most `max_archives` nested archives are opened and all decompressed bytes
    of the call (every level together) are capped by `max_total_decompressed_bytes` (default
    3 x max_member_bytes), so a small nested "amplification" archive fails fast. Nested archives over
    `max_member_bytes` are skipped and reported if nothing is found. Path-traversal/absolute names
    are ignored. Limit-caused failures raise LimitExceeded (a SourceError)."""

    budget = _Budget(max_total_decompressed_bytes or 3 * max_member_bytes)
    opened = [0]
    skipped: list[str] = []

    def search(data: bytes, depth: int) -> bytes | None:
        with _open_zip(data, max_members) as zf:
            infos = [i for i in zf.infolist() if not i.is_dir() and not _unsafe_name(i.filename)]
            hits = [i for i in infos if _is_007(_member_name(i))]
            if len(hits) > 1:
                raise _err(f"ambiguous 007 members: {[_member_name(i) for i in hits]}")
            if hits:
                return _read_member(zf, hits[0], max_member_bytes, budget)
            if depth >= max_depth:
                return None
            nested = [
                i for i in infos
                if (n := _member_name(i).upper()).endswith(".ZIP") and "PDF" not in n and _TOM_I.search(n)
            ]
            for info in nested:
                if info.file_size > max_member_bytes:
                    skipped.append(f"{_member_name(info)!r} ({info.file_size} bytes)")
                    continue
                if opened[0] >= max_archives:
                    raise _limit(f"more than {max_archives} nested archives to search (max_archives)")
                opened[0] += 1
                found = search(_read_member(zf, info, max_member_bytes, budget), depth + 1)
                if found is not None:
                    return found
        return None

    found = search(zip_bytes, 0)
    if found is None:
        if skipped:
            raise _limit(
                "member 007*DOCHODY BP ZESTAWIENIE OG* not found; skipped oversized nested archives "
                f"(limit {max_member_bytes}): {', '.join(skipped)}"
            )
        raise _err("member 007*DOCHODY BP ZESTAWIENIE OG* not found in the archive")
    return found


# --- workbook --------------------------------------------------------------------------------


def _is_number(v: object) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)


def _parse_rows(rows: list[tuple], year: int | None, notes: list[str] | None) -> dict[str, float]:
    wanted = {_norm(label): series for series, label in MF_EXECUTION_ROWS.items()}
    found: dict[str, list[int]] = {s: [] for s in MF_EXECUTION_ROWS}
    title_years: set[int] = set()
    for r, row in enumerate(rows):
        for v in row:
            if isinstance(v, str):
                t = _norm(v)
                if t in wanted:
                    found[wanted[t]].append(r)
                m = _SHEET_YEAR.search(t)
                if m:
                    title_years.add(int(m.group(1)))
    missing = [MF_EXECUTION_ROWS[s] for s, rs in found.items() if not rs]
    if missing:
        raise _err(f"row label(s) not found: {missing}")
    dup = [MF_EXECUTION_ROWS[s] for s, rs in found.items() if len(rs) > 1]
    if dup:
        raise _err(f"row label(s) appear more than once: {dup}")
    if year is not None and title_years != {year}:
        raise _err(f"workbook title year {sorted(title_years)} does not match expected {year}")
    first = min(rs[0] for rs in found.values())
    head = rows[:first]
    if not any(isinstance(v, str) and UNIT_TEXT in _norm(v) for row in head for v in row):
        raise _err(f"unit line '{UNIT_TEXT}' not found above the data rows")
    exec_cols = {c for row in head for c, v in enumerate(row) if isinstance(v, str) and _norm(v) == EXECUTION_HEADER}
    if len(exec_cols) > 1:
        raise _err(f"several 'Wykonanie' header columns: {sorted(exec_cols)}")
    out: dict[str, float] = {}
    for series, (r,) in found.items():
        row, label = rows[r], MF_EXECUTION_ROWS[series]
        if exec_cols:
            (c,) = exec_cols
            v = row[c] if c < len(row) else None
            if not _is_number(v):
                raise _err(f"no numeric 'Wykonanie' value for {label!r} (got {v!r})")
        else:
            nums = [v for v in row if _is_number(v)]
            if not nums:
                raise _err(f"no numeric value for {label!r}")
            v = nums[-1]
        if not 0 < v < PLAUSIBLE_MAX_THOUSAND_ZL:
            raise _err(f"implausible value {v!r} tys. zł for {label!r}")
        out[series] = round(float(v), 2)
    if not exec_cols and notes is not None:
        notes.append("'Wykonanie' header not found; used the last numeric cell of each row")
    return out


def extract_revenue(xlsx_bytes: bytes, *, year: int | None = None, notes: list[str] | None = None) -> dict[str, float]:
    """{'rev_vat'|'rev_cit'|'rev_pit': 'Wykonanie' in tys. zł (rounded to 2 decimals)}.

    Rows are matched by their full label; the column comes from the 'Wykonanie' header (fallback:
    last numeric cell of the row, reported in `notes`). With `year` the sheet title
    ("DOCHODY BUDŻETU PAŃSTWA W {year} R.") must match.
    """
    if xlsx_bytes.startswith(OLE2_MAGIC):
        raise _err("legacy .xls (BIFF/OLE2) workbook is not supported")
    with _open_zip(xlsx_bytes, MAX_MEMBERS) as parts:
        if sum(i.file_size for i in parts.infolist()) > XLSX_MAX_UNCOMPRESSED:
            raise _limit(f"workbook expands beyond {XLSX_MAX_UNCOMPRESSED} bytes")
    try:
        wb = openpyxl.load_workbook(io.BytesIO(xlsx_bytes), read_only=True, data_only=True, keep_links=False)
    except Exception as e:  # untrusted file: any parser failure is a source error
        raise _err(f"cannot open workbook: {e!r}") from e
    errors: list[str] = []
    try:
        for ws in wb.worksheets[:MAX_SHEETS]:
            try:
                rows = list(ws.iter_rows(max_row=MAX_ROWS, max_col=MAX_COLS, values_only=True))
                return _parse_rows(rows, year, notes)
            except SourceError as e:
                errors.append(f"sheet {ws.title!r}: {e.message}")
            except Exception as e:
                errors.append(f"sheet {ws.title!r}: {e!r}")
    finally:
        wb.close()
    raise _err("; ".join(errors) or "workbook has no sheets")


# --- client ----------------------------------------------------------------------------------


class _Unsupported(SourceError):
    """A deterministic content problem of one year's workbook (cached until the resource changes)."""


class MfBudgetExecutionClient:
    """rev_vat / rev_cit / rev_pit (mld zł, state budget, cash) from MF reports on dane.gov.pl.

    Policy: a year that cannot be downloaded or parsed is skipped with a message in
    `self.warnings` ("{year}: reason"); if no year at all could be obtained, fetch() raises
    SourceError. The cache (cache_dir, None = off) keeps only parsed values per year as JSON,
    keyed by resource id and size.
    """

    name = SOURCE

    def __init__(
        self,
        http: httpx.Client,
        cache_dir: str | None,
        *,
        years: range | None = None,
        max_download_bytes: int = 60_000_000,
        max_member_bytes: int = 30_000_000,
        max_total_decompressed_bytes: int | None = None,
        sleep=time.sleep,
        max_retries: int = 3,
    ):
        if max_total_decompressed_bytes is None:
            max_total_decompressed_bytes = 3 * max_member_bytes
        if min(max_download_bytes, max_member_bytes, max_total_decompressed_bytes) <= 0:
            raise ValueError("size limits must be positive")
        self.max_total_decompressed_bytes = max_total_decompressed_bytes
        self.http = http
        self.cache_dir = Path(cache_dir) if cache_dir else None
        self.years = years
        self.max_download_bytes = max_download_bytes
        self.max_member_bytes = max_member_bytes
        self.sleep = sleep
        self.max_retries = max_retries
        self.warnings: list[str] = []

    # cache
    def _cache_path(self, year: int) -> Path | None:
        return self.cache_dir / f"mf_execution_{year}.json" if self.cache_dir else None

    def _fingerprint(self) -> str:
        """Parser version + active limits: changing either invalidates every cached entry."""
        return (
            f"v{CACHE_VERSION}:dl={self.max_download_bytes}:member={self.max_member_bytes}"
            f":total={self.max_total_decompressed_bytes}:archives={MAX_ARCHIVES}:depth={MAX_NESTING}"
            f":members={MAX_MEMBERS}:xlsx={XLSX_MAX_UNCOMPRESSED}:rows={MAX_ROWS}"
        )

    def _cache_read(self, res: Resource) -> dict | None:
        path = self._cache_path(res.year)
        if path is None or not path.is_file():
            return None
        try:
            doc = json.loads(path.read_text(encoding="utf-8"))
            if (
                doc.get("fingerprint") != self._fingerprint()
                or doc.get("year") != res.year
                or doc.get("resource_id") != res.id
                or doc.get("size") != res.size
            ):
                return None
            if "unsupported" in doc:
                return {"unsupported": str(doc["unsupported"])}
            values = doc["values"]
            if set(values) != set(MF_EXECUTION_ROWS) or not all(_is_number(v) for v in values.values()):
                return None
            return {"values": {k: float(v) for k, v in values.items()}}
        except (OSError, ValueError, TypeError, KeyError, AttributeError):
            return None  # corrupted cache: ignore and re-fetch

    def _cache_write(self, res: Resource, payload: dict) -> None:
        path = self._cache_path(res.year)
        if path is None:
            return
        doc = {"fingerprint": self._fingerprint(), "year": res.year, "resource_id": res.id, "size": res.size, "url": res.url}
        doc.update(payload)
        tmp = None
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".mf_execution_", suffix=".tmp")
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(doc, f, ensure_ascii=False)
            os.replace(tmp, path)
        except OSError as e:
            self.warnings.append(f"{res.year}: cache write failed: {e}")
            if tmp and os.path.exists(tmp):
                os.unlink(tmp)

    # download
    def _download(self, url: str) -> bytes:
        limit = self.max_download_bytes
        for _ in range(MAX_REDIRECTS + 1):
            problem = _url_problem(url)
            if problem:
                raise _err(f"download URL rejected: {problem}")
            for attempt in range(self.max_retries + 1):
                try:
                    with self.http.stream("GET", url, timeout=DOWNLOAD_TIMEOUT, follow_redirects=False) as r:
                        if _url_problem(str(r.url)):
                            raise _err(f"response from unexpected location {r.url.host!r}")
                        status = r.status_code
                        if status in (301, 302, 303, 307, 308):
                            location = r.headers.get("Location")
                            if not location:
                                raise _err(f"HTTP {status} without Location for {url}")
                            next_url = str(r.url.join(location))
                        elif status == 429 or status >= 500:
                            if attempt >= self.max_retries:
                                raise _err(f"HTTP {status} for {url} after {attempt + 1} attempts")
                            wait = GusBdlClient._wait_seconds(r, attempt)
                            next_url = None
                        elif not 200 <= status < 300:
                            raise _err(f"HTTP {status} for {url}")
                        else:
                            declared = r.headers.get("Content-Length", "")
                            if declared.isdigit() and int(declared) > limit:
                                raise _err(f"download of {url} declares {declared} bytes (limit {limit})")
                            buf = bytearray()
                            for chunk in r.iter_bytes():
                                buf += chunk
                                if len(buf) > limit:
                                    raise _err(f"download of {url} exceeds {limit} bytes")
                            return bytes(buf)
                except httpx.HTTPError as e:
                    raise _err(f"request failed for {url}: {e}") from e
                if next_url is not None:
                    url = next_url
                    break
                self.sleep(wait)
            else:  # pragma: no cover - the last attempt always raises
                raise _err(f"retries exhausted for {url}")
        raise _err(f"too many redirects for {url}")

    def _year_values(self, res: Resource) -> dict[str, float]:
        if res.id in KNOWN_UNSUPPORTED_RESOURCES:
            raise _Unsupported(SOURCE, f"{KNOWN_UNSUPPORTED_RESOURCES[res.id]} (resource {res.id}, not downloaded)")
        cached = self._cache_read(res)
        if cached is not None:
            if "unsupported" in cached:
                raise _Unsupported(SOURCE, f"{cached['unsupported']} (cached)")
            return cached["values"]
        if res.size is not None and res.size > self.max_download_bytes:
            raise _err(f"resource declares {res.size} bytes (limit max_download_bytes={self.max_download_bytes})")
        data = self._download(res.url)
        notes: list[str] = []
        try:
            member = find_member(
                data,
                max_member_bytes=self.max_member_bytes,
                max_total_decompressed_bytes=self.max_total_decompressed_bytes,
            )
            values = extract_revenue(member, year=res.year, notes=notes)
        except LimitExceeded:
            raise  # depends on the limits: never cached
        except SourceError as e:
            # Cache the verdict only for the exact published file (length == API file_size); an HTML
            # maintenance page, a captive portal or a mangled body is retried on the next fetch.
            if res.size is not None and len(data) == res.size:
                self._cache_write(res, {"unsupported": e.message})
                raise _Unsupported(SOURCE, e.message) from e
            raise _err(f"{e.message} (downloaded {len(data)} bytes, API file_size {res.size}; not cached)") from e
        self.warnings.extend(f"{res.year}: {n}" for n in notes)
        self._cache_write(res, {"values": values})
        return values

    def fetch(self) -> dict[str, pd.DataFrame]:
        self.warnings = []
        resources = list_resources(self.http, warnings=self.warnings, sleep=self.sleep, max_retries=self.max_retries)
        by_year: dict[int, Resource] = {}
        for res in resources:
            if self.years is not None and res.year not in self.years:
                continue
            prev = by_year.get(res.year)
            if prev is not None:
                self.warnings.append(f"{res.year}: several resources ({prev.id}, {res.id}); using the newest id")
                if not (res.id.isdigit() and prev.id.isdigit() and int(res.id) > int(prev.id)):
                    continue
            by_year[res.year] = res
        values: dict[int, dict[str, float]] = {}
        failures: list[str] = []
        hard: list[tuple[int, str]] = []  # expected years that failed for a reason other than "unsupported"
        for year in sorted(by_year):
            try:
                values[year] = self._year_values(by_year[year])
            except _Unsupported as e:
                failures.append(f"{year}: {e.message}")
            except SourceError as e:
                failures.append(f"{year}: {e.message}")
                if year >= FIRST_EXPECTED_YEAR:
                    hard.append((year, e.message))
        self.warnings.extend(failures)
        if hard:
            years = ", ".join(str(y) for y, _ in hard)
            detail = "; ".join(f"{y}: {m}" for y, m in hard)
            raise _err(
                f"Nie udało się pobrać danych MF za lata {years} (wymagane wszystkie opublikowane lata od "
                f"{FIRST_EXPECTED_YEAR} r.; zapisane dane pozostają bez zmian, spróbuj ponownie później): {detail}"
            )
        if not values:
            detail = "; ".join(failures) or "no matching resources listed"
            raise _err(f"no year could be obtained ({detail})")
        return {
            series: to_frame([(y, v[series] / 1e6) for y, v in values.items() if series in v])
            for series in MF_EXECUTION_ROWS
        }
