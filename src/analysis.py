"""
Analysis functions for ASGM sentiment data.

Expected column names (from data_collection.py live API output):
  tone_df:    datetime, "Average Tone"
  volume_df:  datetime, "Article Count", "All Articles"
  country_df: datetime, <country_name>, ... (one column per country)
"""

import pandas as pd


# ---------------------------------------------------------------------------
# Tone analysis
# ---------------------------------------------------------------------------

TONE_COL = "Average Tone"
COUNT_COL = "Article Count"
TOTAL_COL = "All Articles"


def compute_rolling_sentiment(tone_df: pd.DataFrame, window: int = 30) -> pd.DataFrame:
    """
    Add a rolling-average tone column to a tone DataFrame.
    Returns a copy with a new 'tone_rolling' column.
    """
    df = tone_df.copy().sort_values("datetime").reset_index(drop=True)
    df["tone_rolling"] = df[TONE_COL].rolling(window=window, min_periods=1).mean()
    return df


def compute_annual_summary(
    tone_df: pd.DataFrame,
    volume_df: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """
    Aggregate tone and (optionally) volume by calendar year.
    Returns a DataFrame indexed by year.
    """
    df = tone_df.copy().sort_values("datetime")
    df["year"] = df["datetime"].dt.year

    annual = df.groupby("year")[TONE_COL].agg(
        mean_tone="mean",
        median_tone="median",
        std_tone="std",
        min_tone="min",
        max_tone="max",
        days_with_data="count",
    )

    if volume_df is not None:
        vdf = volume_df.copy()
        vdf["year"] = pd.to_datetime(vdf["datetime"]).dt.year
        vol_annual = vdf.groupby("year")[COUNT_COL].sum().rename("total_articles")
        annual = annual.join(vol_annual)

    return annual


def identify_tone_shifts(
    tone_df: pd.DataFrame,
    rolling_window: int = 90,
    threshold: float = 1.5,
) -> pd.DataFrame:
    """
    Return rows where the daily tone deviates significantly from the
    90-day rolling mean (more than threshold * rolling stdev).
    Useful for finding candidate dates to annotate on the chart.
    """
    df = compute_rolling_sentiment(tone_df.copy(), window=rolling_window)
    df["deviation"] = df[TONE_COL] - df["tone_rolling"]
    rolling_std = df["deviation"].std()
    df["significant_shift"] = df["deviation"].abs() > (rolling_std * threshold)
    return df[df["significant_shift"]].copy()


# ---------------------------------------------------------------------------
# Volume analysis
# ---------------------------------------------------------------------------

def normalise_volume(volume_df: pd.DataFrame) -> pd.DataFrame:
    """
    Add a 'articles_per_100k' column: matching articles as a fraction of
    the total GDELT corpus that day, scaled to per-100k articles.
    This corrects for GDELT's expanding source base over time.
    """
    df = volume_df.copy().sort_values("datetime").reset_index(drop=True)
    df["articles_per_100k"] = df.apply(
        lambda row: (row[COUNT_COL] / row[TOTAL_COL] * 100_000)
        if row[TOTAL_COL] > 0 else 0,
        axis=1,
    )
    return df


# ---------------------------------------------------------------------------
# Country analysis
# ---------------------------------------------------------------------------

_INTENSITY_SUFFIX = " Volume Intensity"


def _strip_suffix(name: str) -> str:
    return name.removesuffix(_INTENSITY_SUFFIX)


def top_countries(country_df: pd.DataFrame, n: int = 10) -> list[str]:
    """
    Return the n raw column names (with GDELT suffix) with the highest
    cumulative volume intensity across the full time range.
    """
    cols = [c for c in country_df.columns if c != "datetime"]
    totals = country_df[cols].sum().sort_values(ascending=False)
    return totals.head(n).index.tolist()


def build_annual_comparison(theme_dfs: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """
    Given a dict of {label: tone_df}, return a tidy DataFrame with columns
    [year, theme, mean_tone] suitable for a grouped bar chart.
    Only includes years where ALL themes have data.
    """
    rows = []
    for label, df in theme_dfs.items():
        if df.empty:
            continue
        d = df.copy()
        d["year"] = pd.to_datetime(d["datetime"]).dt.year
        annual = d.groupby("year")[TONE_COL].mean().reset_index()
        annual.columns = ["year", "mean_tone"]
        annual["theme"] = label
        rows.append(annual)
    if not rows:
        return pd.DataFrame(columns=["year", "theme", "mean_tone"])
    return pd.concat(rows, ignore_index=True).sort_values(["year", "theme"])


def melt_country_df(
    country_df: pd.DataFrame,
    countries: list[str],
    rolling_window: int = 1,
) -> pd.DataFrame:
    """
    Reshape wide country DataFrame to long form, strip the ' Volume Intensity'
    suffix, and apply optional per-country rolling average.
    Returns columns: datetime, country, intensity.
    """
    subset = country_df[["datetime"] + countries].copy()
    subset["datetime"] = pd.to_datetime(subset["datetime"])
    subset = subset.sort_values("datetime").reset_index(drop=True)

    if rolling_window > 1:
        for col in countries:
            subset[col] = subset[col].rolling(window=rolling_window, min_periods=1).mean()

    melted = subset.melt(id_vars="datetime", var_name="country", value_name="intensity")
    melted["country"] = melted["country"].apply(_strip_suffix)
    return melted.sort_values(["country", "datetime"]).reset_index(drop=True)
