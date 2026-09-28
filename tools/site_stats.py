#!/usr/bin/env python3
"""Derived counts for every lab, and the site totals.

    python3 tools/site_stats.py

The landing page's hero numbers, the vendor hubs' stat chips and llms.txt all
advertise how much there is to play. Every one of them was typed by hand, and
they had drifted apart: the landing page said 154 games where the manifests
add up to 160, and the AWS hub said 793 cards where the lab tracks 751.

Numbers that describe the manifests belong to the manifests. This module is
the single place they are counted, so a chip and a hero total can no longer
disagree about the same lab.

"Cards" means TRACKED, SCORED cards — the ids the build collects, the same
count the outline-coverage gate uses (design D3). It is deliberately not the
older "things you can place" count, which swept in unscored ladder steps and
so produced a second, larger number for the same lab.
"""

from __future__ import annotations

import contextlib
import io
import json
import sys
from pathlib import Path

import build_lab

REPO = Path(__file__).resolve().parent.parent

_CACHE: dict[str, dict] | None = None


def lab_stats() -> dict[str, dict]:
    """{lab_id: {title, output, games, cards}} for every lab in data/labs/.

    Cached: counting means loading and validating every deck in the repo, and
    the callers (a container build per hub, a verifier walking two pages) each
    want the same numbers several times over.
    """
    global _CACHE
    if _CACHE is not None:
        return _CACHE
    template = build_lab.TEMPLATE.read_text(encoding="utf-8")
    adapters = build_lab.registry_keys(template)
    out: dict[str, dict] = {}
    for path in sorted(build_lab.LABS.glob("*.json")):
        manifest = build_lab.load_json(path)
        # Validation narrates itself — the knowledge modules to stdout, the
        # deck gates to stderr. That belongs to the build, which runs the same
        # checks; counting cards must not print the warnings a second time.
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            _, ids, _, errors = build_lab.load_games(manifest, adapters)
        if errors:
            raise SystemExit(f"{path.name}: does not validate — {errors[0]}")
        out[path.stem] = {
            "title": manifest["title"],
            "output": manifest["output"],
            "games": len(manifest["games"]),
            "cards": len(ids),
        }
    _CACHE = out
    return out


def totals(stats: dict[str, dict] | None = None) -> dict[str, int]:
    stats = stats if stats is not None else lab_stats()
    return {"games": sum(s["games"] for s in stats.values()),
            "cards": sum(s["cards"] for s in stats.values())}


def for_output(output: str, stats: dict[str, dict] | None = None) -> dict | None:
    """Stats for the lab that builds a given output file, e.g. 'AI-901.html'."""
    stats = stats if stats is not None else lab_stats()
    return next((s for s in stats.values() if s["output"] == output), None)


def main() -> int:
    stats = lab_stats()
    width = max(len(k) for k in stats)
    for lab_id, s in stats.items():
        print(f"{lab_id:{width}}  {s['games']:3} games  {s['cards']:5} cards   {s['output']}")
    t = totals(stats)
    print(f"{'TOTAL':{width}}  {t['games']:3} games  {t['cards']:5} cards")
    if "--json" in sys.argv:
        print(json.dumps({"labs": stats, "totals": t}, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
