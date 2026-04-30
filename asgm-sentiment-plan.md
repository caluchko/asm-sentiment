# ASGM Media Sentiment Analysis — Phase 1 Implementation Plan

## Project Goal

Analyse how media perceptions of artisanal and small-scale gold mining (ASGM) have changed over time, using the GDELT project's DOC 2.0 API to retrieve news coverage data and its built-in tone metrics. The output is a Python tool (likely Streamlit) that visualises sentiment trends, volume, and geographic patterns for ASGM-related news coverage from 2017 to present.

## Context for Claude Code

This plan was scoped in a conversation with the user. Key decisions already made:

- **Data source**: GDELT DOC 2.0 API (free, no auth required), accessed via the `gdeltdoc` Python library
- **Primary filter**: The GDELT GKG theme `WB_555_ARTISANAL_AND_SMALL_SCALE_MINING` (World Bank taxonomy tag for ASGM, ~34K tagged articles in the full GDELT corpus)
- **Supplementary filters**: Keyword-based queries for terms GDELT's theme tagger may miss
- **Sentiment metric**: GDELT's built-in "tone" score (avg tone from -100 to +100, computed via 40+ sentiment dictionaries)
- **Approach**: Start with the DOC API's timeline modes for aggregate trends, then pull article lists for validation
- **Output format**: Streamlit dashboard (user is familiar with Streamlit from prior UNEP projects)

## Technical Stack

- Python 3.10+
- `gdeltdoc` — Python wrapper for the GDELT DOC 2.0 API (pip install gdeltdoc)
- `pandas` — data manipulation
- `plotly` — interactive charts
- `streamlit` — dashboard UI
- `requests` — for any direct API calls if needed

## Important: DOC API Constraints

1. **Timeline modes** (timelinetone, timelinevol, etc.) search from **January 2017 to present** — this is the full historical window available.
2. **Article list mode** only returns articles from the **most recent 3 months** of any search window. So you can get tone *trends* going back to 2017, but individual article URLs only for the recent period.
3. **Max 250 articles** per article list request.
4. The `gdeltdoc` library's `Filters` object expects `start_date` and `end_date` in `YYYY-MM-DD` format. The library docs say the API "officially only supports the most recent 3 months" for article lists, but timeline modes work over the full range.
5. **No authentication required** — the API is open.
6. **Rate limiting**: Be respectful. Add small delays between requests. The API doesn't publish formal rate limits but will throttle aggressive use.

## Project Structure

```
asgm-sentiment/
├── README.md
├── requirements.txt
├── src/
│   ├── config.py          # Search terms, themes, date ranges, constants
│   ├── data_collection.py # Functions to query GDELT DOC API
│   ├── analysis.py        # Data processing, aggregation, statistics
│   └── app.py             # Streamlit dashboard
├── data/                  # Cached query results (CSV/parquet)
│   └── .gitkeep
└── notebooks/             # Optional: exploratory Jupyter notebooks
    └── exploration.ipynb
```

## Implementation Steps

### Step 1: Define Search Configuration (`config.py`)

Create a central config defining all the query parameters.

```python
# GDELT GKG Themes relevant to ASGM
THEMES = {
    "primary": "WB_555_ARTISANAL_AND_SMALL_SCALE_MINING",
    "broader": [
        "ENV_MINING",
        "WB_1699_METAL_ORE_MINING",
        "WB_2936_GOLD",
        "WB_2898_EXTRACTIVE_INDUSTRIES",
    ]
}

# Keyword queries to catch articles the theme tagger may miss.
# These are used as gdeltdoc Filters `keyword` values.
# The DOC API does full-text search on these.
KEYWORD_QUERIES = [
    '"artisanal mining"',
    '"small-scale mining"',
    '"small-scale gold"',
    "ASGM",
    "galamsey",           # Ghana-specific term
    "garimpeiro",         # Brazil-specific term
    "orpaillage",         # Francophone Africa term
]

# Date range — full DOC API timeline window
DATE_RANGE = {
    "start": "2017-01-01",
    "end": None,  # None = up to present
}

# Countries of particular interest for ASGM
# (FIPS 2-letter codes used by GDELT)
ASGM_COUNTRIES = [
    "GH",  # Ghana
    "CO",  # Colombia
    "PE",  # Peru
    "PH",  # Philippines
    "ID",  # Indonesia
    "TZ",  # Tanzania
    "KE",  # Kenya
    "BF",  # Burkina Faso
    "ML",  # Mali
    "GY",  # Guyana
    "SR",  # Suriname
    "MN",  # Mongolia
    "BO",  # Bolivia
    "EC",  # Ecuador
    "BR",  # Brazil
]
```

