"""
Streamlit dashboard for ASGM media sentiment analysis.
Data is fetched from GDELT DOC API (via data_collection.py) and cached
locally as parquet files. API calls happen only when the cache is cold
or the user explicitly refreshes.
"""

import sys
import os

sys.path.insert(0, os.path.dirname(__file__))

import streamlit as st
import plotly.graph_objects as go
import plotly.express as px
import pandas as pd

from config import KEY_EVENTS, THEMES, KEYWORD_QUERIES, COMPARISON_THEMES, DATE_RANGE
import analysis
from data_collection import (
    collect_all_data,
    get_tone_timeline,
    load_cached,
)

# ---------------------------------------------------------------------------
# Page config
# ---------------------------------------------------------------------------

st.set_page_config(
    page_title="ASM Media Sentiment",
    page_icon="⛏",
    layout="wide",
)

st.title("Artisanal and Small-Scale Mining — Media Sentiment Analysis")
st.markdown(
    """
    This dashboard tracks how global media has covered **artisanal and small-scale mining (ASM)**
    from January 2017 to the present, using sentiment data from the
    [GDELT Project](https://www.gdeltproject.org/).

    **Data source:** GDELT DOC 2.0 API — a free, real-time index of news media monitored across
    hundreds of thousands of outlets in over 65 languages. GDELT assigns each article a
    *tone score* using a battery of 40+ sentiment dictionaries applied to the full article text
    (or machine-translated text for non-English sources).

    **Filter:** Articles are selected using GDELT's GKG theme tag
    **WB_555 — Artisanal and Small-Scale Mining** (World Bank taxonomy). This tag is applied
    automatically by GDELT's entity-recognition system to articles whose content matches the
    ASM theme. It covers all metals and minerals, not only gold.

    **Sentiment metric:** GDELT's *average tone* score — the mean across all matched articles
    for a given day. Scores are roughly −10 to +10 in practice; negative means coverage
    uses more negative-sentiment language (conflict, harm, illegal activity, deaths) and
    positive means more positive language (investment, growth, reform, success).
    A score near zero indicates neutral or mixed coverage.
    """
)

# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

@st.cache_data(ttl=86_400, show_spinner=False)
def load_data() -> dict:
    return collect_all_data()


with st.sidebar:
    st.header("Controls")

    rolling_window = st.slider("Smoothing window (days)", 7, 180, 30)

    st.divider()
    if st.button("Refresh data from GDELT", type="secondary"):
        st.cache_data.clear()
        st.rerun()

    st.caption(
        "Data is cached locally for 24 hours. "
        "Refresh pulls fresh data from the GDELT DOC API (~60 s)."
    )

with st.spinner("Loading data (first run fetches from GDELT — may take ~60 s)…"):
    data = load_data()

tone_theme = data.get("tone_theme", pd.DataFrame())
volume_theme = data.get("volume_theme", pd.DataFrame())
country_theme = data.get("countries_theme", pd.DataFrame())
recent_articles = data.get("recent_articles", pd.DataFrame())

# keyword tone DataFrames — used in keyword comparison section
kw_tones: dict[str, pd.DataFrame] = {
    kw: data.get(
        f"tone_kw_{kw.replace('\"','').replace(' ','_').replace('-','_').lower()}",
        pd.DataFrame(),
    )
    for kw in KEYWORD_QUERIES
}

# comparison theme DataFrames — used in annual context section
cmp_tones: dict[str, pd.DataFrame] = {
    label: data.get(f"tone_cmp_{theme_id.lower()}", pd.DataFrame())
    for theme_id, label in COMPARISON_THEMES.items()
}

# ---------------------------------------------------------------------------
# Section 1: Tone trend
# ---------------------------------------------------------------------------

st.header("Sentiment Trend (2017–present)")

if tone_theme.empty:
    st.warning("No tone data available. Try refreshing.")
