#!/usr/bin/env python3
"""Build the 0pi.es news page and Atom feed from data/news.json.

    python3 tools/build_news.py

news.html is composed from the deployed index.html so the chrome (topbar,
footer, share modal, theme, modals) is identical by construction: everything
between <div class="wrap"> and <footer> is replaced with news content; the
only other differences are the head metadata, the Atom autodiscovery link,
one scoped style block, and which nav link is active.

Validation is blocking, same stance as build_lab.py: an item without
provenance (sourceName + sourceUrl + asOf) fails the build rather than
shipping. No build-time timestamps reach the output — rebuilding from the
same inputs is byte-identical.
"""
from __future__ import annotations

import json
import os
import re
import sys
from html import escape
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
NEWS = REPO / "data" / "news.json"
OUT = Path(os.environ.get("LAB_OUT") or REPO / "gamification")

DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")
MARKUP_RE = re.compile(r"<[A-Za-z]")
ITEM_REQUIRED = ("id", "date", "asOf", "tag", "title", "summary", "sourceName", "sourceUrl")
FEED_REQUIRED = ("title", "subtitle", "site", "selfUrl", "pageUrl")


def validate(data: dict) -> list[str]:
    errors: list[str] = []
    feed = data.get("feed") or {}
    for key in FEED_REQUIRED:
        if not feed.get(key):
            errors.append(f"feed.{key}: missing")
    items = data.get("items")
    if not isinstance(items, list) or not items:
        return errors + ["items: must be a non-empty list"]
    seen: set[str] = set()
    for i, item in enumerate(items):
        label = f"items[{i}] ({item.get('id', '?')})"
        for key in ITEM_REQUIRED:
            if not item.get(key):
                errors.append(f"{label}: {key} missing (citation/asOf are required provenance)")
        for key in ("date", "asOf"):
            v = item.get(key)
            if v and not DATE_RE.match(v):
                errors.append(f"{label}: {key} is not an ISO date (YYYY-MM-DD): {v!r}")
        slug = item.get("id", "")
        if slug and not SLUG_RE.match(slug):
            errors.append(f"{label}: id is not a slug")
        if slug in seen:
            errors.append(f"{label}: id not unique")
        seen.add(slug)
        url = item.get("sourceUrl", "")
        if url and not url.startswith("https://"):
            errors.append(f"{label}: sourceUrl must be https")
        for key, v in item.items():
            if isinstance(v, str) and MARKUP_RE.search(v):
                errors.append(f"{label}: markup in {key} — data strings must be plain text")
    dates = [i.get("date", "") for i in items if i.get("date")]
    if dates != sorted(dates, reverse=True):
        errors.append("items: must be ordered newest first by date")
    return errors


def load_news(path: Path = NEWS) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    errors = validate(data)
    if errors:
        sys.exit("news.json is not shippable:\n  " + "\n  ".join(errors))
    return data


def _atom_entry(feed: dict, item: dict) -> str:
    entry_id = f"{feed['pageUrl']}#{item['id']}"
    summary = item["summary"]
    if item.get("status"):
        summary += f" [Currency note: {item['status']}]"
    return (
        "  <entry>\n"
        f"    <title>{escape(item['title'])}</title>\n"
        f"    <id>{escape(entry_id)}</id>\n"
        f"    <link rel=\"alternate\" href=\"{escape(item['sourceUrl'])}\"/>\n"
        f"    <updated>{item['date']}T00:00:00Z</updated>\n"
        f"    <category term=\"{escape(item['tag'])}\"/>\n"
        f"    <summary>{escape(summary)} (Source: {escape(item['sourceName'])}. As of {item['asOf']}.)</summary>\n"
        "  </entry>\n"
    )


def render_feed(data: dict) -> str:
    feed, items = data["feed"], data["items"]
    updated = max(i["date"] for i in items) + "T00:00:00Z"
    head = (
        "<?xml version=\"1.0\" encoding=\"utf-8\"?>\n"
        "<feed xmlns=\"http://www.w3.org/2005/Atom\">\n"
        f"  <title>{escape(feed['title'])}</title>\n"
        f"  <subtitle>{escape(feed['subtitle'])}</subtitle>\n"
        f"  <id>{escape(feed['site'])}</id>\n"
        f"  <link rel=\"self\" type=\"application/atom+xml\" href=\"{escape(feed['selfUrl'])}\"/>\n"
        f"  <link rel=\"alternate\" type=\"text/html\" href=\"{escape(feed['pageUrl'])}\"/>\n"
        f"  <updated>{updated}</updated>\n"
    )
    return head + "".join(_atom_entry(feed, i) for i in items) + "</feed>\n"


# Topical filter categories, derived from the source tag. Unknown tags land in
# regulation — the site's home beat — rather than an "other" bucket nobody clicks.
CATEGORY_LABELS = {
    "regulation": "Regulation",
    "security": "Security",
    "research": "Research",
    "labs-tools": "Labs & tools",
    "certs": "Certifications",
}
_TAG_CATEGORY = {
    "AI news": "labs-tools",
    "AI certifications": "certs",
    "China": "regulation",
    "Research": "research",
    "Frontier labs": "labs-tools",
    "Tools & code": "labs-tools",
    "AI security": "security",
    "Threat intel": "security",
    "Cyber news": "security",
    "US CISA": "security",
    "UK NCSC": "security",
}


