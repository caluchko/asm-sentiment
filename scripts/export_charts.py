"""
Export dashboard charts as static PNG files for presentations.
Run from the project root: python3 scripts/export_charts.py
Output goes to exports/
"""

import sys
import os

sys.path.insert(0, "src")

import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
import plotly.io as pio
from plotly.subplots import make_subplots

from config import KEY_EVENTS, COMPARISON_THEMES
import analysis

# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------

OUTPUT_DIR = "exports"
os.makedirs(OUTPUT_DIR, exist_ok=True)

# Presentation defaults
WIDTH = 1600
HEIGHT = 850
SCALE = 2          # render at 2× then downsample → crisp at 150 dpi equivalent
ROLLING_WINDOW = 30
N_COUNTRIES = 8

FONT_FAMILY = "Arial, sans-serif"
FONT_SIZE_TITLE = 18
FONT_SIZE_AXIS = 14
FONT_SIZE_TICK = 12
FONT_SIZE_LEGEND = 12
FONT_SIZE_ANNOTATION = 11

# Title x-position aligns with left edge of the plot area:
# left margin (80px) / total width (1600px) = 0.05 in paper coordinates
TITLE_X = 80 / WIDTH

LAYOUT_BASE = dict(
    font=dict(family=FONT_FAMILY, size=FONT_SIZE_TICK),
    paper_bgcolor="white",
    plot_bgcolor="white",
    margin=dict(t=90, b=60, l=80, r=40),
    legend=dict(
        orientation="h",
        yanchor="bottom",
        y=1.02,
        xanchor="left",
        x=0,
        font=dict(size=FONT_SIZE_LEGEND),
    ),
)

TITLE_STYLE = dict(font=dict(size=FONT_SIZE_TITLE), x=TITLE_X, xanchor="left")


def save(fig: go.Figure, name: str) -> str:
    path = os.path.join(OUTPUT_DIR, f"{name}.png")
    fig.write_image(path, width=WIDTH, height=HEIGHT, scale=SCALE)
    print(f"  Saved → {path}")
    return path


# ---------------------------------------------------------------------------
# Load data
# ---------------------------------------------------------------------------

print("Loading cached data...")
tone = pd.read_parquet("data/tone_theme.parquet")
volume = pd.read_parquet("data/volume_theme.parquet")
country = pd.read_parquet("data/countries_theme.parquet")

kw_files = {
    '"artisanal mining"':   "data/tone_kw_artisanal_mining.parquet",
    '"small-scale mining"': "data/tone_kw_small_scale_mining.parquet",
    '"small-scale gold"':   "data/tone_kw_small_scale_gold.parquet",
    "ASGM":                 "data/tone_kw_asgm.parquet",
    "galamsey":             "data/tone_kw_galamsey.parquet",
    "garimpeiro":           "data/tone_kw_garimpeiro.parquet",
    "orpaillage":           "data/tone_kw_orpaillage.parquet",
}
kw_tones = {
    kw: pd.read_parquet(path)
    for kw, path in kw_files.items()
    if os.path.exists(path)
}

cmp_tones = {
    label: pd.read_parquet(f"data/tone_cmp_{theme_id.lower()}.parquet")
    for theme_id, label in COMPARISON_THEMES.items()
    if os.path.exists(f"data/tone_cmp_{theme_id.lower()}.parquet")
}

# ---------------------------------------------------------------------------
# Chart 1: Sentiment Trend
# ---------------------------------------------------------------------------

print("\nChart 1: Sentiment Trend")

rolled = analysis.compute_rolling_sentiment(tone, window=ROLLING_WINDOW)

fig1 = go.Figure()

fig1.add_trace(go.Scatter(
    x=rolled["datetime"],
    y=rolled[analysis.TONE_COL],
    mode="lines",
    name="Daily tone",
    opacity=0.20,
    line=dict(color="#5b9bd5", width=1),
    hoverinfo="skip",
))

fig1.add_trace(go.Scatter(
    x=rolled["datetime"],
    y=rolled["tone_rolling"],
    mode="lines",
    name=f"{ROLLING_WINDOW}-day rolling average",
    line=dict(color="#1f4e79", width=2.5),
))

fig1.add_hline(
    y=0,
    line_dash="dash",
    line_color="gray",
    line_width=1,
    annotation_text="Neutral",
    annotation_position="bottom right",
    annotation_font_size=FONT_SIZE_ANNOTATION,
)

# Annotations to the right of each vline so text stays inside the plot area
for date_str, label in KEY_EVENTS.items():
    fig1.add_vline(
        x=pd.Timestamp(date_str).value // 10**6,
        line_dash="dot",
        line_color="crimson",
        line_width=1,
        annotation_text=label,
        annotation_position="top right",
        annotation_font_size=FONT_SIZE_ANNOTATION,
        annotation_font_color="crimson",
    )

