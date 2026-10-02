#!/usr/bin/env python3
"""Tests for the build-blocking content gates in build_lab.py.

Run: python3 -m pytest tools/test_build_gates.py -q

These cover the two gates that turn documented intent into machine enforcement:
  - verbatim_errors(): the per-lab source-set declaration and the guard it arms
  - outline_errors():  the per-cert outline coverage floor and owner rule

Both are build-blocking, so the tests assert on the *presence* of an error, not
on a warning being logged somewhere a human might read it.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import build_lab
import check_verbatim

REPO = Path(__file__).resolve().parent.parent
REAL_SOURCE = "tools/fixtures/verbatim-source.json"


def _lifted_sentence() -> str:
    """A real >= 8-token run out of the declared source, to lift verbatim."""
    for s in check_verbatim.load_sources([str(REPO / REAL_SOURCE)]):
        if len(check_verbatim.tokenize(s)) >= 12:
            return s
    raise AssertionError(f"{REAL_SOURCE} has no string long enough to lift")


# --- verbatim guard ---------------------------------------------------------

def test_missing_sources_key_is_an_error():
    errors = build_lab.verbatim_errors({"id": "x"}, {})
    assert errors and "missing sources" in errors[0]


def test_empty_sources_without_a_note_is_an_error():
    errors = build_lab.verbatim_errors({"id": "x", "sources": []}, {})
    assert errors and "no sourcesNote" in errors[0]


def test_empty_sources_with_a_note_passes():
    assert build_lab.verbatim_errors(
        {"id": "x", "sources": [], "sourcesNote": "nothing vendored yet"}, {}) == []


def test_nonexistent_source_path_is_an_error():
    errors = build_lab.verbatim_errors({"id": "x", "sources": ["data/nope.json"]}, {})
    assert errors and "does not exist" in errors[0]


def test_unmapped_private_source_is_an_error(monkeypatch, tmp_path):
    monkeypatch.setenv("SOURCES_ROOT", str(tmp_path))  # no site-sources.json here
    monkeypatch.delenv("SKIP_VERBATIM", raising=False)
    errors = build_lab.verbatim_errors({"id": "x", "sources": ["private:x/bank"]}, {})
    assert errors and "is private" in errors[0] and "SOURCES_ROOT" in errors[0]


def test_private_source_resolves_through_the_map(monkeypatch, tmp_path):
    (tmp_path / "bank.json").write_text((REPO / REAL_SOURCE).read_text(encoding="utf-8"))
    (tmp_path / "site-sources.json").write_text(
        json.dumps({"sources": {"private:x/bank": "bank.json"}}))
    monkeypatch.setenv("SOURCES_ROOT", str(tmp_path))
    monkeypatch.delenv("SKIP_VERBATIM", raising=False)
    deck = {"id": "d", "items": [{"id": "c1", "why": _lifted_sentence()}]}
    errors = build_lab.verbatim_errors(
        {"id": "x", "sources": ["private:x/bank"]}, {"decks/x/d.json": deck})
    assert errors and "verbatim:" in errors[0]


def test_skip_verbatim_disables_the_guard_but_not_the_declaration(monkeypatch):
    monkeypatch.setenv("SKIP_VERBATIM", "1")
    deck = {"id": "d", "items": [{"id": "c1", "why": _lifted_sentence()}]}
    assert build_lab.verbatim_errors(
        {"id": "x", "sources": ["private:x/bank"]}, {"decks/x/d.json": deck}) == []
    assert build_lab.verbatim_errors({"id": "x"}, {}), "a missing declaration still fails"


def test_lifted_card_text_fails_the_build():
    deck = {"id": "d", "items": [{"id": "c1", "why": _lifted_sentence()}]}
    errors = build_lab.verbatim_errors(
        {"id": "x", "sources": [REAL_SOURCE]}, {"decks/x/d.json": deck})
    assert errors, "a card copied verbatim out of a declared source must fail the build"
    assert "verbatim:" in errors[0] and "decks/x/d.json" in errors[0]


def test_freshly_authored_card_passes():
    deck = {"id": "d", "items": [{
        "id": "c1",
        "why": "A junior admin edits payroll records their role never granted. "
               "That is the access-control failure this card drills.",
    }]}
    assert build_lab.verbatim_errors(
        {"id": "x", "sources": [REAL_SOURCE]}, {"decks/x/d.json": deck}) == []


def test_every_shipped_lab_declares_a_source_set():
    """The declaration is the point: a lab that never declares one can't be
    said to have passed the guard, it just never ran it."""
    for path in sorted((REPO / "data" / "labs").glob("*.json")):
        manifest = json.loads(path.read_text(encoding="utf-8"))
        assert "sources" in manifest, f"{path.name} declares no source set"
        if not manifest["sources"]:
            assert manifest.get("sourcesNote"), f"{path.name} has an unexplained empty source set"


# --- outline coverage gate --------------------------------------------------

OUTLINE = "data/outlines/cissp.json"


def _manifest(games, gaps=None):
    m = {"id": "x", "outline": OUTLINE, "games": games}
    if gaps is not None:
        m["acceptedGaps"] = gaps
    return m


def _covering_manifest(share_per_area=None):
    """A manifest that covers every CISSP area at the floor, via one game."""
    areas = [a["id"] for a in json.loads((REPO / OUTLINE).read_text())["areas"]]
    share = 1.0 / len(areas)
    games = [{"id": "everything", "deck": "d.json",
              "areas": {a: round(share, 6) for a in areas}}]
    drift = round(1.0 - sum(games[0]["areas"].values()), 6)
    games[0]["areas"][areas[0]] = round(games[0]["areas"][areas[0]] + drift, 6)
    ids = {"d.json": [f"c{i}" for i in range(build_lab.CARD_FLOOR * len(areas))]}
    return _manifest(games), ids


def test_missing_outline_key_is_an_error():
    errors = build_lab.outline_errors({"id": "x", "games": []}, {}, quiet=True)
    assert errors and "missing outline" in errors[0]


def test_null_outline_needs_a_note():
    assert build_lab.outline_errors(
        {"id": "x", "outline": None, "games": []}, {}, quiet=True)
    assert build_lab.outline_errors(
        {"id": "x", "outline": None, "outlineNote": "topic lab", "games": []}, {}, quiet=True) == []


def test_shares_must_sum_to_one():
    m = _manifest([{"id": "g", "deck": "d.json", "areas": {"1.1": 1.0, "1.2": 1.0}}])
    errors = build_lab.outline_errors(m, {"d.json": ["a"] * 100}, quiet=True)
    assert any("sum to" in e for e in errors), errors


def test_a_game_claiming_an_unknown_area_fails():
    m = _manifest([{"id": "g", "deck": "d.json", "areas": {"99.9": 1.0}}])
    errors = build_lab.outline_errors(m, {"d.json": ["a"] * 100}, quiet=True)
    assert any("not in" in e for e in errors), errors


def test_a_game_with_no_declared_areas_fails():
    m = _manifest([{"id": "g", "deck": "d.json"}])
    errors = build_lab.outline_errors(m, {"d.json": ["a"] * 100}, quiet=True)
    assert any("declares no areas" in e for e in errors), errors


def test_full_coverage_at_the_floor_passes():
    m, ids = _covering_manifest()
    assert build_lab.outline_errors(m, ids, quiet=True) == []


def test_one_card_short_of_the_floor_fails():
    m, ids = _covering_manifest()
    ref = "d.json"
    # Half the cards removed: every area now sits at ~3, well under the floor.
    ids = {ref: ids[ref][: len(ids[ref]) // 2]}
    errors = build_lab.outline_errors(m, ids, quiet=True)
    assert errors and all("below the floor" in e for e in errors), errors[:3]


def test_an_uncovered_area_fails_unless_accepted():
    m, ids = _covering_manifest()
    dropped = sorted(m["games"][0]["areas"])[0]
    share = m["games"][0]["areas"].pop(dropped)
    other = sorted(m["games"][0]["areas"])[0]
    m["games"][0]["areas"][other] = round(m["games"][0]["areas"][other] + share, 6)

    errors = build_lab.outline_errors(m, ids, quiet=True)
    assert any(f"outline area {dropped}: no owner" in e for e in errors), errors[:3]

    m["acceptedGaps"] = {dropped: "not drilled in this release; queued for wave 2"}
    assert build_lab.outline_errors(m, ids, quiet=True) == []


def test_an_accepted_gap_needs_a_reason():
    m, ids = _covering_manifest()
    m["acceptedGaps"] = {"1.1": ""}
    errors = build_lab.outline_errors(m, ids, quiet=True)
    assert any("no reason" in e for e in errors), errors


def test_two_games_sharing_a_deck_do_not_double_count():
    """Counting per game rather than per deck would let one deck inflate every
    area it touches simply by being listed twice on the home ladder."""
    m, ids = _covering_manifest()
    twin = dict(m["games"][0], id="everything-again")
    m["games"].append(twin)
    ref = "d.json"
    ids = {ref: ids[ref][: len(ids[ref]) // 2]}
    errors = build_lab.outline_errors(m, ids, quiet=True)
    assert errors, "a shared deck must be counted once, so half the cards is still half"


def test_cissp_declares_full_outline_coverage():
    """The reference implementation's own claim, machine-checked."""
    manifest = json.loads((REPO / "data" / "labs" / "cissp.json").read_text())
    _, _, ids_by_ref, deck_errors = build_lab.load_games(
        manifest, build_lab.registry_keys(
            (REPO / "tools" / "templates" / "lab.html").read_text(encoding="utf-8")))
    assert deck_errors == [], deck_errors[:3]
    assert build_lab.outline_errors(manifest, ids_by_ref, quiet=True) == []


