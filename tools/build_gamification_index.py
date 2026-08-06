#!/usr/bin/env python3
"""Build the gamification landing page.

Writes gamification/index.html linking every lab in data/labs/.

Counts are derived from the manifests and decks rather than typed in, because a
landing page advertising stale numbers is worse than one advertising none. Now
that all three labs are generated, the manifest is the honest source: it is
what actually decides which games a lab offers.
"""

from __future__ import annotations

import html
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
GAMIFICATION = REPO / "gamification"
TEMPLATE = REPO / "tools" / "templates" / "gamification_index.html"
LABS = REPO / "data" / "labs"
DATA = REPO / "data"
OUTPUT = GAMIFICATION / "index.html"


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def load(path: Path):
    return json.loads(read(path))


def facts(lab_id: str) -> dict:
    """Games and placeable cards for a lab, counted from what it actually loads."""
    m = load(LABS / f"{lab_id}.json")
    cards = 0
    for g in m["games"]:
        ref = g.get("deck") or g.get("data")
        d = load(DATA / ref)
        if g.get("deck"):
            if "items" in d:
                cards += len(d["items"])
            elif "pairs" in d:
                cards += len(d["pairs"]) * 2
            elif "ladders" in d:
                cards += sum(len(l["steps"]) for l in d["ladders"])
        else:
            # The AIGP knowledge file: one card is one thing you place, order, answer
            # or write, counted per game so a file feeding several games is
            # not counted several times over.
            a = g.get("adapter")
            if a == "aigpTells":
                cards += len(d["tells"])
            elif a == "aigpPairs":
                cards += len(d["pairs"]) * 2
            elif a == "aigpRoles":
                s = next(x for x in d["roleMatrix"]["sets"] if x["id"] == g["setId"])
                cards += len(s.get("obligations", s.get("items", [])))
            elif a == "aigpTimeline":
                cards += len(d["timeline"]["milestones"])
            elif a == "aigpMap":
                cards += len(d["map"]["jurisdictions"])
            elif a == "aigpCases":
                cards += sum(len(c["steps"]) for c in d["cases"])
            elif a == "aigpLadders":
                cards += sum(len(l["steps"]) for l in d["ladders"])
            elif a == "aigpBriefs":
                cards += len(d["briefs"])
    refs = {g.get("deck") or g.get("data") for g in m["games"]}
    return {"manifest": m, "games": len(m["games"]), "cards": cards, "refs": refs}


def card(*, href, tone, code, title, blurb, stats, status, cta) -> str:
    chips = "".join(
        f'<span class="stat"><b>{html.escape(str(v))}</b> {html.escape(k)}</span>'
        for k, v in stats
    )
    return f"""<a class="app" style="--tone:{tone}" href="{html.escape(href)}">
      <span class="status">{html.escape(status)}</span>
      <p class="code">{html.escape(code)}</p>
      <h2>{html.escape(title)}</h2>
      <p>{html.escape(blurb)}</p>
      <div class="stats">{chips}</div>
      <span class="go">{html.escape(cta)} &rarr;</span>
    </a>"""


def main() -> int:
    labs = {i: facts(i) for i in ("concepts", "aws", "aigp")}
    missing = [f["manifest"]["output"] for f in labs.values()
               if not (GAMIFICATION / f["manifest"]["output"]).is_file()]
    if missing:
        raise SystemExit(f"lab(s) not built yet: {missing}")

    concepts, aws, aigp = labs["concepts"], labs["aws"], labs["aigp"]
    # Shared means genuinely reused: referenced by more than one manifest. The
    # count of decks a single lab happens to load is a different, larger number.
    counts = {}
    for f in labs.values():
        for r in f["refs"]:
            counts[r] = counts.get(r, 0) + 1
    reused = sum(1 for r, n in counts.items() if n > 1)
    aigp_knowledge = load(DATA / "aigp" / "knowledge" / "domain-ii.json")
    services = len(load(DATA / "decks" / "aws" / "services.json")["items"])

    cards = card(
        href=concepts["manifest"]["output"], tone="var(--concepts)", code="Vendor-neutral",
        title="AI & ML Concepts",
        blurb="The foundations, without a cloud provider attached. Terms, learning methods, "
              "metrics, prompting and RAG — plus heavy coverage of AI risk and eight kinds "
              "of model drift.",
        stats=[("games", concepts["games"]), ("cards", concepts["cards"])],
        status="Complete", cta="Open the lab",
    ) + card(
        href=aws["manifest"]["output"], tone="var(--aws)", code="AIF-C01",
        title="AWS AI Practitioner",
        blurb="The AWS service catalogue and the capabilities behind it, alongside the "
              "concept games that map onto an AIF-C01 domain.",
        stats=[("games", aws["games"]), ("cards", aws["cards"]), ("AWS services", services)],
        status="Complete", cta="Open the lab",
    ) + card(
        href=aigp["manifest"]["output"], tone="var(--aigp)", code="IAPP AIGP",
        title="AI Governance Professional",
        blurb="How laws, standards and frameworks apply to AI. Risk tiers, actor roles, the "
              "GDPR overlap, a global obligations timeline, long-form briefs marked by an AI "
              "examiner — and Domain III risk management.",
        stats=[("games", aigp["games"]), ("cards", aigp["cards"]),
               ("jurisdictions", len(aigp_knowledge["map"]["jurisdictions"])),
               ("briefs", len(aigp_knowledge["briefs"]))],
        status="Domains II & III", cta="Open the lab",
    )

    footer = (
        f'<p>AIGP built against Body of Knowledge v{html.escape(aigp_knowledge["bokVersion"])}, '
        f'effective 2 February 2026. Domain II is complete and the risk half of Domain III '
        f'is live; Domains I and IV are shells.</p>'
        f'<p>{reused} decks are shared: authored once, played in more than one '
        f'lab, so drift and risk stay identical wherever you meet them.</p>'
        '<p>World map: \u201cSimplified World Map\u201d by Guilherme de Souza Vieira via Wikimedia '
        'Commons, <a href="https://creativecommons.org/licenses/by-sa/3.0/" target="_blank" '
        'rel="noopener noreferrer">CC BY-SA 3.0</a>, modified.</p>'
    )

    out = read(TEMPLATE)
    for token, value in (("<!--__CARDS__-->", cards), ("<!--__FOOTER__-->", footer)):
        if token not in out:
            raise SystemExit(f"placeholder {token} not found in {TEMPLATE}")
        out = out.replace(token, value)

    OUTPUT.write_text(out, encoding="utf-8")
    print(f"\u2713 {OUTPUT.relative_to(REPO)}  ({OUTPUT.stat().st_size/1024:.0f} KB)")
    for name, f in labs.items():
        print(f"  {name:9}: {f['games']} games, {f['cards']} cards")
    return 0


if __name__ == "__main__":
    sys.exit(main())