# Tighten y-axis: 2nd–98th percentile clips extreme outliers
daily = rolled[analysis.TONE_COL].dropna()
y_lo = daily.quantile(0.02)
y_hi = daily.quantile(0.98)
y_pad = (y_hi - y_lo) * 0.15
y_range = [y_lo - y_pad, y_hi + y_pad]

fig1.update_layout(
    **LAYOUT_BASE,
    title=dict(
        text="Artisanal and Small-Scale Mining — Media Sentiment (2017–present)",
        **TITLE_STYLE,
    ),
    yaxis=dict(
        title="Average Tone (negative ← 0 → positive)",
        title_font=dict(size=FONT_SIZE_AXIS),
        tickfont=dict(size=FONT_SIZE_TICK),
        gridcolor="#eeeeee",
        range=y_range,
    ),
    xaxis=dict(
        range=["2017-01-01", tone["datetime"].max()],
        tickfont=dict(size=FONT_SIZE_TICK),
        gridcolor="#eeeeee",
    ),
    hovermode="x unified",
    height=HEIGHT,
)

save(fig1, "01_sentiment_trend")

# ---------------------------------------------------------------------------
# Chart 2: Coverage Volume
# ---------------------------------------------------------------------------

print("\nChart 2: Coverage Volume")

norm_vol = analysis.normalise_volume(volume)

fig2 = make_subplots(
    rows=1, cols=2,
    subplot_titles=("Raw article count", "Normalised: articles per 100 000 GDELT corpus"),
    horizontal_spacing=0.10,
)

fig2.add_trace(go.Bar(
    x=norm_vol["datetime"],
    y=norm_vol[analysis.COUNT_COL],
    marker=dict(color="#0d47a1", line=dict(width=0)),
    showlegend=False,
), row=1, col=1)

fig2.add_trace(go.Bar(
    x=norm_vol["datetime"],
    y=norm_vol["articles_per_100k"],
    marker=dict(color="#0a2d6e", line=dict(width=0)),
    showlegend=False,
), row=1, col=2)

fig2.update_layout(
    **LAYOUT_BASE,
    title=dict(
        text="ASM Coverage Volume — WB_555 Theme (2017–present)",
        **TITLE_STYLE,
    ),
    bargap=0,
    height=HEIGHT,
)
fig2.update_xaxes(tickfont=dict(size=FONT_SIZE_TICK), gridcolor="#eeeeee", showgrid=True)
fig2.update_yaxes(tickfont=dict(size=FONT_SIZE_TICK), gridcolor="#eeeeee", showgrid=True)
fig2.update_yaxes(
    title_text="Articles", title_font=dict(size=FONT_SIZE_AXIS), row=1, col=1
)
fig2.update_yaxes(
    title_text="Per 100k articles", title_font=dict(size=FONT_SIZE_AXIS), row=1, col=2
)

save(fig2, "02_coverage_volume")

# ---------------------------------------------------------------------------
# Chart 3: Coverage by Country
# ---------------------------------------------------------------------------

print("\nChart 3: Coverage by Country")

tops = analysis.top_countries(country, n=N_COUNTRIES)
melted = analysis.melt_country_df(country, tops, rolling_window=ROLLING_WINDOW)

colours = px.colors.qualitative.Plotly
fig3 = go.Figure()

for i, ctry in enumerate(melted["country"].unique()):
    subset = melted[melted["country"] == ctry]
    fig3.add_trace(go.Scatter(
        x=subset["datetime"],
        y=subset["intensity"],
        mode="lines",
        name=ctry,
        line=dict(color=colours[i % len(colours)], width=1.8),
    ))

# Annotate each country's peak with its name
for ctry in melted["country"].unique():
    subset = melted[melted["country"] == ctry].dropna(subset=["intensity"])
    if subset.empty:
        continue
    peak_row = subset.loc[subset["intensity"].idxmax()]
    fig3.add_annotation(
        x=peak_row["datetime"],
        y=peak_row["intensity"],
        text=f"<b>{ctry}</b>",
        showarrow=True,
        arrowhead=2,
        arrowsize=0.8,
        arrowwidth=1,
        arrowcolor="#555555",
        ax=0,
        ay=-28,
        font=dict(size=FONT_SIZE_ANNOTATION, family=FONT_FAMILY),
        bgcolor="rgba(255,255,255,0.85)",
        bordercolor="#cccccc",
        borderwidth=1,
    )

