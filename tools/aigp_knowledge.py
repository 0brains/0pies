#!/usr/bin/env python3
"""AIGP knowledge file: projection and validation.

The AIGP knowledge file is typed data, not a generic deck, so it needs
preparation and checks that the generic deck validator knows nothing about.
This module is what build_lab.py calls for it.

Lifted verbatim out of the former build_aigp_game.py when the labs moved onto
the shared engine. The projection constants in particular were fitted by
hit-testing the SVG geometry and must not be re-derived casually — see the
comment below.
"""

from __future__ import annotations

import math
import re

# Projection for the world map (Wikimedia "Simplified World Map", viewBox
# 1016.371 x 514.609, trimmed exactly to the land bounding box).
#
# Longitude is linear and fits to under 4px across the whole width. The map is
# cut at about 170W rather than the antimeridian, which keeps Chukotka whole --
# hence the x offset.
#
# Latitude is NOT linear: vertical scale grows toward the poles, and a Miller
# fit matches it best. The constants below were fitted by hit-testing the SVG
# geometry itself — finding the southernmost land at longitudes whose southern
# extreme is unambiguous (Cape Agulhas, Tasmania, Cape Horn, NZ South Island)
# plus Cape Comorin — rather than by eyeballing landmarks. Max residual is 3.2
# units of 514.6, or 0.62% of board height.
#
# Fitting on northern landmarks alone gave A=299.81 B=139.47, which looked
# plausible but put Australia 8% of the board too far north. Polar islands are
# easy to misidentify on a simplified map; southern continental tips are not.
MAP_W, MAP_H = 1016.371, 514.609
LON_SCALE = MAP_W / 360.0          # px per degree of longitude
LON_OFFSET = -27.93                # map is cut near 170W, not 180
MILLER_A, MILLER_B = 326.46, 173.67


def miller(lat_deg: float) -> float:
    return 1.25 * math.asinh(math.tan(0.8 * math.radians(lat_deg)))


def project(lat: float, lon: float) -> tuple[float, float]:
    """lat/lon -> percentage position on the map board."""
    x = (lon + 180.0) * LON_SCALE + LON_OFFSET
    x %= MAP_W
    y = MILLER_A - MILLER_B * miller(lat)
    return round(x / MAP_W * 100, 3), round(y / MAP_H * 100, 3)

def collect_ids(d: dict) -> list[str]:
    """Every scored/keyed id a typed knowledge file contributes.

    Shared between validate()'s own within-file duplicate check and
    build_lab.py's cross-file collision pass, so the list of collections
    stays in exactly one place.
    """
    map_ = d.get("map") or {}
    role_matrix = d.get("roleMatrix") or {}
    timeline = d.get("timeline") or {}
    campaign = d.get("campaign") or {}
    return ([t["id"] for t in d.get("tells", [])] +
            [c["id"] for c in campaign.get("cards", [])] +
            [e["id"] for e in campaign.get("events", [])] +
            [p["id"] for p in d.get("pairs", [])] +
            [l["id"] for l in d.get("ladders", [])] +
            [c["id"] for c in d.get("cases", [])] +
            [b["id"] for b in d.get("briefs", [])] +
            [g["id"] for g in d.get("amendmentsGrid", [])] +
            [m["id"] for m in timeline.get("milestones", [])] +
            [j["id"] for j in map_.get("jurisdictions", [])] +
            [s["id"] for s in role_matrix.get("sets", [])])


# --- Regulatory Risk campaign section ---------------------------------------
# Only the AIGP domain-ii file carries a top-level "campaign"; every other file
# routed through this module (including the Legislation Lab's data) simply has
# no such key, so this whole branch is a no-op for them.

