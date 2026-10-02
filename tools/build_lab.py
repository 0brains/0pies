#!/usr/bin/env python3
"""Build a games lab from a manifest.

    python3 tools/build_lab.py concepts
    python3 tools/build_lab.py --all

A manifest (data/labs/<id>.json) names a lab and lists its games. Each game
resolves either a runner + deck (generic content) or an adapter + data (an
existing typed knowledge file, e.g. the AIGP one). Decks are inlined into
the output rather than fetched, because opening the page from file:// blocks
fetch() of a local JSON file. The JSON stays the source of truth; the HTML is a
generated artifact.

Validation is blocking. A deck that would quietly hollow out a game — a card
with no resolvable provenance, a zone no card answers, a minimal pair whose two
variants share an answer — fails the build rather than shipping.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from html import escape
from pathlib import Path

import aigp_knowledge
import check_verbatim

REPO = Path(__file__).resolve().parent.parent
LABS = REPO / "data" / "labs"
DECKS = REPO / "data"
TEMPLATE = REPO / "tools" / "templates" / "lab.html"
MAP_SVG = REPO / "tools" / "templates" / "world-map-paths.svg"
MAP_TERRITORIES = REPO / "tools" / "templates" / "world-map-territories.json"
AI_LOGOS = REPO / "tools" / "templates" / "ai-logos.json"
# The site and its sources live together in this repo: a plain build writes
# straight into gamification/, where deploys happen; LAB_OUT overrides for
# anything unusual (scratch builds, the golden master).
import os
OUT = Path(os.environ.get("LAB_OUT") or REPO / "gamification")
CONTAINERS = REPO / "data" / "containers"
CONTAINER_TEMPLATE = REPO / "tools" / "templates" / "container.html"

# Runners that take a generic deck, and the collection each one expects to find.
GENERIC = {"board": "items", "pairs": "pairs", "ladders": "ladders", "gauntlet": "questions",
           "opsCampaign": "campaign", "siegeBoard": "siege", "timeline": "timeline"}

# The home-screen rung ladder, bottom to top (lab.html's RUNGS). A rung outside
# this vocabulary would not fail at runtime — renderHome simply never lists the
# game — so an unknown value is a build error here instead of a silent hole.
RUNGS = ("Learn", "Contrast", "Apply", "Drill", "Sim", "Brief")

# siegeBoard scenes live under tools/templates/ (engine-owned, like the world
# map); each board carries a hard byte budget so single-file file:// pages
# don't bloat (design §7 R6: 60 KB optimized per board).
SCENE_BUDGET = 60 * 1024

# Typed knowledge files are not generic decks: they carry their own schema, their own
# validation, and — in the AIGP case — a derivation step. A knowledge file reached
# through an adapter with no entry here would ship unvalidated and, worse,
# unprepared: the AIGP map renders from x/y that only exist because this runs,
# and missing coordinates throw no error at all. So an unknown knowledge file is a
# build failure rather than a pass-through.
KNOWLEDGE = {
    "aigp/knowledge/domain-i.json": (aigp_knowledge, {"I.B", "I.C"}),
    "aigp/knowledge/domain-ii.json": (aigp_knowledge, {"II.A", "II.B", "II.C", "II.D"}),
    "aigp/knowledge/domain-iii.json": (aigp_knowledge, {"III.A", "III.C"}),
    "aigp/knowledge/domain-iv.json": (aigp_knowledge, {"IV.B", "IV.C"}),
    # CISSP beta.1 reskins of the typed AIGP adapters (design §6, wave 1).
    # Same schemas, same validation and preparation module — Borderlines'
    # jurisdictions in particular need prepare()'s lat/lon → x/y projection,
    # exactly like the AIGP map data. Indicators are empty: outline-area
    # coverage for the CISSP lab is owned by the campaign pool audit, not by
    # any single reskin file.
    "decks/cissp/borderlines.json": (aigp_knowledge, set()),
    "decks/cissp/boilerplate.json": (aigp_knowledge, set()),
    "decks/cissp/chain-of-accountability.json": (aigp_knowledge, set()),
    "decks/cissp/intake-desk.json": (aigp_knowledge, set()),
}


_MARKUP = re.compile(r"<[a-zA-Z/!]")


def _reject_markup(obj, where: str, path: str = "$") -> None:
    """No string anywhere in the data may contain markup.

    The engine escapes text at most render sites, but not every one, and card
    content is trusted at build time — so with the repo public, a merged deck
    PR is the injection path. No legitimate card has ever needed a '<': ban it
    outright at load, which is build-blocking, rather than audit 190-odd
    interpolation sites in the engine and re-audit them after every change.
    """
    if isinstance(obj, str):
        if _MARKUP.search(obj):
            raise SystemExit(
                f"{where}: markup-like '<' in string at {path}: {obj[:80]!r}\n"
                "Card content must be plain text — the engine, not the data, owns the HTML."
            )
    elif isinstance(obj, dict):
        for k, v in obj.items():
            _reject_markup(v, where, f"{path}.{k}")
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            _reject_markup(v, where, f"{path}[{i}]")


def load_json(path: Path):
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise SystemExit(f"missing file: {path.relative_to(REPO)}")
    except json.JSONDecodeError as e:
        raise SystemExit(f"{path.relative_to(REPO)}: invalid JSON — {e}")
    # Only card data is held to the no-markup rule: tools/templates/ is
    # engine-owned (ai-logos.json really is SVG), but everything under data/
    # is the contributor surface.
    if path.is_relative_to(DECKS):
        _reject_markup(data, str(path.relative_to(REPO)))
    return data


I18N_DIR = REPO / "data" / "i18n"
_PLACEHOLDER = re.compile(r"\{(\w+)\}")

# Both the lab pages' and the containers' i18n bundles land inside a
# <script type="application/json">, so the only sequence that could break
# out is a literal </script>.
def payload(obj):
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")


# Manifest keys the build consumes and the page never reads. They are stripped
# before the manifest is inlined: shipping them would put the source-corpus
# paths and the whole outline taxonomy into every lab page as dead weight, and
# would mean any harness-only manifest addition rewrote the shipped bytes of
# labs whose content did not change.
BUILD_ONLY_KEYS = ("sources", "sourcesNote", "outline", "outlineNote", "acceptedGaps")
# Same, per game: the declared outline-area split is coverage accounting, and
# the page has no use for it.
BUILD_ONLY_GAME_KEYS = ("areas",)


# The same rule inside a deck: a justification written for a build gate is
# build-time metadata, and inlining it would ship a paragraph of harness
# argument to every player. Listed as explicit paths rather than matched by
# name, so nothing is stripped from a deck by accident.
DECK_BUILD_ONLY_PATHS = (("campaign", "config", "maxGateRatioNote"),)


def shipped_decks(decks: dict[str, dict]) -> dict[str, dict]:
    out = dict(decks)
    for ref, deck in decks.items():
        for path in DECK_BUILD_ONLY_PATHS:
            node = deck
            for key in path[:-1]:
                node = node.get(key) if isinstance(node, dict) else None
                if node is None:
                    break
            if isinstance(node, dict) and path[-1] in node:
                copy = json.loads(json.dumps(out[ref]))
                target = copy
                for key in path[:-1]:
                    target = target[key]
                del target[path[-1]]
                out[ref] = copy
    return out


def shipped(manifest: dict) -> dict:
    out = {k: v for k, v in manifest.items() if k not in BUILD_ONLY_KEYS}
    if "games" in out:
        out["games"] = [{k: v for k, v in g.items() if k not in BUILD_ONLY_GAME_KEYS}
                        for g in out["games"]]
    return out

def validate_index(idx: dict[str, dict], full_coverage: set[str]) -> list[str]:
    """Check the landing page's idx.* dictionaries for internal consistency.

    index/en.json is the source of truth. Any other code may not carry a key
    absent from en (that would be dead weight nothing ever falls back from).
    Codes in `full_coverage` (the languages.json-listed locales — es, ar
    today) must additionally carry *every* en key: they are real shipped
    languages, not partial-coverage jokes. Codes outside `full_coverage`
    (egy, kli) are allowed to cover only a subset — the runtime falls back
    to en for whatever they omit.
    """
    errors: list[str] = []
    if "en" not in idx:
        errors.append("index/en.json: missing (source of truth for the landing page dictionary)")
        return errors
    en_keys = set(idx["en"])
    for code in sorted(idx):
        if code == "en":
            continue
        d = idx[code]
        unknown = sorted(set(d) - en_keys)
        if unknown:
            errors.append(f"index/{code}.json: unknown keys not in index/en.json {unknown[:8]}"
                          + (f" (+{len(unknown)-8} more)" if len(unknown) > 8 else ""))
        if code in full_coverage:
            missing = sorted(en_keys - set(d))
            if missing:
                errors.append(f"index/{code}.json: missing keys {missing[:8]}"
                              + (f" (+{len(missing)-8} more)" if len(missing) > 8 else ""))
    return errors


def diff_index_bundle(idx: dict[str, dict], bundle_ui: dict) -> list[str]:
    """Compare data/i18n/index/*.json (the source of truth) against the
    'ui' half of the inline bundle hand-embedded in the 0pies clone's
    gamification/index.html. index.html has no build step of its own, so
    nothing else catches the two drifting apart — this is that check.
    """
    errors: list[str] = []
    for code in sorted(idx):
        d = idx[code]
        b = bundle_ui.get(code)
        if b is None:
            errors.append(f"index.html bundle: missing language '{code}' "
                          f"present in data/i18n/index/{code}.json")
            continue
        if b != d:
            key_diff = sorted(set(d) ^ set(b))
            val_diff = sorted(k for k in set(d) & set(b) if d[k] != b[k])
            parts = []
            if key_diff:
                parts.append(f"key mismatch {key_diff[:5]}")
            if val_diff:
                parts.append(f"value mismatch {val_diff[:5]}")
            errors.append(f"index.html bundle: '{code}' out of sync with "
                          f"data/i18n/index/{code}.json — " + "; ".join(parts))
    extra = sorted(set(bundle_ui) - set(idx))
    if extra:
        errors.append(f"index.html bundle: language(s) present but not in "
                      f"data/i18n/index/*.json: {extra}")
    return errors


_I18N_SCRIPT = re.compile(r'<script id="i18n" type="application/json">(.*?)</script>', re.S)


def load_index_bundle(path: Path):
    """Read the inline i18n bundle out of the hand-edited index.html and
    return its 'ui' half, or None if the file isn't there (the sibling
    0pies clone is a separate repo — CI without it must still build)."""
    if not path.exists():
        return None
    html = path.read_text(encoding="utf-8")
    m = _I18N_SCRIPT.search(html)
    if not m:
        raise SystemExit(f'{path}: no <script id="i18n" type="application/json"> bundle found')
    try:
        bundle = json.loads(m.group(1))
    except json.JSONDecodeError as e:
        raise SystemExit(f"{path}: inline i18n bundle is not valid JSON — {e}")
    return bundle.get("ui", {})


def load_i18n():
    """Load languages.json + every listed UI locale + labs translations +
    the landing page's idx.* dictionaries.

    Strictness rule: a language listed in languages.json is a shipped
    language. Its ui/<code>.json must exist and carry exactly en.json's key
    set, with identical {placeholder} sets per key. labs/<code>.json (absent
    for en — the manifests are the English source) must cover exactly every
    <labid>.<gameid>.title/.blurb. data/i18n/index/*.json (en plus whatever
    other codes exist — es/ar today, egy/kli as partial-coverage jokes) is
    validated the same way _reject_markup and key-parity apply to everything
    else under data/. Returns (languages, ui, labs_tr, idx, errors).
    """
    errors: list[str] = []
    langs = load_json(I18N_DIR / "languages.json")["langs"]
    codes = [l["code"] for l in langs]
    if codes[0] != "en":
        errors.append("languages.json: 'en' must be first")
    if len(set(codes)) != len(codes):
        errors.append("languages.json: duplicate language codes")
    ui: dict[str, dict] = {}
    for code in codes:
        ui[code] = load_json(I18N_DIR / "ui" / f"{code}.json")
    en_keys = set(ui["en"])
    for code in codes[1:]:
        missing = en_keys - set(ui[code])
        extra = set(ui[code]) - en_keys
        if missing:
            errors.append(f"ui/{code}.json: missing keys {sorted(missing)[:8]}"
                          + (f" (+{len(missing)-8} more)" if len(missing) > 8 else ""))
        if extra:
            errors.append(f"ui/{code}.json: unknown keys {sorted(extra)[:8]}")
        for k in en_keys & set(ui[code]):
            if set(_PLACEHOLDER.findall(ui["en"][k])) != set(_PLACEHOLDER.findall(ui[code][k])):
                errors.append(f"ui/{code}.json: '{k}' placeholder mismatch vs en")
    expected = set()
    for path in sorted(LABS.glob("*.json")):
        m = json.loads(path.read_text(encoding="utf-8"))
        # An untranslated lab (manifest "untranslated": true) is an English-only
        # release end to end: its card overlays are skipped in build(), and its
        # game titles/blurbs must likewise not be *required* of labs/<code>.json
        # — otherwise adding one game to an English-only lab blocks the build on
        # every shipped locale. Translations that DO exist for such a lab are
        # still bundled and used (tGame falls back per key), they just stop
        # being a gate.
        if m.get("untranslated"):
            continue
        for g in m.get("games", []):
            expected.add(f"{m['id']}.{g['id']}.title")
            expected.add(f"{m['id']}.{g['id']}.blurb")
    labs_tr: dict[str, dict] = {}
    for code in codes[1:]:
        p = I18N_DIR / "labs" / f"{code}.json"
        if not p.exists():
            errors.append(f"labs/{code}.json: missing (must cover every game title/blurb)")
            continue
        labs_tr[code] = load_json(p)
        missing = expected - set(labs_tr[code])
        if missing:
            errors.append(f"labs/{code}.json: missing {sorted(missing)[:8]}"
                          + (f" (+{len(missing)-8} more)" if len(missing) > 8 else ""))

    idx: dict[str, dict] = {}
    for p in sorted((I18N_DIR / "index").glob("*.json")):
        idx[p.stem] = load_json(p)
    # es/ar are real shipped languages (listed in languages.json); egy/kli
    # are landing-page-only jokes with no entry there, so they only get the
    # "no keys absent from en" half of validate_index, not full coverage.
    errors += validate_index(idx, full_coverage=set(codes[1:]))

    return langs, ui, labs_tr, idx, errors

def i18n_payload(manifest, langs, ui, labs_tr):
    """The bundle stamped into one lab page: all UI locales, this lab's
    game-title translations only."""
    prefix = manifest["id"] + "."
    return {
        "meta": {l["code"]: {"name": l["name"], "dir": l["dir"], "cards": l["cards"],
                              "flag": l.get("flag", "")}
                 for l in langs},
        "ui": ui,
        "labs": {code: {k: v for k, v in tr.items() if k.startswith(prefix)}
                 for code, tr in labs_tr.items()},
    }


# Fields a card may localize vs the ones the games score on. A key in neither
# set is ignored (ids, coordinates, icons...). This is THE policy line — the
# spec's "answers stay English" lives here.
TRANSLATABLE = {"label", "sub", "why", "text", "detail", "prompt", "snippet",
                "tell", "note", "hint", "def", "brief", "scenario", "milestone",
                "definition", "zdef"}


def extract_translatables(data) -> dict:
    """Walk a deck/corpus; return {ancestor_id: {dotted.path: english_text}}.

    Ancestor = nearest enclosing object with an 'id' (cards, pairs, ladders,
    cases, briefs, milestones); an object with 'key'+'def' but no id anchors
    as "zone:<key>". Strings under TRANSLATABLE keys within an ancestor are
    recorded at their dotted path relative to the ancestor.
    """
    out: dict[str, dict[str, str]] = {}
    def walk(node, anchor, path):
        if isinstance(node, list):
            for i, v in enumerate(node):
                walk(v, anchor, f"{path}[{i}]" if path else f"[{i}]")
            return
        if not isinstance(node, dict):
            return
        if node.get("id") is not None:
            anchor, path = str(node["id"]), ""
        elif anchor is None and node.get("key") is not None and node.get("def") is not None:
            anchor, path = f"zone:{node['key']}", ""
        for k, v in node.items():
            sub = f"{path}.{k}" if path else k
            if isinstance(v, str) and k in TRANSLATABLE and anchor is not None:
                out.setdefault(anchor, {})[sub] = v
            else:
                walk(v, anchor, sub)
    walk(data, None, "")
    return out


def untranslated_paths(fields: dict, got: dict, snapshot: dict) -> set[str]:
    """Paths an overlay is missing that the build must reject.

    fields: {path: current English}; got: the overlay's {path: text} for the
    same id; snapshot: {path: English the overlay was translated from}. A path
    whose English changed since the snapshot (or is new) is pending
    re-translation, so its absence is allowed and the page falls back to
    English; a path whose English is unchanged must be translated.
    """
    return {p for p in set(fields) - set(got) if snapshot.get(p) == fields[p]}


def registry_keys(template: str) -> set[str]:
    """The adapter names the engine actually implements.

    Parsed out of lab.html so a manifest naming a runner the engine does not
    have fails the build instead of shipping a lab with a missing game.
    """
    m = re.search(r"const ADAPTERS = \{(.*?)\n\};", template, re.S)
    if not m:
        raise SystemExit("could not find the ADAPTERS registry in lab.html")
    return set(re.findall(r"^\s*(\w+):", m.group(1), re.M))


def gate_ratio_errors(camp: dict, wc: str) -> list[str]:
    """Audit a campaign's question density against its declared maxGateRatio.

    The anti-quiz guardrail from the CISSP beta design (R4): campaign gates are
    still MCQ cards, so if gate density is high and the containment loop
    shallow, a strategy campaign is the retired quiz with a map behind it. The
    config has carried `maxGateRatio` since beta.1 and nothing read it — a
    number in a file is not a guardrail.

    The ratio measured here is questions against board beats:

        cards = mean gate cards drawn per expansion, across the territories a
                run can actually reach (tier gateSize)  x  turns
        beats = turns — one board decision each: which territory, which action,
                what it costs
        ratio = cards / (cards + beats)

    So 1 card per turn reads as 0.50 (answer, decide, answer, decide) and 3
    cards per turn as 0.75. It deliberately measures the expansion path, which
    is the one a player takes every turn; the worst case is reported alongside
    but not gated on, since no run is all-c3.

    A deck may ship above its cap only by declaring `maxGateRatioNote` — the
    same treatment as an accepted coverage gap. Recording an overshoot is a
    decision; passing silently is not.
    """
    cfg = camp.get("config") or {}
    cap = cfg.get("maxGateRatio")
    if cap is None:
        return [f"{wc}: config missing maxGateRatio — a campaign must declare the share of "
                f"itself it is willing to spend on questions (design R4, the anti-quiz "
                f"guardrail)"]

    tiers = cfg.get("tiers") or {}
    terrs = camp.get("territories") or []
    sizes = [((tiers.get(t.get("coverage")) or {}).get("gateSize") or 1) for t in terrs]
    if not sizes:
        return []
    mean_size = sum(sizes) / len(sizes)
    ratio = mean_size / (mean_size + 1)
    worst = max(sizes) / (max(sizes) + 1)
    if ratio <= cap + 1e-9:
        return []

    detail = (f"{wc}: gate ratio {ratio:.2f} exceeds the declared maxGateRatio of {cap:.2f} "
              f"({mean_size:.1f} question cards per board decision; worst case {worst:.2f}). "
              f"Lowering it means fewer cards per gate or a deeper containment loop — not a "
              f"larger cap")
    note = cfg.get("maxGateRatioNote")
    if note:
        print(f"  ⚠ {detail}\n    recorded: {note}", file=sys.stderr)
        return []
    return [detail]


def validate_deck(deck: dict, path: str, runner: str, errors: list[str]) -> list[str]:
    """Check one generic deck. Returns the ids it contributes to the lab."""
    where = path
    ids: list[str] = []
    coll = GENERIC[runner]
    if coll not in deck:
        errors.append(f"{where}: runner '{runner}' needs a '{coll}' collection")
        return ids

    def provenance(obj, label):
        if not (obj.get("citation") or deck.get("source")):
            errors.append(f"{label}: no citation and the deck declares no source")
        if not (obj.get("asOf") or deck.get("asOf")):
            errors.append(f"{label}: no asOf and the deck declares no asOf")

    if runner == "board":
        items = deck["items"]
        if not items:
            errors.append(f"{where}: no items")
        answers = set()
        for it in items:
            label = f"{where}#{it.get('id','?')}"
            for field in ("id", "label", "answer", "why"):
                if not it.get(field):
                    errors.append(f"{label}: missing {field}")
            provenance(it, label)
            answers.add(it.get("answer"))
            ids.append(it.get("id"))
        if deck.get("zones"):
            zones = [z["key"] for z in deck["zones"]]
            if len(zones) < 3:
                errors.append(f"{where}: a fixed-taxonomy board needs at least 3 zones")
            for a in answers:
                if a not in zones:
                    errors.append(f"{where}: answer '{a}' is not one of the zones")
            for z in zones:
                n = sum(1 for it in items if it.get("answer") == z)
                if n == 0:
                    errors.append(f"{where}: zone '{z}' is a dead drop target — no card answers it")
                elif n < 2:
                    errors.append(f"{where}: zone '{z}' has only {n} card; stratified dealing "
                                  f"needs at least 2")
        elif deck.get("zoneMode") == "options":
            for it in items:
                opts = it.get("options") or []
                if len(opts) < 3:
                    errors.append(f"{where}#{it.get('id','?')}: zoneMode 'options' needs at "
                                  f"least 3 options")
                elif it.get("answer") not in opts:
                    errors.append(f"{where}#{it.get('id','?')}: answer is not among its options")
        else:
            if len(answers) < 3:
                errors.append(f"{where}: only {len(answers)} distinct answers; a matching board "
                              f"needs at least 3")

    elif runner == "pairs":
        for p in deck["pairs"]:
            label = f"{where}#{p.get('id','?')}"
            if not p.get("dimension"):
                errors.append(f"{label}: missing dimension — a pair must name the flipped variable")
            provenance(p, label)
            buckets = p.get("buckets") or []
            if len(buckets) < 2:
                errors.append(f"{label}: fewer than 2 buckets")
            a, b = p.get("a", {}), p.get("b", {})
            if a.get("answer") == b.get("answer"):
                errors.append(f"{label}: degenerate pair — both variants answer "
                              f"'{a.get('answer')}', so nothing is being contrasted")
            for side in ("a", "b"):
                v = p.get(side, {})
                if v.get("answer") not in buckets:
                    errors.append(f"{label}.{side}: answer not among buckets")
                for field in ("text", "why"):
                    if not v.get(field):
                        errors.append(f"{label}.{side}: missing {field}")
            ids.append(p.get("id"))

    elif runner == "ladders":
        for lad in deck["ladders"]:
            label = f"{where}#{lad.get('id','?')}"
            provenance(lad, label)
            steps = lad.get("steps") or []
            if len(steps) < 3:
                errors.append(f"{label}: fewer than 3 steps")
            for s in steps:
                if not s.get("label") or not s.get("detail"):
                    errors.append(f"{label}: step needs both label and detail")
            if not lad.get("prompt"):
                errors.append(f"{label}: missing prompt")

    elif runner == "gauntlet":
        w = deck.get("weights") or {}
        if sorted(w) != [str(i) for i in range(1, 9)]:
            errors.append(f"{where}: gauntlet deck needs a weights map for domains 1-8")
        for q in deck["questions"]:
            qid = q.get("id")
            label = f"{where} q {qid or '<no id>'}"
            if not qid:
                errors.append(f"{label}: missing id"); continue
            ids.append(qid)
            if q.get("domain") not in {str(i) for i in range(1, 9)}:
                errors.append(f"{label}: domain must be '1'..'8'")
            for field in ("area", "label", "why", "ref"):
                if not q.get(field):
                    errors.append(f"{label}: missing {field}")
            opts = q.get("options") or []
            if len(opts) != 4 or len(set(opts)) != 4:
                errors.append(f"{label}: needs exactly 4 distinct options")
            if q.get("answer") not in opts:
                errors.append(f"{label}: answer is not one of the options")

    elif runner == "timeline":
        # Generic timeline deck (the aigpTimeline board, area-parameterized —
        # design beta.1 / Crypto Graveyard). Buckets are the drop zones,
        # milestones the cards. Field resolution mirrors the engine exactly:
        # label falls back to "instrument — milestone", why to "date. note",
        # area/citation/asOf resolve milestone-first then timeline-level
        # (citation additionally falls back to the timeline title).
        tl = deck["timeline"]
        wt = f"{where} timeline"
        if not tl.get("prompt"):
            errors.append(f"{wt}: missing prompt")
        buckets = tl.get("buckets") or []
        if len(buckets) < 3:
            errors.append(f"{wt}: needs at least 3 buckets (drop zones)")
        ms = tl.get("milestones") or []
        if not ms:
            errors.append(f"{wt}: no milestones")
        for m in ms:
            mid = m.get("id")
            label = f"{wt}#{mid or '?'}"
            if not mid:
                errors.append(f"{label}: missing id")
                continue
            ids.append(mid)
            if m.get("bucket") not in buckets:
                errors.append(f"{label}: bucket '{m.get('bucket')}' is not one of the buckets")
            if not (m.get("label") or (m.get("instrument") and m.get("milestone"))):
                errors.append(f"{label}: needs label (or instrument + milestone)")
            if not (m.get("why") or (m.get("date") and m.get("note"))):
                errors.append(f"{label}: needs why (or date + note)")
            if not (m.get("area") or tl.get("area")):
                errors.append(f"{label}: no area and the timeline declares no area")
            if not (m.get("citation") or tl.get("citation") or tl.get("title")):
                errors.append(f"{label}: no citation and the timeline declares no "
                              f"citation/title")
            if not (m.get("asOf") or tl.get("asOf")):
                errors.append(f"{label}: no asOf and the timeline declares no asOf")
        for b in buckets:
            n = sum(1 for m in ms if m.get("bucket") == b)
            if n == 0:
                errors.append(f"{wt}: bucket '{b}' is a dead drop target — no milestone "
                              f"answers it")
            elif n < 2:
                errors.append(f"{wt}: bucket '{b}' has only {n} milestone; stratified "
                              f"dealing needs at least 2")

    elif runner == "opsCampaign":
        # Generic campaign deck (the rr schema, content-agnostic — spec §3.1).
        # The AIGP campaign does not pass through here: it lives in a typed
        # knowledge file validated by aigp_knowledge; this branch guards decks
        # like SOC Shift Command's that reach the runner as plain deck JSON.
        camp = deck["campaign"]
        wc = f"{where} campaign"
        cfg = camp.get("config") or {}
        for field in ("turns", "startCapital", "capitalCap", "gateFailCost",
                      "escalateEveryTurns", "l3Cost", "tiers", "grades"):
            if field not in cfg:
                errors.append(f"{wc}: config missing {field}")
        if not camp.get("prompt"):
            errors.append(f"{wc}: missing prompt")
        tiers = cfg.get("tiers") or {}
        roles = camp.get("roles") or []
        if not roles:
            errors.append(f"{wc}: needs at least one role")
        role_ids = set()
        for r in roles:
            if not (r.get("id") and r.get("name") and r.get("definition")):
                errors.append(f"{wc}: role '{r.get('id', '?')}' needs id, name, definition")
            role_ids.add(r.get("id"))
        for h in camp.get("hats") or []:
            if not (h.get("id") and h.get("name") and h.get("blurb")):
                errors.append(f"{wc}: hat '{h.get('id', '?')}' needs id, name, blurb")
        need = cfg.get("opsRequired", 2)
        ops = camp.get("operations") or []
        if len(ops) <= need:
            errors.append(f"{wc}: only {len(ops)} operations for a {need}-pick loadout — no choice")
        for o in ops:
            if not (o.get("id") and o.get("name")):
                errors.append(f"{wc}: operation '{o.get('id', '?')}' needs id and name")
        has_map = bool(deck.get("map"))
        terr_ids = set()
        for tr in camp.get("territories") or []:
            tid = tr.get("mapId")
            if not tid:
                errors.append(f"{wc}: territory with no mapId")
                continue
            terr_ids.add(tid)
            if not has_map:
                # No map to join against: the territory entry itself must carry
                # the display + tier fields the runner reads off a jurisdiction.
                for field in ("name", "short", "coverage"):
                    if not tr.get(field):
                        errors.append(f"{wc} territory {tid}: missing {field} "
                                      f"(map-less campaigns carry display fields inline)")
                if tr.get("coverage") and tr["coverage"] not in tiers:
                    errors.append(f"{wc} territory {tid}: coverage '{tr['coverage']}' "
                                  f"has no config.tiers entry")
        if not terr_ids:
            errors.append(f"{wc}: no territories")
        card_ids = set()
        gate_terrs = set()
        defend_ok = set()
        for c in camp.get("cards") or []:
            cid = c.get("id")
            label = f"{wc} card {cid or '?'}"
            if not cid:
                errors.append(f"{label}: missing id")
                continue
            ids.append(cid)
            card_ids.add(cid)
            if c.get("kind") not in ("gate", "defend", "consolidate"):
                errors.append(f"{label}: kind must be gate/defend/consolidate")
            terr = c.get("territory")
            if terr != "any" and terr not in terr_ids:
                errors.append(f"{label}: territory '{terr}' is not declared")
            if c.get("kind") == "gate":
                gate_terrs.add(terr)
                croles = c.get("roles") or []
                if not croles:
                    errors.append(f"{label}: gate card needs a roles list ('*' for all)")
                bad = [r for r in croles if r != "*" and r not in role_ids]
                if bad:
                    errors.append(f"{label}: unknown roles {bad}")
            if c.get("kind") == "defend":
                defend_ok.add(terr)
            for field in ("q", "why", "area"):
                if not c.get(field):
                    errors.append(f"{label}: missing {field}")
            provenance(c, label)
            opts = c.get("options") or []
            if len(opts) < 2 or len(set(opts)) != len(opts):
                errors.append(f"{label}: needs at least 2 distinct options")
            if c.get("answer") not in opts:
                errors.append(f"{label}: answer is not one of the options")
        for tid in sorted(terr_ids - gate_terrs):
            errors.append(f"{wc}: territory '{tid}' has no gate cards — it can never be taken")

        errors += gate_ratio_errors(camp, wc)
        if "any" not in defend_ok:
            errors.append(f"{wc}: no territory-'any' defend cards — escalations and "
                          f"role-shift notices would have an empty containment pool")
        for e in camp.get("events") or []:
            label = f"{wc} event {e.get('id', '?')}"
            if not e.get("id"):
                errors.append(f"{label}: missing id")
            if not (e.get("title") and e.get("text")):
                errors.append(f"{label}: needs title and text")
            provenance(e, label)
            eff = e.get("effect") or {}
            if eff.get("type") not in ("audit", "check", "roleShift", "info"):
                errors.append(f"{label}: effect.type must be audit/check/roleShift/info")
            if eff.get("type") == "check":
                refs = ([eff["cardId"]] if eff.get("cardId") else []) + list(eff.get("cardPool") or [])
                if not refs:
                    errors.append(f"{label}: check event needs cardId or cardPool")
                for rc in refs:
                    if rc not in card_ids:
                        errors.append(f"{label}: references unknown card '{rc}'")
            if eff.get("type") == "roleShift" and eff.get("toRole") not in role_ids:
                errors.append(f"{label}: roleShift toRole '{eff.get('toRole')}' is not a role")

    elif runner == "siegeBoard":
        # Build-then-defend deck (spec §3.2), point-target grammar only in this
        # wave: slots/line/edge grammars land later and are rejected here so a
        # deck can't quietly author against an interaction that doesn't exist.
        sg = deck["siege"]
        ws = f"{where} siege"
        for field in ("id", "title", "prompt"):
            if not sg.get(field):
                errors.append(f"{ws}: missing {field}")
        scene = sg.get("scene") or {}
        if not scene.get("svgRef"):
            errors.append(f"{ws}: scene.svgRef is required (board SVG under tools/templates/)")
        if not scene.get("viewBox"):
            errors.append(f"{ws}: scene.viewBox is required")
        t_ids: set[str] = set()
        for tg in scene.get("targets") or []:
            tid = tg.get("id")
            lbl = f"{ws} target {tid or '?'}"
            if not tid:
                errors.append(f"{lbl}: missing id")
                continue
            if tid in t_ids:
                errors.append(f"{lbl}: duplicate target id")
            t_ids.add(tid)
            if tg.get("type") != "point":
                errors.append(f"{lbl}: type must be 'point' — slots/line/edge grammars "
                              f"are not in this wave")
            for ax in ("x", "y"):
                v = tg.get(ax)
                if not isinstance(v, (int, float)) or isinstance(v, bool) or not (0 <= v <= 100):
                    errors.append(f"{lbl}: {ax} must be a number in 0..100 "
                                  f"(percent of the scene)")
            if not tg.get("label"):
                errors.append(f"{lbl}: missing label")
        if len(t_ids) < 2:
            errors.append(f"{ws}: needs at least 2 point targets")
        budget, par = sg.get("budget"), sg.get("par")
        if not isinstance(budget, int) or budget <= 0:
            errors.append(f"{ws}: budget must be a positive integer")
        if not isinstance(par, int) or par <= 0 or (isinstance(budget, int) and par > budget):
            errors.append(f"{ws}: par must be a positive integer no greater than budget")
        chip_ids: set[str] = set()
        chip_props: set[str] = set()
        chips = sg.get("chips") or []
        total_cost = 0
        for c in chips:
            cid = c.get("id")
            lbl = f"{ws} chip {cid or '?'}"
            if not cid:
                errors.append(f"{lbl}: missing id")
                continue
            if cid in chip_ids:
                errors.append(f"{lbl}: duplicate chip id")
            chip_ids.add(cid)
            if not isinstance(c.get("cost"), int) or c["cost"] <= 0:
                errors.append(f"{lbl}: cost must be a positive integer")
            else:
                total_cost += c["cost"]
            props = c.get("properties") or []
            if not props or not all(isinstance(p, str) and p for p in props):
                errors.append(f"{lbl}: properties must be a non-empty list of strings — "
                              f"attack resolution matches on them")
            chip_props.update(p for p in props if isinstance(p, str))
            for field in ("label", "definition", "why", "area"):
                if not c.get(field):
                    errors.append(f"{lbl}: missing {field}")
            provenance(c, lbl)
        if len(chip_ids) < 3:
            errors.append(f"{ws}: needs at least 3 chips — the shop must force a triage choice")
        if isinstance(budget, int) and total_cost and total_cost <= budget:
            errors.append(f"{ws}: total chip cost ({total_cost}) must exceed the budget "
                          f"({budget}) — a budget that buys the whole shop forces no triage")

        by_chip = {c.get("id"): c for c in chips}

        def check_siege_event(e, lbl, scored):
            if e.get("target") not in t_ids:
                errors.append(f"{lbl}: target '{e.get('target')}' is not a scene target")
            if not e.get("attackClass"):
                errors.append(f"{lbl}: missing attackClass")
            req = e.get("requires") or []
            if not req or not all(isinstance(p, str) and p for p in req):
                errors.append(f"{lbl}: requires must name at least one stopping property")
            elif not any(p in chip_props for p in req):
                errors.append(f"{lbl}: no chip in the shop carries any of {req} — "
                              f"the attack would be unstoppable")
            bp = e.get("breachPath") or []
            if not bp:
                errors.append(f"{lbl}: missing breachPath")
            else:
                if bp[0] != e.get("target"):
                    errors.append(f"{lbl}: breachPath must start at the struck target")
                for tid in bp:
                    if tid not in t_ids:
                        errors.append(f"{lbl}: breachPath id '{tid}' is not a scene target")
            for field in ("failCopy", "stopCopy"):
                if not e.get(field):
                    errors.append(f"{lbl}: missing {field} — the animation copy IS the lesson")
            if scored:
                for field in ("why", "area"):
                    if not e.get(field):
                        errors.append(f"{lbl}: missing {field}")
                provenance(e, lbl)

        waves = sg.get("waves") or []
        if not waves:
            errors.append(f"{ws}: needs at least one wave")
        ev_ids: set[str] = set()
        for wi, w in enumerate(waves):
            evs = (w or {}).get("events") or []
            if not evs:
                errors.append(f"{ws} wave {wi}: no events")
            for e in evs:
                eid = e.get("id")
                lbl = f"{ws} wave {wi} event {eid or '?'}"
                if not eid:
                    errors.append(f"{lbl}: missing id")
                    continue
                if eid in ev_ids:
                    errors.append(f"{lbl}: duplicate event id")
                ev_ids.add(eid)
                ids.append(eid)
                check_siege_event(e, lbl, scored=True)

        fb = sg.get("freebie")
        if fb:
            place = fb.get("place") or []
            if not place:
                errors.append(f"{ws} freebie: needs a scripted `place` list")
            placed_on: dict[str, list[str]] = {}
            for p in place:
                if p.get("chip") not in chip_ids:
                    errors.append(f"{ws} freebie: unknown chip '{p.get('chip')}'")
                if p.get("target") not in t_ids:
                    errors.append(f"{ws} freebie: unknown target '{p.get('target')}'")
                placed_on.setdefault(p.get("target"), []).append(p.get("chip"))
            fevs = fb.get("events") or []
            if len(fevs) < 2:
                errors.append(f"{ws} freebie: needs at least 2 events "
                              f"(one interception + one breach demo)")
            outcomes = []
            for e in fevs:
                lbl = f"{ws} freebie event {e.get('id') or '?'}"
                check_siege_event(e, lbl, scored=False)
                stopped = False
                for cid in placed_on.get(e.get("target"), []):
                    props = (by_chip.get(cid) or {}).get("properties") or []
                    if any(p in props for p in (e.get("requires") or [])):
                        stopped = True
                outcomes.append(stopped)
            if outcomes and not (any(outcomes) and not all(outcomes)):
                errors.append(f"{ws} freebie: the scripted wave must demonstrate BOTH one "
                              f"interception and one breach against the authored placement")

    return ids


def stamp_territories(svg_text: str, tdata: dict, jurisdictions: list,
                      errors: list[str]) -> str:
    """Stamp territory classes onto the inlined world map for a Regulatory Risk lab.

    Build-time string surgery only — world-map-paths.svg stays pristine on disk.
    The committed whitelist (tools/templates/world-map-territories.json) is the
    single source of truth for which of the SVG's paths belong to which
    territory; each listed path gains class="t t-<short> cov-<coverage>" where
    <short> is the map id minus its "map-" prefix (t-eu, t-kr, ...; the data's
    display `short` — "S. Korea", "US federal" — is not a CSS token) and
    coverage joins from the lab's own map data. Appended after the paths:
    <defs> with the #rr-hatch notice pattern, the CoE dashed ring (.rr-coe) and
    one .rr-dot circle per sub-4px territory in the whitelist's `dots` list.

    Any inconsistency is a validation error appended to `errors` (the caller's
    normal fail-the-build path), never an exception; on error the pristine SVG
    text is returned unstamped.
    """
    where = "world-map-territories.json"
    local: list[str] = []
    juris_by_id = {j.get("id"): j for j in jurisdictions}
    territories: dict[str, list[int]] = tdata.get("territories") or {}
    counts: dict[str, int] = tdata.get("counts") or {}
    dots: list[str] = tdata.get("dots") or []
    n_paths = svg_text.count("<path")

    idx_to_terr: dict[int, str] = {}
    for terr, indices in territories.items():
        if terr not in juris_by_id:
            local.append(f"{where}: territory '{terr}' is absent from map.jurisdictions")
        if counts.get(terr) != len(indices):
            local.append(f"{where}: '{terr}' lists {len(indices)} path(s) but the pinned "
                         f"count is {counts.get(terr)}")
        for i in indices:
            if not (0 <= i < n_paths):
                local.append(f"{where}: '{terr}' index {i} is out of range "
                             f"(the SVG has {n_paths} paths)")
            elif i in idx_to_terr:
                local.append(f"{where}: path index {i} is claimed by both "
                             f"'{idx_to_terr[i]}' and '{terr}'")
            else:
                idx_to_terr[i] = terr
    for dot in dots:
        if dot not in juris_by_id:
            local.append(f"{where}: dots entry '{dot}' is absent from map.jurisdictions")
    coe = juris_by_id.get("map-coe")
    if coe is None or "x" not in coe:
        local.append(f"{where}: 'map-coe' with projected coordinates is required for the "
                     f"CoE ring but is absent from map.jurisdictions")
    if any("x" not in juris_by_id[d] for d in dots if d in juris_by_id):
        local.append(f"{where}: a dots territory has no projected x/y (knowledge file not prepared)")
    if local:
        errors += local
        return svg_text

    def cls_of(terr: str) -> str:
        j = juris_by_id[terr]
        short = terr[4:] if terr.startswith("map-") else terr
        return f"t t-{short} cov-{j['coverage']}"

    parts = svg_text.split("<path")
    stamped = [parts[0]]
    for i, chunk in enumerate(parts[1:]):
        terr = idx_to_terr.get(i)
        prefix = f'<path class="{cls_of(terr)}"' if terr else "<path"
        stamped.append(prefix + chunk)
    result = "".join(stamped)

    # Belt-and-braces pinned-count check on the *output*: what actually shipped
    # must match the committed counts, not merely the whitelist's arithmetic.
    for terr in territories:
        got = result.count(f'class="{cls_of(terr)}"')
        if got != counts.get(terr):
            local.append(f"{where}: '{terr}' stamped {got} path(s) in the output but the "
                         f"pinned count is {counts.get(terr)}")
    if local:
        errors += local
        return svg_text

    # viewBox units from the projected percentage positions prepare() derived.
    w, h = aigp_knowledge.MAP_W, aigp_knowledge.MAP_H
    extra = ['<defs><pattern id="rr-hatch" patternUnits="userSpaceOnUse" width="6" '
             'height="6" patternTransform="rotate(45)">'
             '<line x1="0" y1="0" x2="0" y2="6"/></pattern></defs>',
             f'<ellipse class="rr-coe" cx="{round(coe["x"] / 100 * w, 2)}" '
             f'cy="{round(coe["y"] / 100 * h, 2)}" rx="55" ry="38" fill="none"/>']
    for dot in dots:
        j = juris_by_id[dot]
        extra.append(f'<circle class="{cls_of(dot)} rr-dot" '
                     f'cx="{round(j["x"] / 100 * w, 2)}" '
                     f'cy="{round(j["y"] / 100 * h, 2)}" r="6"/>')
    return result + "\n" + "\n".join(extra) + "\n"


def verbatim_errors(manifest: dict, decks: dict[str, dict]) -> list[str]:
    """Run the verbatim-similarity guard over every deck this lab loads.

    The #1 content constraint is that authored cards never share a long
    verbatim run with the source material they were written from — sources are
    cited for *concept* provenance, never copied. tools/check_verbatim.py has
    always been able to prove that; it was a tool you had to remember to run,
    which for a constraint that ranks first is the wrong enforcement level. So
    the manifest declares the source set and the build enforces it.

    "sources" is required, not defaulted: a lab that silently checks against
    nothing is indistinguishable from a lab that passes. Declaring it empty is
    allowed — several labs predate any vendored corpus — but only with a
    sourcesNote saying why, so the empty set is a decision on the record rather
    than an omission nobody noticed.
    """
    if "sources" not in manifest:
        return ["manifest: missing sources — declare the source texts this lab's decks "
                "must not lift prose from, as repo-relative paths (files or dirs). "
                "Use [] plus a sourcesNote if this lab has no vendored source corpus."]

    declared = manifest["sources"]
    if not isinstance(declared, list):
        return ["manifest: sources must be a list of repo-relative paths"]
    if not declared:
        if not manifest.get("sourcesNote"):
            return ["manifest: sources is empty and no sourcesNote explains why — "
                    "an undeclared source set makes the verbatim guard a no-op"]
        return []

    if check_verbatim.verbatim_skipped():
        print(f"⚠ SKIP_VERBATIM=1 — verbatim guard NOT run for {manifest.get('id')}: "
              "this build has not proven its cards are freshly authored", file=sys.stderr)
        return []

    errors: list[str] = []
    paths: list[str] = []
    for rel in declared:
        p = check_verbatim.resolve_source(rel)
        if p is None:
            errors.append(f"manifest: source '{rel}' is private and "
                          f"{check_verbatim.sources_root()}/{check_verbatim.SOURCE_MAP_NAME} "
                          "does not map it — set SOURCES_ROOT to the private source "
                          "checkout, or SKIP_VERBATIM=1 to build without the guard")
            continue
        if not p.exists():
            errors.append(f"manifest: source '{rel}' does not exist")
            continue
        paths.append(str(p))
    if errors:
        return errors

    index = (check_verbatim.source_index(check_verbatim.load_sources(paths))
             - check_verbatim.public_index())
    dindex = check_verbatim.derivation_index(paths)
    for ref, deck in decks.items():
        for _, card_path, run in check_verbatim.check_data(deck, ref, index):
            errors.append(f"verbatim: {ref} {card_path} shares an 8-token run with a "
                          f'declared source: "{run}"')
        for _, card_path, reason in check_verbatim.check_derivation(deck, ref, dindex):
            errors.append(f"derived: {ref} {card_path} {reason}")
    return errors


# Beta gate (design D2): an outline area is drillable only if the lab tracks at
# least this many scored cards against it. Below the floor, "covered" means a
# card exists, not that anyone could learn the area from it.
CARD_FLOOR = 6


def outline_errors(manifest: dict, ids_by_ref: dict[str, list[str]],
                   quiet: bool = False) -> list[str]:
    """Check the lab's coverage of its certification's outline.

    Three conventions for counting coverage existed across the labs, and they
    disagreed by enough that "every area is drillable" meant a different thing
    per lab. This is the AI-901 one, made the standard (design D3):

      - count only TRACKED, SCORED cards — the ids the build already collects,
        which is why unscored ladders fall out for free
      - a game straddling areas is SPLIT FRACTIONALLY, never claimed wholesale
        against each area it touches
      - the split is DECLARED per game and validated here; it is deliberately
        not derived, because a derivation would silently re-describe coverage
        every time a deck changed

    Failing area: below CARD_FLOOR, or no owner game at all. Either can be
    accepted deliberately via manifest "acceptedGaps" — with a reason, which
    is the whole point of naming them rather than quietly rounding up.
    """
    if "outline" not in manifest:
        return ["manifest: missing outline — name the certification outline file this lab is "
                "measured against (data/outlines/<cert>.json), or null plus an outlineNote."]
    ref = manifest["outline"]
    if ref is None:
        if not manifest.get("outlineNote"):
            return ["manifest: outline is null and no outlineNote explains why — a lab with no "
                    "declared outline cannot claim area coverage at all"]
        return []

    outline_path = REPO / ref
    if not outline_path.exists():
        return [f"manifest: outline '{ref}' does not exist"]
    outline = load_json(outline_path)
    area_ids = [a["id"] for a in outline.get("areas", [])]
    if not area_ids:
        return [f"outline {ref}: declares no areas"]
    if len(set(area_ids)) != len(area_ids):
        return [f"outline {ref}: duplicate area ids"]

    errors: list[str] = []
    gaps = manifest.get("acceptedGaps") or {}
    for gap_id, reason in gaps.items():
        if gap_id not in area_ids:
            errors.append(f"acceptedGaps: '{gap_id}' is not an area in {ref}")
        if not reason:
            errors.append(f"acceptedGaps: '{gap_id}' has no reason — an accepted gap without "
                          f"one is an unaccepted gap")

    # Cards are counted per deck file, not per game: two games sharing a deck
    # would otherwise count its cards twice and inflate every area they touch.
    coverage = {a: 0.0 for a in area_ids}
    owners: dict[str, list[str]] = {a: [] for a in area_ids}
    claimed: dict[str, str] = {}
    for g in manifest["games"]:
        declared = g.get("areas")
        deck_ref = g.get("deck") or g.get("data")
        if not declared:
            errors.append(f"game {g['id']}: declares no areas — every game must say which "
                          f"outline areas it drills, and in what proportion")
            continue
        if not isinstance(declared, dict):
            errors.append(f"game {g['id']}: areas must be a map of area id -> share of the "
                          f"game's cards")
            continue
        for aid in declared:
            if aid not in coverage:
                errors.append(f"game {g['id']}: area '{aid}' is not in {ref}")
        total = sum(declared.values())
        if abs(total - 1.0) > 0.005:
            errors.append(f"game {g['id']}: area shares sum to {total:.3f}, not 1.0 — a game's "
                          f"cards are split across the areas it drills, never multiplied")
            continue
        for aid in declared:
            owners.setdefault(aid, []).append(g["id"])
        if deck_ref in claimed:
            # The deck's cards already counted under the first game to claim
            # them; the second game still names its areas (it is an owner) but
            # contributes no further cards.
            continue
        claimed[deck_ref] = g["id"]
        cards = len(ids_by_ref.get(deck_ref, []))
        for aid, share in declared.items():
            if aid in coverage:
                coverage[aid] += cards * share

    if errors:
        return errors

    for aid in area_ids:
        if aid in gaps:
            continue
        if not owners.get(aid):
            errors.append(f"outline area {aid}: no owner game — nothing in this lab drills it")
        # Compared after rounding to the nearest whole card: a declared share is
        # a rounded proportion of an integer card count, so a 536-card campaign
        # splitting 61 ways lands each area at 5.9 when it holds exactly 6 real
        # cards. Cards are integers; 5.9 of one cannot exist.
        elif round(coverage[aid]) < CARD_FLOOR:
            errors.append(f"outline area {aid}: {coverage[aid]:.1f} tracked scored cards, "
                          f"below the floor of {CARD_FLOOR} (owners: "
                          f"{', '.join(owners[aid])})")

    if not errors and not quiet:
        covered = len(area_ids) - len(gaps)
        print(f"  coverage: {covered}/{len(area_ids)} outline areas at or above "
              f"{CARD_FLOOR} tracked scored cards" +
              (f" · {len(gaps)} accepted gap(s)" if gaps else ""))
    return errors


def coverage_matrix(manifest: dict, ids_by_ref: dict[str, list[str]]) -> list[dict]:
    """One row per outline area, naming the games that drill it (design D3).

    Published rather than merely checked: the matrix is what makes the coverage
    claim inspectable, and the accepted-gaps list is what stops a gap being
    quietly absorbed into a rounded-up total.
    """
    outline = load_json(REPO / manifest["outline"])
    gaps = manifest.get("acceptedGaps") or {}
    rows: list[dict] = []
    counts: dict[str, float] = {}
    owners: dict[str, list[str]] = {}
    claimed: set[str] = set()
    for g in manifest["games"]:
        deck_ref = g.get("deck") or g.get("data")
        fresh = deck_ref not in claimed
        claimed.add(deck_ref)
        cards = len(ids_by_ref.get(deck_ref, [])) if fresh else 0
        for aid, share in (g.get("areas") or {}).items():
            owners.setdefault(aid, []).append(g["id"])
            counts[aid] = counts.get(aid, 0.0) + cards * share
    for a in outline["areas"]:
        rows.append({
            "area": a["id"], "label": a["label"], "domain": a["domain"],
            "cards": round(counts.get(a["id"], 0.0), 1),
            "games": owners.get(a["id"], []),
            "acceptedGap": gaps.get(a["id"], ""),
        })
    return rows


def write_coverage(lab_id: str, template: str, adapters: set[str]) -> int:
    """Render the coverage matrix + accepted gaps to docs/coverage/<lab>.md."""
    manifest = load_json(LABS / f"{lab_id}.json")
    if not manifest.get("outline"):
        raise SystemExit(f"{lab_id}: no outline declared — nothing to report coverage against")
    _, _, ids_by_ref, errors = load_games(manifest, adapters)
    if errors:
        for e in errors:
            print(f"  ✗ {e}", file=sys.stderr)
        raise SystemExit(f"{lab_id}: decks do not validate; fix the build before reporting coverage")

    outline = load_json(REPO / manifest["outline"])
    rows = coverage_matrix(manifest, ids_by_ref)
    gaps = manifest.get("acceptedGaps") or {}
    lines = [
        f"# {manifest['title']} — outline coverage",
        "",
        f"Measured against **{outline['title']}** (effective {outline.get('effective', '?')}), "
        f"`{manifest['outline']}`.",
        "",
        f"Generated by `python3 tools/build_lab.py {lab_id} --coverage`. Cards are *tracked, "
        f"scored* cards only; a game spanning several areas is split by the shares declared "
        f"on it in the manifest, never counted whole against each. The build fails on any "
        f"area under {CARD_FLOOR} cards or with no owner game, unless it is an accepted gap "
        f"below.",
        "",
        "| Area | Title | Cards | Drilled by |",
        "|---|---|---:|---|",
    ]
    for r in rows:
        games = ", ".join(f"`{g}`" for g in r["games"]) or "—"
        flag = " ⚠︎" if r["acceptedGap"] else ""
        lines.append(f"| {r['area']}{flag} | {r['label']} | {r['cards']:g} | {games} |")

    lines += ["", "## Accepted gaps", ""]
    if gaps:
        lines.append("Deliberately not covered in this release, and why:")
        lines.append("")
        for aid, reason in gaps.items():
            label = next((r["label"] for r in rows if r["area"] == aid), "")
            lines.append(f"- **{aid} {label}** — {reason}")
    else:
        lines.append("None: every area in the outline is drilled at or above the floor.")
    lines.append("")

    out = REPO / "docs" / "coverage" / f"{lab_id}.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines), encoding="utf-8")
    covered = sum(1 for r in rows if r["area"] not in gaps)
    print(f"✓ {out.relative_to(REPO)}  ({covered}/{len(rows)} areas, {len(gaps)} accepted gap(s))")
    return 0


def load_games(manifest: dict, adapters: set[str]):
    """Load, validate and prepare every deck the manifest names.

    Returns (decks, ids, ids_by_ref, errors). Split out of build() so the
    coverage report counts cards the same way the build does — the alternative
    is a second implementation of "what is a tracked scored card", which is the
    exact ambiguity design D3 exists to remove.
    """
    errors: list[str] = []
    decks: dict[str, dict] = {}
    ids: list[str] = []
    ids_by_ref: dict[str, list[str]] = {}

    for g in manifest["games"]:
        runner = g.get("runner", "board")
        name = g.get("adapter", runner)
        if name not in adapters:
            errors.append(f"game {g['id']}: adapter '{name}' is not in the engine registry")
        ref = g.get("deck") or g.get("data")
        if not ref:
            errors.append(f"game {g['id']}: names neither a deck nor a data file")
            continue
        for field in ("title", "blurb", "rung"):
            if not g.get(field):
                errors.append(f"game {g['id']}: missing {field}")
        if g.get("rung") and g["rung"] not in RUNGS:
            errors.append(f"game {g['id']}: rung '{g['rung']}' is not one of "
                          f"{'/'.join(RUNGS)} — the home ladder would silently hide it")
        if ref not in decks:
            decks[ref] = load_json(DECKS / ref)
            if g.get("deck"):
                ref_ids = validate_deck(decks[ref], ref, runner, errors)
                ids += ref_ids
                ids_by_ref[ref] = ref_ids
            else:
                entry = KNOWLEDGE.get(ref)
                if entry is None:
                    errors.append(f"game {g['id']}: '{ref}' is a typed knowledge file with no entry in "
                                  f"KNOWLEDGE, so it would ship unvalidated and unprepared")
                else:
                    knowledge, indicators = entry
                    errors += [f"{ref}: {e}" for e in knowledge.validate(decks[ref], indicators)]
                    knowledge.prepare(decks[ref])
                    ref_ids = knowledge.collect_ids(decks[ref])
                    ids += ref_ids
                    ids_by_ref[ref] = ref_ids

    return decks, ids, ids_by_ref, errors


def build(lab_id: str, template: str, adapters: set[str], langs: list[dict] = None, ui: dict[str, dict] = None, labs_tr: dict[str, dict] = None, quiet: bool = False) -> int:
    manifest = load_json(LABS / f"{lab_id}.json")
    decks, ids, ids_by_ref, errors = load_games(manifest, adapters)

    # Ids are the scheduler's primary key. A shared deck appears in more than
    # one lab, so a collision inside a lab would cross-contaminate progress
    # between two unrelated cards.
    dupes = sorted({i for i in ids if ids.count(i) > 1})
    if dupes:
        errors.append(f"duplicate card ids within the lab: {dupes}")

    # Lab-wide id collision across files: two *different* files (e.g. a
    # domain-ii file and a domain-iii file, or a knowledge file and a generic
    # deck) that happen to reuse an id would silently cross-contaminate
    # progress the same way a within-file collision would, but the flat
    # 'dupes' check above can't say which files are at fault. This pass
    # names both.
    id_to_refs: dict[str, set[str]] = {}
    for ref, ref_ids in ids_by_ref.items():
        for i in ref_ids:
            id_to_refs.setdefault(i, set()).add(ref)
    for i, refs in sorted(id_to_refs.items()):
        if len(refs) > 1:
            errors.append(f"id '{i}' is defined in more than one file: {sorted(refs)}")

    game_ids = [g["id"] for g in manifest["games"]]
    dupe_games = sorted({i for i in game_ids if game_ids.count(i) > 1})
    if dupe_games:
        errors.append(f"duplicate game ids: {dupe_games}")

    # A solo lab opens straight into one game; naming a game it doesn't have
    # would leave the page on an empty hub it promised never to show.
    if manifest.get("solo") and manifest["solo"] not in game_ids:
        errors.append(f"manifest: solo game '{manifest['solo']}' is not one of the lab's games")

    tabs = {t["id"] for t in manifest.get("tabs", [])}
    for g in manifest["games"]:
        if tabs and g.get("tab") and g["tab"] not in tabs:
            errors.append(f"game {g['id']}: tab '{g['tab']}' is not declared")

    # Home-page ladder groups (design §5, beta.1 ship gate R8): when the
    # manifest declares "groups", the home screen renders one Learn→Apply→Sim
    # section per group — so every game must name a declared group, or it
    # would silently never appear on the home screen at all.
    group_list = manifest.get("groups") or []
    for gr in group_list:
        if not (gr.get("id") and gr.get("label")):
            errors.append(f"manifest: group '{gr.get('id', '?')}' needs id and label")
    group_ids = {gr.get("id") for gr in group_list}
    if len(group_ids) != len(group_list):
        errors.append("manifest: duplicate group ids")
    if group_list:
        for g in manifest["games"]:
            if not g.get("group"):
                errors.append(f"game {g['id']}: manifest declares groups but the game "
                              f"names none — it would never appear on the home ladder")
            elif g["group"] not in group_ids:
                errors.append(f"game {g['id']}: group '{g['group']}' is not declared")
    for field in ("id", "title", "storageKey", "studyContext", "citeInstruction"):
        if not manifest.get(field):
            errors.append(f"manifest: missing {field}")

    errors += verbatim_errors(manifest, decks)
    errors += outline_errors(manifest, ids_by_ref, quiet)

    # The 234 KB world map is inlined only into a lab that has a map game;
    # every other lab would carry it as dead weight. A lab with a Regulatory
    # Risk game additionally gets the territory-class stamping + rr defs;
    # plain aigpMap labs (Legislation Lab) get the pristine SVG unchanged.
    needs_map = any(g.get("adapter") in ("aigpMap", "aigpRisk") for g in manifest["games"])
    map_svg = MAP_SVG.read_text(encoding="utf-8") if needs_map else ""
    risk_game = next((g for g in manifest["games"] if g.get("adapter") == "aigpRisk"), None)
    if risk_game is not None:
        ref = risk_game.get("deck") or risk_game.get("data")
        juris = ((decks.get(ref) or {}).get("map") or {}).get("jurisdictions", [])
        map_svg = stamp_territories(map_svg, load_json(MAP_TERRITORIES), juris, errors)

    # Per-game siegeBoard scenes: the world-map conditional-inlining rule
    # generalized. Each scene named by a siege deck's scene.svgRef is read from
    # tools/templates/ and inlined ONLY into labs whose games reference it, as
    # a JSON blob the engine injects at render time — every other lab carries
    # an empty object. Budget + self-containment are ship gates (design §7 R6):
    # over 60 KB or any external reference fails the build.
    scenes: dict[str, str] = {}
    template_dir = TEMPLATE.parent.resolve()
    for g in manifest["games"]:
        if g.get("adapter", g.get("runner", "board")) != "siegeBoard":
            continue
        ref = g.get("deck") or g.get("data")
        svg_ref = ((((decks.get(ref) or {}).get("siege") or {}).get("scene")) or {}).get("svgRef")
        if not svg_ref or svg_ref in scenes:
            continue   # a missing svgRef is already a validate_deck error
        p = (template_dir / svg_ref).resolve()
        if not str(p).startswith(str(template_dir)):
            errors.append(f"game {g['id']}: scene svgRef '{svg_ref}' escapes tools/templates/")
            continue
        if not p.exists():
            errors.append(f"game {g['id']}: scene SVG missing: tools/templates/{svg_ref}")
            continue
        text = p.read_text(encoding="utf-8")
        size = len(text.encode("utf-8"))
        if size > SCENE_BUDGET:
            errors.append(f"game {g['id']}: scene '{svg_ref}' is {size/1024:.0f} KB — over "
                          f"the {SCENE_BUDGET//1024} KB per-board budget")
        lowered = text.lower()
        for marker in ("http://", "https://", "url(", "<script", "<image",
                       "xlink:href", "<foreignobject"):
            if marker in lowered:
                errors.append(f"game {g['id']}: scene '{svg_ref}' contains '{marker}' — "
                              f"scenes must be self-contained (zero outbound requests)")
        scenes[svg_ref] = text

    # Card-translation overlays: for every language that claims cards:true,
    # each of this lab's refs must have data/i18n/decks/<ref-stem>.<lang>.json
    # whose ids and dotted paths exactly match a fresh extraction — the
    # in-memory extraction, not the snapshot on disk, so source drift after a
    # deck edit fails the build instead of shipping stale translations.
    #
    # A lab may opt out with manifest "untranslated": true — an English-only
    # release that ships before its card translations exist. The alternative is
    # committing overlays whose "translations" are the English strings verbatim,
    # which passes the gate above while lying about coverage and then has to be
    # un-lied later. The opt-in is per lab and per manifest, so every lab that
    # does not carry the flag keeps the full check; the runtime already falls
    # back to English cards when an overlay is absent (lab.html's overlay fetch
    # swallows the miss), so the page degrades exactly as it does on file://.
    #
    # Pending re-translation: data/i18n/source/<ref> is the English snapshot the
    # overlays were translated from (written by --extract-i18n). When an English
    # string is corrected, its stale translations are deleted rather than left
    # teaching the old fact; a path may then be missing from an overlay only
    # while its English differs from (or is absent in) that snapshot. The page
    # shows English for it until the overlay is re-translated and the snapshot
    # re-extracted. Unchanged English must still be fully translated.
    overlays: dict[str, dict] = {}
    for l in ([] if manifest.get("untranslated") else (langs or [])):
        if not l.get("cards") or l["code"] == "en":
            continue
        code, bundle = l["code"], {}
        for ref, deck in decks.items():
            src = extract_translatables(deck)
            snap_path = I18N_DIR / "source" / ref
            snap = load_json(snap_path) if snap_path.exists() else {}
            rel = Path(ref)
            rel2 = rel.relative_to("decks") if rel.parts[0] == "decks" else rel
            tp = I18N_DIR / "decks" / rel2.parent / f"{rel2.stem}.{code}.json"
            if not tp.exists():
                errors.append(f"i18n[{code}]: missing translation file {tp.relative_to(REPO)}")
                continue
            tr = load_json(tp)
            for iid, fields in src.items():
                got = tr.get(iid, {})
                miss = untranslated_paths(fields, got, snap.get(iid, {}))
                if miss:
                    errors.append(f"i18n[{code}] {ref}#{iid}: untranslated {sorted(miss)[:4]}")
                unknown = set(got) - set(fields)
                if unknown:
                    errors.append(f"i18n[{code}] {ref}#{iid}: unknown paths {sorted(unknown)[:4]}")
            for iid in set(tr) - set(src):
                errors.append(f"i18n[{code}] {ref}: translation for unknown id '{iid}'")
            for iid, fields in tr.items():
                bundle.setdefault(iid, {}).update(
                    {p: v for p, v in fields.items() if p in src.get(iid, {})})
        overlays[code] = bundle

    if errors:
        print(f"BUILD FAILED ({lab_id}) — {len(errors)} validation error(s):", file=sys.stderr)
        for e in errors:
            print(f"  ✗ {e}", file=sys.stderr)
        return 1

    html = template.replace("__LAB_TITLE__", manifest["title"])
    html = html.replace("<!--__WORLD_MAP__-->", map_svg)

    logos = load_json(AI_LOGOS)
    missing = {"claude", "chatgpt", "perplexity"} - set(logos)
    if missing:
        raise SystemExit(f"AI logos missing: {sorted(missing)}")
    html = html.replace("/*__AI_LOGOS__*/",
                        json.dumps(logos, ensure_ascii=False).replace("</", "<\\/"))

    html = html.replace("/*__LAB__*/", payload(shipped(manifest)))
    html = html.replace("/*__DECKS__*/", payload(shipped_decks(decks)))
    html = html.replace("/*__SCENES__*/", payload(scenes))
    if langs is not None and ui is not None and labs_tr is not None:
        html = html.replace("/*__I18N__*/", payload(i18n_payload(manifest, langs, ui, labs_tr)))

    out = OUT / manifest["output"]
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html, encoding="utf-8")

    i18n_out = OUT / "i18n"
    i18n_out.mkdir(parents=True, exist_ok=True)
    for code, bundle in overlays.items():
        (i18n_out / f"{manifest['id']}.{code}.json").write_text(
            json.dumps(bundle, ensure_ascii=False, separators=(",", ":")),
            encoding="utf-8")

    if not quiet:
        print(f"✓ {out.name}  ({out.stat().st_size/1024:.0f} KB)")
        print(f"  {len(manifest['games'])} games · {len(decks)} decks · {len(ids)} scored cards")
    return 0