# --- gate-ratio audit (the anti-quiz guardrail) -----------------------------

def _campaign(gate_sizes, cap=0.6, note=None):
    cfg = {"turns": 15, "maxGateRatio": cap,
           "tiers": {f"c{i}": {"gateSize": n} for i, n in enumerate(gate_sizes)}}
    if note:
        cfg["maxGateRatioNote"] = note
    return {"config": cfg,
            "territories": [{"mapId": f"t{i}", "coverage": f"c{i}"}
                            for i in range(len(gate_sizes))]}


def test_one_card_per_decision_passes():
    assert build_lab.gate_ratio_errors(_campaign([1]), "c") == []


def test_two_cards_per_decision_exceeds_a_point_six_cap():
    errors = build_lab.gate_ratio_errors(_campaign([2]), "c")
    assert errors and "exceeds the declared maxGateRatio" in errors[0]


def test_a_campaign_must_declare_a_cap():
    camp = _campaign([1])
    del camp["config"]["maxGateRatio"]
    errors = build_lab.gate_ratio_errors(camp, "c")
    assert errors and "missing maxGateRatio" in errors[0]


def test_an_overshoot_may_be_recorded_but_not_hidden(capsys):
    camp = _campaign([2], note="beta ships over; contain loop lands next wave")
    assert build_lab.gate_ratio_errors(camp, "c") == []
    assert "exceeds the declared maxGateRatio" in capsys.readouterr().err


