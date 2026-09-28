#!/usr/bin/env python3
"""Fetch the sources whose hosts block Google Cloud egress IPs and merge them
into the news archive bucket from wherever this runs (GitHub runners, laptop).

    python3 tools/fetch_news_blocked.py            # fetch, merge, upload
    python3 tools/fetch_news_blocked.py --dry-run  # show what would be added

The Firebase refresh_news function cannot reach these hosts (CISA and the
European Parliament 403/empty-body Google Cloud IPs), so a scheduled GitHub
Actions job runs this hourly instead. It writes the same bucket blob the
function merges from, guarded by a generation precondition so the two writers
cannot silently clobber each other — on a race this retries with fresh state.

Auth: application-default credentials (GOOGLE_APPLICATION_CREDENTIALS service
account in CI, gcloud ADC locally). Needs storage.objectAdmin on the bucket.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import build_news
import fetch_news

BUCKET = "djjonestech-news"
BLOB = "news/news.json"

_BROWSER = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                          "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36",
            "Accept": "application/rss+xml, application/xml;q=0.9, */*;q=0.8"}

# Hosts that 403/empty-body every datacenter IP (GCP and GitHub runners alike,
# verified 2026-08-07). Only reachable from residential connections.
BLOCKED_SOURCES = [
    {"slug": "cisa", "name": "CISA", "tag": "US CISA", "max": 3,
     "url": "https://www.cisa.gov/news.xml", "headers": _BROWSER},
    {"slug": "cisaadv", "name": "CISA", "tag": "US CISA", "max": 3,
     "url": "https://www.cisa.gov/cybersecurity-advisories/all.xml", "headers": _BROWSER},
    {"slug": "europarl", "name": "European Parliament", "tag": "EU AI Act", "max": 3,
     "url": "https://www.europarl.europa.eu/rss/doc/press-releases/en.xml", "headers": _BROWSER},
]


def fetch_blocked() -> list[dict]:
    original = fetch_news.SOURCES
    fetch_news.SOURCES = BLOCKED_SOURCES
    try:
        return fetch_news.fetch_all()
    finally:
        fetch_news.SOURCES = original


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    fetched = fetch_blocked()
    if not fetched:
        print("blocked sources returned no AI-relevant items")
        return

    store = _make_store()
    for attempt in range(3):
        generation, existing = store.read()
        merged = fetch_news.merge(existing, fetched, today=date.today().isoformat())
        new_ids = {i["id"] for i in merged["items"]} - {i["id"] for i in existing["items"]}
        if not new_ids:
            print("no new items")
            return
        errors = build_news.validate(merged)
        if errors:
            sys.exit("merged result fails validation (not written):\n  " + "\n  ".join(errors))
        if args.dry_run:
            print("would add: " + ", ".join(sorted(new_ids)))
            return
        body = json.dumps(merged, ensure_ascii=False, indent=2) + "\n"
        if store.write(body, generation):
            print(f"added {len(new_ids)}: " + ", ".join(sorted(new_ids)))
            return
        print(f"write raced the refresh function (attempt {attempt + 1}), retrying")
    sys.exit("gave up after repeated write races")


class _GsutilStore:
    """Bucket access via the gcloud CLI's auth — for laptops without ADC."""

    def read(self) -> tuple[int, dict]:
        import subprocess
        stat = subprocess.run(["gsutil", "stat", f"gs://{BUCKET}/{BLOB}"],
                              capture_output=True, text=True, check=True).stdout
        generation = int(next(l.split(":")[1] for l in stat.splitlines()
                              if l.strip().startswith("Generation:")))
        text = subprocess.run(["gsutil", "cat", f"gs://{BUCKET}/{BLOB}"],
                              capture_output=True, text=True, check=True).stdout
        return generation, json.loads(text)

    def write(self, body: str, generation: int) -> bool:
        import subprocess
        proc = subprocess.run(
            ["gsutil", "-h", f"x-goog-if-generation-match:{generation}",
             "-h", "Content-Type:application/json; charset=utf-8",
             "cp", "-", f"gs://{BUCKET}/{BLOB}"],
            input=body, capture_output=True, text=True)
        if proc.returncode and "412" not in proc.stderr and "Precondition" not in proc.stderr:
            sys.exit(f"gsutil upload failed:\n{proc.stderr}")
        return proc.returncode == 0


class _AdcStore:
    """Bucket access via google-cloud-storage — for CI with a service account."""

    def __init__(self):
        from google.cloud import storage
        self._blob = storage.Client().bucket(BUCKET).blob(BLOB)

    def read(self) -> tuple[int, dict]:
        self._blob.reload()
        return self._blob.generation, json.loads(self._blob.download_as_text())

    def write(self, body: str, generation: int) -> bool:
        from google.api_core.exceptions import PreconditionFailed
        try:
            self._blob.upload_from_string(
                body, content_type="application/json; charset=utf-8",
                if_generation_match=generation)
            return True
        except PreconditionFailed:
            return False


def _make_store():
    try:
        return _AdcStore()
    except Exception:
        return _GsutilStore()


if __name__ == "__main__":
    main()