### Step 2: Data Collection (`data_collection.py`)

Build functions to query each of the DOC API's timeline modes, plus article lists.

**Key queries to run:**

#### 2a. Tone Timeline (primary deliverable)

```python
from gdeltdoc import GdeltDoc, Filters

def get_tone_timeline(theme=None, keyword=None, start_date="2017-01-01",
                      end_date=None, country=None):
    """
    Returns a DataFrame of average tone over time for matching articles.
    Use EITHER theme or keyword (not both — the API ANDs all filters).
    """
    filter_kwargs = {
        "start_date": start_date,
        "theme": theme,
        "keyword": keyword,
        "country": country,
    }
    if end_date:
        filter_kwargs["end_date"] = end_date
    else:
        # Use timespan instead for "up to now"
        filter_kwargs.pop("start_date", None)
        filter_kwargs["timespan"] = "FULL"  # see note below

    # Remove None values
    filter_kwargs = {k: v for k, v in filter_kwargs.items() if v is not None}

    f = Filters(**filter_kwargs)
    gd = GdeltDoc()
    return gd.timeline_search("timelinetone", f)
```

> **Important note on timespan**: The `gdeltdoc` library may not support arbitrary timespans gracefully. You may need to test whether passing `start_date="2017-01-01"` and `end_date` as today's date works for timeline modes. If the library complains, try constructing the API URL directly with `requests`. The raw API URL pattern is:
> ```
> https://api.gdeltproject.org/api/v2/doc/doc?query=theme:WB_555_ARTISANAL_AND_SMALL_SCALE_MINING&mode=timelinetone&startdatetime=20170101000000&enddatetime=20260428000000&format=json
> ```

#### 2b. Volume Timeline

```python
def get_volume_timeline(theme=None, keyword=None, **kwargs):
    """Number of matching articles over time."""
    f = Filters(theme=theme, keyword=keyword, **kwargs)
    gd = GdeltDoc()
    # timelinevolraw gives actual counts (not percentages)
    return gd.timeline_search("timelinevolraw", f)
```

#### 2c. Volume by Source Country

```python
def get_country_timeline(theme=None, keyword=None, **kwargs):
    """Article volume broken down by source country."""
    f = Filters(theme=theme, keyword=keyword, **kwargs)
    gd = GdeltDoc()
    return gd.timeline_search("timelinesourcecountry", f)
```

#### 2d. Article List (recent 3 months only)

```python
def get_recent_articles(theme=None, keyword=None, num_records=250):
    """
    Fetch actual article URLs/titles for the most recent 3 months.
    Useful for validation and qualitative review.
    """
    f = Filters(
        theme=theme,
        keyword=keyword,
        num_records=num_records,
    )
    gd = GdeltDoc()
    return gd.article_search(f)
```

#### 2e. Combined Query Strategy

Run these queries in sequence to build a comprehensive dataset:

```python
import time
import pandas as pd

def collect_all_data():
    """Master collection function. Runs all queries and caches results."""
    results = {}

    # 1. Theme-based tone timeline (highest precision)
    print("Fetching tone timeline for WB_555 theme...")
    results["tone_theme"] = get_tone_timeline(
        theme="WB_555_ARTISANAL_AND_SMALL_SCALE_MINING"
    )
    time.sleep(2)

    # 2. Theme-based volume timeline
    print("Fetching volume timeline for WB_555 theme...")
    results["volume_theme"] = get_volume_timeline(
        theme="WB_555_ARTISANAL_AND_SMALL_SCALE_MINING"
    )
    time.sleep(2)

    # 3. Keyword-based queries for broader recall
    for kw in KEYWORD_QUERIES:
        safe_name = kw.replace('"', '').replace(' ', '_').lower()
        print(f"Fetching tone timeline for keyword: {kw}")
        results[f"tone_kw_{safe_name}"] = get_tone_timeline(keyword=kw)
        time.sleep(2)

    # 4. Country breakdown for the theme
    print("Fetching country breakdown...")
    results["countries_theme"] = get_country_timeline(
        theme="WB_555_ARTISANAL_AND_SMALL_SCALE_MINING"
    )
    time.sleep(2)

    # 5. Recent articles for validation
    print("Fetching recent articles...")
    results["recent_articles"] = get_recent_articles(
        theme="WB_555_ARTISANAL_AND_SMALL_SCALE_MINING"
    )

    return results
```