def test_night_shift_ratio_is_the_one_recorded():
    """The shipped campaign is over its own cap; the build says so out loud
    rather than the number sitting unread in the config."""
    deck = json.loads((REPO / "data" / "decks" / "cissp" / "night-shift.json").read_text())
    cfg = deck["campaign"]["config"]
    sizes = [cfg["tiers"][t["coverage"]]["gateSize"] for t in deck["campaign"]["territories"]]
    mean = sum(sizes) / len(sizes)
    assert round(mean / (mean + 1), 2) == 0.67
    assert cfg["maxGateRatio"] == 0.6
    assert cfg.get("maxGateRatioNote"), "an overshoot must be recorded, not silent"


def test_the_recorded_note_never_reaches_the_page():
    deck = json.loads((REPO / "data" / "decks" / "cissp" / "night-shift.json").read_text())
    out = build_lab.shipped_decks({"d": deck})
    assert "maxGateRatioNote" not in out["d"]["campaign"]["config"]
    assert "maxGateRatioNote" in deck["campaign"]["config"], "the source deck must be untouched"


# --- build-only manifest keys ----------------------------------------------

def test_build_only_keys_never_reach_the_page():
    manifest = {"id": "x", "title": "X", "sources": ["a"], "sourcesNote": "b",
                "outline": {"areas": []}, "acceptedGaps": ["c"], "games": []}
    out = build_lab.shipped(manifest)
    assert set(out) == {"id", "title", "games"}


# --- reference fields, public-text allowlist, derivation gate ---------------