_RR_ID = re.compile(r"^ii-rr-[a-z0-9-]+$")
_RR_EV_ID = re.compile(r"^ii-rr-ev-[a-z0-9-]+$")
_RR_CARD_KINDS = {"gate", "defend", "consolidate", "check", "sweep"}
_RR_EVENT_TYPES = {"audit", "check", "roleShift", "info"}
_RR_UNLOCK_FORMS = ("start", "holdsAtLeast", "requiresHeld", "requiresAnyHeld")
_RR_BANNED_RE = re.compile(r"Set-\d+-Q\d+")  # ids of this shape may never appear in public data
_RR_AIDA_ALIVE = re.compile(r"\b(pending|tabled|proposed|before parliament|awaiting|expected to pass)\b", re.I)
_RR_AIDA_DEAD = re.compile(r"\b(dead|died|abandon\w*|defunct|never revived|scrap\w*|withdraw\w*|lapsed)\b", re.I)
_RR_EO_2023 = re.compile(r"\b(EO\s*14110|Executive Order 14110|2023 (AI )?executive order)\b", re.I)
_RR_EO_GONE = re.compile(r"\b(rescind\w*|revok\w*)\b", re.I)
_RR_STOPWORDS = {
    "about", "above", "after", "again", "against", "among", "annual", "answer",
    "based", "because", "before", "being", "below", "between", "carried",
    "companies", "company", "could", "under", "duties", "during", "every",
    "first", "following", "framework", "governance", "which", "while", "there",
    "their", "these", "those", "through", "requirements", "rules", "shall",
    "should", "state", "states", "still", "system", "systems", "would", "where",
    "other", "national", "market", "within", "without",
}


def _rr_strings(obj) -> list[str]:
    """Every string value reachable from obj (for the banned-content scans)."""
    if isinstance(obj, str):
        return [obj]
    if isinstance(obj, dict):
        return [s for v in obj.values() for s in _rr_strings(v)]
    if isinstance(obj, list):
        return [s for v in obj for s in _rr_strings(v)]
    return []


def _rr_banned(obj, where: str, errors: list[str]) -> None:
    for text in _rr_strings(obj):
        m = _RR_BANNED_RE.search(text)
        if m:
            errors.append(f"{where}: id pattern {m.group()!r} is not allowed in public data")
        if "AIDA" in text and _RR_AIDA_ALIVE.search(text) and not _RR_AIDA_DEAD.search(text):
            errors.append(f"{where}: AIDA framed as pending/current — it died in January 2025")
        if _RR_EO_2023.search(text) and not _RR_EO_GONE.search(text):
            errors.append(f"{where}: 2023 AI Executive Order cited without noting it was rescinded")


