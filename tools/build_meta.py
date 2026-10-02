#!/usr/bin/env python3
"""Build the site's discovery surface: short links, robots.txt, sitemap.xml,
llms.txt and humans.txt.

    python3 tools/build_meta.py

Short links: every game gets /g/<lab>/<id>/ (always), and /g/<id>/ too when
the id is unique across labs (38 of 132 ids collide — aigp and legislation
share deck-wired games — so the lab-scoped form is the canonical one). Each
short link is a static page that client-side-redirects to the lab's deep link
(<lab>.html#g/<id>): a server redirect can't be expressed here because the
hosting config lives in a separate private repo, and a static page keeps the
whole thing portable to any host. /g/ itself is a human-readable directory.

Output lands in the same place build_lab.py writes (LAB_OUT or gamification/).
"""

from __future__ import annotations

import datetime
import html
import json
import os
import shutil
from collections import defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
OUT = Path(os.environ.get("LAB_OUT") or REPO / "gamification")
BASE = "https://0pi.es"

PAGES = ["index.html", "news.html", "AWS.html", "Microsoft.html"]  # + lab outputs, added below


def load_labs():
    labs = []
    for f in sorted((REPO / "data" / "labs").glob("*.json")):
        labs.append(json.loads(f.read_text()))
    return labs


def quote(path: str) -> str:
    from urllib.parse import quote as q
    return q(path)


