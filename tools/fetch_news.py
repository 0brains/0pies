#!/usr/bin/env python3
"""Refresh data/news.json from a whitelist of vetted sources.

    python3 tools/fetch_news.py            # fetch, merge, validate, write
    python3 tools/fetch_news.py --dry-run  # show what would be added

Build-time only — nothing here ever runs in a visitor's browser. Existing
items are never overwritten (hand edits win); new items are keyword-filtered,
markup-stripped, capped. The validator gate is the same one the page build
uses, so a bad fetch cannot ship.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.request
import xml.etree.ElementTree as ET
from datetime import date, datetime
from html import unescape
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import build_news

DATE_RE = build_news.DATE_RE

SOURCES = [
    {"slug": "ec", "name": "European Commission", "tag": "EU AI Act",
     "url": "https://digital-strategy.ec.europa.eu/rss.xml"},
    {"slug": "edpb", "name": "EDPB", "tag": "EU data protection",
     "url": "https://www.edpb.europa.eu/rss.xml"},
    {"slug": "nist", "name": "NIST", "tag": "US federal",
     "url": "https://www.nist.gov/news-events/news/rss.xml"},
    {"slug": "dsit", "name": "UK DSIT", "tag": "UK",
     "url": "https://www.gov.uk/search/news-and-communications.atom?organisations%5B%5D=department-for-science-innovation-and-technology"},
    {"slug": "cdt", "name": "CDT", "tag": "Policy analysis",
     "url": "https://cdt.org/feed/"},
    {"slug": "ada", "name": "Ada Lovelace Institute", "tag": "Policy analysis", "max": 3,
     "url": "https://www.adalovelaceinstitute.org/feed/"},
    {"slug": "importai", "name": "Import AI (Jack Clark)", "tag": "Policy analysis", "max": 3,
     "url": "https://jack-clark.net/feed/"},
    # Research / frontier labs / tools & code. High-volume feeds carry "max"
    # so they can't crowd regulation items out of the CAP-sized window.
    {"slug": "arxiv", "name": "arXiv cs.AI", "tag": "Research", "max": 3,
     "url": "https://rss.arxiv.org/rss/cs.AI"},
    {"slug": "dm", "name": "Google DeepMind", "tag": "Frontier labs", "max": 3,
     "url": "https://deepmind.google/blog/rss.xml"},
    {"slug": "oai", "name": "OpenAI", "tag": "Frontier labs", "max": 3,
     "url": "https://openai.com/news/rss.xml"},
    {"slug": "hf", "name": "Hugging Face", "tag": "Tools & code", "max": 3,
     "url": "https://huggingface.co/blog/feed.xml"},
    # Anthropic has no RSS: company news comes from the robots-sanctioned
    # sitemap (titles derived from slugs). The alignment blog dropped its feed
    # in a site revamp (every path, feed.xml included, returns the SPA's HTML)
    # — nothing machine-readable to poll there any more.
    {"slug": "anthropic", "name": "Anthropic", "tag": "Frontier labs", "max": 3, "kind": "sitemap",
     "url": "https://www.anthropic.com/sitemap.xml", "prefix": "https://www.anthropic.com/news/"},
    {"slug": "mistral", "name": "Mistral AI", "tag": "Frontier labs", "max": 3,
     "url": "https://mistral.ai/rss.xml"},
    {"slug": "googleai", "name": "Google AI Blog", "tag": "Frontier labs", "max": 3,
     "url": "https://blog.google/technology/ai/rss/"},
    {"slug": "mssource", "name": "Microsoft Source", "tag": "Frontier labs", "max": 3,
     "url": "https://news.microsoft.com/source/topics/ai/feed/"},
    {"slug": "awsml", "name": "AWS Machine Learning Blog", "tag": "Tools & code", "max": 3,
     "url": "https://aws.amazon.com/blogs/machine-learning/feed/"},
    {"slug": "qwen", "name": "Alibaba Qwen", "tag": "Frontier labs", "max": 3,
     "url": "https://qwenlm.github.io/blog/index.xml"},
    # Chinese AI governance in English translation/analysis. CAC itself and
    # DeepSeek/Meta AI/xAI publish no machine-readable feeds.
    {"slug": "digichina", "name": "DigiChina (Stanford)", "tag": "China", "max": 3,
     "url": "https://digichina.stanford.edu/feed/"},
    {"slug": "cset", "name": "CSET (Georgetown)", "tag": "China", "max": 3,
     "url": "https://cset.georgetown.edu/feed/"},
    {"slug": "technode", "name": "TechNode", "tag": "China", "max": 3,
     "url": "https://technode.com/feed/"},
    {"slug": "gh", "name": "GitHub Blog", "tag": "Tools & code", "max": 3,
     "url": "https://github.blog/ai-and-ml/feed/"},
    # Security / critical-infrastructure sources. All pass the AI keyword
    # filter, so high-volume general-security feeds contribute only AI items.
    # OECD has no working public feed (403/404 everywhere, JS-only site).
    {"slug": "owasp", "name": "OWASP", "tag": "AI security", "max": 3,
     "url": "https://owasp.org/feed.xml"},
    {"slug": "owaspgenai", "name": "OWASP GenAI Security Project", "tag": "AI security", "max": 3,
     "url": "https://genai.owasp.org/feed/"},
    {"slug": "mitre", "name": "MITRE Engenuity", "tag": "Threat intel", "max": 3,
     "url": "https://medium.com/feed/mitre-engenuity"},
    {"slug": "bleep", "name": "BleepingComputer", "tag": "Cyber news", "max": 3,
     "url": "https://www.bleepingcomputer.com/feed/"},
    {"slug": "schneier", "name": "Schneier on Security", "tag": "AI security", "max": 3,
     "url": "https://www.schneier.com/feed/atom/"},
    {"slug": "sansisc", "name": "SANS ISC", "tag": "Cyber news", "max": 3,
     "url": "https://isc.sans.edu/rssfeed.xml"},
    # CISA and the European Parliament block ALL datacenter egress IPs (GCP
    # and GitHub runners alike, verified 2026-08-07) — they live in
    # fetch_news_blocked.py, runnable from a residential connection.
    {"slug": "ncsc", "name": "UK NCSC", "tag": "UK NCSC", "max": 3,
     "url": "https://www.ncsc.gov.uk/api/1/services/v1/all-rss-feed.xml"},
    # AI certification news. IAPP (AIGP's owner) and ISACA have no public
    # feeds since their site revamps — nothing compliant to poll there.
    {"slug": "awscert", "name": "AWS Training & Certification", "tag": "AI certifications", "max": 3,
     "url": "https://aws.amazon.com/blogs/training-and-certification/feed/"},
    {"slug": "mslearn", "name": "Microsoft Learn", "tag": "AI certifications", "max": 3,
     "url": "https://techcommunity.microsoft.com/t5/s/gxcuf89792/rss/board?board.id=MicrosoftLearnBlog"},
    # Trending (JSON APIs, not RSS): rendered in the page's Trending box.
    # GitHub search API — new AI repos this week by stars. The created:> date
    # is filled at fetch time in main(); {week_ago} is the placeholder.
    {"slug": "ghtrend", "name": "GitHub", "tag": "Trending on GitHub", "max": 3, "kind": "gh",
     "url": "https://api.github.com/search/repositories?q=topic%3Aai+created%3A%3E{week_ago}&sort=stars&order=desc&per_page=10"},
    # Hacker News front page, AI-filtered, via the Algolia API.
    {"slug": "hn", "name": "Hacker News", "tag": "Trending on HN", "max": 3, "kind": "hn",
     "url": "https://hn.algolia.com/api/v1/search?tags=front_page&hitsPerPage=30"},
    # Mastodon trending links (public API, no auth), AI-filtered.
    {"slug": "masto", "name": "Mastodon", "tag": "Trending on Mastodon", "max": 3, "kind": "masto",
     "url": "https://mastodon.social/api/v1/trends/links"},
    # Bluesky trending topics (public AppView API, no auth), AI-filtered.
    {"slug": "bsky", "name": "Bluesky", "tag": "Trending on Bluesky", "max": 3, "kind": "bsky",
     "url": "https://public.api.bsky.app/xrpc/app.bsky.unspecced.getTrendingTopics"},
    # X and Instagram: no free, ToS-compliant trend access (X trends are a paid
    # API tier; Meta requires business auth). Reddit's API needs a registered
    # OAuth app — add credentials and a parser if that access is ever wanted.
]
# NewsAPI (newsapi.org): AI coverage from the mainstream tech press, which
# publishes no usable RSS wall-free. Source ids are discovered daily from
# /v2/top-headlines/sources (category=technology); articles come from
# /v2/everything scoped to those sources with a query mirroring KEYWORDS.
# The free tier allows 100 requests/day but the refresh loop fires every
# 5 minutes, so fetches are throttled to one per NEWSAPI_INTERVAL_MIN via
# state kept under news.json's top-level "newsapi" key (merge() spreads
# existing and validate() only reads feed/items, so the key rides along).
# Requires NEWSAPI_KEY in env (Secret Manager in production, like GITHUB_TOKEN).
NEWSAPI_SOURCE = {"slug": "newsapi", "name": "NewsAPI", "tag": "AI news", "max": 5, "kind": "newsapi"}
NEWSAPI_SOURCES_URL = "https://newsapi.org/v2/top-headlines/sources?category=technology&language=en"
NEWSAPI_QUERY = ('AI OR "artificial intelligence" OR "frontier model" OR "foundation model" OR '
                 '"machine learning" OR deepfake OR "AI Act" OR LLM OR chatbot OR ChatGPT OR '
                 'Claude OR Gemini OR OpenAI OR Anthropic OR DeepMind OR agentic OR GenAI OR '
                 '"neural network"')
NEWSAPI_INTERVAL_MIN = 30
NEWSAPI_MAX_SOURCES = 20  # /v2/everything accepts at most 20 source ids
KEYWORDS = re.compile(
    r"\b(AI|artificial intelligence|algorithm|frontier model|foundation model|"
    r"machine learning|automated decision|deepfake|synthetic content|AI Act|"
    r"model card|LLM|chatbot|biometric|GPT|ChatGPT|Claude|Gemini|OpenAI|"
    r"Anthropic|DeepMind|agentic|GenAI|neural network|AIGP|AI Practitioner)\b", re.I)
TAG_STRIP = re.compile(r"<[^>]+>")
ATOM = "{http://www.w3.org/2005/Atom}"


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", unescape(TAG_STRIP.sub(" ", text or ""))).strip()


def _slug(url: str, source: dict) -> str:
    tail = re.sub(r"[^a-z0-9]+", "-", url.rstrip("/").rsplit("/", 1)[-1].lower()).strip("-")
    return f"{source['slug']}-{tail}"[:80].rstrip("-")


def _parse_date(raw: str) -> str | None:
    raw = (raw or "").strip()
    for fmt in ("%a, %d %b %Y %H:%M:%S %z", "%a, %d %b %Y %H:%M:%S %Z",
                "%a, %d %b %y %H:%M:%S %z", "%a, %d %b %y %H:%M:%S %Z",  # 2-digit year (CISA)
                "%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%d"):
        try:
            return datetime.strptime(raw[:31 if "," in raw else 25], fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    m = re.match(r"(\d{4}-\d{2}-\d{2})", raw)
    return m.group(1) if m else None


def parse_feed(xml_bytes: bytes, source: dict) -> list[dict]:
    # Security: these bytes come from external servers. stdlib expat doesn't
    # resolve external entities, but a DTD still enables entity-expansion
    # (billion-laughs) tricks. A DTD is only dangerous in the prolog — HTML
    # doctypes inside CDATA article bodies (WordPress feeds) are inert text —
    # so the guard covers everything before the root element opens.
    head = xml_bytes[:1024].lstrip()
    root_at = min((p for p in (xml_bytes.find(b"<rss"), xml_bytes.find(b"<feed")) if p != -1), default=-1)
    prolog = xml_bytes[:root_at] if root_at != -1 else xml_bytes
    if b"<!DOCTYPE" in prolog or b"<!ENTITY" in prolog or head[:5] not in (b"<?xml", b"<feed", b"<rss "):
        raise ValueError(f"{source['name']}: refusing feed with DTD or non-XML preamble")
    root = ET.fromstring(xml_bytes)
    raw = []
    for entry in root.iter(f"{ATOM}entry"):  # Atom
        link = next((l.get("href") for l in entry.findall(f"{ATOM}link")
                     if l.get("rel") in (None, "alternate")), None)
        raw.append((entry.findtext(f"{ATOM}title"), link,
                    entry.findtext(f"{ATOM}summary") or entry.findtext(f"{ATOM}content"),
                    entry.findtext(f"{ATOM}updated") or entry.findtext(f"{ATOM}published")))
    for item in root.iter("item"):  # RSS 2.0
        raw.append((item.findtext("title"), item.findtext("link"),
                    item.findtext("description"), item.findtext("pubDate")))
    out = []
    for title, link, summary, pub in raw:
        title, summary = _clean(title), _clean(summary)
        day = _parse_date(pub)
        if not (title and link and day and link.startswith("https://")):
            continue
        if not (KEYWORDS.search(title) or KEYWORDS.search(summary)):
            continue
        out.append({
            "id": _slug(link, source), "date": day, "asOf": date.today().isoformat(),
            "tag": source["tag"], "title": title[:200],
            "summary": (summary[:400].rsplit(" ", 1)[0] + "…") if len(summary) > 400 else (summary or title),
            "sourceName": source["name"], "sourceUrl": link,
        })
    return out


def parse_gh(json_bytes: bytes, source: dict) -> list[dict]:
    """GitHub repo-search JSON → trending items (section: trending)."""
    out = []
    for repo in json.loads(json_bytes).get("items", []):
        url, name = repo.get("html_url", ""), repo.get("full_name", "")
        day = (repo.get("created_at") or "")[:10]
        if not (url.startswith("https://") and name and DATE_RE.match(day)):
            continue
        out.append({
            "id": _slug(url.replace("github.com/", "github-com-"), source),
            "date": day, "asOf": date.today().isoformat(), "tag": source["tag"],
            "title": f"{name} — {repo.get('stargazers_count', 0):,} stars",
            "summary": _clean(repo.get("description") or f"New repository {name}"),
            "sourceName": "GitHub", "sourceUrl": url, "section": "trending",
        })
    return out


def parse_hn(json_bytes: bytes, source: dict) -> list[dict]:
    """HN Algolia front-page JSON → AI-relevant trending items."""
    out = []
    for hit in json.loads(json_bytes).get("hits", []):
        title = _clean(hit.get("title") or "")
        day = (hit.get("created_at") or "")[:10]
        oid = hit.get("objectID")
        if not (title and oid and DATE_RE.match(day) and KEYWORDS.search(title)):
            continue
        out.append({
            "id": f"{source['slug']}-{oid}",
            "date": day, "asOf": date.today().isoformat(), "tag": source["tag"],
            "title": title[:200],
            "summary": f"On the Hacker News front page with {hit.get('points', 0)} points.",
            "sourceName": "Hacker News",
            "sourceUrl": f"https://news.ycombinator.com/item?id={oid}",
            "section": "trending",
        })
    return out


def parse_mastodon(json_bytes: bytes, source: dict) -> list[dict]:
    """Mastodon trends/links JSON → AI-relevant trending items."""
    out = []
    for link in json.loads(json_bytes):
        title = _clean(link.get("title") or "")
        url = link.get("url") or ""
        if not (title and url.startswith("https://")):
            continue
        if not (KEYWORDS.search(title) or KEYWORDS.search(_clean(link.get("description") or ""))):
            continue
        accounts = (link.get("history") or [{}])[0].get("accounts", "0")
        out.append({
            "id": _slug(url, source), "date": date.today().isoformat(),
            "asOf": date.today().isoformat(), "tag": source["tag"],
            "title": title[:200],
            "summary": f"Trending across Mastodon — shared by {accounts} accounts today.",
            "sourceName": "Mastodon", "sourceUrl": url, "section": "trending",
        })
    return out


def parse_bluesky(json_bytes: bytes, source: dict) -> list[dict]:
    """Bluesky getTrendingTopics JSON → AI-relevant trending items."""
    out = []
    for topic in json.loads(json_bytes).get("topics", []):
        name = _clean(topic.get("topic") or "")
        link = topic.get("link") or ""
        if not (name and link.startswith("/") and KEYWORDS.search(name)):
            continue
        out.append({
            "id": _slug(link, source), "date": date.today().isoformat(),
            "asOf": date.today().isoformat(), "tag": source["tag"],
            "title": name[:200],
            "summary": "Trending topic on Bluesky right now.",
            "sourceName": "Bluesky", "sourceUrl": f"https://bsky.app{link}",
            "section": "trending",
        })
    return out


def parse_sitemap(xml_bytes: bytes, source: dict) -> list[dict]:
    """Sitemap XML → items for URLs under source['prefix'] (no-RSS sites)."""
    root_at = xml_bytes.find(b"<urlset")
    prolog = xml_bytes[:root_at] if root_at != -1 else xml_bytes
    if b"<!DOCTYPE" in prolog or b"<!ENTITY" in prolog:
        raise ValueError(f"{source['name']}: refusing sitemap with DTD")
    SM = "{http://www.sitemaps.org/schemas/sitemap/0.9}"
    prefix = source["prefix"]
    out = []
    for url in ET.fromstring(xml_bytes).iter(f"{SM}url"):
        loc = (url.findtext(f"{SM}loc") or "").strip()
        day = (url.findtext(f"{SM}lastmod") or "")[:10]
        slug = loc[len(prefix):]
        if not (loc.startswith(prefix) and slug and "/" not in slug and DATE_RE.match(day)):
            continue
        title = " ".join(w.capitalize() if w.islower() else w for w in slug.replace("-", " ").split())
        out.append({
            "id": _slug(loc, source), "date": day, "asOf": date.today().isoformat(),
            "tag": source["tag"], "title": title[:200],
            "summary": f"New from {source['name']}: {title}.",
            "sourceName": source["name"], "sourceUrl": loc,
        })
    return out


def parse_newsapi(json_bytes: bytes, source: dict) -> list[dict]:
    """NewsAPI /v2/everything JSON → keyword-filtered news items."""
    out = []
    for art in json.loads(json_bytes).get("articles", []):
        title = _clean(art.get("title") or "")
        summary = _clean(art.get("description") or "")
        url = art.get("url") or ""
        day = (art.get("publishedAt") or "")[:10]
        if not (title and url.startswith("https://") and DATE_RE.match(day)):
            continue
        # The server-side query already selects for AI, but the local filter is
        # the site's contract — an article that wouldn't pass KEYWORDS doesn't ship.
        if not (KEYWORDS.search(title) or KEYWORDS.search(summary)):
            continue
        pub = _clean((art.get("source") or {}).get("name") or "") or source["name"]
        # NewsAPI suffixes titles with "| Publisher" — redundant next to sourceName.
        if title.endswith(f"| {pub}"):
            title = title[: -len(f"| {pub}")].strip(" |")
        out.append({
            "id": _slug(url, source), "date": day, "asOf": date.today().isoformat(),
            "tag": source["tag"], "title": title[:200],
            "summary": (summary[:400].rsplit(" ", 1)[0] + "…") if len(summary) > 400 else (summary or title),
            "sourceName": f"{pub} · via NewsAPI", "sourceUrl": url,
        })
    return out


def _newsapi_due(state: dict, now: datetime) -> bool:
    try:
        prev = datetime.strptime(state.get("lastFetch", ""), "%Y-%m-%dT%H:%M:%SZ")
    except ValueError:
        return True
    return (now - prev).total_seconds() >= NEWSAPI_INTERVAL_MIN * 60


def fetch_newsapi(state: dict, week_ago: str) -> list[dict]:
    """Throttled two-call NewsAPI fetch; state is mutated in place and persists
    because merge() carries every top-level key of the existing archive."""
    import os
    key = os.environ.get("NEWSAPI_KEY", "").strip()
    if not key:
        print("warn: NewsAPI: NEWSAPI_KEY not set, skipping", file=sys.stderr)
        return []
    now = datetime.utcnow()
    if not _newsapi_due(state, now):
        return []
    # Stamp before fetching so a failing upstream still backs off a full
    # interval instead of burning the 100/day quota every 5-minute cycle.
    state["lastFetch"] = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    headers = {"User-Agent": "0pi.es news build (https://0pi.es)", "X-Api-Key": key}

    def get(url: str) -> bytes:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.read()

    today = now.strftime("%Y-%m-%d")
    if state.get("sourcesAsOf") != today or not state.get("sourceIds"):
        found = json.loads(get(NEWSAPI_SOURCES_URL)).get("sources", [])
        ids = [s["id"] for s in found if s.get("id")]
        if ids:
            state["sourceIds"] = ids[:NEWSAPI_MAX_SOURCES]
            state["sourcesAsOf"] = today
    ids = state.get("sourceIds") or []
    if not ids:
        return []
    from urllib.parse import quote
    url = ("https://newsapi.org/v2/everything?q=" + quote(NEWSAPI_QUERY) +
           "&sources=" + ",".join(ids) +
           f"&from={week_ago}&language=en&sortBy=publishedAt&pageSize=50")
    return cap_source(parse_newsapi(get(url), NEWSAPI_SOURCE), NEWSAPI_SOURCE)


def cap_source(items: list[dict], source: dict) -> list[dict]:
    limit = source.get("max")
    if not limit:
        return items
    return sorted(items, key=lambda i: i["date"], reverse=True)[:limit]


TREND_CAP = 6


def _norm_title(title: str) -> str:
    """Punctuation/case-insensitive key for same-story detection across sources."""
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", title.lower())).strip()


def _is_aggregated(item_id: str) -> bool:
    return item_id.startswith(NEWSAPI_SOURCE["slug"] + "-")


def merge(existing: dict, fetched: list[dict], today: str, cap: int | None = None) -> dict:
    ex_news = [i for i in existing["items"] if i.get("section") != "trending"]
    ex_trend = [i for i in existing["items"] if i.get("section") == "trending"]
    f_news = [i for i in fetched if i.get("section") != "trending"]
    f_trend = [i for i in fetched if i.get("section") == "trending"]
    # News accumulates; hand edits win (a fetched id that already exists loses).
    known = {i["id"] for i in ex_news}
    # Same-story dedup by normalized title, first-party preferred: aggregator
    # (NewsAPI) copies are processed last so they lose within a batch, and a
    # first-party arrival evicts an archived aggregator copy of the same story.
    # First-party-vs-first-party overlaps are left alone — two outlets covering
    # one story with the same headline is analysis worth keeping, syndication is not.
    ex_titles = {_norm_title(i["title"]): i["id"] for i in ex_news}
    fresh, seen, seen_titles, evicted = [], set(), set(), set()
    for item in sorted(f_news, key=lambda i: _is_aggregated(i["id"])):
        if item["id"] in known or item["id"] in seen:
            continue
        title = _norm_title(item["title"])
        if title:
            if _is_aggregated(item["id"]) and (title in seen_titles or title in ex_titles):
                continue  # aggregator copy of a story we already carry
            if not _is_aggregated(item["id"]):
                ex_id = ex_titles.get(title)
                if ex_id is not None and _is_aggregated(ex_id):
                    evicted.add(ex_id)  # first-party supersedes archived aggregator copy
        seen.add(item["id"])
        if title:
            seen_titles.add(title)
        fresh.append(dict(item, asOf=today))
    ex_news = [i for i in ex_news if i["id"] not in evicted]
    # No length limit: the page is the archive, newest first, back through time.
    news = sorted(ex_news + fresh, key=lambda i: (i["date"], i["id"]), reverse=True)
    if cap:
        news = news[:cap]
    # Trending is ephemeral, but per source: a source that returned items this
    # round replaces its own entries; a source that failed (rate limit, outage)
    # keeps its previous entries instead of flapping out of the box.
    trend_sources = {t["sourceName"] for t in f_trend}
    carried = [t for t in ex_trend if t["sourceName"] not in trend_sources]
    trend_seen: set[str] = set()
    trend = [t for t in f_trend + carried
             if not (t["id"] in trend_seen or trend_seen.add(t["id"]))][:TREND_CAP]
    return {**existing, "items": sorted(trend + news, key=lambda i: (i["date"], i["id"]), reverse=True)}


def fetch_all(newsapi_state: dict | None = None) -> list[dict]:
    """Poll every source; a dead source warns and is skipped, never fatal.

    newsapi_state is the archive's top-level "newsapi" dict (throttle timestamp
    + cached source ids). Callers that can't persist state pass None and the
    quota-limited NewsAPI source is skipped entirely.
    """
    from datetime import timedelta
    week_ago = (date.today() - timedelta(days=7)).isoformat()
    parsers = {"gh": parse_gh, "hn": parse_hn, "masto": parse_mastodon,
               "bsky": parse_bluesky, "sitemap": parse_sitemap}
    fetched: list[dict] = []
    import os
    gh_token = os.environ.get("GITHUB_TOKEN", "").strip()
    for source in SOURCES:
        try:
            url = source["url"].replace("{week_ago}", week_ago)
            headers = {"User-Agent": "0pi.es news build (https://0pi.es)",
                       **source.get("headers", {})}
            if source.get("kind") == "gh" and gh_token:
                # Authenticated search: 30 req/min instead of a 10/min pool
                # shared across every unauthenticated caller on the same IP.
                headers["Authorization"] = f"Bearer {gh_token}"
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=30) as resp:
                parser = parsers.get(source.get("kind"), parse_feed)
                fetched += cap_source(parser(resp.read(), source), source)
        except Exception as exc:
            print(f"warn: {source['name']}: {exc}", file=sys.stderr)
    if newsapi_state is not None:
        try:
            fetched += fetch_newsapi(newsapi_state, week_ago)
        except Exception as exc:
            print(f"warn: NewsAPI: {exc}", file=sys.stderr)
    return fetched


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    existing = build_news.load_news()
    merged = merge(existing, fetch_all(existing.setdefault("newsapi", {})),
                   today=date.today().isoformat())
    new_ids = {i["id"] for i in merged["items"]} - {i["id"] for i in existing["items"]}
    if not new_ids:
        print("no new items")
        return
    errors = build_news.validate(merged)
    if errors:
        sys.exit("fetched result fails validation (not written):\n  " + "\n  ".join(errors))
    if args.dry_run:
        print("would add: " + ", ".join(sorted(new_ids)))
        return
    build_news.NEWS.write_text(json.dumps(merged, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"added {len(new_ids)}: " + ", ".join(sorted(new_ids)))


if __name__ == "__main__":
    main()