def test_citation_fields_are_not_checked():
    lifted = _lifted_sentence()
    deck = {"id": "d", "items": [{"id": "c1", "citation": lifted, "source": {"title": lifted}}]}
    assert check_verbatim.check_data(deck, "d", [lifted]) == []


def test_public_text_runs_are_allowed(monkeypatch, tmp_path):
    public = tmp_path / "public-texts.json"
    law = "The data subject shall have the right not to be subject to a decision based solely on automated processing"
    public.write_text(json.dumps({"texts": [{"text": law, "source": "GDPR Art. 22(1)"}]}))
    monkeypatch.setattr(check_verbatim, "PUBLIC_TEXTS", public)
    index = check_verbatim.source_index([law + " quoted inside a study guide"]) - check_verbatim.public_index()
    deck = {"id": "d", "items": [{"id": "c1", "why": law}]}
    assert check_verbatim.check_data(deck, "d", index) == []


def _bank(tmp_path, question, choices):
    f = tmp_path / "bank.json"
    f.write_text(json.dumps([{"question": question, "choices": choices}]))
    return check_verbatim.derivation_index([str(f)])


def test_distinctive_distractor_set_is_flagged(tmp_path):
    choices = ["Apply one uniform control set everywhere", "Centralise every control at head office",
               "Differentiate controls by site risk profile", "Mandate multifactor login at all sites"]
    dindex = _bank(tmp_path, "Our branch offices differ from headquarters in risk; how should controls be designed?", choices)
    card = {"id": "c", "q": "Night shift: a new depot opens. Your move?", "options": choices, "answer": choices[2]}
    assert check_verbatim.check_derivation({"cards": [card]}, "d", dindex)


def test_standard_term_options_with_a_new_stem_pass(tmp_path):
    choices = ["Bell-LaPadula", "Biba", "Clark-Wilson", "Brewer-Nash"]
    dindex = _bank(tmp_path, "Which model prevents reading up and writing down in a military classification system?", choices)
    card = {"id": "c", "q": "A consultancy serves two rival banks and must wall off each team's files. Your move?",
            "options": choices, "answer": "Brewer-Nash"}
    assert check_verbatim.check_derivation({"cards": [card]}, "d", dindex) == []


def test_paraphrased_stem_is_flagged(tmp_path):
    q = ("A hospital lets the lead surgeon read complete patient records before operating, while the ward nurse "
         "with general clearance is blocked from the same detailed diagnosis records.")
    dindex = _bank(tmp_path, q, ["a", "b", "c", "d"])
    card = {"id": "c", "q": "At the hospital the lead surgeon may read complete patient records before operating, but the ward "
                            "nurse with general clearance is blocked from the detailed diagnosis records. Why?",
            "options": ["w", "x", "y", "z"], "answer": "w"}
    assert check_verbatim.check_derivation({"cards": [card]}, "d", dindex)


# ---- solo labs (a game with a page of its own) ------------------------------

def _build_risk_with(monkeypatch, tmp_path, **override):
    manifest = json.loads((build_lab.LABS / "risk.json").read_text(encoding="utf-8"))
    manifest.update(override)
    labs = tmp_path / "labs"
    labs.mkdir()
    (labs / "risk.json").write_text(json.dumps(manifest), encoding="utf-8")
    monkeypatch.setattr(build_lab, "LABS", labs)
    monkeypatch.setattr(build_lab, "OUT", tmp_path / "out")
    monkeypatch.setenv("SKIP_VERBATIM", "1")
    template = build_lab.TEMPLATE.read_text(encoding="utf-8")
    return build_lab.build("risk", template, build_lab.registry_keys(template), quiet=True)


def test_a_solo_game_the_lab_does_not_have_fails(monkeypatch, tmp_path, capsys):
    assert _build_risk_with(monkeypatch, tmp_path, solo="no-such-game") == 1
    assert "solo game 'no-such-game'" in capsys.readouterr().err


def test_the_regulatory_risk_page_builds_as_a_solo_lab(monkeypatch, tmp_path):
    assert _build_risk_with(monkeypatch, tmp_path) == 0
    page = (tmp_path / "out" / "Regulatory Risk.html").read_text(encoding="utf-8")
    assert '"solo":"risk"' in page.replace(" ", "")