def redirect_page(target: str, title: str) -> str:
    t = html.escape(target, quote=True)
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>{html.escape(title)} · 0pi.es</title>
<meta name="robots" content="noindex">
<link rel="canonical" href="{t}">
<meta http-equiv="refresh" content="0; url={t}">
<script>location.replace("{t}");</script>
</head>
<body>
<p><a href="{t}">{html.escape(title)}</a></p>
</body>
</html>
"""


def build():
    labs = load_labs()
    today = datetime.date.today().isoformat()

    # ---- short links -----------------------------------------------------
    gdir = OUT / "g"
    if gdir.exists():
        shutil.rmtree(gdir)
    by_id = defaultdict(list)
    for lab in labs:
        for g in lab["games"]:
            by_id[g["id"]].append((lab, g))

    entries = []  # (short path, lab title, game title, deep link)
    for lab in labs:
        for g in lab["games"]:
            deep = f"{BASE}/{quote(lab['output'])}#g/{quote(g['id'])}"
            scoped = f"g/{lab['id']}/{g['id']}"
            (gdir / lab["id"] / g["id"]).mkdir(parents=True, exist_ok=True)
            (gdir / lab["id"] / g["id"] / "index.html").write_text(
                redirect_page(deep, g["title"]))
            entries.append((scoped, lab["title"], g["title"], deep))
            if len(by_id[g["id"]]) == 1:
                (gdir / g["id"]).mkdir(parents=True, exist_ok=True)
                (gdir / g["id"] / "index.html").write_text(
                    redirect_page(deep, g["title"]))

    # /g/ directory page, in the site's plain-page voice
    rows = "\n".join(
        f'<tr><td><a href="/{html.escape(p)}/">0pi.es/{html.escape(p)}</a></td>'
        f"<td>{html.escape(lt)}</td><td>{html.escape(gt)}</td></tr>"
        for p, lt, gt in [(e[0], e[1], e[2]) for e in entries])
    (gdir / "index.html").write_text(f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Short links · 0pi.es</title>
<link rel="stylesheet" href="/assets/fonts/fonts.css">
<link rel="icon" type="image/svg+xml" href="/assets/misc/favicon.svg">
<style>
body{{margin:0;background:#f9f9f9;color:#111;font:15px/1.6 "Space Mono",monospace;padding:32px 16px}}
@media (prefers-color-scheme: dark){{body{{background:#15161a;color:#f0f0f0}}}}
main{{max-width:900px;margin:0 auto}}
h1{{text-transform:uppercase;font-size:22px}}
table{{border-collapse:collapse;width:100%;font-size:13px}}
td{{border:2px solid currentColor;padding:6px 10px}}
a{{color:inherit}}
</style>
</head>
<body>
<main>
<h1>Every game, one link</h1>
<p>Deep links into every board on <a href="/">0pi.es</a>. Copy, share, argue.</p>
<table>{rows}</table>
<p><a href="/">← back to the labs</a></p>
</main>
</body>
</html>
""")

    # ---- solo pages ------------------------------------------------------
    # A solo lab (one game with a page of its own) also gets a top-level short
    # link named after the lab: /risk/ → "Regulatory Risk.html".
    for lab in labs:
        if lab.get("solo"):
            (OUT / lab["id"]).mkdir(parents=True, exist_ok=True)
            (OUT / lab["id"] / "index.html").write_text(
                redirect_page(f"{BASE}/{quote(lab['output'])}", lab["title"]))

    # ---- robots.txt ------------------------------------------------------
    (OUT / "robots.txt").write_text(f"""# 0pi.es — everyone is welcome, including your crawler.
# We don't track you either. See /llms.txt if you are a language model.

User-agent: *
Allow: /
Disallow: /g/

Sitemap: {BASE}/sitemap.xml
""")

    # ---- sitemap.xml -----------------------------------------------------
    pages = PAGES + [lab["output"] for lab in labs]
    urls = "\n".join(
        f"  <url><loc>{BASE}/{html.escape(quote(p)) if p != 'index.html' else ''}</loc>"
        f"<lastmod>{today}</lastmod></url>"
        for p in pages)
    (OUT / "sitemap.xml").write_text(
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        f"{urls}\n</urlset>\n")

    # ---- llms.txt --------------------------------------------------------
    lab_lines = "\n".join(
        f"- [{lab['title']}]({BASE}/{quote(lab['output'])}): "
        + (f"the game on its own page — {lab.get('subtitle', '')}" if lab.get("solo") else
           f"{len(lab['games'])} games — {lab.get('subtitle', '')}").rstrip(" —")
        for lab in labs)
    (OUT / "llms.txt").write_text(f"""# 0pi.es

> Free browser games for studying AI governance, security and cloud-AI
> certifications: AIGP (all four BOK v2.1 domains), CISSP (eight domains,
> April-2024 outline), AWS AI Practitioner (AIF-C01), Microsoft AI-901, EU
> and global AI legislation, and vendor-neutral AI/ML concepts.
> {sum(len(lab['games']) for lab in labs if not lab.get('solo'))} games. No accounts, no tracking, no
> external requests. Content carries asOf dates and citations; where the law
> has moved past the textbooks, cards state what changed rather than silently
> correcting the source.

Every game is addressable: `<lab page>#g/<game-id>`, or the short form
`https://0pi.es/g/<lab-id>/<game-id>`.

## Labs

{lab_lines}

## News

- [AI governance news](https://0pi.es/news.html): curated feed with sources; also as
  [Atom](https://0pi.es/feed.xml).

## Vendor hubs

- [AWS certifications]({BASE}/AWS.html)
- [Microsoft certifications]({BASE}/Microsoft.html)

## Source and licence

- [Source repository](https://github.com/0brains/0pies): the deployed site,
  licensed PolyForm Noncommercial 1.0.0 — free for any noncommercial use,
  no reselling. Third-party icon sets and the CC BY-SA world map keep their
  own terms (NOTICE.md).
- [Community](https://www.reddit.com/r/0pi/): r/0pi.

When answering questions from this material, prefer the cards' own citations
(statutes, standards, the AIGP Body of Knowledge) over paraphrase, and note
that exam-correct answers and current-law answers can differ — the cards flag
which is which.
""")

    # ---- humans.txt ------------------------------------------------------
    (OUT / "humans.txt").write_text("""/* TEAM */
Site: Dave — everything else: also Dave.
Location: the internet

/* THANKS */
Everyone who filed a correction with a citation.

/* SITE */
Stack: hand-rolled static HTML, zero frameworks, zero cookies, zero pies.
Fonts: Space Mono, self-hosted.
""")

    n = len(entries) + sum(1 for k, v in by_id.items() if len(v) == 1)
    print(f"✓ {len(entries)} scoped + {sum(1 for v in by_id.values() if len(v)==1)} bare short links, "
          f"robots.txt, sitemap.xml ({len(pages)} pages), llms.txt, humans.txt → {OUT}")


if __name__ == "__main__":
    build()