def _validate_campaign(camp: dict, map_: dict) -> list[str]:
    errors: list[str] = []
    jurisdictions = map_.get("jurisdictions", [])
    map_ids = {j["id"] for j in jurisdictions}
    coverage = {j["id"]: j.get("coverage") for j in jurisdictions}
    config = camp.get("config") or {}
    tiers = config.get("tiers") or {}
    op_ids = {o["id"] for o in camp.get("operations", [])}

    # territories: one entry per map jurisdiction, exactly one unlock form each
    terrs = camp.get("territories", [])
    if len(terrs) != 22:
        errors.append(f"campaign: {len(terrs)} territories, must be exactly 22")
    seen: set[str] = set()
    for t in terrs:
        mid = t.get("mapId", "?")
        where = f"campaign.territories[{mid}]"
        if mid not in map_ids:
            errors.append(f"{where}: mapId not in map.jurisdictions")
        elif mid in seen:
            errors.append(f"{where}: duplicate territory entry")
        else:
            seen.add(mid)
            tier = coverage.get(mid)
            if tier not in tiers:
                errors.append(f"{where}: map coverage '{tier}' has no config.tiers entry")
        unlock = t.get("unlock") or {}
        forms = [k for k in unlock if k in _RR_UNLOCK_FORMS]
        if len(forms) != 1 or len(unlock) != 1:
            errors.append(f"{where}: unlock must carry exactly one of {_RR_UNLOCK_FORMS}")
        for h in t.get("opsHooks", []):
            if h not in op_ids:
                errors.append(f"{where}: opsHook '{h}' not a declared operation")
    missing = map_ids - seen
    if terrs and missing:
        errors.append(f"campaign: map jurisdictions with no territory entry: {sorted(missing)}")

    # cards
    cards = camp.get("cards", [])
    card_kind: dict[str, str] = {}
    facts_seen: set[tuple[str, str]] = set()
    for c in cards:
        cid = c.get("id", "?")
        if not _RR_ID.match(cid):
            errors.append(f"{cid}: card id must match ^ii-rr-[a-z0-9-]+$")
        if cid.endswith("-map"):
            errors.append(f"{cid}: card id must not end in -map (legacy scheduler key clash)")
        kind = c.get("kind")
        card_kind[cid] = kind
        if kind not in _RR_CARD_KINDS:
            errors.append(f"{cid}: kind '{kind}' not in {sorted(_RR_CARD_KINDS)}")
        terr = c.get("territory")
        if terr != "any" and terr not in map_ids:
            errors.append(f"{cid}: territory '{terr}' is neither 'any' nor a map id")
        fact = c.get("fact")
        if not fact:
            errors.append(f"{cid}: missing fact slug")
        elif (terr, fact) in facts_seen:
            errors.append(f"{cid}: fact '{fact}' duplicated within territory {terr}")
        else:
            facts_seen.add((terr, fact))
        if not c.get("citation"):
            errors.append(f"{cid}: missing citation")
        if not c.get("asOf"):
            errors.append(f"{cid}: missing asOf")
        options = c.get("options", [])
        answer = c.get("answer")
        if not isinstance(answer, str) or options.count(answer) != 1:
            errors.append(f"{cid}: answer must exactly match one option")
        if kind == "gate":
            if len(options) < 4:
                errors.append(f"{cid}: gate card has {len(options)} options, minimum 4")
        elif not 3 <= len(options) <= 4:
            errors.append(f"{cid}: {len(options)} options, non-gate cards need 3-4")
        roles = c.get("roles")
        if not isinstance(roles, list) or not roles:
            errors.append(f"{cid}: roles must be a non-empty array (['*'] for shared)")
        _rr_banned(c, cid, errors)
        # stem-leak scan: warn only, never an error
        stem = (c.get("q") or "").lower()
        for tok in set(re.findall(r"[a-z]{5,}", (answer or "").lower())):
            if tok not in _RR_STOPWORDS and tok in stem:
                print(f"  leak-warn {cid}: answer token '{tok}' appears in its own stem")

    # events
    defend_terrs = {c.get("territory") for c in cards if c.get("kind") == "defend"}
    for e in camp.get("events", []):
        eid = e.get("id", "?")
        if not _RR_EV_ID.match(eid):
            errors.append(f"{eid}: event id must match ^ii-rr-ev-")
        if not e.get("citation"):
            errors.append(f"{eid}: missing citation")
        if not e.get("asOf"):
            errors.append(f"{eid}: missing asOf")
        eff = e.get("effect") or {}
        etype = eff.get("type")
        if etype not in _RR_EVENT_TYPES:
            errors.append(f"{eid}: effect.type '{etype}' not in {sorted(_RR_EVENT_TYPES)}")
        if etype == "audit":
            terr = eff.get("territory")
            if terr != "match" and terr not in map_ids:
                errors.append(f"{eid}: audit territory must be 'match' or a map id")
            elif terr != "match" and cards and terr not in defend_terrs:
                errors.append(f"{eid}: audit territory {terr} has no defend cards")
        if etype == "check":
            refs = [eff["cardId"]] if eff.get("cardId") else list(eff.get("cardPool", []))
            if not refs:
                errors.append(f"{eid}: check event needs cardId or cardPool")
            for ref in refs:
                if card_kind.get(ref) not in ("check", "sweep"):
                    errors.append(f"{eid}: '{ref}' does not resolve to a check|sweep card")
        _rr_banned(e, eid, errors)

    # per-territory fact slug emission (human dedup review reads this)
    if cards:
        by_terr: dict[str, list[str]] = {}
        for terr, fact in sorted(facts_seen):
            by_terr.setdefault(str(terr), []).append(str(fact))
        for terr, facts in sorted(by_terr.items()):
            print(f"  rr-facts {terr}: {', '.join(facts)}")

    return errors


