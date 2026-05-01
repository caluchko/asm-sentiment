"""
Unit tests for src/analysis.py.

Run from project root:
    python3 -m pytest tests/ -v
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import pytest
import pandas as pd
import numpy as np

import analysis


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_tone_df(dates, tones):
    return pd.DataFrame({
        "datetime": pd.to_datetime(dates, utc=True),
        "Average Tone": tones,
    })


def make_volume_df(dates, counts, totals):
    return pd.DataFrame({
        "datetime": pd.to_datetime(dates, utc=True),
        "Article Count": counts,
        "All Articles": totals,
    })


def make_country_df(dates, countries_data):
    """countries_data: {col_name: [values]}"""
    df = pd.DataFrame({"datetime": pd.to_datetime(dates, utc=True)})
    for col, vals in countries_data.items():
        df[col] = vals
    return df


# ---------------------------------------------------------------------------
# compute_rolling_sentiment
# ---------------------------------------------------------------------------

class TestComputeRollingSentiment:
    def test_adds_tone_rolling_column(self):
        df = make_tone_df(["2020-01-01", "2020-01-02", "2020-01-03"], [-1.0, -2.0, -3.0])
        result = analysis.compute_rolling_sentiment(df, window=3)
        assert "tone_rolling" in result.columns

    def test_does_not_mutate_input(self):
        df = make_tone_df(["2020-01-01", "2020-01-02"], [-1.0, -2.0])
        original_cols = list(df.columns)
        analysis.compute_rolling_sentiment(df, window=2)
        assert list(df.columns) == original_cols

    def test_window_1_equals_original(self):
        tones = [-1.0, -2.0, -3.0]
        df = make_tone_df(["2020-01-01", "2020-01-02", "2020-01-03"], tones)
        result = analysis.compute_rolling_sentiment(df, window=1)
        assert list(result["tone_rolling"]) == tones

    def test_rolling_mean_calculated_correctly(self):
        tones = [10.0, 20.0, 30.0]
        df = make_tone_df(["2020-01-01", "2020-01-02", "2020-01-03"], tones)
        result = analysis.compute_rolling_sentiment(df, window=2)
        # window=2, min_periods=1: row 0=10.0, row 1=mean(10,20)=15.0, row 2=mean(20,30)=25.0
        expected = [10.0, 15.0, 25.0]
        assert list(result["tone_rolling"]) == pytest.approx(expected)

    def test_sorts_unsorted_input_by_datetime(self):
        df = pd.DataFrame({
            "datetime": pd.to_datetime(["2020-01-03", "2020-01-01", "2020-01-02"], utc=True),
            "Average Tone": [30.0, 10.0, 20.0],
        })
        result = analysis.compute_rolling_sentiment(df, window=1)
        assert list(result["Average Tone"]) == [10.0, 20.0, 30.0]

    def test_min_periods_1_no_nans_at_start(self):
        tones = [-1.0, -2.0, -3.0, -4.0, -5.0]
        df = make_tone_df(
            [f"2020-01-0{i+1}" for i in range(5)], tones
        )
        result = analysis.compute_rolling_sentiment(df, window=30)
        # min_periods=1 means no NaN values even with window > len
        assert result["tone_rolling"].isna().sum() == 0


# ---------------------------------------------------------------------------
# compute_annual_summary
# ---------------------------------------------------------------------------

class TestComputeAnnualSummary:
    def test_groups_by_year(self):
        df = make_tone_df(
            ["2020-06-15", "2020-12-31", "2021-01-01", "2021-06-01"],
            [-1.0, -3.0, -2.0, -4.0],
        )
        result = analysis.compute_annual_summary(df)
        assert set(result.index) == {2020, 2021}

    def test_mean_tone_correct(self):
        df = make_tone_df(["2020-01-01", "2020-01-02"], [-2.0, -4.0])
        result = analysis.compute_annual_summary(df)
        assert result.loc[2020, "mean_tone"] == pytest.approx(-3.0)

    def test_days_with_data_count(self):
        df = make_tone_df(
            ["2020-01-01", "2020-01-02", "2020-01-03"],
            [-1.0, -2.0, -3.0],
        )
        result = analysis.compute_annual_summary(df)
        assert result.loc[2020, "days_with_data"] == 3

    def test_with_volume_adds_total_articles(self):
        tone = make_tone_df(["2020-01-01", "2020-01-02"], [-1.0, -2.0])
        vol = make_volume_df(["2020-01-01", "2020-01-02"], [10, 20], [1000, 1000])
        result = analysis.compute_annual_summary(tone, vol)
        assert "total_articles" in result.columns
        assert result.loc[2020, "total_articles"] == 30

    def test_without_volume_no_total_articles(self):
        tone = make_tone_df(["2020-01-01"], [-1.0])
        result = analysis.compute_annual_summary(tone)
        assert "total_articles" not in result.columns

    def test_all_stat_columns_present(self):
        df = make_tone_df(["2020-01-01", "2020-01-02"], [-1.0, -2.0])
        result = analysis.compute_annual_summary(df)
        for col in ["mean_tone", "median_tone", "std_tone", "min_tone", "max_tone", "days_with_data"]:
            assert col in result.columns


# ---------------------------------------------------------------------------
# identify_tone_shifts
# ---------------------------------------------------------------------------

class TestIdentifyToneShifts:
    def test_returns_dataframe_subset(self):
        tones = list(range(-10, 10))
        dates = [f"2020-01-{i+1:02d}" for i in range(20)]
        df = make_tone_df(dates, [float(t) for t in tones])
        result = analysis.identify_tone_shifts(df)
        assert len(result) < len(df)

    def test_higher_threshold_fewer_shifts(self):
        tones = list(range(-20, 20))
        dates = pd.date_range("2020-01-01", periods=len(tones), freq="D").strftime("%Y-%m-%d").tolist()
        df = make_tone_df(dates, [float(t) for t in tones])
        strict = analysis.identify_tone_shifts(df, threshold=3.0)
        loose = analysis.identify_tone_shifts(df, threshold=0.5)
        assert len(strict) <= len(loose)

    def test_all_identical_tones_no_shifts(self):
        tones = [-1.0] * 100
        dates = pd.date_range("2020-01-01", periods=100, freq="D").strftime("%Y-%m-%d").tolist()
        df = make_tone_df(dates, tones)
        result = analysis.identify_tone_shifts(df)
        assert result.empty

    def test_significant_shift_column_present(self):
        tones = list(range(-20, 20))
        dates = pd.date_range("2020-01-01", periods=len(tones), freq="D").strftime("%Y-%m-%d").tolist()
        df = make_tone_df(dates, [float(t) for t in tones])
        result = analysis.identify_tone_shifts(df)
        assert "significant_shift" in result.columns

    def test_uses_global_std_not_rolling_std(self):
        """
        ISSUE: The docstring says 'threshold * rolling stdev' but the
        implementation uses the global std of all deviations.
        This test documents the current actual behavior.
        """
        tones = [0.0] * 90 + [100.0]
        dates = pd.date_range("2020-01-01", periods=91, freq="D").strftime("%Y-%m-%d").tolist()
        df = make_tone_df(dates, tones)
        result = analysis.identify_tone_shifts(df, rolling_window=90, threshold=1.5)
        # The last point (100.0) should be a significant shift
        assert not result.empty


# ---------------------------------------------------------------------------
# normalise_volume
# ---------------------------------------------------------------------------

class TestNormaliseVolume:
    def test_adds_articles_per_100k_column(self):
        df = make_volume_df(["2020-01-01"], [50], [100_000])
        result = analysis.normalise_volume(df)
        assert "articles_per_100k" in result.columns

    def test_correct_calculation(self):
        # 50 / 100_000 * 100_000 = 50.0
        df = make_volume_df(["2020-01-01"], [50], [100_000])
        result = analysis.normalise_volume(df)
        assert result["articles_per_100k"].iloc[0] == pytest.approx(50.0)

    def test_scaling(self):
        # 1 / 1_000_000 * 100_000 = 0.1
        df = make_volume_df(["2020-01-01"], [1], [1_000_000])
        result = analysis.normalise_volume(df)
        assert result["articles_per_100k"].iloc[0] == pytest.approx(0.1)

    def test_zero_total_returns_nan(self):
        """Zero corpus size (data gap) returns NaN, not 0."""
        df = make_volume_df(["2020-01-01"], [5], [0])
        result = analysis.normalise_volume(df)
        assert pd.isna(result["articles_per_100k"].iloc[0])

    def test_does_not_mutate_input(self):
        df = make_volume_df(["2020-01-01"], [50], [100_000])
        original_cols = list(df.columns)
        analysis.normalise_volume(df)
        assert list(df.columns) == original_cols


# ---------------------------------------------------------------------------
# top_countries
# ---------------------------------------------------------------------------

class TestTopCountries:
    def test_returns_top_n(self):
        df = make_country_df(
            ["2020-01-01", "2020-01-02"],
            {
                "Ghana Volume Intensity": [10, 10],
                "Mali Volume Intensity": [5, 5],
                "Peru Volume Intensity": [1, 1],
            },
        )
        result = analysis.top_countries(df, n=2)
        assert len(result) == 2

    def test_sorted_by_cumulative_descending(self):
        df = make_country_df(
            ["2020-01-01", "2020-01-02"],
            {
                "Ghana Volume Intensity": [10, 10],   # sum=20
                "Mali Volume Intensity": [5, 5],       # sum=10
                "Peru Volume Intensity": [1, 1],       # sum=2
            },
        )
        result = analysis.top_countries(df, n=3)
        assert result[0] == "Ghana Volume Intensity"
        assert result[1] == "Mali Volume Intensity"
        assert result[2] == "Peru Volume Intensity"

    def test_excludes_datetime_column(self):
        df = make_country_df(
            ["2020-01-01"],
            {"Ghana Volume Intensity": [100]},
        )
        result = analysis.top_countries(df, n=10)
        assert "datetime" not in result

    def test_n_larger_than_countries(self):
        df = make_country_df(
            ["2020-01-01"],
            {"Ghana Volume Intensity": [10], "Mali Volume Intensity": [5]},
        )
        result = analysis.top_countries(df, n=100)
        assert len(result) == 2  # only 2 countries available


# ---------------------------------------------------------------------------
# melt_country_df
# ---------------------------------------------------------------------------

class TestMeltCountryDf:
    def setup_method(self):
        self.dates = ["2020-01-01", "2020-01-02", "2020-01-03"]
        self.df = make_country_df(
            self.dates,
            {
                "Ghana Volume Intensity": [10.0, 20.0, 30.0],
                "Mali Volume Intensity": [5.0, 10.0, 15.0],
            },
        )

    def test_output_columns(self):
        result = analysis.melt_country_df(self.df, ["Ghana Volume Intensity"])
        assert set(result.columns) == {"datetime", "country", "intensity"}

    def test_strips_volume_intensity_suffix(self):
        result = analysis.melt_country_df(self.df, ["Ghana Volume Intensity"])
        assert "Ghana" in result["country"].values
        assert "Ghana Volume Intensity" not in result["country"].values

    def test_rolling_window_1_no_change(self):
        result = analysis.melt_country_df(self.df, ["Ghana Volume Intensity"], rolling_window=1)
        ghana = result[result["country"] == "Ghana"].sort_values("datetime")
        assert list(ghana["intensity"]) == pytest.approx([10.0, 20.0, 30.0])

    def test_rolling_window_applied(self):
        result = analysis.melt_country_df(self.df, ["Ghana Volume Intensity"], rolling_window=2)
        ghana = result[result["country"] == "Ghana"].sort_values("datetime")
        # window=2, min_periods=1: [10.0, mean(10,20)=15.0, mean(20,30)=25.0]
        assert list(ghana["intensity"]) == pytest.approx([10.0, 15.0, 25.0])

    def test_multiple_countries(self):
        result = analysis.melt_country_df(
            self.df, ["Ghana Volume Intensity", "Mali Volume Intensity"]
        )
        assert set(result["country"].unique()) == {"Ghana", "Mali"}


# ---------------------------------------------------------------------------
# build_annual_comparison
# ---------------------------------------------------------------------------

class TestBuildAnnualComparison:
    def test_basic_structure(self):
        df = make_tone_df(
            ["2020-01-01", "2020-06-01", "2021-01-01"],
            [-1.0, -2.0, -3.0],
        )
        result = analysis.build_annual_comparison({"Theme A": df})
        assert set(result.columns) == {"year", "theme", "mean_tone"}

    def test_correct_mean_tone(self):
        df = make_tone_df(["2020-01-01", "2020-07-01"], [-2.0, -4.0])
        result = analysis.build_annual_comparison({"Theme A": df})
        row = result[result["year"] == 2020]
        assert row["mean_tone"].iloc[0] == pytest.approx(-3.0)

    def test_empty_input_returns_empty_df(self):
        result = analysis.build_annual_comparison({})
        assert result.empty
        assert list(result.columns) == ["year", "theme", "mean_tone"]

    def test_empty_dataframe_skipped(self):
        df = make_tone_df(["2020-01-01"], [-1.0])
        result = analysis.build_annual_comparison({"Good": df, "Empty": pd.DataFrame()})
        assert "Empty" not in result["theme"].values
        assert "Good" in result["theme"].values

    def test_multiple_themes(self):
        df_a = make_tone_df(["2020-01-01"], [-1.0])
        df_b = make_tone_df(["2020-01-01"], [-3.0])
        result = analysis.build_annual_comparison({"Theme A": df_a, "Theme B": df_b})
        assert set(result["theme"].unique()) == {"Theme A", "Theme B"}

    def test_partial_years_filtered_to_common_only(self):
        """Years present in only a subset of themes are excluded."""
        df_a = make_tone_df(["2017-01-01", "2018-01-01"], [-1.0, -2.0])  # 2017 + 2018
        df_b = make_tone_df(["2018-01-01"], [-3.0])                        # 2018 only
        result = analysis.build_annual_comparison({"Theme A": df_a, "Theme B": df_b})
        years_in_result = set(result["year"].unique())
        # 2017 should be excluded because Theme B has no 2017 data
        assert 2017 not in years_in_result
        assert 2018 in years_in_result

    def test_sorted_by_year_and_theme(self):
        df = make_tone_df(
            ["2021-01-01", "2020-01-01"],
            [-1.0, -2.0],
        )
        result = analysis.build_annual_comparison({"A": df})
        assert list(result["year"]) == [2020, 2021]
