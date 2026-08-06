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

REPO = Path(__file__).resolve().parent.parent
LABS = REPO / "data" / "labs"
DECKS = REPO / "data"
TEMPLATE = REPO / "tools" / "templates" / "lab.html"
MAP_SVG = REPO / "tools" / "templates" / "world-map-paths.svg"
MAP_TERRITORIES = REPO / "tools" / "templates" / "world-map-territories.json"
AI_LOGOS = REPO / "tools" / "templates" / "ai-logos.json"
OUT = REPO / "gamification"
CONTAINERS = REPO / "data" / "containers"
CONTAINER_TEMPLATE = REPO / "tools" / "templates" / "container.html"

# Runners that take a generic deck, and the collection each one expects to find.
GENERIC = {"board": "items", "pairs": "pairs", "ladders": "ladders"}

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


def registry_keys(template: str) -> set[str]:
    """The adapter names the engine actually implements.

    Parsed out of lab.html so a manifest naming a runner the engine does not
    have fails the build instead of shipping a lab with a missing game.
    """
    m = re.search(r"const ADAPTERS = \{(.*?)\n\};", template, re.S)
    if not m:
        raise SystemExit("could not find the ADAPTERS registry in lab.html")
    return set(re.findall(r"^\s*(\w+):", m.group(1), re.M))


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


def build(lab_id: str, template: str, adapters: set[str], quiet: bool = False) -> int:
    manifest = load_json(LABS / f"{lab_id}.json")
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

    tabs = {t["id"] for t in manifest.get("tabs", [])}
    for g in manifest["games"]:
        if tabs and g.get("tab") and g["tab"] not in tabs:
            errors.append(f"game {g['id']}: tab '{g['tab']}' is not declared")
    for field in ("id", "title", "storageKey", "studyContext", "citeInstruction"):
        if not manifest.get(field):
            errors.append(f"manifest: missing {field}")

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

    # Both payloads land inside <script type="application/json">, so the only
    # sequence that could break out is a literal </script>.
    def payload(obj):
        return json.dumps(obj, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")

    html = html.replace("/*__LAB__*/", payload(manifest))
    html = html.replace("/*__DECKS__*/", payload(decks))

    out = OUT / manifest["output"]
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html, encoding="utf-8")

    if not quiet:
        print(f"✓ {out.relative_to(REPO)}  ({out.stat().st_size/1024:.0f} KB)")
        print(f"  {len(manifest['games'])} games · {len(decks)} decks · {len(ids)} scored cards")
    return 0


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
            for i, s in enumerate([exam["status"], *exam["stats"]])
        )
        href = escape(exam["href"])
        return (
            f'    <a class="app brutal-heavy brutal-shadow-lg brutal-hover-lg" '
            f'style="--tone:{tone}" href="{href}">\n'
            f'      <span class="badge">Exam</span>\n'
            f'      <div>\n'
            f'        <p class="code">{code}</p>\n'
            f'        <h2>{title}</h2>\n'
            f'        <p>{subtitle}</p>\n'
            f'      </div>\n'
            f'      <div>\n'
            f'        <div class="stats">{stats}</div>\n'
            f'        <span class="go">Open the lab <span class="arrow">&rarr;</span></span>\n'
            f'      </div>\n'
            f'    </a>'
        )
    soon = escape(exam.get("soon", "Not built yet."))
    return (
        f'    <div class="app brutal-heavy brutal-shadow-lg soon" style="--tone:{tone}">\n'
        f'      <span class="badge">Coming soon</span>\n'
        f'      <div>\n'
        f'        <p class="code">{code}</p>\n'
        f'        <h2>{title}</h2>\n'
        f'        <p>{subtitle}</p>\n'
        f'      </div>\n'
        f'      <p class="soon-note">{soon}</p>\n'
        f'    </div>'
    )


def build_container(container_id: str, template: str, quiet: bool = False) -> int:
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
                for field in ("href", "status", "stats"):
                    if not exam.get(field):
                        errors.append(f"exam '{exam.get('title')}': enabled exam missing {field}")
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

    out = OUT / manifest["output"]
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html_out, encoding="utf-8")

    if not quiet:
        print(f"✓ {out.relative_to(REPO)}  ({out.stat().st_size/1024:.0f} KB)")
        print(f"  {len(manifest['exams'])} exam(s)")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("lab", nargs="?", help="lab id (a file in data/labs/)")
    ap.add_argument("--all", action="store_true", help="build every lab")
    args = ap.parse_args()

    template = TEMPLATE.read_text(encoding="utf-8")
    for ph in ("__LAB_TITLE__", "/*__LAB__*/", "/*__DECKS__*/", "/*__AI_LOGOS__*/"):
        if ph not in template:
            raise SystemExit(f"placeholder {ph} not found in {TEMPLATE.name}")
    adapters = registry_keys(template)

    if args.all:
        rc = 0
        for path in sorted(LABS.glob("*.json")):
            rc |= build(path.stem, template, adapters)
        container_template = CONTAINER_TEMPLATE.read_text(encoding="utf-8")
        for ph in ("__CONTAINER_TITLE__", "__CONTAINER_SUBTITLE__", "<!--__EXAM_CARDS__-->"):
            if ph not in container_template:
                raise SystemExit(f"placeholder {ph} not found in {CONTAINER_TEMPLATE.name}")
        for path in sorted(CONTAINERS.glob("*.json")):
            rc |= build_container(path.stem, container_template)
        return rc
    if not args.lab:
        ap.error("give a lab id, or --all")
    return build(args.lab, template, adapters)


if __name__ == "__main__":
    sys.exit(main())