else:
    rolled = analysis.compute_rolling_sentiment(tone_theme, window=rolling_window)

    fig = go.Figure()

    # Daily raw tone — light, semi-transparent
    fig.add_trace(go.Scatter(
        x=rolled["datetime"],
        y=rolled[analysis.TONE_COL],
        mode="lines",
        name="Daily tone",
        opacity=0.25,
        line=dict(color="#5b9bd5", width=1),
        hovertemplate="%{x|%Y-%m-%d}: %{y:.2f}<extra>Daily</extra>",
    ))

    # Rolling average — main signal
    fig.add_trace(go.Scatter(
        x=rolled["datetime"],
        y=rolled["tone_rolling"],
        mode="lines",
        name=f"{rolling_window}-day rolling avg",
        line=dict(color="#1f4e79", width=2.5),
        hovertemplate="%{x|%Y-%m-%d}: %{y:.2f}<extra>Rolling avg</extra>",
    ))

    # Zero line
    fig.add_hline(y=0, line_dash="dash", line_color="gray", line_width=1,
                  annotation_text="Neutral", annotation_position="bottom right")

    # Key event annotations
    for date_str, label in KEY_EVENTS.items():
        fig.add_vline(
            x=pd.Timestamp(date_str).value // 10**6,  # ms since epoch (Plotly datetime axis)
            line_dash="dot",
            line_color="crimson",
            line_width=1,
            annotation_text=label,
            annotation_position="top left",
            annotation_font_size=10,
            annotation_font_color="crimson",
        )

    fig.update_layout(
        yaxis_title="Average Tone (negative ← 0 → positive)",
        xaxis_title="",
        xaxis=dict(range=["2017-01-01", tone_theme["datetime"].max()]),
        hovermode="x unified",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
        height=420,
        margin=dict(t=60, b=40),
    )
    st.plotly_chart(fig, use_container_width=True)

    # Annual summary table
    with st.expander("Annual summary"):
        annual = analysis.compute_annual_summary(
            tone_theme,
            volume_theme if not volume_theme.empty else None,
        )
        annual_display = annual.copy()
        for col in ["mean_tone", "median_tone", "std_tone", "min_tone", "max_tone"]:
            if col in annual_display.columns:
                annual_display[col] = annual_display[col].map("{:+.2f}".format)
        st.dataframe(annual_display, use_container_width=True)

# ---------------------------------------------------------------------------
# Section 2: Coverage volume
# ---------------------------------------------------------------------------

st.header("Coverage Volume")

if volume_theme.empty:
    st.warning("No volume data available.")
else:
    norm_vol = analysis.normalise_volume(volume_theme)

    col1, col2 = st.columns(2)

    with col1:
        fig_raw = px.bar(
            norm_vol,
            x="datetime",
            y=analysis.COUNT_COL,
            title="Raw article count (WB_555 theme)",
            labels={analysis.COUNT_COL: "Articles", "datetime": ""},
            color_discrete_sequence=["#5b9bd5"],
        )
        fig_raw.update_layout(height=320, margin=dict(t=40, b=20))
        st.plotly_chart(fig_raw, use_container_width=True)

    with col2:
        fig_norm = px.bar(
            norm_vol,
            x="datetime",
            y="articles_per_100k",
            title="Normalised: articles per 100k GDELT corpus",
            labels={"articles_per_100k": "Per 100k articles", "datetime": ""},
            color_discrete_sequence=["#2e75b6"],
        )
        fig_norm.update_layout(height=320, margin=dict(t=40, b=20))
        st.plotly_chart(fig_norm, use_container_width=True)

# ---------------------------------------------------------------------------
# Section 3: Country breakdown
# ---------------------------------------------------------------------------

st.header("Coverage by Country")

st.caption(
    "**What is Volume Intensity?** GDELT's source-country metric is not a raw article count. "
    "It measures how intensely each country's publications covered ASM on a given day, "
    "normalised against that country's total presence in the GDELT corpus. "
    "A value of 10 means ASM stories made up a relatively high share of that country's monitored output. "
    "This corrects for the fact that large English-language publishers (US, UK, Australia) "
    "produce far more total articles, so their raw counts would otherwise dominate. "
    "**Note:** country reflects where the publication is registered, not the story's subject country."
)

if country_theme.empty:
    st.warning("No country data available. Try refreshing.")
else:
    n_countries = st.slider("Number of countries to show", 3, 15, 8)
    tops = analysis.top_countries(country_theme, n=n_countries)
    melted = analysis.melt_country_df(country_theme, tops, rolling_window=rolling_window)

    st.markdown(
        f"**ASM coverage intensity by source country — {rolling_window}-day rolling average "
        f"(top {n_countries})**"
    )
    fig_ctry = px.line(
        melted,
        x="datetime",
        y="intensity",
        color="country",
        labels={"intensity": "Volume intensity", "datetime": "", "country": "Country"},
    )
    fig_ctry.update_traces(line=dict(width=1.5))
    fig_ctry.update_layout(
        height=420,
        margin=dict(t=20, b=20),
        hovermode="x unified",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
    )
    st.plotly_chart(fig_ctry, use_container_width=True)

# ---------------------------------------------------------------------------
# Section 4: Keyword comparison
# ---------------------------------------------------------------------------

st.header("ASM Keyword Sentiment Comparison")

available_kws = {kw: df for kw, df in kw_tones.items() if not df.empty}

if not available_kws:
    st.warning("No keyword tone data available.")
