"""
GDELT DOC 2.0 API data collection for ASGM sentiment analysis.

Timeline modes (timelinetone, timelinevolraw, timelinesourcecountry) cover
2017–present. Article list mode only returns the most recent 3 months.

Note: We bypass gdeltdoc's URL construction because its _filter_to_string()
appends a trailing space after every filter value, which GDELT rejects with
a 429. We use the library's whitelisted User-Agent but build URLs ourselves.
"""

import os
import time
import logging

import pandas as pd
import requests

from config import (
    THEMES,
    KEYWORD_QUERIES,
    COMPARISON_THEMES,
    DATE_RANGE,
    CACHE_DIR,
    REQUEST_DELAY,
)

logger = logging.getLogger(__name__)

_GDELT_BASE = "https://api.gdeltproject.org/api/v2/doc/doc"
_HEADERS = {
    "User-Agent": "GDELT DOC Python API client 1.12.0 - https://github.com/alex9smith/gdelt-doc-api"
}

_VALID_TIMELINE_MODES = {
    "timelinetone",
    "timelinevolraw",
    "timelinevol",
    "timelinelang",
    "timelinesourcecountry",
}


# ---------------------------------------------------------------------------
# Low-level request helpers
# ---------------------------------------------------------------------------

def _build_query(theme: str | None, keyword: str | None) -> str:
    """Combine theme and/or keyword into a GDELT query string."""
    parts = []
    if theme:
        parts.append(f"theme:{theme}")
    if keyword:
        parts.append(keyword)
    if not parts:
        raise ValueError("At least one of theme or keyword must be provided.")
    return " ".join(parts)


def _gdelt_get(url: str, retries: int = 3) -> dict:
    """
    GET a GDELT API URL with the whitelisted User-Agent and retry on 429.
    Returns parsed JSON or raises RuntimeError.
    """
    delay = REQUEST_DELAY
    for attempt in range(1, retries + 1):
        resp = requests.get(url, headers=_HEADERS, timeout=60)
        if resp.status_code == 200:
            if "text/html" in resp.headers.get("content-type", ""):
                raise ValueError(f"GDELT returned HTML error: {resp.text.strip()[:200]}")
            return resp.json()
        if resp.status_code == 429:
            logger.warning(
                "Rate-limited (attempt %d/%d). Sleeping %ds.", attempt, retries, delay
            )
            time.sleep(delay)
            delay *= 2
        else:
            resp.raise_for_status()
    raise RuntimeError(f"GDELT request failed after {retries} attempts: {url}")


def _timeline_request(
    mode: str,
    query: str,
    start_date: str,
    end_date: str,
    max_records: int = 250,
) -> pd.DataFrame:
    """
    Call a GDELT timeline mode and parse the response into a DataFrame.

    GDELT timeline JSON structure:
      {"timeline": [{"series": "<name>", "data": [{"date": "...", "value": N}, ...]}, ...]}

    Returns a DataFrame with a 'datetime' column plus one column per series.
    For timelinevolraw, a second 'All Articles' column carries the total corpus count.
    """
    if mode not in _VALID_TIMELINE_MODES:
        raise ValueError(f"Invalid mode: {mode}. Choose from {_VALID_TIMELINE_MODES}")

    start_dt = start_date.replace("-", "") + "000000"
    end_dt = end_date.replace("-", "") + "000000"
    url = (
        f"{_GDELT_BASE}"
        f"?query={requests.utils.quote(query, safe=':\"')}"
        f"&mode={mode}"
        f"&startdatetime={start_dt}"
        f"&enddatetime={end_dt}"
        f"&maxrecords={max_records}"
        f"&format=json"
    )
    logger.info("_timeline_request: %s", url)
    data = _gdelt_get(url)

    series_list = data.get("timeline", [])
    if not series_list:
        return pd.DataFrame()

    results: dict[str, list] = {
        "datetime": [entry["date"] for entry in series_list[0]["data"]]
    }
    for series in series_list:
        results[series["series"]] = [entry["value"] for entry in series["data"]]

    # timelinevolraw includes a normalised total alongside the match count
    if mode == "timelinevolraw":
        results["All Articles"] = [
            entry.get("norm", 0) for entry in series_list[0]["data"]
        ]

    df = pd.DataFrame(results)
    df["datetime"] = pd.to_datetime(df["datetime"])
    return df


def _artlist_request(query: str, num_records: int = 250) -> pd.DataFrame:
    """
    Call GDELT's artlist mode (recent ~3 months only).
    Returns a DataFrame with url, title, seendate, language, domain, sourcecountry.
    """
    url = (
        f"{_GDELT_BASE}"
        f"?query={requests.utils.quote(query, safe=':\"')}"
        f"&mode=artlist"
        f"&maxrecords={num_records}"
        f"&format=json"
    )
    logger.info("_artlist_request: %s", url)
    data = _gdelt_get(url)
    return pd.DataFrame(data.get("articles", []))


# ---------------------------------------------------------------------------
# Public query functions
# ---------------------------------------------------------------------------