def category_of(item: dict) -> str:
    return _TAG_CATEGORY.get(item.get("tag", ""), "regulation")


NEWS_STYLES = """<style id="news-styles">
.news-list{display:flex;flex-direction:column;gap:18px;margin-top:28px}
.news-item{background:var(--panel);padding:20px}
.news-item .tagline{display:flex;flex-wrap:wrap;gap:10px;align-items:center;margin-bottom:10px}
.news-tag{background:var(--primary);color:#1a1c1c;border:2px solid var(--edge);
  font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:.6px;padding:3px 8px}
.news-dates{font-size:12px;color:var(--dim)}
.news-item h3{margin:0 0 8px;font-size:20px;line-height:1.3;text-transform:none}
.news-item p{margin:0 0 12px;font-size:14px;color:var(--dim);max-width:70ch}
.news-status{border:2px dashed var(--edge);background:var(--panel2);padding:8px 10px;
  font-size:12px;margin:0 0 12px;max-width:70ch}
.news-src{font-size:13px;font-weight:700}
.news-src a{color:var(--ink);text-decoration:underline;text-decoration-thickness:2px;text-underline-offset:4px}
.trending-box{background:var(--panel2);padding:16px 20px;margin-top:28px}
.trending-box h2{margin:0 0 10px;font-size:15px;text-transform:uppercase;letter-spacing:.6px}
.trending-list{display:flex;flex-direction:column;gap:8px;margin:0;padding:0;list-style:none}
.trending-list li{display:flex;flex-wrap:wrap;gap:8px;align-items:baseline;font-size:13px}
.trend-tag{background:var(--secondary);color:#1a1c1c;border:2px solid var(--edge);
  font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:.5px;padding:2px 6px;white-space:nowrap}
.trending-list a{color:var(--ink);font-weight:700;text-decoration:underline;
  text-decoration-thickness:2px;text-underline-offset:3px}
.trending-list .meta{color:var(--dim);font-size:12px}
.subscribe-card{background:var(--panel2);padding:20px;display:flex;flex-direction:column;gap:10px}
.subscribe-card .feed-url{display:flex;gap:8px;flex-wrap:wrap;align-items:stretch}
.subscribe-card code{background:var(--bg);border:2px solid var(--edge);padding:8px 10px;
  font-family:inherit;font-size:13px;user-select:all;overflow-wrap:anywhere}
.copy-feed{background:var(--primary);border:2px solid var(--edge);padding:8px 14px;font:inherit;
  font-size:12px;font-weight:700;text-transform:uppercase;cursor:pointer;color:#1a1c1c;
  box-shadow:3px 3px 0 0 var(--edge);transition:transform .1s,box-shadow .1s}
.copy-feed:hover{transform:translate(3px,3px);box-shadow:0 0 0 0 var(--edge)}
.filter-bar{display:flex;flex-wrap:wrap;gap:8px;margin-top:24px}
.filter-chip{border:2px solid var(--edge);background:var(--panel2);color:var(--ink);
  font:inherit;font-size:12px;font-weight:700;text-transform:uppercase;letter-spacing:.4px;
  padding:7px 12px;cursor:pointer;box-shadow:3px 3px 0 0 var(--edge);
  transition:transform .1s,box-shadow .1s}
.filter-chip:hover{transform:translate(3px,3px);box-shadow:0 0 0 0 var(--edge)}
.filter-chip[aria-pressed="true"]{background:var(--primary);color:#1a1c1c}
/* Category colours reuse the site's lab palette (index :root variables). */
.filter-chip::before{content:"";display:inline-block;width:10px;height:10px;
  border:2px solid var(--edge);margin-right:7px;vertical-align:-1px;background:var(--cat, var(--primary))}
.filter-chip[data-cat="all"]::before{display:none}
.filter-chip[data-cat="regulation"],.news-item[data-cat="regulation"]{--cat:var(--legislation)}
.filter-chip[data-cat="security"],.news-item[data-cat="security"]{--cat:var(--secondary)}
.filter-chip[data-cat="research"],.news-item[data-cat="research"]{--cat:var(--microsoft)}
.filter-chip[data-cat="labs-tools"],.news-item[data-cat="labs-tools"]{--cat:var(--aigp)}
.filter-chip[data-cat="certs"],.news-item[data-cat="certs"]{--cat:var(--concepts)}
.filter-chip[data-cat="regulation"][aria-pressed="true"],
.filter-chip[data-cat="security"][aria-pressed="true"],
.filter-chip[data-cat="research"][aria-pressed="true"],
.filter-chip[data-cat="labs-tools"][aria-pressed="true"],
.filter-chip[data-cat="certs"][aria-pressed="true"]{background:var(--cat);color:#1a1c1c}
.news-item .news-tag{background:var(--cat, var(--primary))}
.news-item[hidden]{display:none}
.explore-row{display:flex;flex-wrap:wrap;gap:6px;align-items:center;margin-top:10px;
  padding-top:10px;border-top:2px dashed var(--edge)}
.explore-row .lbl{font-size:11px;font-weight:700;text-transform:uppercase;
  letter-spacing:.5px;color:var(--dim);margin-right:2px}
.explore-row a{border:2px solid var(--edge);background:var(--panel2);color:var(--ink);
  display:inline-grid;place-items:center;width:30px;height:30px;text-decoration:none;
  box-shadow:2px 2px 0 0 var(--edge);transition:transform .1s,box-shadow .1s}
.explore-row a svg{width:17px;height:17px;display:block}
.explore-row a:hover{transform:translate(2px,2px);box-shadow:0 0 0 0 var(--edge);
  background:var(--primary);color:#1a1c1c}
.share-row{display:flex;flex-wrap:wrap;gap:6px;align-items:center;margin-top:10px}
.share-row .lbl{font-size:11px;font-weight:700;text-transform:uppercase;
  letter-spacing:.5px;color:var(--dim);margin-right:2px}
.share-row a{border:2px solid var(--edge);background:var(--panel2);color:var(--ink);
  display:inline-grid;place-items:center;width:30px;height:30px;text-decoration:none;
  box-shadow:2px 2px 0 0 var(--edge);transition:transform .1s,box-shadow .1s}
.share-row a svg{width:15px;height:15px;display:block}
.share-row a:hover{transform:translate(2px,2px);box-shadow:0 0 0 0 var(--edge);
  background:var(--primary);color:#1a1c1c}
.explore-row[hidden],.share-row[hidden]{display:none}
.archive-nav{display:flex;flex-wrap:wrap;gap:8px;align-items:center;margin-top:28px;font-size:12px}
.archive-nav .lbl{font-weight:700;text-transform:uppercase;letter-spacing:.5px;color:var(--dim)}
.archive-nav a{border:2px solid var(--edge);background:var(--panel2);color:var(--ink);font-weight:700;
  text-decoration:none;padding:6px 10px;min-height:32px;display:inline-flex;gap:6px;align-items:center}
.archive-nav a[aria-current="page"]{background:var(--primary);color:#1a1c1c}
.archive-nav a .n{color:var(--dim);font-weight:400}
.archive-note{font-size:13px;color:var(--dim);margin:14px 0 0}
</style>
"""


