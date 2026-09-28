#!/usr/bin/env python3
"""Checks for build_news.py. Run: python3 tools/test_build_news.py"""
import copy, json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
import build_news

GOOD = json.loads((build_news.REPO / "data" / "news.json").read_text())

def expect_errors(mutate, needle):
    data = copy.deepcopy(GOOD)
    mutate(data)
    errs = build_news.validate(data)
    assert any(needle in e for e in errs), f"expected error containing {needle!r}, got {errs}"

def main():
    assert build_news.validate(GOOD) == [], build_news.validate(GOOD)
    print("ok seed-valid")
    expect_errors(lambda d: d["items"][0].pop("asOf"), "asOf"); print("ok asof-required")
    expect_errors(lambda d: d["items"][0].pop("sourceUrl"), "sourceUrl"); print("ok citation-required")
    expect_errors(lambda d: d["items"][0].update(sourceUrl="http://x.example/a"), "https"); print("ok https-required")
    expect_errors(lambda d: d["items"][0].update(summary="a <b>bold</b> claim"), "markup"); print("ok no-markup")
    expect_errors(lambda d: d["items"][1].update(id=d["items"][0]["id"]), "unique"); print("ok unique-ids")
    expect_errors(lambda d: d["items"][0].update(date="30/07/2026"), "date"); print("ok iso-dates")
    expect_errors(lambda d: d["feed"].pop("selfUrl"), "selfUrl"); print("ok feed-meta")

    import xml.etree.ElementTree as ET
    xml = build_news.render_feed(GOOD)
    root = ET.fromstring(xml)
    NS = "{http://www.w3.org/2005/Atom}"
    assert root.tag == f"{NS}feed"
    entries = root.findall(f"{NS}entry")
    assert len(entries) == len(GOOD["items"])
    assert root.find(f"{NS}updated").text == max(i["date"] for i in GOOD["items"]) + "T00:00:00Z"
    ids = [e.find(f"{NS}id").text for e in entries]
    assert ids[0] == GOOD["feed"]["pageUrl"] + "#" + GOOD["items"][0]["id"]
    assert len(set(ids)) == len(ids)
    links = [l.get("href") for l in root.findall(f"{NS}link")]
    assert GOOD["feed"]["selfUrl"] in links and GOOD["feed"]["pageUrl"] in links
    assert build_news.render_feed(GOOD) == xml  # deterministic
    print("ok atom-feed")

    from html import escape
    index_html = (build_news.OUT / "index.html").read_text(encoding="utf-8")
    page = build_news.render_page(GOOD, index_html)
    assert page.count("<topbar>") == 1 and "</footer>" in page
    assert 'rel="alternate" type="application/atom+xml"' in page
    # Attribute-tolerant: the index nav carries data-i18n attrs since the i18n rollout.
    assert 'href="./#labs"' in page and '<a class="active" href="news.html"' in page
    assert "share-open" in page and "NO COOKIES. NO TRACKING. NO PIES." in page
    assert "cookie-overlay" in page and "terms-overlay" in page
    for item in GOOD["items"]:
        assert escape(item["title"]) in page or item["title"] in page
        assert escape(item["sourceUrl"]) in page or item["sourceUrl"] in page
    assert "googleapis" not in page and "Instrument Serif" not in page
    assert "ai-newsfeed" not in page
    assert build_news.render_page(GOOD, index_html) == page  # deterministic
    print("ok page-compose")

    import fetch_news
    existing = copy.deepcopy(GOOD)
    hand_edited = existing["items"][0]
    fetched = [
        dict(hand_edited, title="OVERWRITE ATTEMPT"),  # same id — must lose
        {"id": "ec-new-guidance", "date": "2026-08-05", "asOf": "2026-08-06",
         "tag": "EU AI Act", "title": "New guidance lands",
         "summary": "Fresh item from the fetcher.", "sourceName": "European Commission",
         "sourceUrl": "https://digital-strategy.ec.europa.eu/en/news/new-guidance"},
    ]
    merged = fetch_news.merge(existing, fetched, today="2026-08-06")
    ids = [i["id"] for i in merged["items"]]
    assert "ec-new-guidance" in ids
    kept = next(i for i in merged["items"] if i["id"] == hand_edited["id"])
    assert kept["title"] == hand_edited["title"]
    assert ids == [i["id"] for i in sorted(merged["items"], key=lambda x: (x["date"], x["id"]), reverse=True)]
    assert build_news.validate(merged) == []
    big = [dict(fetched[1], id=f"filler-{n}", date="2026-01-01") for n in range(40)]
    uncapped = fetch_news.merge(existing, big, today="2026-08-06")["items"]
    assert len(uncapped) == len(existing["items"]) + 40  # no length limit — page is the archive
    trend_count = sum(1 for i in existing["items"] if i.get("section") == "trending")
    capped_news = [i for i in fetch_news.merge(existing, big, today="2026-08-06", cap=10)["items"]
                   if i.get("section") != "trending"]
    assert len(capped_news) == 10  # explicit cap still honoured if ever needed
    try:
        fetch_news.parse_feed(b'<?xml version="1.0"?><!DOCTYPE r [<!ENTITY a "x">]><rss/>', fetch_news.SOURCES[0])
        raise AssertionError("DTD feed was not rejected")
    except ValueError:
        pass
    rss = b'''<?xml version="1.0"?><rss version="2.0"><channel>
      <item><title>AI Act guidance published</title><link>https://example.org/ai-act-guidance</link>
      <description>New &lt;b&gt;guidance&lt;/b&gt; on the AI Act.</description>
      <pubDate>Wed, 05 Aug 2026 10:00:00 +0000</pubDate></item>
      <item><title>Cheese prices rise</title><link>https://example.org/cheese</link>
      <description>Nothing to do with the topic.</description>
      <pubDate>Wed, 05 Aug 2026 10:00:00 +0000</pubDate></item>
      </channel></rss>'''
    parsed = fetch_news.parse_feed(rss, fetch_news.SOURCES[0])
    assert len(parsed) == 1, parsed  # keyword filter drops the cheese item
    assert parsed[0]["title"] == "AI Act guidance published"
    assert "<" not in parsed[0]["summary"]  # markup stripped
    assert parsed[0]["id"].startswith(fetch_news.SOURCES[0]["slug"] + "-")
    print("ok fetch-merge")

    many = [{"id": f"x-{n}", "date": f"2026-08-{n:02d}", "asOf": "2026-08-06", "tag": "t",
             "title": f"AI item {n}", "summary": "s", "sourceName": "X",
             "sourceUrl": f"https://example.org/{n}"} for n in range(1, 6)]
    capped = fetch_news.cap_source(many, {"max": 2})
    assert [i["id"] for i in capped] == ["x-5", "x-4"]  # newest two win
    assert len(fetch_news.cap_source(many, {})) == len(many)  # no max → untouched
    tags = {s["tag"] for s in fetch_news.SOURCES}
    assert "Research" in tags and "Tools & code" in tags and "Frontier labs" in tags
    assert all(s.get("max") for s in fetch_news.SOURCES if s["tag"] in ("Research", "Tools & code", "Frontier labs"))
    print("ok source-caps")

    gh_json = json.dumps({"items": [
        {"full_name": "acme/agent-kit", "html_url": "https://github.com/acme/agent-kit",
         "description": "Toolkit for building AI agents", "stargazers_count": 4210,
         "created_at": "2026-08-01T09:00:00Z"},
        {"full_name": "x/no-desc", "html_url": "https://github.com/x/no-desc",
         "description": None, "stargazers_count": 900, "created_at": "2026-08-02T00:00:00Z"},
    ]}).encode()
    gh_src = next(s for s in fetch_news.SOURCES if s.get("kind") == "gh")
    gh = fetch_news.parse_gh(gh_json, gh_src)
    assert gh[0]["title"] == "acme/agent-kit — 4,210 stars"
    assert gh[0]["date"] == "2026-08-01" and gh[0]["sourceUrl"] == "https://github.com/acme/agent-kit"
    assert gh[1]["summary"]  # missing description still yields a valid summary
    assert build_news.validate({**GOOD, "items": sorted(gh, key=lambda i: i["date"], reverse=True)}) == []
    hn_json = json.dumps({"hits": [
        {"title": "Show HN: Local LLM router", "objectID": "45001", "points": 512,
         "created_at": "2026-08-05T12:00:00Z"},
        {"title": "Sourdough tips", "objectID": "45002", "points": 300,
         "created_at": "2026-08-05T13:00:00Z"},
    ]}).encode()
    hn_src = next(s for s in fetch_news.SOURCES if s.get("kind") == "hn")
    hn = fetch_news.parse_hn(hn_json, hn_src)
    assert len(hn) == 1  # keyword filter drops sourdough
    assert hn[0]["sourceUrl"] == "https://news.ycombinator.com/item?id=45001"
    assert "512 points" in hn[0]["summary"]
    assert build_news.validate({**GOOD, "items": hn}) == []
    print("ok trending-parsers")

    trended = copy.deepcopy(GOOD)
    trended["items"].insert(0, {
        "id": "gh-acme-agent-kit", "date": "2026-08-06", "asOf": "2026-08-06",
        "tag": "Trending on GitHub", "title": "acme/agent-kit — 4,210 stars",
        "summary": "Toolkit for building AI agents", "sourceName": "GitHub",
        "sourceUrl": "https://github.com/acme/agent-kit", "section": "trending"})
    tpage = build_news.render_page(trended, index_html)
    assert 'id="trending"' in tpage and "acme/agent-kit" in tpage
    ti, ni = tpage.find('id="trending"'), tpage.find('class="news-list"')
    assert -1 < ti < ni  # trending box sits above the news list
    assert tpage.count("acme/agent-kit") >= 1 and "news-item" in tpage
    plain = {**GOOD, "items": [i for i in GOOD["items"] if i.get("section") != "trending"]}
    assert 'id="trending"' not in build_news.render_page(plain, index_html)  # no trending items → no box
    feed_xml = build_news.render_feed(trended)
    assert "acme/agent-kit" in feed_xml  # trending items still reach subscribers
    print("ok trending-box")

    masto_json = json.dumps([
        {"url": "https://example.org/ai-story", "title": "New LLM benchmark drops",
         "description": "d", "history": [{"day": "1770336000", "accounts": "212"}]},
        {"url": "https://example.org/politics", "title": "Election roundup",
         "description": "d", "history": [{"day": "1770336000", "accounts": "999"}]},
    ]).encode()
    masto_src = next(s for s in fetch_news.SOURCES if s.get("kind") == "masto")
    masto = fetch_news.parse_mastodon(masto_json, masto_src)
    assert len(masto) == 1 and masto[0]["title"] == "New LLM benchmark drops"
    assert masto[0]["sourceUrl"] == "https://example.org/ai-story"
    assert masto[0]["section"] == "trending" and "212" in masto[0]["summary"]
    bsky_json = json.dumps({"topics": [
        {"topic": "Claude agents", "link": "/profile/trending.bsky.app/feed/1"},
        {"topic": "Clacton By-Election", "link": "/profile/trending.bsky.app/feed/2"},
    ]}).encode()
    bsky_src = next(s for s in fetch_news.SOURCES if s.get("kind") == "bsky")
    bsky = fetch_news.parse_bluesky(bsky_json, bsky_src)
    assert len(bsky) == 1 and bsky[0]["title"] == "Claude agents"
    assert bsky[0]["sourceUrl"].startswith("https://bsky.app/")
    assert build_news.validate({**GOOD, "items": masto + bsky}) == []
    print("ok social-trending")

    sm = b'''<?xml version="1.0" encoding="UTF-8"?>
    <urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
    <url><loc>https://www.anthropic.com/news/claude-cowork</loc><lastmod>2026-08-01T10:00:00.000Z</lastmod></url>
    <url><loc>https://www.anthropic.com/about</loc><lastmod>2026-08-02T10:00:00.000Z</lastmod></url>
    <url><loc>https://www.anthropic.com/news</loc><lastmod>2026-08-03T10:00:00.000Z</lastmod></url>
    </urlset>'''
    sm_src = next(s for s in fetch_news.SOURCES if s.get("kind") == "sitemap")
    smi = fetch_news.parse_sitemap(sm, sm_src)
    assert len(smi) == 1, smi  # /about and the /news index page are excluded
    assert smi[0]["title"] == "Claude Cowork" and smi[0]["date"] == "2026-08-01"
    assert smi[0]["sourceUrl"] == "https://www.anthropic.com/news/claude-cowork"
    assert build_news.validate({**GOOD, "items": smi}) == []
    try:
        fetch_news.parse_sitemap(b'<?xml version="1.0"?><!DOCTYPE u [<!ENTITY x "y">]><urlset/>', sm_src)
        raise AssertionError("DTD sitemap was not rejected")
    except ValueError:
        pass
    # anthropicalign left the whitelist when the alignment blog dropped its feed.
    for slug in ("anthropic", "mistral", "qwen", "digichina", "cset", "technode"):
        assert any(s["slug"] == slug for s in fetch_news.SOURCES), f"missing source {slug}"
    print("ok labs-china")

    newsapi_json = json.dumps({"status": "ok", "articles": [
        {"source": {"id": "the-verge", "name": "The Verge"},
         "title": "Anthropic ships a new Claude model | The Verge",
         "description": "The frontier lab's latest release.",
         "url": "https://www.theverge.com/ai/claude-release",
         "publishedAt": "2026-08-12T09:00:00Z"},
        {"source": {"id": "wired", "name": "Wired"},
         "title": "Best mechanical keyboards of 2026",
         "description": "Clacky picks.", "url": "https://www.wired.com/keyboards",
         "publishedAt": "2026-08-12T10:00:00Z"},
        {"source": {"id": None, "name": "[Removed]"}, "title": "[Removed]",
         "description": None, "url": "https://removed.com", "publishedAt": "2026-08-12T11:00:00Z"},
    ]}).encode()
    napi = fetch_news.parse_newsapi(newsapi_json, fetch_news.NEWSAPI_SOURCE)
    assert len(napi) == 1, napi  # keyword filter drops keyboards and [Removed]
    assert napi[0]["title"] == "Anthropic ships a new Claude model"
    assert napi[0]["sourceName"] == "The Verge · via NewsAPI"  # NewsAPI attribution required by ToS
    assert napi[0]["id"].startswith("newsapi-")
    assert build_news.validate({**GOOD, "items": napi}) == []
    from datetime import datetime as _dt
    now = _dt(2026, 8, 14, 7, 0, 0)
    assert fetch_news._newsapi_due({}, now)  # no state → due
    assert not fetch_news._newsapi_due({"lastFetch": "2026-08-14T06:45:00Z"}, now)
    assert fetch_news._newsapi_due({"lastFetch": "2026-08-14T06:29:00Z"}, now)
    assert fetch_news._newsapi_due({"lastFetch": "garbage"}, now)
    # Query aligns with the site's keyword filter: every term the query sends
    # to NewsAPI would itself pass the local KEYWORDS gate.
    for term in fetch_news.NEWSAPI_QUERY.split(" OR "):
        assert fetch_news.KEYWORDS.search(term.strip('"')), f"query term {term} not in KEYWORDS"
    assert build_news.category_of({"tag": "AI news"}) == "labs-tools"
    import os as _os
    _os.environ.pop("NEWSAPI_KEY", None)
    assert fetch_news.fetch_newsapi({}, "2026-08-07") == []  # no key → skip, no network
    print("ok newsapi")

    def _story(id_, title, source="Anthropic", url="https://example.org/a"):
        return {"id": id_, "date": "2026-08-13", "asOf": "2026-08-13", "tag": "Frontier labs",
                "title": title, "summary": "s", "sourceName": source, "sourceUrl": url}
    base = copy.deepcopy(GOOD)
    # Same batch, same story: first-party wins over the aggregator copy.
    batch = [_story("newsapi-claude-watermarks", "Anthropic Ships Claude Watermarks!",
                    "TechCrunch · via NewsAPI", "https://techcrunch.com/claude-watermarks"),
             _story("anthropic-claude-watermarks", "Anthropic ships Claude watermarks")]
    ids = {i["id"] for i in fetch_news.merge(base, batch, today="2026-08-13")["items"]}
    assert "anthropic-claude-watermarks" in ids and "newsapi-claude-watermarks" not in ids
    # Aggregator copy of an already-archived story is dropped.
    archived = fetch_news.merge(base, [_story("anthropic-claude-watermarks",
                                              "Anthropic ships Claude watermarks")], today="2026-08-13")
    later = fetch_news.merge(archived, [batch[0]], today="2026-08-14")
    assert "newsapi-claude-watermarks" not in {i["id"] for i in later["items"]}
    # First-party arriving later evicts the archived aggregator copy.
    agg_first = fetch_news.merge(base, [batch[0]], today="2026-08-13")
    assert "newsapi-claude-watermarks" in {i["id"] for i in agg_first["items"]}
    swapped = fetch_news.merge(agg_first, [batch[1]], today="2026-08-14")
    ids = {i["id"] for i in swapped["items"]}
    assert "anthropic-claude-watermarks" in ids and "newsapi-claude-watermarks" not in ids
    # Two first-party outlets with the same headline both stay.
    two = fetch_news.merge(base, [_story("technode-x", "New AI rules land", "TechNode", "https://technode.com/x"),
                                  _story("cset-y", "New AI rules land", "CSET", "https://cset.georgetown.edu/y")],
                           today="2026-08-13")
    ids = {i["id"] for i in two["items"]}
    assert "technode-x" in ids and "cset-y" in ids
    assert build_news.validate(swapped) == []
    print("ok title-dedup")

    assert build_news.category_of({"tag": "EU AI Act"}) == "regulation"
    assert build_news.category_of({"tag": "Cyber news"}) == "security"
    assert build_news.category_of({"tag": "UK NCSC"}) == "security"
    assert build_news.category_of({"tag": "Research"}) == "research"
    assert build_news.category_of({"tag": "Hugging Face nonsense tag"}) == "regulation"  # fallback
    assert build_news.category_of({"tag": "Tools & code"}) == "labs-tools"
    assert build_news.category_of({"tag": "AI certifications"}) == "certs"
    assert "certs" in build_news.CATEGORY_LABELS
    assert any(s["tag"] == "AI certifications" for s in fetch_news.SOURCES)
    assert '--cat:var(--concepts)' in build_news.NEWS_STYLES  # cert colour from site palette
    fpage = build_news.render_page(GOOD, index_html)
    assert 'class="filter-bar"' in fpage and 'data-cat="all"' in fpage
    assert 'data-cat="regulation"' in fpage
    import re as _re
    assert _re.search(r'<article class="news-item[^"]*"[^>]*data-cat="[a-z-]+"', fpage)
    assert "filter-chip" in fpage
    print("ok tag-filter")

    from urllib.parse import quote
    first = GOOD["items"][0]
    for host in ("https://chatgpt.com/?q=", "https://claude.ai/new?q=",
                 "https://www.perplexity.ai/search?q=", "https://www.google.com/search?udm=50&amp;q="):
        assert host in fpage, f"missing explore link {host}"
    assert quote(first["sourceUrl"], safe="") in fpage  # prompt carries the source URL
    assert fpage.count("explore-row") >= len([i for i in GOOD["items"] if i.get("section") != "trending"])
    for svc in ("ChatGPT", "Claude", "Perplexity", "Gemini"):
        assert f'aria-label="Explore with {svc}"' in fpage  # logo-only links stay labelled
    assert 'class="ai-gemini"' in fpage and fpage.count("<svg viewBox=\"0 0 24 24\"") >= 4
    print("ok explore-ai")

    for rule in ('--cat:var(--legislation)', '--cat:var(--secondary)',
                 '--cat:var(--microsoft)', '--cat:var(--aigp)'):
        assert rule in fpage, f"missing category colour mapping {rule}"
    assert ".news-item .news-tag{background:var(--cat, var(--primary))}" in fpage
    print("ok category-colours")

if __name__ == "__main__":
    main()
    print("ALL OK")
