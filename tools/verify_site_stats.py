#!/usr/bin/env python3
"""Check the hand-maintained site pages against the manifest-derived counts.

    python3 tools/verify_site_stats.py

The landing page and llms.txt live in the public site repo and are edited by
hand — the landing page carries an inline i18n bundle across 18 locales, which
is why generating it was abandoned. What was lost with the generator was the
one useful half of it: the numbers being counted rather than typed.

So the numbers are still derived (tools/site_stats.py), and this checks the
hand-written pages against them instead of overwriting the pages. It reads:

  index.html  hero totals (N games / N cards) and each lab card's GAMES/CARDS
  llms.txt    the headline game total and each lab's game count

Exit 1 on any drift, naming the file, the claim and the derived value. This is
a ship gate, not a build step: it inspects the deploy target, which the private
pipeline repo does not own.

Point it at a site clone with LAB_OUT, or let it default to this repo's gamification/.
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path

import site_stats

REPO = Path(__file__).resolve().parent.parent
SITE = Path(os.environ.get("LAB_OUT") or REPO / "gamification")

# index.html hero: <span class="n">154</span><span class="l" …>games</span>
HERO = re.compile(r'<span class="n">([\d,]+)</span><span class="l"[^>]*>(games|cards)')
# index.html lab card: <a … href="AI Concepts.html"> … <span class="stat">27 GAMES</span>
CARD_HREF = re.compile(r'href="([^"]+\.html)"')
CARD_STAT = re.compile(r'<span class="stat">([\d,]+) (GAMES|CARDS)</span>')
# llms.txt: "> 160 games." and "- [Title](url): 52 games — …"
LLMS_TOTAL = re.compile(r'^>\s*([\d,]+) games', re.M)
SITE_VERSION = re.compile(r'<span id="site-version">([^<]+)</span>')
CHANGELOG = REPO / "CHANGELOG.md"
CHANGELOG_TOP = re.compile(r"^## (\d{4}\.\d{2}\.\d{2})\s*$", re.M)
RISK_CHECKED = re.compile(r'<time id="risk-checked" datetime="([^"]+)">([^<]+)</time>')
RISK_DATA = REPO / "data" / "aigp" / "knowledge" / "domain-ii.json"
LLMS_LAB = re.compile(r'^- \[([^\]]+)\]\((https?://[^)]+)\): ([\d,]+) games', re.M)


def num(text: str) -> int:
    return int(text.replace(",", ""))


def fmt(n: int) -> str:
    return f"{n:,}"


def check_index(path: Path, stats: dict, totals: dict) -> list[str]:
    html = path.read_text(encoding="utf-8")
    problems: list[str] = []

    hero = {kind: num(v) for v, kind in HERO.findall(html)}
    for kind in ("games", "cards"):
        if kind not in hero:
            problems.append(f"index.html: no hero '{kind}' total found")
        elif hero[kind] != totals[kind]:
            problems.append(f"index.html: hero says {fmt(hero[kind])} {kind}, "
                            f"manifests total {fmt(totals[kind])}")

    # Each lab card: the nearest preceding href says which lab the chips describe.
    by_output = {s["output"]: s for s in stats.values()}
    for m in CARD_STAT.finditer(html):
        prior = CARD_HREF.findall(html[: m.start()])
        if not prior:
            continue
        from urllib.parse import unquote
        import html as _html
        lab = by_output.get(unquote(_html.unescape(prior[-1])))
        if not lab:
            continue   # a card pointing at a vendor hub or an external page
        claimed, kind = num(m.group(1)), m.group(2).lower()
        derived = lab["games"] if kind == "games" else lab["cards"]
        if claimed != derived:
            problems.append(f"index.html: '{lab['title']}' card says {fmt(claimed)} {kind}, "
                            f"manifest has {fmt(derived)}")

    # The footer's release number is the newest CHANGELOG entry, so the page
    # and the release notes it links to can't disagree.
    shown = SITE_VERSION.search(html)
    top = CHANGELOG_TOP.search(CHANGELOG.read_text(encoding="utf-8")) if CHANGELOG.is_file() else None
    if not shown:
        problems.append("index.html: no footer release number (<span id=\"site-version\">)")
    elif not top:
        problems.append("CHANGELOG.md: no '## YYYY.MM.DD' release heading found")
    elif shown.group(1) != top.group(1):
        problems.append(f"index.html: footer says release {shown.group(1)}, "
                        f"CHANGELOG.md's newest is {top.group(1)}")

    # The featured Regulatory Risk banner promises when its laws were checked;
    # that date belongs to the campaign data, not to whoever last edited the page.
    stamp = RISK_CHECKED.search(html)
    if stamp:
        import json
        as_of = json.loads(RISK_DATA.read_text(encoding="utf-8"))["campaign"]["asOf"]
        if stamp.group(1) != as_of or stamp.group(2) != as_of:
            problems.append(f"index.html: Regulatory Risk banner says laws checked "
                            f"{stamp.group(2)} (datetime {stamp.group(1)}), campaign asOf is {as_of}")
    return problems


def check_llms(path: Path, stats: dict, totals: dict) -> list[str]:
    text = path.read_text(encoding="utf-8")
    problems: list[str] = []

    m = LLMS_TOTAL.search(text)
    if not m:
        problems.append("llms.txt: no headline game total found")
    elif num(m.group(1)) != totals["games"]:
        problems.append(f"llms.txt: headline says {fmt(num(m.group(1)))} games, "
                        f"manifests total {fmt(totals['games'])}")

    from urllib.parse import unquote
    by_output = {s["output"]: s for s in stats.values()}
    for title, url, games in LLMS_LAB.findall(text):
        lab = by_output.get(unquote(url.rsplit("/", 1)[-1]))
        if not lab:
            problems.append(f"llms.txt: '{title}' links to {url}, which no lab manifest builds")
        elif num(games) != lab["games"]:
            problems.append(f"llms.txt: '{title}' says {fmt(num(games))} games, "
                            f"manifest has {fmt(lab['games'])}")
    return problems


def main() -> int:
    stats = site_stats.lab_stats()
    totals = site_stats.totals(stats)

    problems: list[str] = []
    for name, checker in (("index.html", check_index), ("llms.txt", check_llms)):
        path = SITE / name
        if not path.is_file():
            problems.append(f"{name}: not found at {path} — point LAB_OUT at a site clone")
            continue
        problems += checker(path, stats, totals)

    if problems:
        print(f"SITE STATS DRIFT — {len(problems)} claim(s) disagree with the manifests:",
              file=sys.stderr)
        for p in problems:
            print(f"  ✗ {p}", file=sys.stderr)
        print(f"\nDerived now: {fmt(totals['games'])} games, {fmt(totals['cards'])} cards. "
              f"See `python3 tools/site_stats.py` for the per-lab breakdown.", file=sys.stderr)
        return 1

    print(f"✓ site stats agree with the manifests — {fmt(totals['games'])} games, "
          f"{fmt(totals['cards'])} cards")
    return 0


if __name__ == "__main__":
    sys.exit(main())