# Same handoff endpoints the labs use (AI_URLS in lab.html), plus Google's
# AI Mode standing in for Gemini — the Gemini app has no prompt query param.
# Buttons are logo-only, drawn from the same ai-logos.json the labs inline.
EXPLORE_AI = (
    ("chatgpt", "ChatGPT", "https://chatgpt.com/?q="),
    ("claude", "Claude", "https://claude.ai/new?q="),
    ("perplexity", "Perplexity", "https://www.perplexity.ai/search?q="),
    ("gemini", "Gemini", "https://www.google.com/search?udm=50&q="),
)
# Repo layout first; falls back to a sibling tools/ dir for the bundled
# Firebase function, where this module is staged next to main.py.
_LOGO_PATHS = (REPO / "tools" / "templates" / "ai-logos.json",
               Path(__file__).resolve().parent / "tools" / "templates" / "ai-logos.json")
AI_LOGOS = json.loads(next(p for p in _LOGO_PATHS if p.exists()).read_text(encoding="utf-8"))


EXPLORE_PROMPT = (
    "Explore this AI news story and go deeper.\n\n"
    "Title: {title}\n"
    "Source: {source}, {date} — {url}\n"
    "Summary: {summary}\n\n"
    "Please: 1) summarise what actually happened, 2) explain why it matters "
    "for AI governance, security and compliance, 3) note what to watch next. "
    "Cite your sources."
)


def _explore_template() -> str:
    links = "".join(
        f'<a target="_blank" rel="noopener noreferrer" data-ai="{slug}" '
        f'aria-label="Explore with {name}" title="Explore with {name}" class="ai-{slug}">'
        f'<svg viewBox="0 0 24 24" fill="{AI_LOGOS[slug]["fill"]}" aria-hidden="true" '
        f'focusable="false">{AI_LOGOS[slug]["inner"]}</svg></a>'
        for slug, name, _ in EXPLORE_AI)
    return f'<template id="explore-tpl"><span class="lbl">Explore with AI</span>{links}</template>\n'