else:
    fig_kw = go.Figure()
    colours = px.colors.qualitative.Plotly

    for i, (kw, df) in enumerate(available_kws.items()):
        rolled_kw = analysis.compute_rolling_sentiment(df, window=rolling_window)
        label = kw.strip('"')
        fig_kw.add_trace(go.Scatter(
            x=rolled_kw["datetime"],
            y=rolled_kw["tone_rolling"],
            mode="lines",
            name=label,
            line=dict(color=colours[i % len(colours)], width=1.8),
            hovertemplate=f"%{{x|%Y-%m-%d}}: %{{y:.2f}}<extra>{label}</extra>",
        ))

    # Start x-axis after the rolling window to avoid unstable early values
    kw_x_start = pd.Timestamp("2017-01-01", tz="UTC") + pd.Timedelta(days=rolling_window)

    # Compute y-axis range from the visible data (after x clip) with 10% padding
    all_rolled = [
        analysis.compute_rolling_sentiment(df, window=rolling_window)
        for df in available_kws.values()
    ]
    visible = pd.concat([
        r[r["datetime"] >= kw_x_start]["tone_rolling"] for r in all_rolled
    ]).dropna()
    y_pad = (visible.max() - visible.min()) * 0.10
    y_range = [visible.min() - y_pad, visible.max() + y_pad]

    fig_kw.add_hline(y=0, line_dash="dash", line_color="gray", line_width=1)
    fig_kw.update_layout(
        yaxis_title=f"Average Tone ({rolling_window}-day rolling)",
        yaxis=dict(range=y_range),
        xaxis_title="",
        xaxis=dict(range=[kw_x_start, pd.Timestamp.now()]),
        hovermode="x unified",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
        height=400,
        margin=dict(t=40, b=20),
    )
    st.plotly_chart(fig_kw, use_container_width=True)

# ---------------------------------------------------------------------------
# Section 5: Recent articles
# ---------------------------------------------------------------------------

st.header("Recent Articles (Last 3 Months)")

if recent_articles.empty:
    st.info("No recent article data. Refresh to fetch from GDELT.")
else:
    display_cols = [c for c in ["seendate", "title", "domain", "sourcecountry", "url"]
                    if c in recent_articles.columns]
    articles_display = recent_articles[display_cols].copy()

    if "seendate" in articles_display.columns:
        articles_display["seendate"] = (
            pd.to_datetime(articles_display["seendate"], format="%Y%m%dT%H%M%SZ", utc=True)
            .dt.strftime("%Y-%m-%d")
        )

    st.dataframe(
        articles_display,
        use_container_width=True,
        column_config={
            "url": st.column_config.LinkColumn("URL"),
            "seendate": st.column_config.TextColumn("Date"),
            "title": st.column_config.TextColumn("Title", width="large"),
            "sourcecountry": st.column_config.TextColumn("Source country"),
        },
        hide_index=True,
    )
    st.caption(
        f"{len(recent_articles)} articles shown. GDELT artlist mode covers the most recent ~3 months only. "
        "**Note:** 'Source country' reflects where the publication is registered, not the story's subject country — "
        "e.g. allafrica.com stories appear as Nigeria regardless of the country covered."
    )

# ---------------------------------------------------------------------------
# Section 6: Annual sentiment in context
# ---------------------------------------------------------------------------

st.header("Annual Sentiment in Context")
st.markdown(
    "How does ASM media sentiment compare with other mining and resource-extraction themes? "
    "Annual averages only — daily granularity is not meaningful at this scale."
)

available_cmp = {k: v for k, v in cmp_tones.items() if not v.empty}

if not available_cmp and tone_theme.empty:
    st.warning("No comparison data available. Refresh to fetch from GDELT.")
else:
    # Build the ASM entry plus any available comparison themes
    all_themes = {"ASM (WB_555)": tone_theme, **available_cmp}
    cmp_df = analysis.build_annual_comparison(
        {k: v for k, v in all_themes.items() if not v.empty}
    )

    # Drop incomplete current year to avoid misleading partial-year bars
    current_year = pd.Timestamp.now().year
    cmp_df = cmp_df[cmp_df["year"] < current_year]

    if cmp_df.empty:
        st.info("Comparison data is loading — refresh the page in a moment.")
    else:
        st.markdown("**Mean annual tone by theme (GDELT, 2017–present)**")
        fig_cmp = px.bar(
            cmp_df,
            x="year",
            y="mean_tone",
            color="theme",
            barmode="group",
            labels={"mean_tone": "Mean tone", "year": "Year", "theme": "Theme"},
            color_discrete_sequence=px.colors.qualitative.Safe,
        )
        fig_cmp.add_hline(y=0, line_dash="dash", line_color="gray", line_width=1)
        fig_cmp.update_layout(
            height=420,
            margin=dict(t=20, b=20),
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
            xaxis=dict(tickmode="linear", dtick=1),
        )
        st.plotly_chart(fig_cmp, use_container_width=True)

        # Summary table
        with st.expander("Annual comparison table"):
            pivot = cmp_df.pivot(index="year", columns="theme", values="mean_tone")
            st.dataframe(pivot.style.format("{:+.2f}"), use_container_width=True)

        st.caption(
            "Tone scores are GDELT's pre-computed daily averages, aggregated annually. "
            "Scores reflect the language used in articles matching each theme — "
            "negative does not necessarily mean 'anti' the topic, but that coverage "
            "tends to use more negative-sentiment words (conflict, harm, loss, etc.)."
        )
