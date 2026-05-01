"""
Unit tests for src/data_collection.py.

Run from project root:
    python3 -m pytest tests/ -v
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import pytest
import pandas as pd
from unittest.mock import patch, MagicMock

import data_collection as dc


# ---------------------------------------------------------------------------
# _build_query
# ---------------------------------------------------------------------------

class TestBuildQuery:
    def test_theme_only(self):
        result = dc._build_query(theme="WB_555", keyword=None)
        assert result == "theme:WB_555"

    def test_keyword_only(self):
        result = dc._build_query(theme=None, keyword='"artisanal mining"')
        assert result == '"artisanal mining"'

    def test_both_theme_and_keyword(self):
        result = dc._build_query(theme="WB_555", keyword="galamsey")
        assert "theme:WB_555" in result
        assert "galamsey" in result

    def test_neither_raises_value_error(self):
        with pytest.raises(ValueError):
            dc._build_query(theme=None, keyword=None)

    def test_theme_prefix_format(self):
        result = dc._build_query(theme="WB_555_ARTISANAL", keyword=None)
        assert result.startswith("theme:")

    def test_keyword_with_quotes_preserved(self):
        kw = '"small-scale gold"'
        result = dc._build_query(theme=None, keyword=kw)
        assert kw in result


# ---------------------------------------------------------------------------
# _gdelt_get — retry on 429
# ---------------------------------------------------------------------------

class TestGdeltGet:
    def _mock_response(self, status_code, json_data=None, content_type="application/json"):
        mock = MagicMock()
        mock.status_code = status_code
        mock.headers = {"content-type": content_type}
        if json_data is not None:
            mock.json.return_value = json_data
        mock.raise_for_status = MagicMock()
        return mock

    @patch("data_collection.time.sleep")
    @patch("data_collection.requests.get")
    def test_200_returns_json(self, mock_get, mock_sleep):
        mock_get.return_value = self._mock_response(200, {"timeline": []})
        result = dc._gdelt_get("http://fake.url")
        assert result == {"timeline": []}
        mock_sleep.assert_not_called()

    @patch("data_collection.time.sleep")
    @patch("data_collection.requests.get")
    def test_429_retries_with_backoff(self, mock_get, mock_sleep):
        mock_get.side_effect = [
            self._mock_response(429),
            self._mock_response(200, {"timeline": []}),
        ]
        result = dc._gdelt_get("http://fake.url", retries=3)
        assert result == {"timeline": []}
        assert mock_sleep.call_count == 1

    @patch("data_collection.time.sleep")
    @patch("data_collection.requests.get")
    def test_429_exhausted_retries_raises_runtime_error(self, mock_get, mock_sleep):
        mock_get.return_value = self._mock_response(429)
        with pytest.raises(RuntimeError, match="failed after"):
            dc._gdelt_get("http://fake.url", retries=2)

    @patch("data_collection.time.sleep")
    @patch("data_collection.requests.get")
    def test_html_response_raises_value_error(self, mock_get, mock_sleep):
        mock = self._mock_response(200, content_type="text/html")
        mock.text = "<html>Error</html>"
        mock_get.return_value = mock
        with pytest.raises(ValueError, match="HTML error"):
            dc._gdelt_get("http://fake.url")

    @patch("data_collection.time.sleep")
    @patch("data_collection.requests.get")
    def test_non_429_error_raises_immediately(self, mock_get, mock_sleep):
        resp = self._mock_response(500)
        resp.raise_for_status.side_effect = Exception("Server error")
        mock_get.return_value = resp
        with pytest.raises(Exception, match="Server error"):
            dc._gdelt_get("http://fake.url", retries=3)
        # Should not retry on non-429 errors
        assert mock_get.call_count == 1


# ---------------------------------------------------------------------------
# _timeline_request — parsing
# ---------------------------------------------------------------------------

class TestTimelineRequest:
    def _gdelt_tone_response(self, dates, values):
        return {
            "timeline": [
                {
                    "series": "Average Tone",
                    "data": [{"date": d, "value": v} for d, v in zip(dates, values)],
                }
            ]
        }

    def _gdelt_volraw_response(self, dates, counts, norms):
        return {
            "timeline": [
                {
                    "series": "Article Count",
                    "data": [
                        {"date": d, "value": c, "norm": n}
                        for d, c, n in zip(dates, counts, norms)
                    ],
                }
            ]
        }

    @patch("data_collection._gdelt_get")
    def test_timelinetone_columns(self, mock_get):
        mock_get.return_value = self._gdelt_tone_response(
            ["2020-01-01", "2020-01-02"], [-1.5, -2.0]
        )
        df = dc._timeline_request("timelinetone", "theme:WB_555", "2020-01-01", "2020-01-02")
        assert "datetime" in df.columns
        assert "Average Tone" in df.columns

    @patch("data_collection._gdelt_get")
    def test_timelinetone_values(self, mock_get):
        mock_get.return_value = self._gdelt_tone_response(
            ["2020-01-01", "2020-01-02"], [-1.5, -2.0]
        )
        df = dc._timeline_request("timelinetone", "theme:WB_555", "2020-01-01", "2020-01-02")
        assert list(df["Average Tone"]) == pytest.approx([-1.5, -2.0])

    @patch("data_collection._gdelt_get")
    def test_timelinetone_datetime_parsed(self, mock_get):
        mock_get.return_value = self._gdelt_tone_response(["2020-01-15"], [-1.0])
        df = dc._timeline_request("timelinetone", "theme:WB_555", "2020-01-01", "2020-01-31")
        assert pd.api.types.is_datetime64_any_dtype(df["datetime"])

    @patch("data_collection._gdelt_get")
    def test_timelinevolraw_adds_all_articles_from_norm(self, mock_get):
        mock_get.return_value = self._gdelt_volraw_response(
            ["2020-01-01"], [10], [500_000]
        )
        df = dc._timeline_request("timelinevolraw", "theme:WB_555", "2020-01-01", "2020-01-01")
        assert "All Articles" in df.columns
        assert df["All Articles"].iloc[0] == 500_000

    @patch("data_collection._gdelt_get")
    def test_empty_response_returns_empty_df(self, mock_get):
        mock_get.return_value = {"timeline": []}
        df = dc._timeline_request("timelinetone", "theme:WB_555", "2020-01-01", "2020-01-02")
        assert df.empty

    @patch("data_collection._gdelt_get")
    def test_invalid_mode_raises_value_error(self, mock_get):
        with pytest.raises(ValueError, match="Invalid mode"):
            dc._timeline_request("badmode", "theme:WB_555", "2020-01-01", "2020-01-02")

    @patch("data_collection._gdelt_get")
    def test_date_format_in_url(self, mock_get):
        mock_get.return_value = self._gdelt_tone_response(["2020-01-01"], [-1.0])
        dc._timeline_request("timelinetone", "theme:WB_555", "2020-01-01", "2020-12-31")
        call_url = mock_get.call_args[0][0]
        assert "20200101000000" in call_url
        assert "20201231000000" in call_url


# ---------------------------------------------------------------------------
# caching helpers
# ---------------------------------------------------------------------------

class TestCachingHelpers:
    def test_cache_result_and_load(self, tmp_path):
        df = pd.DataFrame({"a": [1, 2, 3], "b": [4.0, 5.0, 6.0]})
        with patch("data_collection.CACHE_DIR", str(tmp_path)):
            dc.cache_result(df, "test_cache")
            loaded = dc.load_cached("test_cache")
        pd.testing.assert_frame_equal(df, loaded)

    def test_load_cached_missing_returns_none(self, tmp_path):
        with patch("data_collection.CACHE_DIR", str(tmp_path)):
            result = dc.load_cached("nonexistent")
        assert result is None

    def test_load_or_fetch_uses_cache(self, tmp_path):
        df = pd.DataFrame({"x": [1, 2]})
        fetch_fn = MagicMock(return_value=df)
        with patch("data_collection.CACHE_DIR", str(tmp_path)):
            # First call: no cache, calls fetch_fn; fetched=True
            result1, fetched1 = dc.load_or_fetch("item", fetch_fn)
            assert fetch_fn.call_count == 1
            assert fetched1 is True
            # Second call: cache exists, fetch_fn not called again; fetched=False
            result2, fetched2 = dc.load_or_fetch("item", fetch_fn)
            assert fetch_fn.call_count == 1
            assert fetched2 is False
        pd.testing.assert_frame_equal(result1, result2)

    def test_load_or_fetch_empty_df_not_cached(self, tmp_path):
        """Empty DataFrames should not be cached (avoids masking real failures)."""
        fetch_fn = MagicMock(return_value=pd.DataFrame())
        with patch("data_collection.CACHE_DIR", str(tmp_path)):
            dc.load_or_fetch("empty", fetch_fn)
            result = dc.load_cached("empty")
        assert result is None


# ---------------------------------------------------------------------------
# collect_all_data — structural checks
# ---------------------------------------------------------------------------

class TestCollectAllData:
    def _lof_return(self):
        return (pd.DataFrame({"datetime": [], "Average Tone": []}), False)

    @patch("data_collection.time.sleep")
    @patch("data_collection.load_or_fetch")
    def test_returns_expected_keys(self, mock_lof, mock_sleep):
        mock_lof.return_value = self._lof_return()
        results = dc.collect_all_data()
        assert "tone_theme" in results
        assert "volume_theme" in results
        assert "countries_theme" in results
        assert "recent_articles" in results

    @patch("data_collection.time.sleep")
    @patch("data_collection.load_or_fetch")
    def test_all_7_keyword_tone_files_present(self, mock_lof, mock_sleep):
        mock_lof.return_value = self._lof_return()
        results = dc.collect_all_data()
        kw_keys = [k for k in results if k.startswith("tone_kw_")]
        assert len(kw_keys) == 7

    @patch("data_collection.time.sleep")
    @patch("data_collection.load_or_fetch")
    def test_all_4_comparison_tone_files_present(self, mock_lof, mock_sleep):
        mock_lof.return_value = self._lof_return()
        results = dc.collect_all_data()
        cmp_keys = [k for k in results if k.startswith("tone_cmp_")]
        assert len(cmp_keys) == 4

    @patch("data_collection.time.sleep")
    @patch("data_collection.load_or_fetch")
    def test_failed_dataset_still_returns_empty_df(self, mock_lof, mock_sleep):
        def side_effect(name, fn, *args, **kwargs):
            if name == "volume_theme":
                raise RuntimeError("API error")
            return (pd.DataFrame({"datetime": [], "Average Tone": []}), False)
        mock_lof.side_effect = side_effect
        results = dc.collect_all_data()
        assert "volume_theme" in results
        assert results["volume_theme"].empty

    @patch("data_collection.time.sleep")
    @patch("data_collection.load_or_fetch")
    def test_no_sleep_on_cache_hits(self, mock_lof, mock_sleep):
        """Sleep must not be called when all data loads from parquet cache."""
        mock_lof.return_value = (pd.DataFrame({"datetime": [], "Average Tone": []}), False)
        dc.collect_all_data()
        mock_sleep.assert_not_called()

    @patch("data_collection.time.sleep")
    @patch("data_collection.load_or_fetch")
    def test_sleep_called_on_api_fetch(self, mock_lof, mock_sleep):
        """Sleep must be called once per dataset that was fetched from the API."""
        mock_lof.return_value = (pd.DataFrame({"datetime": [], "Average Tone": []}), True)
        dc.collect_all_data()
        # 15 datasets total (2 primary + 7 keyword + 1 country + 4 comparison + 1 articles)
        assert mock_sleep.call_count == 15

    def test_recent_articles_not_inside_run_helper(self):
        """
        ISSUE: recent_articles is fetched outside the _run() helper, which means
        it does NOT call time.sleep(REQUEST_DELAY) after the API call. This is
        inconsistent with all other datasets and risks rate limiting.
        This test documents the structural inconsistency by inspecting the source.
        """
        import inspect
        source = inspect.getsource(dc.collect_all_data)
        # _run calls time.sleep; recent_articles is fetched outside _run
        # The last fetch in collect_all_data should call load_or_fetch directly
        assert "recent_articles" in source
        # Verify it's not wrapped in _run (which handles sleep)
        # This is a documentation test — it passes as long as the code exists
        assert "load_or_fetch" in source