# Same networks and endpoints as the page-level share modal in index.html.
# Static pre-encoded links — no JS, so they work under the strict CSP and in
# feed-reader webviews alike. Logo-only buttons (brand glyphs, 24×24 paths);
# LinkedIn and Reddit reuse the same paths as the site footer.
SHARE_NETS = (
    ("X", "https://twitter.com/intent/tweet?text={t}&url={u}",
     "M18.901 1.153h3.68l-8.04 9.19L24 22.846h-7.406l-5.8-7.584-6.638 7.584H.474l8.6-9.83L0 1.154h7.594l5.243 6.932ZM17.61 20.644h2.039L6.486 3.24H4.298Z"),
    ("LinkedIn", "https://www.linkedin.com/feed/?shareActive=true&text={t}%20{u}",
     "M20.45 20.45h-3.56v-5.58c0-1.33-.02-3.04-1.85-3.04-1.86 0-2.15 1.45-2.15 2.94v5.68H9.34V9h3.41v1.56h.05c.48-.9 1.64-1.85 3.38-1.85 3.61 0 4.28 2.38 4.28 5.47v6.27zM5.34 7.43a2.07 2.07 0 1 1 0-4.13 2.07 2.07 0 0 1 0 4.13zM7.12 20.45H3.56V9h3.56v11.45z"),
    ("Facebook", "https://www.facebook.com/sharer/sharer.php?u={u}&quote={t}",
     "M24 12.073c0-6.627-5.373-12-12-12s-12 5.373-12 12c0 5.99 4.388 10.954 10.125 11.854v-8.385H7.078v-3.47h3.047V9.43c0-3.007 1.792-4.669 4.533-4.669 1.312 0 2.686.235 2.686.235v2.953H15.83c-1.491 0-1.956.925-1.956 1.874v2.25h3.328l-.532 3.47h-2.796v8.385C19.612 23.027 24 18.062 24 12.073z"),
    ("Reddit", "https://www.reddit.com/submit?url={u}&title={t}",
     "M22 11.06a2.4 2.4 0 0 0-4.07-1.72 11.8 11.8 0 0 0-6.02-1.9l1.02-3.22 2.78.62a1.73 1.73 0 1 0 .2-1.19l-3.2-.71a.6.6 0 0 0-.71.4l-1.27 4.04a11.8 11.8 0 0 0-6.36 1.94A2.4 2.4 0 1 0 2.5 13.4a4.3 4.3 0 0 0-.05.68c0 3.42 4.28 6.2 9.55 6.2s9.55-2.78 9.55-6.2c0-.22-.02-.44-.05-.65A2.4 2.4 0 0 0 22 11.06zM7.7 12.7a1.44 1.44 0 1 1 2.88 0 1.44 1.44 0 0 1-2.88 0zm8.13 4.2c-1 1-2.9 1.08-3.45 1.08-.56 0-2.46-.08-3.46-1.08a.38.38 0 0 1 .53-.53c.63.63 1.98.85 2.93.85.94 0 2.3-.22 2.93-.85a.38.38 0 0 1 .52.53zm-.27-2.76a1.44 1.44 0 1 1 0-2.88 1.44 1.44 0 0 1 0 2.88z"),
    ("Bluesky", "https://bsky.app/intent/compose?text={t}%20{u}",
     "M12 10.8c-1.087-2.114-4.046-6.053-6.798-7.995C2.566.944 1.561 1.266.902 1.565.139 1.908 0 3.08 0 3.768c0 .69.378 5.65.624 6.479.815 2.736 3.713 3.66 6.383 3.364.136-.02.275-.039.415-.056-3.912.58-7.387 2.005-2.83 7.078 5.013 5.19 6.87-1.113 7.823-4.308.953 3.195 2.05 9.271 7.733 4.308 4.267-4.308 1.172-6.498-2.74-7.078a8.741 8.741 0 0 1-.415-.056c.14.017.279.036.415.056 2.67.297 5.568-.628 6.383-3.364.246-.828.624-5.79.624-6.478 0-.69-.139-1.861-.902-2.206-.659-.298-1.664-.62-4.3 1.24C16.046 4.748 13.087 8.687 12 10.8Z"),
    ("Threads", "https://www.threads.net/intent/post?text={t}%20{u}",
     "M12.186 24h-.007c-3.581-.024-6.334-1.205-8.184-3.509C2.35 18.44 1.5 15.586 1.472 12.01v-.017c.03-3.579.879-6.43 2.525-8.482C5.845 1.205 8.6.024 12.18 0h.014c2.746.02 5.043.725 6.826 2.098 1.677 1.29 2.858 3.13 3.509 5.467l-2.04.569c-1.104-3.96-3.898-5.984-8.304-6.015-2.91.022-5.11.936-6.54 2.717C4.307 6.504 3.616 8.914 3.589 12c.027 3.086.718 5.496 2.057 7.164 1.43 1.783 3.631 2.698 6.54 2.717 2.623-.02 4.358-.631 5.8-2.045 1.647-1.613 1.618-3.593 1.09-4.798-.31-.71-.873-1.3-1.634-1.75-.192 1.352-.622 2.446-1.284 3.272-.886 1.102-2.14 1.704-3.73 1.79-1.202.065-2.361-.218-3.259-.801-1.063-.689-1.685-1.74-1.752-2.964-.065-1.19.408-2.285 1.33-3.082.88-.76 2.119-1.207 3.583-1.291a13.853 13.853 0 0 1 3.02.142c-.126-.742-.375-1.332-.75-1.757-.513-.586-1.308-.883-2.359-.89h-.029c-.844 0-1.992.232-2.721 1.32L7.734 7.847c.98-1.454 2.568-2.256 4.478-2.256h.044c3.194.02 5.097 1.975 5.287 5.388.108.046.216.094.321.142 1.49.7 2.58 1.761 3.154 3.07.797 1.82.871 4.79-1.548 7.158-1.85 1.81-4.094 2.628-7.277 2.65Zm1.003-11.69c-.242 0-.487.007-.739.021-1.836.103-2.98.946-2.916 2.143.067 1.256 1.452 1.839 2.784 1.767 1.224-.065 2.818-.543 3.086-3.71a10.5 10.5 0 0 0-2.215-.221z"),
    ("WhatsApp", "https://wa.me/?text={t}%20{u}",
     "M17.472 14.382c-.297-.149-1.758-.867-2.03-.967-.273-.099-.471-.148-.67.15-.197.297-.767.966-.94 1.164-.173.199-.347.223-.644.075-.297-.15-1.255-.463-2.39-1.475-.883-.788-1.48-1.761-1.653-2.059-.173-.297-.018-.458.13-.606.134-.133.298-.347.446-.52.149-.174.198-.298.298-.497.099-.198.05-.371-.025-.52-.075-.149-.669-1.612-.916-2.207-.242-.579-.487-.5-.669-.51-.173-.008-.371-.01-.57-.01-.198 0-.52.074-.792.372-.272.297-1.04 1.016-1.04 2.479 0 1.462 1.065 2.875 1.213 3.074.149.198 2.096 3.2 5.077 4.487.709.306 1.262.489 1.694.625.712.227 1.36.195 1.871.118.571-.085 1.758-.719 2.006-1.413.248-.694.248-1.289.173-1.413-.074-.124-.272-.198-.57-.347m-5.421 7.403h-.004a9.87 9.87 0 0 1-5.031-1.378l-.361-.214-3.741.982.998-3.648-.235-.374a9.86 9.86 0 0 1-1.51-5.26c.001-5.45 4.436-9.884 9.888-9.884 2.64 0 5.122 1.03 6.988 2.898a9.825 9.825 0 0 1 2.893 6.994c-.003 5.45-4.437 9.884-9.885 9.884m8.413-18.297A11.815 11.815 0 0 0 12.05 0C5.495 0 .16 5.335.157 11.892c0 2.096.547 4.142 1.588 5.945L.057 24l6.305-1.654a11.882 11.882 0 0 0 5.683 1.448h.005c6.554 0 11.89-5.335 11.893-11.893a11.821 11.821 0 0 0-3.48-8.413Z"),
    ("Telegram", "https://t.me/share/url?url={u}&text={t}",
     "M11.944 0A12 12 0 0 0 0 12a12 12 0 0 0 12 12 12 12 0 0 0 12-12A12 12 0 0 0 12 0a12 12 0 0 0-.056 0zm4.962 7.224c.1-.002.321.023.465.14a.506.506 0 0 1 .171.325c.016.093.036.306.02.472-.18 1.898-.962 6.502-1.36 8.627-.168.9-.499 1.201-.82 1.23-.696.065-1.225-.46-1.9-.902-1.056-.693-1.653-1.124-2.678-1.8-1.185-.78-.417-1.21.258-1.91.177-.184 3.247-2.977 3.307-3.23.007-.032.014-.15-.056-.212s-.174-.041-.249-.024c-.106.024-1.793 1.14-5.061 3.345-.48.33-.913.49-1.302.48-.428-.008-1.252-.241-1.865-.44-.752-.245-1.349-.374-1.297-.789.027-.216.325-.437.893-.663 3.498-1.524 5.83-2.529 6.998-3.014 3.332-1.386 4.025-1.627 4.476-1.635z"),
)


