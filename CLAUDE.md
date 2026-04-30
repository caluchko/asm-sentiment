# ASGM Sentiment Analysis — Project State

## What this project is

A GDELT DOC 2.0-based tool for analysing media sentiment toward artisanal and small-scale gold mining (ASGM) from 2017 to present. Output: a Streamlit dashboard showing tone trends, article volume, country breakdowns, and key event annotations. Full plan in `asgm-sentiment-plan.md`.

## Running the app

```bash
streamlit run src/app.py   # served on http://localhost:8501
```

Data is cached as parquet in `data/`. First run fetches from GDELT (~60–90 s for all queries). Subsequent runs load from cache. "Refresh data from GDELT" button in the sidebar clears the cache and re-fetches.

## Implementation status

### Done — all working

- `requirements.txt` — gdeltdoc, pandas, plotly, streamlit, requests, pyarrow
- `src/config.py` — themes, keywords, comparison themes, date range, country list, key events, `REQUEST_DELAY = 6`
- `src/data_collection.py` — GDELT client (see gotchas below); caching via parquet; `collect_all_data()` fetches all datasets with per-dataset error handling
- `src/analysis.py` — `compute_rolling_sentiment`, `compute_annual_summary`, `identify_tone_shifts`, `normalise_volume`, `top_countries`, `melt_country_df`, `build_annual_comparison`
- `src/app.py` — six-section Streamlit dashboard (details below)
- `scripts/body_text_vader_analysis.py` — one-off validation script (not part of the app)

### Cached data (14 parquet files in `data/`)

| File | Contents |
|---|---|
| `tone_theme.parquet` | Daily avg tone, WB_555 theme, 2017–present |
| `volume_theme.parquet` | Daily article count + total corpus count, WB_555 |
| `countries_theme.parquet` | Daily Volume Intensity per country (146 countries), WB_555 |
| `recent_articles.parquet` | 250 most recent articles (last ~3 months), WB_555 |
| `tone_kw_*.parquet` | Daily tone for 7 keyword queries |
| `tone_cmp_*.parquet` | Daily tone for 4 comparison themes |

### Dashboard sections

1. **Sentiment Trend** — daily tone (faint) + rolling average (bold); key event vertical annotations; annual summary table in expander
2. **Coverage Volume** — raw article count + normalised per-100k (two-column bar charts)
3. **Coverage by Country** — line chart, rolling average applied via sidebar slider; Volume Intensity explained in caption; top-N countries selectable; " Volume Intensity" suffix stripped from display labels
4. **Keyword Sentiment Comparison** — rolling average lines for all 7 keyword queries
5. **Recent Articles** — dates parsed from `20260219T073000Z` format to `2026-02-19`; clickable URL links; sourcecountry caveat noted
6. **Annual Sentiment in Context** — grouped bar chart comparing ASGM (WB_555) vs metal ore mining, gold broadly, all extractives, deforestation; current year excluded; pivot table in expander

### Not yet started

- Formatting/design changes to the dashboard (user to specify on return)
- Static graphics for a presentation (user to specify on return)

## GDELT API gotchas (must know before touching data_collection.py)

**gdeltdoc library bug:** `_filter_to_string()` in v1.12.0 appends a trailing space after every filter value → GDELT returns 429. We bypass the library's URL construction entirely in `_timeline_request()` and `_artlist_request()`.

**User-Agent matters:** Use `_HEADERS` with the gdeltdoc library UA (`"GDELT DOC Python API client 1.12.0 - https://github.com/alex9smith/gdelt-doc-api"`). Generic UAs are throttled harder.

**Rate limiting:** Burst of ~8+ requests causes a 15+ minute IP block. `REQUEST_DELAY = 6` between calls. The artlist endpoint throttles more aggressively than timeline endpoints.

**GDELT timeline JSON structure is nested:**
```
{"timeline": [{"series": "Average Tone", "data": [{"date": "...", "value": N}]}]}
```

**GDELT OR syntax requires parentheses:** `("artisanal mining" OR galamsey OR ...)`

**Column names from live API:**
- `timelinetone` → `["datetime", "Average Tone"]`
- `timelinevolraw` → `["datetime", "Article Count", "All Articles"]`
- `timelinesourcecountry` → `["datetime", "<Country> Volume Intensity", ...]` — one col per country, values are 0–100 normalised intensity scores (not raw counts, not tone)

**Plotly `add_vline` with datetime axis:** Pass `pd.Timestamp(date_str).value // 10**6` (milliseconds since epoch), not a raw string — newer Plotly versions iterate over string characters and crash.

## Key data findings

- **Tone**: Persistently negative overall (mean -0.665, 60% of days negative). 2023 anomaly — median = 0, least negative year. 2025 reverted to near-2017 levels. Modest long-run improvement: 2017-18 mean -0.86 → 2024-25 mean -0.65.
- **Country coverage**: Ghana dominates by cumulative intensity (1702), followed by Zambia, Zimbabwe, Liberia, DRC. `sourcecountry` in artlist reflects publication registration, not story subject — allafrica.com always shows Nigeria.
- **WB_555 false positive rate**: ~40% of articles are off-topic (lithium, silver, unrelated mining). Noise is stable over time so trend comparisons remain valid.
- **Per-article tone**: Not available from DOC API. `timelinetone` is a pre-computed daily aggregate only. Per-article scores available via BigQuery GKG (Phase 2).
- **Country mode data**: Volume Intensity, not article counts or tone. Each value is a within-country normalised ratio (0–100).
