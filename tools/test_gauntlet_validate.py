#!/usr/bin/env python3
"""Build-validation tests for the gauntlet runner in build_lab.py.

Run: python3 -m pytest tools/test_gauntlet_validate.py -q
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import build_lab


def _deck(**over):
    q = {"id": "ns-0001", "domain": "4", "area": "4.1",
         "label": "A router forwards packets between two segments. Which layer?",
         "options": ["Layer 2", "Layer 3", "Layer 4", "Layer 7"],
         "answer": "Layer 3", "why": "Routing is a network-layer function.",
         "ref": "SG ch.11"}
    q.update(over.pop("q", {}))
    d = {"id": "night-shift", "runner": "gauntlet", "title": "Night Shift",
         "blurb": "b", "source": "SG", "asOf": "2026-08",
         "weights": {"1":16,"2":10,"3":13,"4":13,"5":13,"6":12,"7":13,"8":10},
         "questions": [q]}
    d.update(over)
    return d


def test_valid_gauntlet_deck_passes():
    errors = []
    ids = build_lab.validate_deck(_deck(), "decks/cissp/night-shift.json", "gauntlet", errors)
    assert errors == [] and ids == ["ns-0001"]


def test_answer_must_be_an_option():
    errors = []
    build_lab.validate_deck(_deck(q={"answer": "Layer 9"}), "d", "gauntlet", errors)
    assert any("answer" in e for e in errors)


def test_missing_why_domain_or_weights_fails():
    for bad in ({"q": {"why": ""}}, {"q": {"domain": "9"}}, {"weights": {}}):
        errors = []
        build_lab.validate_deck(_deck(**bad), "d", "gauntlet", errors)
        assert errors, f"expected errors for {bad}"