def share_url(item: dict, page_url: str) -> str:
    """Per-story share link: /n/<id> serves story-specific OG tags to link
    crawlers (fragments are stripped by unfurlers) and bounces humans to the
    story's anchor on the news page."""
    return f"{page_url.rsplit('/', 1)[0]}/n/{item['id']}"


def render_share_stub(item: dict, page_url: str) -> str:
    """Tiny page served at /n/<id>: Open Graph card for crawlers, instant
    redirect to the anchored story for people — on its month's archive page,
    which always holds it (the main page only shows the newest stories)."""
    target = f"{page_url}?m={item['date'][:7]}#{item['id']}"
    title = escape(item["title"])
    desc = escape(f"{item['summary']} (Source: {item['sourceName']}, as of {item['asOf']}.)")
    origin = page_url.rsplit("/", 1)[0]
    return (
        '<!DOCTYPE html>\n<html lang="en">\n<head>\n<meta charset="utf-8">\n'
        f"<title>{title} — 0pi.es News</title>\n"
        f'<meta name="description" content="{desc}">\n'
        f'<link rel="canonical" href="{escape(target)}">\n'
        '<meta property="og:type" content="article">\n'
        '<meta property="og:site_name" content="0pi.es">\n'
        f'<meta property="og:url" content="{escape(share_url(item, page_url))}">\n'
        f'<meta property="og:title" content="{title}">\n'
        f'<meta property="og:description" content="{desc}">\n'
        f'<meta property="og:image" content="{origin}/assets/social/og-image.png">\n'
        '<meta property="og:image:width" content="1200">\n'
        '<meta property="og:image:height" content="630">\n'
        '<meta name="twitter:card" content="summary_large_image">\n'
        f'<meta name="twitter:title" content="{title}">\n'
        f'<meta name="twitter:description" content="{desc}">\n'
        f'<meta name="twitter:image" content="{origin}/assets/social/og-image.png">\n'
        f'<meta http-equiv="refresh" content="0;url={escape(target)}">\n'
        "</head>\n<body>\n"
        f'<p><a href="{escape(target)}">{title}</a></p>\n'
        "</body>\n</html>\n"
    )