def get_tone_timeline(
    theme: str | None = None,
    keyword: str | None = None,
    start_date: str = DATE_RANGE["start"],
    end_date: str = DATE_RANGE["end"],
) -> pd.DataFrame:
    """
    Average tone over time for articles matching theme or keyword.
    Use theme OR keyword — not both (the API ANDs all filters).
    Returns a DataFrame with columns: datetime, All.
    """
    q = _build_query(theme, keyword)
    return _timeline_request("timelinetone", q, start_date, end_date)


def get_volume_timeline(
    theme: str | None = None,
    keyword: str | None = None,
    start_date: str = DATE_RANGE["start"],
    end_date: str = DATE_RANGE["end"],
) -> pd.DataFrame:
    """
    Raw article count over time.
    Returns DataFrame with columns: datetime, All (match count), All Articles (corpus total).
    """
    q = _build_query(theme, keyword)
    return _timeline_request("timelinevolraw", q, start_date, end_date)


def get_country_timeline(
    theme: str | None = None,
    keyword: str | None = None,
    start_date: str = DATE_RANGE["start"],
    end_date: str = DATE_RANGE["end"],
) -> pd.DataFrame:
    """
    Article volume by source country over time.
    Returns a wide DataFrame with one column per country plus datetime.
    """
    q = _build_query(theme, keyword)
    return _timeline_request("timelinesourcecountry", q, start_date, end_date)


def get_recent_articles(
    theme: str | None = None,
    keyword: str | None = None,
    num_records: int = 250,
) -> pd.DataFrame:
    """
    Article list for the most recent ~3 months (API limitation).
    Returns a DataFrame with url, title, seendate, language, domain, sourcecountry.
    """
    q = _build_query(theme, keyword)
    return _artlist_request(q, num_records)


# ---------------------------------------------------------------------------
# Caching helpers
# ---------------------------------------------------------------------------

def cache_result(df: pd.DataFrame, name: str) -> str:
    """Write a DataFrame to parquet in CACHE_DIR. Returns the file path."""
    os.makedirs(CACHE_DIR, exist_ok=True)
    path = os.path.join(CACHE_DIR, f"{name}.parquet")
    df.to_parquet(path)
    logger.info("Cached %s → %s", name, path)
    return path


def load_cached(name: str) -> pd.DataFrame | None:
    """Load a cached parquet file, or return None if it doesn't exist."""
    path = os.path.join(CACHE_DIR, f"{name}.parquet")
    if os.path.exists(path):
        logger.info("Loading cached: %s", path)
        return pd.read_parquet(path)
    return None


def load_or_fetch(name: str, fetch_fn, *args, **kwargs) -> tuple[pd.DataFrame, bool]:
    """
    Return (df, fetched_from_api). Loads from parquet cache when available;
    otherwise calls fetch_fn, caches the result, and returns fetched_from_api=True.
    Empty DataFrames are never cached (avoids masking real failures).
    """
    cached = load_cached(name)
    if cached is not None:
        return cached, False
    df = fetch_fn(*args, **kwargs)
    if not df.empty:
        cache_result(df, name)
    return df, True


def clear_parquet_cache() -> int:
    """Delete all parquet files in CACHE_DIR. Returns the count deleted."""
    import glob
    files = glob.glob(os.path.join(CACHE_DIR, "*.parquet"))
    for f in files:
        os.remove(f)
        logger.info("Deleted cache file: %s", f)
    logger.info("Cleared %d cached parquet files.", len(files))
    return len(files)


# ---------------------------------------------------------------------------
# Master collection
# ---------------------------------------------------------------------------

def collect_all_data() -> dict[str, pd.DataFrame]:
    """
    Run all queries and cache results. Skips queries that are already cached.
    Returns a dict of {name: DataFrame}.
    """
    results: dict[str, pd.DataFrame] = {}
    primary = THEMES["primary"]

    def _run(name: str, fn, *args, **kwargs) -> None:
        try:
            df, fetched = load_or_fetch(name, fn, *args, **kwargs)
        except Exception as exc:
            logger.warning("Skipping %s — fetch failed: %s", name, exc)
            df = pd.DataFrame()
            fetched = False
        results[name] = df
        if fetched:
            time.sleep(REQUEST_DELAY)

    logger.info("=== Starting ASGM data collection ===")

    _run("tone_theme", get_tone_timeline, theme=primary)
    _run("volume_theme", get_volume_timeline, theme=primary)

    for kw in KEYWORD_QUERIES:
        safe = kw.replace('"', "").replace(" ", "_").replace("-", "_").lower()
        _run(f"tone_kw_{safe}", get_tone_timeline, keyword=kw)

    _run("countries_theme", get_country_timeline, theme=primary)

    for theme_id in COMPARISON_THEMES:
        safe = theme_id.lower()
        _run(f"tone_cmp_{safe}", get_tone_timeline, theme=theme_id)

    _run("recent_articles", get_recent_articles, theme=primary)

    logger.info("=== Collection complete: %d datasets ===", len(results))
    return results


# ---------------------------------------------------------------------------
# Smoke test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    print("Smoke test: tone timeline for WB_555, Jan 2024")
    df = get_tone_timeline(
        theme=THEMES["primary"],
        start_date="2024-01-01",
        end_date="2024-01-31",
    )
    print(f"Shape: {df.shape}")
    print(f"Columns: {df.columns.tolist()}")
    print(df.to_string())
