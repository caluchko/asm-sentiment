"""
Body-text scrape + VADER sentiment analysis.
Parses 250 article URLs from cached GDELT output, fetches body text via
trafilatura, classifies ASGM relevance, computes VADER compound scores,
and compares mean sentiment between relevant and non-relevant articles.
"""
import re
import time
import sys
import statistics

import trafilatura
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

CACHED_FILE = (
    "/Users/kennethdavis/.claude/projects/"
    "-Users-kennethdavis-Projects-ASGM-sentiment/"
    "35b3ebc4-0b76-4a99-af57-4e1ad07c528e/tool-results/bbxh006kr.txt"
)

ASGM_TERMS = [
    "artisanal mining",
    "artisanal gold",
    "small-scale mining",
    "small scale mining",
    "asgm",
    "galamsey",
    "garimpeiro",
    "orpaillage",
    "illegal mining",
    "illegal gold",
]

REQUEST_DELAY = 1.5  # seconds between fetches


def parse_records(path: str) -> list[dict]:
    records = []
    with open(path) as f:
        for line in f:
            urls = re.findall(r'https?://\S+', line)
            if not urls:
                continue
            url = urls[-1].strip()
            m = re.match(r'^\d{8}T\d+\s+(.*?)\s{3,}(\S+)\s{3,}', line)
            title = m.group(1).strip() if m else ""
            records.append({"url": url, "title": title})
    return records


def is_asgm_relevant(text: str) -> bool:
    lower = text.lower()
    return any(term in lower for term in ASGM_TERMS)


def main():
    records = parse_records(CACHED_FILE)
    print(f"Loaded {len(records)} article records", flush=True)

    analyzer = SentimentIntensityAnalyzer()

    asgm_scores = []
    non_asgm_scores = []
    fetch_ok = 0
    fetch_fail = 0

    for i, rec in enumerate(records, 1):
        url = rec["url"]
        title = rec["title"]

        try:
            downloaded = trafilatura.fetch_url(url)
            body = trafilatura.extract(downloaded) if downloaded else None
        except Exception as e:
            body = None

        if body:
            fetch_ok += 1
            full_text = f"{title} {body}"
            relevant = is_asgm_relevant(full_text)
            score = analyzer.polarity_scores(full_text)["compound"]

            flag = "ASGM" if relevant else "NONASGM"
            print(f"[{i:3d}/{len(records)}] {flag} score={score:+.3f} | {title[:60]}", flush=True)

            if relevant:
                asgm_scores.append(score)
            else:
                non_asgm_scores.append(score)
        else:
            fetch_fail += 1
            print(f"[{i:3d}/{len(records)}] FETCH_FAIL | {url[:70]}", flush=True)

        if i < len(records):
            time.sleep(REQUEST_DELAY)

    print("\n" + "="*60, flush=True)
    print(f"Fetch results: {fetch_ok} ok, {fetch_fail} failed", flush=True)
    print(f"\nASGM-relevant articles (n={len(asgm_scores)}):", flush=True)
    if asgm_scores:
        print(f"  Mean VADER compound: {statistics.mean(asgm_scores):+.4f}", flush=True)
        print(f"  Median:              {statistics.median(asgm_scores):+.4f}", flush=True)
        print(f"  Stdev:               {statistics.stdev(asgm_scores):.4f}" if len(asgm_scores) > 1 else "", flush=True)

    print(f"\nNon-ASGM articles (n={len(non_asgm_scores)}):", flush=True)
    if non_asgm_scores:
        print(f"  Mean VADER compound: {statistics.mean(non_asgm_scores):+.4f}", flush=True)
        print(f"  Median:              {statistics.median(non_asgm_scores):+.4f}", flush=True)
        print(f"  Stdev:               {statistics.stdev(non_asgm_scores):.4f}" if len(non_asgm_scores) > 1 else "", flush=True)

    if asgm_scores and non_asgm_scores:
        diff = statistics.mean(asgm_scores) - statistics.mean(non_asgm_scores)
        print(f"\nDifference (ASGM minus non-ASGM): {diff:+.4f}", flush=True)
        relevance_pct = 100 * len(asgm_scores) / (len(asgm_scores) + len(non_asgm_scores))
        print(f"Body-text ASGM relevance rate: {relevance_pct:.1f}%", flush=True)

    print("="*60, flush=True)


if __name__ == "__main__":
    main()