### Step 3: Analysis (`analysis.py`)

Process the raw timeline data into analysis-ready form.

```python
def compute_rolling_sentiment(tone_df, window=30):
    """
    Compute rolling average of tone to smooth daily noise.
    The tone_df from gdeltdoc has datetime index and a tone column.
    """
    tone_df = tone_df.copy()
    tone_df["tone_rolling"] = tone_df["tone"].rolling(window=window).mean()
    return tone_df


def compute_annual_summary(tone_df, volume_df):
    """
    Aggregate tone and volume by year for summary statistics.
    """
    tone_df["year"] = tone_df.index.year  # or tone_df["datetime"].dt.year
    annual = tone_df.groupby("year").agg(
        mean_tone=("tone", "mean"),
        median_tone=("tone", "median"),
        std_tone=("tone", "std"),
        min_tone=("tone", "min"),
        max_tone=("tone", "max"),
    )
    # Add volume counts if available
    if volume_df is not None:
        volume_df["year"] = volume_df.index.year
        vol_annual = volume_df.groupby("year")["value"].sum()
        annual = annual.join(vol_annual.rename("total_articles"))
    return annual


def identify_tone_shifts(tone_df, threshold=1.5):
    """
    Flag periods where tone shifts significantly from the rolling mean.
    Useful for annotating the timeline with notable events.
    """
    tone_df = compute_rolling_sentiment(tone_df, window=90)
    tone_df["deviation"] = tone_df["tone"] - tone_df["tone_rolling"]
    tone_df["significant_shift"] = tone_df["deviation"].abs() > (
        tone_df["deviation"].std() * threshold
    )
    return tone_df[tone_df["significant_shift"]]
```

### Step 4: Streamlit Dashboard (`app.py`)

Build the interactive dashboard.

```python
import streamlit as st
import plotly.express as px
import plotly.graph_objects as go

st.set_page_config(page_title="ASGM Media Sentiment", layout="wide")
st.title("ASGM Media Sentiment Analysis")
st.markdown("Tracking global media perceptions of artisanal and small-scale "
            "gold mining using GDELT data (2017–present)")

# Sidebar controls
st.sidebar.header("Filters")
query_type = st.sidebar.radio(
    "Query approach",
    ["Theme: WB_555 (ASGM)", "Keywords", "Compare both"]
)
rolling_window = st.sidebar.slider("Smoothing window (days)", 7, 180, 30)

# --- Section 1: Tone over time ---
st.header("Sentiment Trend")
# Plot the tone timeline with rolling average
# Use plotly for interactivity — dual axis with volume overlay

fig = go.Figure()
fig.add_trace(go.Scatter(
    x=tone_df.index, y=tone_df["tone"],
    mode="lines", name="Daily tone", opacity=0.3,
    line=dict(color="steelblue")
))
fig.add_trace(go.Scatter(
    x=tone_df.index, y=tone_df["tone_rolling"],
    mode="lines", name=f"{rolling_window}-day rolling avg",
    line=dict(color="darkblue", width=2)
))
fig.add_hline(y=0, line_dash="dash", line_color="gray",
              annotation_text="Neutral")
fig.update_layout(
    yaxis_title="Average Tone (negative ← → positive)",
    xaxis_title="Date",
    hovermode="x unified"
)
st.plotly_chart(fig, use_container_width=True)

# --- Section 2: Coverage volume ---
st.header("Coverage Volume")
# Bar chart or area chart of article counts over time

# --- Section 3: Geographic breakdown ---
st.header("Coverage by Country")
# Stacked area or heatmap of source countries over time

# --- Section 4: Keyword comparison ---
st.header("Term Comparison")
# Overlay tone timelines for different keyword queries
# e.g., "galamsey" vs "artisanal mining" vs "ASGM"

# --- Section 5: Recent articles ---
st.header("Recent Articles (Last 3 Months)")
# Sortable table of recent article URLs, titles, dates
# Link to source articles for qualitative validation

# --- Section 6: Key event annotations ---
st.header("Key Events Timeline")
# Manually curated list of ASGM milestones to overlay:
KEY_EVENTS = {
    "2017-08-16": "Minamata Convention enters into force",
    "2019-09-01": "planetGOLD programme launches",
    "2021-03-01": "Ghana galamsey crackdown intensifies",
    "2023-10-01": "Minamata COP-5",
    # Add more as needed
}
```