def validate(d: dict, indicators: set[str] | None = None) -> list[str]:
    """Validate a typed AIGP knowledge file.

    Every collection is optional: a partial file (e.g. a domain carrying only
    `cases` and `briefs`) validates cleanly as long as its own collections are
    internally consistent and it covers every BoK area handed to it via
    `indicators`.
    """
    errors: list[str] = []

    def need(obj, field, where):
        if not obj.get(field):
            errors.append(f"{where}: missing {field}")

    tells = d.get("tells", [])
    pairs = d.get("pairs", [])
    ladders = d.get("ladders", [])
    cases = d.get("cases", [])
    briefs = d.get("briefs", [])
    amendments_grid = d.get("amendmentsGrid", [])
    timeline = d.get("timeline") or {}
    milestones = timeline.get("milestones", [])
    map_ = d.get("map") or {}
    jurisdictions = map_.get("jurisdictions", [])
    role_matrix = d.get("roleMatrix") or {}
    role_sets = role_matrix.get("sets", [])

    for t in tells:
        need(t, "citation", t["id"]); need(t, "asOf", t["id"])
        need(t, "tell", t["id"])
        if t["answer"] not in t["options"]:
            errors.append(f"{t['id']}: answer not among options")
        if len(t["options"]) < 3:
            errors.append(f"{t['id']}: fewer than 3 options")

    for p in pairs:
        need(p, "citation", p["id"]); need(p, "asOf", p["id"])
        need(p, "dimension", p["id"])
        a, b = p["a"], p["b"]
        if a["answer"] == b["answer"]:
            errors.append(f"{p['id']}: degenerate pair — both variants answer "
                          f"'{a['answer']}', so nothing is being contrasted")
        for side in ("a", "b"):
            if p[side]["answer"] not in p["buckets"]:
                errors.append(f"{p['id']}.{side}: answer not among buckets")
            if not p[side].get("why"):
                errors.append(f"{p['id']}.{side}: missing why")
        if p.get("status") == "superseded" and not p.get("currency"):
            errors.append(f"{p['id']}: marked superseded but carries no currency note")

    for lad in ladders:
        need(lad, "citation", lad["id"]); need(lad, "asOf", lad["id"])
        if len(lad["steps"]) < 3:
            errors.append(f"{lad['id']}: fewer than 3 steps")
        if lad.get("dualTrack"):
            for s in lad["steps"]:
                if not s.get("date") or not s.get("amended"):
                    errors.append(f"{lad['id']}: dual-track step '{s['label']}' "
                                  f"needs both date and amended")

    for m in milestones:
        need(m, "date", m["id"]); need(m, "note", m["id"])
        if m["bucket"] not in timeline.get("buckets", []):
            errors.append(f"{m['id']}: bucket '{m['bucket']}' not in the bucket list")
        if m.get("scope") not in ("bok", "horizon"):
            errors.append(f"{m['id']}: scope must be bok or horizon")

    for j in jurisdictions:
        need(j, "tell", j["id"]); need(j, "effective", j["id"]); need(j, "short", j["id"])
        if not j.get("instruments"):
            errors.append(f"{j['id']}: no instruments")
        if not (-90 <= j.get("lat", 999) <= 90) or not (-180 <= j.get("lon", 999) <= 180):
            errors.append(f"{j['id']}: lat/lon missing or out of range")
        else:
            x, y = project(j["lat"], j["lon"])
            if not (0 <= x <= 100 and 0 <= y <= 100):
                errors.append(f"{j['id']}: projects to {x},{y} — outside the map")
        if j["coverage"] not in {l["key"] for l in map_.get("legend", [])}:
            errors.append(f"{j['id']}: coverage '{j['coverage']}' not in legend")

    for s in role_sets:
        need(s, "citation", s["id"])
        if s.get("obligations"):
            ids = {r["id"] for r in s["roles"]}
            for o in s["obligations"]:
                if o["role"] not in ids:
                    errors.append(f"{s['id']}: obligation references unknown role '{o['role']}'")
            unused = ids - {o["role"] for o in s["obligations"]}
            if unused:
                errors.append(f"{s['id']}: roles with no obligations: {sorted(unused)}")
        elif s.get("items"):
            for i, it in enumerate(s["items"]):
                if it["answer"] not in s["buckets"]:
                    errors.append(f"{s['id']} item {i}: answer not among buckets")
                if not it.get("why"):
                    errors.append(f"{s['id']} item {i}: missing why")
        else:
            errors.append(f"{s['id']}: neither obligations nor items")

    for c in cases:
        need(c, "citation", c["id"]); need(c, "asOf", c["id"]); need(c, "brief", c["id"])
        if len(c["steps"]) < 2:
            errors.append(f"{c['id']}: a case file needs at least 2 chained steps")
        for i, s in enumerate(c["steps"]):
            if s["answer"] not in s["options"]:
                errors.append(f"{c['id']} step {i}: answer not among options")
            if not s.get("why"):
                errors.append(f"{c['id']} step {i}: missing why")

    for b in briefs:
        need(b, "scenario", b["id"]); need(b, "asOf", b["id"])
        if len(b["rubric"]) < 4:
            errors.append(f"{b['id']}: rubric has {len(b['rubric'])} criteria, minimum is 4")
        if len(b["fields"]) < 3:
            errors.append(f"{b['id']}: fewer than 3 response fields")
        for r in b["rubric"]:
            if not r.get("citation"):
                errors.append(f"{b['id']}: rubric criterion '{r['criterion']}' has no citation")
        words = len(b["scenario"].split())
        if words < 120:
            errors.append(f"{b['id']}: scenario is {words} words; a brief needs a real fact pattern")
        if b.get("status") == "superseded" and not b.get("currency"):
            errors.append(f"{b['id']}: marked superseded but carries no currency note")

    for g in amendments_grid:
        need(g, "domain", g["id"])
        for side in ("original", "updated"):
            v = g.get(side, {})
            if not v.get("text"):
                errors.append(f"{g['id']}.{side}: missing text")
            if not v.get("citation"):
                errors.append(f"{g['id']}.{side}: missing citation")
        if g.get("original", {}).get("text") == g.get("updated", {}).get("text"):
            errors.append(f"{g['id']}: original and updated text are identical — nothing to contrast")

    if "campaign" in d:
        errors += _validate_campaign(d["campaign"], map_)

    if "amendmentsGrid" in d and len(amendments_grid) != 9:
        errors.append(f"amendmentsGrid has {len(amendments_grid)} entries; the grid3x3 runner requires exactly 9")

    # Coverage: every area handed to this file must be reachable from at
    # least one card. Cards are tagged to area, not indicator, and a card can
    # come from any collection that carries an 'area' tag.
    covered = ({t["area"] for t in tells} |
               {p["area"] for p in pairs} |
               {a for c in cases for a in c.get("areas", [])} |
               {b["area"] for b in briefs if b.get("area")} |
               {s["area"] for s in role_sets if s.get("area")})
    for area in (indicators or set()):
        if area not in covered:
            errors.append(f"coverage: area {area} has no tell, pair, case, brief, "
                          f"or role-set card")

    ids = collect_ids(d)
    dupes = {i for i in ids if ids.count(i) > 1}
    if dupes:
        errors.append(f"duplicate ids: {sorted(dupes)}")

    return errors


def prepare(d: dict) -> None:
    """Derive every jurisdiction's board position from its real coordinates.

    lat/lon stays the source of truth in the JSON; x/y is derived here so the
    geography can be checked rather than trusted. Without this step the map
    renders with undefined coordinates — which throws no error and looks like
    an empty board, so the build calls it unconditionally. A file with no map
    collection has nothing to derive.
    """
    for j in (d.get("map") or {}).get("jurisdictions", []):
        j["x"], j["y"] = project(j["lat"], j["lon"])