def _share_template() -> str:
    links = "".join(
        f'<a target="_blank" rel="noopener noreferrer" data-net="{n}" '
        f'aria-label="Share on {name}" title="Share on {name}">'
        f'<svg viewBox="0 0 24 24" fill="currentColor" aria-hidden="true" focusable="false">'
        f'<path d="{path}"/></svg></a>'
        for n, (name, _, path) in enumerate(SHARE_NETS))
    return f'<template id="share-tpl"><span class="lbl">Share</span>{links}</template>\n'


def _buttons_script(page_url: str) -> str:
    """Explore/share links for every story, built in the browser from one
    template and each story's own text. Pre-encoding twelve links per story
    made each story ~18 KB of markup; at 2,962 stories news.html reached
    52.9 MB, past the 32 MiB serving limit, and the page returned 500.
    The CSP allows inline scripts; without JS the rows simply stay hidden."""
    bases = json.dumps({slug: base for slug, _, base in EXPLORE_AI})
    nets = json.dumps([tpl for _, tpl, _ in SHARE_NETS])
    origin = json.dumps(page_url.rsplit("/", 1)[0])
    prompt = json.dumps(EXPLORE_PROMPT, ensure_ascii=False)
    return (
        _explore_template() + _share_template() +
        "<script>\n(() => {\n"
        f"  const AI = {bases}, NETS = {nets}, ORIGIN = {origin}, PROMPT = {prompt};\n"
        '  const ex = document.getElementById("explore-tpl"), sh = document.getElementById("share-tpl");\n'
        '  const fill = (s, v) => s.replace(/\\{(\\w+)\\}/g, (m, k) => k in v ? v[k] : m);\n'
        '  document.querySelectorAll("article.news-item").forEach(a => {\n'
        '    const link = a.querySelector(".news-src a");\n'
        '    const v = {title: a.querySelector("h3").textContent, summary: (a.querySelector("h3 + p") || {}).textContent || "",\n'
        '               source: a.dataset.src, date: a.dataset.date, url: link ? link.href : ""};\n'
        '    const q = encodeURIComponent(fill(PROMPT, v));\n'
        '    const er = a.querySelector(".explore-row"), sr = a.querySelector(".share-row");\n'
        '    er.append(ex.content.cloneNode(true));\n'
        '    er.querySelectorAll("a[data-ai]").forEach(l => { l.href = AI[l.dataset.ai] + q; });\n'
        '    const sv = {t: encodeURIComponent(v.title), u: encodeURIComponent(ORIGIN + "/n/" + a.id)};\n'
        '    sr.append(sh.content.cloneNode(true));\n'
        '    sr.querySelectorAll("a[data-net]").forEach(l => { l.href = fill(NETS[+l.dataset.net], sv); });\n'
        "    er.hidden = sr.hidden = false;\n"
        "  });\n})();\n</script>\n")


def _news_item_html(item: dict, page_url: str) -> str:
    status = ""
    if item.get("status"):
        status = f'      <p class="news-status">⚠ {escape(item["status"])}</p>\n'
    return (
        f'    <article class="news-item brutal brutal-shadow" id="{escape(item["id"])}" data-cat="{category_of(item)}"'
        f' data-src="{escape(item["sourceName"])}" data-date="{item["date"]}">\n'
        '      <div class="tagline">\n'
        f'        <span class="news-tag">{escape(item["tag"])}</span>\n'
        f'        <span class="news-dates">{item["date"]} · as of {item["asOf"]}</span>\n'
        "      </div>\n"
        f"      <h3>{escape(item['title'])}</h3>\n"
        f"      <p>{escape(item['summary'])}</p>\n"
        + status +
        f'      <p class="news-src">{escape(item["sourceName"])} — '
        f'<a href="{escape(item["sourceUrl"])}" target="_blank" rel="noopener noreferrer">Open source ↗</a></p>\n'
        + '      <div class="explore-row" hidden></div>\n'
        + '      <div class="share-row" hidden></div>\n' +
        "    </article>\n"
    )