### Step 5: Caching and Persistence

The DOC API doesn't charge for queries, but responses can be slow for large time ranges. Cache all results locally.

```python
import os
import hashlib

CACHE_DIR = "data/"

def cache_result(df, query_name):
    """Save query result to parquet for reuse."""
    path = os.path.join(CACHE_DIR, f"{query_name}.parquet")
    df.to_parquet(path)
    return path

def load_cached(query_name):
    """Load cached result if available."""
    path = os.path.join(CACHE_DIR, f"{query_name}.parquet")
    if os.path.exists(path):
        return pd.read_parquet(path)
    return None
```

## Validation Checklist

Before trusting the results, validate:

1. **Relevance check**: Pull a sample of 50 recent articles from the WB_555 theme. Manually review titles — what percentage are actually about ASGM? Document the false positive rate.
2. **Keyword gap check**: Search for known ASGM articles (e.g., from planetGOLD news) and verify they appear in the GDELT results. If major stories are missing, adjust keywords.
3. **Tone sanity check**: For articles you can read in full, compare the GDELT tone score to your own assessment. Note any systematic biases (e.g., articles about mercury pollution will score negative on tone even if the article is about *progress* in reducing mercury use).
4. **Volume normalisation**: GDELT's total monitored volume has grown over time. A raw increase in ASGM article counts may reflect GDELT's expanding source base, not increased media interest. Use `timelinevol` (percentage of total) alongside `timelinevolraw` (absolute counts).

## Known Risks and Gotchas

- **`gdeltdoc` library maintenance**: The library was last actively maintained a few years ago. If it throws errors, you may need to fall back to direct HTTP requests to the DOC API. The URL pattern is well-documented and simple to construct.
- **Theme vs keyword overlap**: Articles tagged with `WB_555` may also match keyword queries. When combining results, deduplicate on article URL.
- **Tone ≠ framing**: A negative tone score doesn't mean "anti-ASGM" — it means the article contains more negative-sentiment words. An article about mercury poisoning harming miners will score very negative even if it's sympathetic to miners. This is a fundamental limitation of dictionary-based sentiment. Flag this clearly in any presentation of results.
- **Non-English coverage**: GDELT translates articles from 65 languages into English before analysis, so tone scores are computed on machine-translated text. Translation quality varies and may introduce sentiment artifacts.
- **API timeouts**: For very large date ranges, the API can time out. If this happens, split queries into yearly chunks and concatenate.

## Definition of Done (Phase 1)

- [ ] Successfully retrieve tone and volume timelines for WB_555 theme from 2017–present
- [ ] Successfully retrieve tone timelines for at least 3 keyword queries
- [ ] Retrieve and display country breakdown of coverage
- [ ] Retrieve recent article list for manual validation
- [ ] Streamlit app with at least: tone trend chart, volume chart, country breakdown, article table
- [ ] Cache all query results locally
- [ ] Document validation findings (relevance rate, tone accuracy)
- [ ] README with setup instructions

## Phase 2 Preview (for later)

Once Phase 1 is validated, Phase 2 would move to BigQuery for:
- Full GKG access with GCAM emotional dimensions (not just tone)
- Longer/richer historical data
- Source-level analysis (which outlets cover ASGM most?)
- Cross-referencing with the GDELT Event Database for specific ASGM-related events
- Enhanced NLP: fetching article text and running BERT or LLM-based sentiment for more nuanced framing analysis