def exam_chips(exam: dict) -> list[str]:
    """The stat chips for one exam card: derived counts, then authored extras.

    The games/cards chips are counted from the lab manifest the exam links to,
    not typed into the container manifest. Hand-typed counts are how the AWS
    hub came to advertise 793 cards for a lab that tracks 751 — a number nobody
    could have checked without knowing which of two counting conventions had
    produced it. Anything the manifest can't derive (service counts, and other
    genuinely editorial chips) stays authored in "stats".
    """
    # Imported here, not at module scope: site_stats counts cards by calling
    # back into this module, so a top-level import would be circular.
    import site_stats

    chips: list[str] = []
    if exam.get("lab"):
        s = site_stats.lab_stats().get(exam["lab"])
        if s:
            chips += [f"{s['games']} GAMES", f"{s['cards']} CARDS"]
    return chips + list(exam.get("stats") or [])


def render_exam_card(exam: dict, tone: str) -> str:
    """One exam entry from a container manifest, as card markup.

    Enabled exams render as a clickable card identical in structure to the
    landing page's own cards. Disabled ("soon") exams render the same shell
    with no link and a note instead of stats, matching the pattern lab.html
    already uses for AIGP's not-yet-built domain tabs.
    """
    title = escape(exam["title"])
    subtitle = escape(exam.get("subtitle", ""))
    code = escape(exam.get("code", ""))
    if exam.get("enabled", True):
        stats = "".join(
            f'<span class="stat{" status" if i == 0 else ""}">{escape(s)}</span>'
            for i, s in enumerate([exam["status"], *exam_chips(exam)])
        )
        href = escape(exam["href"])
        return (
            f'    <a class="app brutal-heavy brutal-shadow-lg brutal-hover-lg" '
            f'style="--tone:{tone}" href="{href}">\n'
            f'      <span class="badge" data-i18n="container.exam">Exam</span>\n'
            f'      <div>\n'
            f'        <p class="code">{code}</p>\n'
            f'        <h2>{title}</h2>\n'
            f'        <p>{subtitle}</p>\n'
            f'      </div>\n'
            f'      <div>\n'
            f'        <div class="stats">{stats}</div>\n'
            f'        <span class="go"><span data-i18n="container.open">Open the lab</span> <span class="arrow">&rarr;</span></span>\n'
            f'      </div>\n'
            f'    </a>'
        )
    soon = escape(exam.get("soon", "Not built yet."))
    return (
        f'    <div class="app brutal-heavy brutal-shadow-lg soon" style="--tone:{tone}">\n'
        f'      <span class="badge" data-i18n="container.soon">Coming soon</span>\n'
        f'      <div>\n'
        f'        <p class="code">{code}</p>\n'
        f'        <h2>{title}</h2>\n'
        f'        <p>{subtitle}</p>\n'
        f'      </div>\n'
        f'      <p class="soon-note">{soon}</p>\n'
        f'    </div>'
    )