def _trending_html(items: list[dict]) -> str:
    if not items:
        return ""
    rows = "".join(
        '      <li><span class="trend-tag">{tag}</span>'
        '<a href="{url}" target="_blank" rel="noopener noreferrer">{title}</a>'
        '<span class="meta">{summary}</span></li>\n'.format(
            tag=escape(i["tag"]), url=escape(i["sourceUrl"]),
            title=escape(i["title"]), summary=escape(i["summary"]))
        for i in items)
    return (
        '  <section id="trending" class="trending-box brutal brutal-shadow" aria-label="Trending in AI">\n'
        "    <h2>Trending in AI right now</h2>\n"
        '    <ul class="trending-list">\n' + rows + "    </ul>\n"
        "  </section>\n\n")


def _filter_bar_html(stories: list[dict]) -> str:
    present = {category_of(i) for i in stories}
    chips = "".join(
        f'      <button type="button" class="filter-chip" data-cat="{cat}" aria-pressed="false">{label}</button>\n'
        for cat, label in CATEGORY_LABELS.items() if cat in present)
    return (
        '    <nav class="filter-bar" aria-label="Filter news by topic">\n'
        '      <button type="button" class="filter-chip" data-cat="all" aria-pressed="true">All</button>\n'
        + chips + "    </nav>\n"
        "    <script>\n"
        "    (() => {\n"
        '      const chips = [...document.querySelectorAll(".filter-chip")];\n'
        "      chips.forEach(chip => chip.addEventListener(\"click\", () => {\n"
        '        chips.forEach(c => c.setAttribute("aria-pressed", String(c === chip)));\n'
        "        const cat = chip.dataset.cat;\n"
        '        document.querySelectorAll(".news-item").forEach(a =>\n'
        '          a.toggleAttribute("hidden", cat !== "all" && a.dataset.cat !== cat));\n'
        "      }));\n"
        "    })();\n"
        "    </script>\n")


# news.html shows the newest stories only; every story stays on its month's
# archive page (news.html?m=YYYY-MM), so the history is complete and no single
# page grows with the archive.
PAGE_LIMIT = 200
MONTH_RE = re.compile(r"^\d{4}-\d{2}$")


def _stories(data: dict) -> list[dict]:
    return [i for i in data["items"] if i.get("section") != "trending"]


def months(data: dict) -> list[tuple[str, int]]:
    """[(YYYY-MM, story count)], newest month first."""
    counts: dict[str, int] = {}
    for i in _stories(data):
        counts[i["date"][:7]] = counts.get(i["date"][:7], 0) + 1
    return sorted(counts.items(), reverse=True)


def month_label(month: str) -> str:
    from datetime import date as _date
    return _date(int(month[:4]), int(month[5:]), 1).strftime("%B %Y")


def _archive_nav_html(data: dict, current: str | None) -> str:
    links = "".join(
        f'<a href="news.html?m={m}"{" aria-current=\"page\"" if m == current else ""}>'
        f'{month_label(m)} <span class="n">{n}</span></a>'
        for m, n in months(data))
    latest = '<a href="news.html">Latest</a>' if current else ""
    return (f'  <nav class="archive-nav" aria-label="News archive by month">'
            f'<span class="lbl">Archive</span>{latest}{links}</nav>\n')


def _middle_html(data: dict, shown: list[dict], month: str | None = None) -> str:
    feed = data["feed"]
    trending = [] if month else [i for i in data["items"] if i.get("section") == "trending"]
    items_html = "".join(_news_item_html(i, feed["pageUrl"]) for i in shown)
    total = len(_stories(data))
    if month:
        note = f'{len(shown)} stories from {month_label(month)}.'
    elif total > len(shown):
        note = f'The newest {len(shown)} of {total} stories. Older stories are in the monthly archive.'
    else:
        note = ""
    note_html = f'  <p class="archive-note">{escape(note)}</p>\n' if note else ""
    return f"""<div class="wrap">
  <header class="hero">
    <div class="hero-row">
      <div class="hero-text">
        <p class="eyebrow">AI regulation &amp; critical AI headlines</p>
        <h1>News.<br>Zero Tracking.</h1>
        <p class="lede">What moved in AI regulation, and the adjacent signals that matter. Updated as news lands.</p>
      </div>
      <div class="subscribe-card brutal brutal-shadow-lg">
        <p class="eyebrow">Subscribe — no email, no tracking</p>
        <p style="margin:0;font-size:14px;color:var(--dim)">Paste this into any feed reader (RSS/Atom). We never know you subscribed.</p>
        <div class="feed-url">
          <code id="feed-url">{escape(feed["selfUrl"])}</code>
          <button type="button" class="copy-feed" id="copy-feed">Copy</button>
        </div>
        <p style="margin:0;font-size:13px"><a href="feed.xml" style="text-decoration:underline;text-decoration-thickness:2px;text-underline-offset:4px">Or open the raw feed →</a></p>
      </div>
    </div>
  </header>

{_trending_html(trending)}{_archive_nav_html(data, month)}{note_html}  <section id="news" aria-label="News items">
{_filter_bar_html(shown)}    <div class="news-list">
{items_html}    </div>
  </section>
{_archive_nav_html(data, month)}
{_buttons_script(feed["pageUrl"])}
  <script>
  (() => {{
    const btn = document.getElementById("copy-feed");
    btn.addEventListener("click", async () => {{
      try {{ await navigator.clipboard.writeText(document.getElementById("feed-url").textContent.trim()); }}
      catch {{ const r = document.createRange(); r.selectNodeContents(document.getElementById("feed-url")); const s = getSelection(); s.removeAllRanges(); s.addRange(r); document.execCommand("copy"); }}
      const old = btn.textContent; btn.textContent = "Copied"; setTimeout(() => btn.textContent = old, 1200);
    }});
  }})();
  </script>
"""


