# ASM Media Sentiment Dashboard

A Streamlit dashboard tracking how global media has covered **artisanal and small-scale mining (ASM)** from January 2017 to the present, using sentiment data from the [GDELT Project](https://www.gdeltproject.org/).

**Live app:** [asm-sentiment.streamlit.app](https://asm-sentiment.streamlit.app)

---

## What it shows

| Section | Description |
|---|---|
| Sentiment Trend | Daily tone + 30-day rolling average, 2017–present, with key event annotations |
| Coverage Volume | Raw article count and normalised per-100k GDELT corpus |
| Coverage by Country | Volume intensity by source country (top N, rolling average) |
| Keyword Sentiment | Tone comparison across seven ASM-related keyword searches |
| Recent Articles | The 250 most recent articles matched by GDELT (last ~3 months) |
| Annual Context | ASM sentiment vs. large-scale mining, gold, extractives, and deforestation |

## Data source

**GDELT DOC 2.0 API** — a real-time index of news media across hundreds of thousands of outlets in 65+ languages. Articles are filtered using GDELT's GKG theme tag **WB_555 — Artisanal and Small-Scale Mining** (World Bank taxonomy), applied automatically by GDELT's entity-recognition system.

**Sentiment metric:** GDELT's average tone score — a composite from 40+ sentiment dictionaries applied to full article text. Scores are roughly −10 (most negative) to +10 (most positive); values near zero indicate neutral or mixed coverage.

Data covers January 2017 to present (~3 400 daily observations). Cached as parquet files in `data/` and committed to this repo so the live app loads instantly.

## Running locally

```bash
# Install dependencies
pip install -r requirements.txt

# Start the dashboard
streamlit run src/app.py
```

The app loads from the cached parquet files in `data/`. To pull fresh data from GDELT, click **"Refresh data from GDELT"** in the sidebar (~60–90 seconds for all queries).

## Refreshing the data

The live app serves whatever is in the `data/` directory. To update it:

1. Run the app locally and click **Refresh data from GDELT**
2. Commit and push the updated parquet files:

```bash
git add data/
git commit -m "Refresh GDELT data"
git push
```

Streamlit Cloud picks up the new files automatically.

## Project structure

```
src/
  app.py              # Streamlit dashboard
  analysis.py         # Rolling averages, volume normalisation, country analysis
  data_collection.py  # GDELT DOC API client and caching
  config.py           # Themes, keywords, date range, key events
data/
  *.parquet           # Cached GDELT query results
scripts/
  export_charts.py    # Export dashboard charts as presentation PNGs
  create_deck.py      # Generate a .pptx slide deck from the exported charts
```

## Notes

- **Source country** in GDELT reflects where a publication is registered, not the story's subject country.
- The WB_555 theme tag has a false-positive rate of roughly 40% (off-topic mining articles), but the noise is stable over time so trend comparisons remain valid.
- Per-article tone scores are not available from the DOC API; `timelinetone` returns a pre-computed daily aggregate only.
