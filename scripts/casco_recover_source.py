"""Explicit recovery only: recheck a dead pin, then propose official replacements."""
import argparse
from dataclasses import asdict
import json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from collector.casco_sources import sources_for, official_url, HOSTS
from collector.http_client import HttpFetcher, FetchError


def recover(insurer, url, *, fetcher=None, search=None):
    if url not in {s.url for s in sources_for(insurer)}:
        raise ValueError("URL is not a pinned source")
    try:
        (fetcher or HttpFetcher()).fetch(url)
    except FetchError as exc:
        if exc.status_code not in (404, 410):
            raise ValueError("Not a dead URL: retry later; search is disabled") from exc
    else:
        raise ValueError("Pinned URL is alive; search is disabled")
    if search is None:
        from collector.web_search import DuckDuckGoSearch
        search = DuckDuckGoSearch()
    host = sorted(HOSTS[insurer], key=len)[0]
    return [asdict(hit) for hit in search.search(f"site:{host} КАСКО правила страхования pdf", limit=5)
            if official_url(insurer, hit.url)]


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--insurer", required=True)
    p.add_argument("--url", required=True)
    args = p.parse_args()
    print(json.dumps({"proposals": recover(args.insurer, args.url),
        "note": "Review document/product/version and update the pinned registry; proposals never publish cards."},
        ensure_ascii=False, indent=2))