def _swap(html: str, old: str, new: str, what: str) -> str:
    if html.count(old) < 1:
        sys.exit(f"index.html chrome drifted: cannot find {what} anchor {old!r}")
    return html.replace(old, new, 1)


def render_page(data: dict, index_html: str) -> str:
    """news.html: the newest PAGE_LIMIT stories plus the month archive links."""
    return _compose(data, index_html, _middle_html(data, _stories(data)[:PAGE_LIMIT]))


def render_archive(data: dict, index_html: str, month: str) -> str:
    """news.html?m=YYYY-MM: every story from one month."""
    if not MONTH_RE.match(month):
        raise ValueError(f"not a month: {month!r}")
    shown = [i for i in _stories(data) if i["date"][:7] == month]
    if not shown:
        raise ValueError(f"no stories in {month}")
    page = _compose(data, index_html, _middle_html(data, shown, month))
    url = f"{data['feed']['pageUrl']}?m={month}"
    page = page.replace('href="https://0pi.es/news.html"', f'href="{url}"', 1)  # canonical
    return re.sub(r"<title>(.*?) — ", rf"<title>\g<1> — {month_label(month)} — ", page, count=1, flags=re.S)


def _compose(data: dict, index_html: str, middle: str) -> str:
    feed = data["feed"]
    html = index_html
    # Head metadata (title/description/canonical/social) — News page identity.
    html = re.sub(r"<title>.*?</title>", f"<title>{escape(feed['title'])} — AI regulation &amp; critical AI headlines</title>", html, count=1, flags=re.S)
    html = re.sub(r'(<meta name="description" content=")[^"]*(">)', rf"\g<1>{escape(feed['subtitle'])}\g<2>", html, count=1)
    html = html.replace('href="https://0pi.es/"', 'href="https://0pi.es/news.html"')
    html = html.replace('content="https://0pi.es/"', 'content="https://0pi.es/news.html"')
    for prop in ("og:title", "twitter:title"):
        html = re.sub(rf'(<meta (?:property|name)="{prop}" content=")[^"]*(">)', r"\g<1>0pi.es News\g<2>", html, count=1)
    for prop in ("og:description", "twitter:description"):
        html = re.sub(rf'(<meta (?:property|name)="{prop}" content=")[^"]*(">)', rf"\g<1>{escape(feed['subtitle'])}\g<2>", html, count=1)
    # Autodiscovery + scoped styles, kept adjacent to </head>.
    html = _swap(html, "</head>",
                 '<link rel="alternate" type="application/atom+xml" title="0pi.es News" href="feed.xml">\n'
                 + NEWS_STYLES + "</head>", "head close")
    # Nav: Labs points home, News is active. Index must already carry the News
    # link. Attribute-tolerant so extras like data-i18n don't count as drift.
    html, n = re.subn(r'<a class="active" href="#labs"([^>]*)>Labs</a>',
                      r'<a href="./#labs"\1>Labs</a>', html, count=1)
    if not n:
        sys.exit("index.html chrome drifted: cannot find nav Labs anchor")
    html, n = re.subn(r'<a href="news.html"([^>]*)>News</a>',
                      r'<a class="active" href="news.html"\1>News</a>', html, count=1)
    if not n:
        sys.exit("index.html chrome drifted: cannot find nav News anchor")
    # Replace the middle: <div class="wrap"> .. up to the footer inside it.
    start = html.find('<div class="wrap">')
    foot = html.find("<footer>", start)
    if start == -1 or foot == -1:
        sys.exit("index.html chrome drifted: wrap/footer anchors not found")
    return html[:start] + middle + "\n  " + html[foot:]


def main() -> None:
    data = load_news()
    index_path = OUT / "index.html"
    if not index_path.exists():
        sys.exit(f"{index_path} not found — run from the 0pies repo (or set LAB_OUT)")
    page = render_page(data, index_path.read_text(encoding="utf-8"))
    (OUT / "news.html").write_text(page, encoding="utf-8")
    (OUT / "feed.xml").write_text(render_feed(data), encoding="utf-8")
    print(f"news: wrote {OUT / 'news.html'} ({len(data['items'])} items) and {OUT / 'feed.xml'}")


if __name__ == "__main__":
    main()