def build_container(container_id: str, template: str, langs: list[dict] = None,
                     ui: dict[str, dict] = None, quiet: bool = False) -> int:
    manifest = load_json(CONTAINERS / f"{container_id}.json")
    errors: list[str] = []

    for field in ("id", "title", "subtitle", "output", "tone", "exams"):
        if not manifest.get(field):
            errors.append(f"container manifest: missing {field}")
    if not errors:
        for exam in manifest["exams"]:
            if not exam.get("title"):
                errors.append("exam entry missing title")
            if exam.get("enabled", True):
                for field in ("href", "status", "lab"):
                    if not exam.get(field):
                        errors.append(f"exam '{exam.get('title')}': enabled exam missing {field}")
                # The lab link is what makes the games/cards chips derivable; an
                # exam card that names no lab is back to advertising hand-typed
                # numbers nobody can check.
                lab_id = exam.get("lab")
                if lab_id:
                    lab_path = LABS / f"{lab_id}.json"
                    if not lab_path.exists():
                        errors.append(f"exam '{exam.get('title')}': lab '{lab_id}' has no manifest")
                    elif load_json(lab_path)["output"] != exam.get("href"):
                        errors.append(
                            f"exam '{exam.get('title')}': lab '{lab_id}' builds "
                            f"'{load_json(lab_path)['output']}' but the card links to "
                            f"'{exam.get('href')}' — the chips would describe a different lab")
                href = exam.get("href")
                if href and not (OUT / href).exists():
                    errors.append(
                        f"exam '{exam.get('title')}': href '{href}' does not exist under "
                        f"gamification/ (build labs before containers)"
                    )

    if errors:
        print(f"BUILD FAILED (container:{container_id}) — {len(errors)} validation error(s):",
              file=sys.stderr)
        for e in errors:
            print(f"  ✗ {e}", file=sys.stderr)
        return 1

    cards = "\n".join(render_exam_card(e, f"var({manifest['tone']})") for e in manifest["exams"])
    html_out = template.replace("__CONTAINER_TITLE__", escape(manifest["title"]))
    html_out = html_out.replace("__CONTAINER_SUBTITLE__", escape(manifest["subtitle"]))
    html_out = html_out.replace("<!--__EXAM_CARDS__-->", cards)
    if langs is not None and ui is not None:
        # Containers carry no per-lab card content, so the bundle's "labs"
        # half is always empty — same shape as a lab page's, minus the
        # translations that page has nothing to key into.
        bundle = {
            "meta": {l["code"]: {"name": l["name"], "dir": l["dir"], "cards": l["cards"],
                                  "flag": l.get("flag", "")}
                     for l in langs},
            "ui": ui,
            "labs": {},
        }
        html_out = html_out.replace("/*__I18N__*/", payload(bundle))

    out = OUT / manifest["output"]
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html_out, encoding="utf-8")

    if not quiet:
        print(f"✓ {out.name}  ({out.stat().st_size/1024:.0f} KB)")
        print(f"  {len(manifest['exams'])} exam(s)")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("lab", nargs="?", help="lab id (a file in data/labs/)")
    ap.add_argument("--all", action="store_true", help="build every lab")
    ap.add_argument("--extract-i18n", action="store_true", help="extract translatable content from all decks")
    ap.add_argument("--coverage", action="store_true",
                    help="write the outline-coverage matrix for a lab to docs/coverage/<lab>.md")
    args = ap.parse_args()

    template = TEMPLATE.read_text(encoding="utf-8")
    for ph in ("__LAB_TITLE__", "/*__LAB__*/", "/*__DECKS__*/", "/*__SCENES__*/",
               "/*__AI_LOGOS__*/", "/*__I18N__*/"):
        if ph not in template:
            raise SystemExit(f"placeholder {ph} not found in {TEMPLATE.name}")
    adapters = registry_keys(template)

    langs, ui, labs_tr, idx, i18n_errors = load_i18n()

    # index.html has no build step of its own (it's hand-edited, in a
    # sibling public repo) so nothing else would catch its inline bundle
    # drifting from data/i18n/index/*.json. A deploy build — one that has
    # explicitly pointed LAB_OUT or INDEX_HTML at a real target (the sibling
    # 0pies clone, in practice) — MUST fail if that target doesn't carry the
    # expected bundle: a missing/lost bundle there is exactly the C1
    # incident this gate exists to catch. Only the fully-default path (no
    # LAB_OUT, no INDEX_HTML — e.g. CI without the sibling clone checked
    # out) skips with a warning instead of erroring.
    is_deploy_build = bool(os.environ.get("LAB_OUT") or os.environ.get("INDEX_HTML"))
    index_html_path = Path(os.environ.get("INDEX_HTML") or (OUT / "index.html"))
    bundle_ui = load_index_bundle(index_html_path)
    if bundle_ui is None:
        if is_deploy_build:
            i18n_errors.append(
                f"index.html bundle-sync check: {index_html_path} not found or has no "
                f'<script id="i18n" type="application/json"> bundle — required because '
                f"LAB_OUT/INDEX_HTML was set explicitly (deploy build)"
            )
        else:
            print(f"  (skip: index.html bundle-sync check — {index_html_path} not found)",
                  file=sys.stderr)
    else:
        i18n_errors += diff_index_bundle(idx, bundle_ui)

    if i18n_errors:
        print(f"BUILD FAILED — {len(i18n_errors)} i18n error(s):", file=sys.stderr)
        for e in i18n_errors:
            print(f"  ✗ {e}", file=sys.stderr)
        return 1

    if args.extract_i18n:
        # Extract translatable content from all decks and corpus files referenced by labs
        source_dir = I18N_DIR / "source"
        source_dir.mkdir(parents=True, exist_ok=True)
        refs_written = set()
        all_ids = set()
        total_strings = 0
        total_words = 0

        for lab_path in sorted(LABS.glob("*.json")):
            manifest = load_json(lab_path)
            for g in manifest.get("games", []):
                ref = g.get("deck") or g.get("data")
                if not ref or ref in refs_written:
                    continue
                refs_written.add(ref)

                # Load deck exactly as build() does
                deck = load_json(DECKS / ref)
                if g.get("data"):  # It's a typed knowledge file (e.g., AIGP)
                    entry = KNOWLEDGE.get(ref)
                    if entry is not None:
                        knowledge, indicators = entry
                        knowledge.prepare(deck)

                # Extract translatables
                extracted = extract_translatables(deck)

                # Count stats
                all_ids.update(extracted.keys())
                for iid, fields in extracted.items():
                    total_strings += len(fields)
                    total_words += sum(len(v.split()) for v in fields.values())

                # Write source file
                out_path = source_dir / ref.replace(".json", ".json")
                out_path.parent.mkdir(parents=True, exist_ok=True)
                sorted_data = {k: extracted[k] for k in sorted(extracted.keys())}
                out_path.write_text(json.dumps(sorted_data, ensure_ascii=False, indent=1),
                                   encoding="utf-8")

        print(f"✓ Extracted {len(refs_written)} refs, {len(all_ids)} ids, "
              f"{total_strings} strings, ~{total_words} words")
        return 0

    if args.coverage:
        if not args.lab:
            ap.error("--coverage needs a lab id")
        return write_coverage(args.lab, template, adapters)

    if args.all:
        rc = 0
        for path in sorted(LABS.glob("*.json")):
            rc |= build(path.stem, template, adapters, langs, ui, labs_tr)
        container_template = CONTAINER_TEMPLATE.read_text(encoding="utf-8")
        for ph in ("__CONTAINER_TITLE__", "__CONTAINER_SUBTITLE__", "<!--__EXAM_CARDS__-->",
                   "/*__I18N__*/"):
            if ph not in container_template:
                raise SystemExit(f"placeholder {ph} not found in {CONTAINER_TEMPLATE.name}")
        for path in sorted(CONTAINERS.glob("*.json")):
            rc |= build_container(path.stem, container_template, langs, ui)
        return rc
    if not args.lab:
        ap.error("give a lab id, or --all")
    return build(args.lab, template, adapters, langs, ui, labs_tr)


if __name__ == "__main__":
    sys.exit(main())