fig3.update_layout(
    **LAYOUT_BASE,
    title=dict(
        text=f"ASM Coverage Intensity by Source Country — {ROLLING_WINDOW}-day Rolling Average (top {N_COUNTRIES})",
        **TITLE_STYLE,
    ),
    yaxis=dict(
        title="Volume Intensity (0–100, within-country normalised)",
        title_font=dict(size=FONT_SIZE_AXIS),
        tickfont=dict(size=FONT_SIZE_TICK),
        gridcolor="#eeeeee",
    ),
    xaxis=dict(
        tickfont=dict(size=FONT_SIZE_TICK),
        gridcolor="#eeeeee",
    ),
    hovermode="x unified",
    height=HEIGHT,
)

save(fig3, "03_coverage_by_country")

# ---------------------------------------------------------------------------
# Chart 4: Keyword Sentiment Comparison
# ---------------------------------------------------------------------------

print("\nChart 4: Keyword Sentiment Comparison")

fig4 = go.Figure()

kw_x_start = pd.Timestamp("2017-01-01", tz="UTC") + pd.Timedelta(days=ROLLING_WINDOW)

all_rolled_kw = []
for kw, df in kw_tones.items():
    rolled_kw = analysis.compute_rolling_sentiment(df, window=ROLLING_WINDOW)
    all_rolled_kw.append(rolled_kw)
    label = kw.strip('"')
    is_galamsey = (label == "galamsey")
    fig4.add_trace(go.Scatter(
        x=rolled_kw["datetime"],
        y=rolled_kw["tone_rolling"],
        mode="lines",
        name=label,
        line=dict(
            color="#d62728" if is_galamsey else "#bbbbbb",
            width=3.5 if is_galamsey else 1.2,
        ),
        opacity=1.0 if is_galamsey else 0.65,
    ))

fig4.add_hline(y=0, line_dash="dash", line_color="gray", line_width=1)

# Dynamic y-axis from visible data with 10% padding
visible_kw = pd.concat([
    r[r["datetime"] >= kw_x_start]["tone_rolling"] for r in all_rolled_kw
]).dropna()
kw_y_pad = (visible_kw.max() - visible_kw.min()) * 0.10
kw_y_range = [visible_kw.min() - kw_y_pad, visible_kw.max() + kw_y_pad]

fig4.update_layout(
    **LAYOUT_BASE,
    title=dict(
        text=f"ASM Keyword Sentiment Comparison — {ROLLING_WINDOW}-day Rolling Average (2017–present)",
        **TITLE_STYLE,
    ),
    yaxis=dict(
        title=f"Average Tone ({ROLLING_WINDOW}-day rolling)",
        title_font=dict(size=FONT_SIZE_AXIS),
        tickfont=dict(size=FONT_SIZE_TICK),
        gridcolor="#eeeeee",
        range=kw_y_range,
    ),
    xaxis=dict(
        range=[kw_x_start, pd.Timestamp.now(tz="UTC")],
        tickfont=dict(size=FONT_SIZE_TICK),
        gridcolor="#eeeeee",
    ),
    hovermode="x unified",
    height=HEIGHT,
)

save(fig4, "04_keyword_sentiment")

# ---------------------------------------------------------------------------
# Chart 5: Annual Sentiment in Context
# ---------------------------------------------------------------------------

print("\nChart 5: Annual Sentiment in Context")

all_themes = {"ASM (WB_555)": tone, **cmp_tones}
cmp_df = analysis.build_annual_comparison(
    {k: v for k, v in all_themes.items() if not v.empty}
)

current_year = pd.Timestamp.now().year
cmp_df = cmp_df[cmp_df["year"] < current_year]

fig5 = px.bar(
    cmp_df,
    x="year",
    y="mean_tone",
    color="theme",
    barmode="group",
    labels={"mean_tone": "Mean annual tone", "year": "Year", "theme": "Theme"},
    color_discrete_sequence=px.colors.qualitative.Safe,
)

fig5.add_hline(y=0, line_dash="dash", line_color="gray", line_width=1)

fig5.update_layout(
    **LAYOUT_BASE,
    title=dict(
        text="Annual Media Sentiment by Theme — GDELT (2017–present)",
        **TITLE_STYLE,
    ),
    yaxis=dict(
        title="Mean annual tone",
        title_font=dict(size=FONT_SIZE_AXIS),
        tickfont=dict(size=FONT_SIZE_TICK),
        gridcolor="#eeeeee",
    ),
    xaxis=dict(
        tickmode="linear",
        dtick=1,
        tickfont=dict(size=FONT_SIZE_TICK),
        gridcolor="#eeeeee",
    ),
    height=HEIGHT,
)

save(fig5, "05_annual_context")

print("\nDone. All charts saved to exports/")
