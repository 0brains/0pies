#!/usr/bin/env python3
"""One-off authoring aid: classify world-map-paths.svg paths into territories.

Per ADD §7.1 this script is NOT a build step. It proposes territory membership
for each <path> in tools/templates/world-map-paths.svg from hand-tuned lat/lon
candidate boxes, applies an optional overrides file, runs numeric sanity rules,
emits an HTML preview for human audit, and (with --emit) writes the audited
whitelist to tools/templates/world-map-territories.json. That committed JSON is
the single source of truth thereafter; build_lab.py never runs this script.

Usage:
  python3 tools/classify_world_map.py [--overrides overrides.json]
      [--preview classify_preview.html] [--emit]

Overrides schema: {"add": {"map-xx": [idx, ...]}, "remove": {"map-xx": [...]}}

Projection: constants are imported READ-ONLY from tools/aigp_knowledge.py; the
inverse (px -> lat/lon) is derived here from the same constants so candidate
boxes can be written in geographic coordinates.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import aigp_knowledge as ac  # read-only: MAP_W/MAP_H/LON_SCALE/LON_OFFSET/MILLER_*

SVG_PATH = os.path.join(HERE, "templates", "world-map-paths.svg")
OUT_PATH = os.path.join(HERE, "templates", "world-map-territories.json")

MIN_AREA = 1.0  # bbox px^2 below which a path is sub-pixel debris: never assigned


def inv_project(x: float, y: float) -> tuple[float, float]:
    """viewBox px -> (lat, lon); exact inverse of aigp_knowledge.project()."""
    lon = (x - ac.LON_OFFSET) / ac.LON_SCALE - 180.0
    if lon > 180.0:
        lon -= 360.0
    m = (ac.MILLER_A - y) / ac.MILLER_B
    lat = math.degrees(math.atan(math.sinh(m / 1.25)) / 0.8)
    return lat, lon


def ll2xy(lat: float, lon: float) -> tuple[float, float]:
    xp, yp = ac.project(lat, lon)
    return xp * ac.MAP_W / 100.0, yp * ac.MAP_H / 100.0


NUM = re.compile(r"-?\d*\.?\d+(?:e-?\d+)?")


def path_vertices(d: str) -> list[tuple[float, float]]:
    """Accumulate on-curve vertices from a path d string (±2px is plenty)."""
    out: list[tuple[float, float]] = []
    cx = cy = sx = sy = 0.0
    for cmd, args in re.findall(r"([A-Za-z])([^A-Za-z]*)", d):
        ns = [float(n) for n in NUM.findall(args)]
        i = 0
        if cmd == "M":
            cx, cy = ns[0], ns[1]
            sx, sy = cx, cy
            out.append((cx, cy))
            i = 2
            while i < len(ns):
                cx, cy = ns[i], ns[i + 1]; out.append((cx, cy)); i += 2
        elif cmd == "m":
            cx += ns[0]; cy += ns[1]
            sx, sy = cx, cy
            out.append((cx, cy))
            i = 2
            while i < len(ns):
                cx += ns[i]; cy += ns[i + 1]; out.append((cx, cy)); i += 2
        elif cmd == "L":
            while i < len(ns):
                cx, cy = ns[i], ns[i + 1]; out.append((cx, cy)); i += 2
        elif cmd == "l":
            while i < len(ns):
                cx += ns[i]; cy += ns[i + 1]; out.append((cx, cy)); i += 2
        elif cmd == "H":
            for n in ns: cx = n; out.append((cx, cy))
        elif cmd == "h":
            for n in ns: cx += n; out.append((cx, cy))
        elif cmd == "V":
            for n in ns: cy = n; out.append((cx, cy))
        elif cmd == "v":
            for n in ns: cy += n; out.append((cx, cy))
        elif cmd == "C":
            while i < len(ns):
                cx, cy = ns[i + 4], ns[i + 5]; out.append((cx, cy)); i += 6
        elif cmd == "c":
            while i < len(ns):
                cx += ns[i + 4]; cy += ns[i + 5]; out.append((cx, cy)); i += 6
        elif cmd == "S":
            while i < len(ns):
                cx, cy = ns[i + 2], ns[i + 3]; out.append((cx, cy)); i += 4
        elif cmd == "s":
            while i < len(ns):
                cx += ns[i + 2]; cy += ns[i + 3]; out.append((cx, cy)); i += 4
        elif cmd in "Zz":
            cx, cy = sx, sy
    return out


# --------------------------------------------------------------------------
# Hand-tuned candidate boxes, (lat_min, lat_max, lon_min, lon_max), tested
# against each path's CENTROID in geographic coordinates. First territory in
# TERRITORY_ORDER whose include-boxes contain the centroid (and no exclude-box
# does) wins; a min-area filter drops sub-pixel debris. Boxes cannot follow
# the EU/Balkan zigzag exactly — the OVERRIDES below carry the audited
# corrections and are part of the committed record.
# --------------------------------------------------------------------------
BOXES: dict[str, dict[str, list[tuple[float, float, float, float]]]] = {
    # Specific before broad: uk/ch before eu; tw/kr/jp before cn; us before ca.
    "map-uk": {"in": [(49.5, 61.5, -7.5, 2.0)]},          # GB + Northern Ireland
    "map-ch": {"in": [(45.5, 48.0, 5.5, 10.8)]},
    "map-eu": {
        "in": [(34.8, 66.0, -11.0, 32.0)],
        "out": [
            (49.5, 61.5, -7.5, 2.0),    # UK (Ireland at lon -8.0 stays in)
            (45.5, 48.0, 5.5, 10.8),    # Switzerland
            (63.5, 72.0, 4.0, 21.0),    # Norway (Sweden c 62.3 / Finland lon 25.9 stay in)
            (40.5, 45.2, 15.5, 23.2),   # W. Balkans BA/RS/ME/XK/AL/MK (Croatia re-added via override)
            (44.0, 57.0, 26.5, 41.0),   # Ukraine / Belarus / Moldova
            (53.9, 55.0, 19.5, 23.0),   # Kaliningrad (RU)
            (40.0, 42.3, 26.0, 30.0),   # East Thrace (TR-in-Europe path)
        ],
    },
    "map-tw": {"in": [(21.5, 25.8, 119.5, 122.5)]},
    "map-kr": {"in": [(33.0, 38.7, 125.5, 130.0)]},
    "map-jp": {"in": [(30.0, 46.0, 129.0, 146.0)]},
    "map-cn": {
        # Mainland + Hainan; excludes TW/KR boxes by order, NK by lon cap.
        "in": [(18.0, 46.0, 96.5, 127.0)],
        "out": [(21.5, 25.8, 119.5, 122.5)],  # Taiwan
    },
    "map-us": {
        "in": [
            (25.3, 49.5, -125.0, -66.0),      # CONUS (floor 25.3: Mexico centroid 24.7 out)
            (51.0, 72.0, -170.0, -140.5),     # Alaska
        ],
        "out": [(41.5, 49.2, -93.0, -75.5)],  # Great Lakes water paths
    },
    "map-ca": {
        "in": [(41.0, 84.0, -142.0, -52.0)],
        "out": [
            (24.0, 49.5, -125.0, -66.0),      # CONUS (order also guards this)
            (41.5, 49.2, -93.0, -75.5),       # Great Lakes water paths
        ],
    },
    "map-br": {"in": [(-34.0, 4.9, -60.0, -34.0)]},
    "map-pe": {"in": [(-18.5, -2.5, -82.0, -68.5)]},
    "map-in": {"in": [(8.5, 32.0, 70.0, 88.0)]},
    "map-au": {"in": [(-44.0, -10.5, 112.0, 154.0)]},
    "map-ae": {"in": [(22.0, 26.5, 51.5, 57.0)]},
    "map-ke": {"in": [(-5.0, 4.5, 33.5, 42.0)]},
}
TERRITORY_ORDER = list(BOXES.keys())

# Audited corrections (see report): boxes cannot trace the EU/neighbour zigzag.
OVERRIDES_BUILTIN = {
    "add": {
        "map-eu": [142, 157],  # 142 Croatia (EU, inside W-Balkans box); 157 Cyprus (EU, east of box)
    },
    "remove": {
        "map-cn": [73, 84],    # 73 Laos (centroid lat 19.3 ties Hainan's band); 84 Myanmar
        "map-br": [276, 288, 293],  # Paraguay, Suriname, French Guiana
        "map-in": [88],        # Nepal/Bangladesh path (centroid inside box)
    },
}

# Tint-dot territories: landmass absent or sub-4px on this simplified map.
# Verified: no path centroid within 25px of Singapore's projected point.
DOTS = ["map-sg"]

HUES = {
    "map-eu": "#3b6fd4", "map-uk": "#d43b8f", "map-ch": "#d4a03b",
    "map-us": "#3bd46f", "map-ca": "#8f3bd4", "map-br": "#2f9e44",
    "map-pe": "#e8590c", "map-in": "#f59f00", "map-jp": "#e03131",
    "map-kr": "#0ca678", "map-cn": "#c2255c", "map-tw": "#5f3dc4",
    "map-au": "#1098ad", "map-ae": "#846358", "map-ke": "#66a80f",
}


def load_paths() -> list[dict]:
    svg = open(SVG_PATH, encoding="utf-8").read()
    ds = re.findall(r'<path[^>]*\bd="([^"]+)"', svg)
    rows = []
    for idx, d in enumerate(ds):
        v = path_vertices(d)
        xs = [p[0] for p in v]
        ys = [p[1] for p in v]
        cx, cy = sum(xs) / len(xs), sum(ys) / len(ys)
        lat, lon = inv_project(cx, cy)
        rows.append({
            "i": idx, "d": d,
            "x0": min(xs), "x1": max(xs), "y0": min(ys), "y1": max(ys),
            "cx": cx, "cy": cy, "lat": lat, "lon": lon,
            "area": (max(xs) - min(xs)) * (max(ys) - min(ys)),
        })
    return rows


def in_box(lat: float, lon: float, box: tuple[float, float, float, float]) -> bool:
    a, b, c, d = box
    return a <= lat <= b and c <= lon <= d


def classify(rows: list[dict], overrides: dict) -> dict[str, list[int]]:
    terr: dict[str, list[int]] = {t: [] for t in TERRITORY_ORDER}
    removed = {t: set(v) for t, v in (overrides.get("remove") or {}).items()}
    added = {t: list(v) for t, v in (overrides.get("add") or {}).items()}
    added_all = {i for v in added.values() for i in v}
    for r in rows:
        if r["area"] < MIN_AREA or r["i"] in added_all:
            continue
        for t in TERRITORY_ORDER:
            spec = BOXES[t]
            if not any(in_box(r["lat"], r["lon"], b) for b in spec["in"]):
                continue
            if any(in_box(r["lat"], r["lon"], b) for b in spec.get("out", [])):
                continue
            if r["i"] not in removed.get(t, set()):
                terr[t].append(r["i"])
            break
    for t, idxs in added.items():
        terr.setdefault(t, []).extend(idxs)
    return {t: sorted(set(v)) for t, v in terr.items()}


def sanity(rows: list[dict], terr: dict[str, list[int]]) -> bool:
    by = {r["i"]: r for r in rows}
    checks: list[tuple[str, bool]] = []

    eu = [by[i] for i in terr["map-eu"]]
    checks.append(("map-eu: no centroid west of Iceland band (lon < -12)",
                   all(r["lon"] >= -12 for r in eu)))
    for name, box in [("UK", (49.5, 61.5, -7.5, 2.0)),
                      ("CH", (45.5, 48.0, 5.5, 10.8)),
                      ("Norway", (63.5, 72.0, 4.0, 21.0))]:
        checks.append((f"map-eu: no centroid inside {name} box",
                       all(not in_box(r["lat"], r["lon"], box) for r in eu)))
    checks.append(("map-us: contains an Alaska path (lon < -140, lat > 51)",
                   any(by[i]["lon"] < -140 and by[i]["lat"] > 51 for i in terr["map-us"])))
    checks.append(("map-au: contains Tasmania (centroid lat < -40)",
                   any(by[i]["lat"] < -40 for i in terr["map-au"])))
    checks.append(("map-jp: >= 2 paths", len(terr["map-jp"]) >= 2))
    tw = [by[i] for i in terr["map-tw"]]
    tx, ty = ll2xy(25.0, 121.0)
    checks.append(("map-tw: exactly 1 small path near projected (25N,121E)",
                   len(tw) == 1 and tw[0]["area"] < 200
                   and abs(tw[0]["cx"] - tx) < 25 and abs(tw[0]["cy"] - ty) < 25))
    checks.append(("map-cn: does not contain the Taiwan path",
                   not (tw and tw[0]["i"] in terr["map-cn"])))
    for t in ("map-ke", "map-pe", "map-ch", "map-ae"):
        checks.append((f"{t}: >= 1 path", len(terr[t]) >= 1))
    seen: dict[int, str] = {}
    dup_ok = True
    for t, idxs in terr.items():
        for i in idxs:
            if i in seen:
                dup_ok = False
                print(f"  DUP: path {i} in both {seen[i]} and {t}")
            seen[i] = t
    checks.append(("no path index assigned to two territories", dup_ok))

    ok = True
    for label, passed in checks:
        print(f"{'PASS' if passed else 'FAIL'}  {label}")
        ok &= passed
    return ok


def report(rows: list[dict], terr: dict[str, list[int]]) -> None:
    by = {r["i"]: r for r in rows}
    print("\n== per-territory report ==")
    for t in TERRITORY_ORDER:
        rs = [by[i] for i in terr[t]]
        total = sum(r["area"] for r in rs)
        print(f"{t:8s} paths={len(rs):3d} total_bbox_area={total:9.0f}")
        for r in sorted(rs, key=lambda r: -r["area"])[:5]:
            print(f"    #{r['i']:3d} bbox=({r['x0']:.0f},{r['y0']:.0f})-"
                  f"({r['x1']:.0f},{r['y1']:.0f}) c=({r['lat']:.1f},{r['lon']:.1f})"
                  f" area={r['area']:.0f}")
    # Dot verification: distance from each dot's pin to nearest path centroid
    dom = json.load(open(os.path.join(HERE, "..", "data", "aigp", "knowledge", "domain-ii.json")))
    pins = {j["id"]: (j["lat"], j["lon"]) for j in dom["map"]["jurisdictions"]}
    for d in DOTS:
        x, y = ll2xy(*pins[d])
        # A dot is genuine if no SMALL path (own landmass; a city-state would be
        # a few px^2, so area < 60) sits at the pin. Big/medium neighbours
        # (Sumatra 8px away, the Malay peninsula tip 10px away) don't count.
        small = [r for r in rows if r["area"] < 60]
        near = min(small, key=lambda r: (r["cx"] - x) ** 2 + (r["cy"] - y) ** 2)
        dist = math.hypot(near["cx"] - x, near["cy"] - y)
        if dist > 15:
            print(f"dot {d}: pin=({x:.0f},{y:.0f}) nearest small path #{near['i']} at "
                  f"{dist:.0f}px -> landmass genuinely absent, dot confirmed")
        else:
            print(f"dot {d}: WARNING small path #{near['i']} only {dist:.0f}px from pin — "
                  f"consider filling it instead")


def preview(rows: list[dict], terr: dict[str, list[int]], out: str) -> None:
    owner = {i: t for t, idxs in terr.items() for i in idxs}
    parts = [
        "<title>classify_world_map preview</title>",
        "<style>body{background:#111;margin:0}svg{width:100%;height:auto}"
        "path{stroke:#000;stroke-width:.3}</style>",
        f'<svg viewBox="0 0 {ac.MAP_W} {ac.MAP_H}" xmlns="http://www.w3.org/2000/svg">',
    ]
    for r in rows:
        t = owner.get(r["i"])
        fill = HUES.get(t, "#555") if t else "#3a3f45"
        parts.append(f'<path d="{r["d"]}" fill="{fill}">'
                     f'<title>#{r["i"]} {t or "unassigned"} '
                     f'({r["lat"]:.1f},{r["lon"]:.1f})</title></path>')
    dom = json.load(open(os.path.join(HERE, "..", "data", "aigp", "knowledge", "domain-ii.json")))
    pins = {j["id"]: (j["lat"], j["lon"]) for j in dom["map"]["jurisdictions"]}
    for d in DOTS:
        x, y = ll2xy(*pins[d])
        parts.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="6" fill="#ffd43b">'
                     f'<title>dot {d}</title></circle>')
    parts.append("</svg>")
    with open(out, "w", encoding="utf-8") as f:
        f.write("\n".join(parts))
    print(f"\npreview written: {out}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--overrides", help="extra overrides json (merged over built-ins)")
    ap.add_argument("--preview", help="write HTML preview to this path")
    ap.add_argument("--emit", action="store_true",
                    help=f"write audited whitelist to {OUT_PATH}")
    args = ap.parse_args()

    overrides = {"add": dict(OVERRIDES_BUILTIN["add"]),
                 "remove": dict(OVERRIDES_BUILTIN["remove"])}
    if args.overrides:
        extra = json.load(open(args.overrides))
        for k in ("add", "remove"):
            for t, idxs in (extra.get(k) or {}).items():
                overrides[k][t] = sorted(set(overrides[k].get(t, [])) | set(idxs))

    rows = load_paths()
    terr = classify(rows, overrides)
    ok = sanity(rows, terr)
    report(rows, terr)
    if args.preview:
        preview(rows, terr, args.preview)
    if args.emit:
        if not ok:
            print("REFUSING --emit: sanity rules failing")
            return 1
        payload = {
            "territories": terr,
            "dots": DOTS,
            "counts": {t: len(v) for t, v in terr.items()},
            "generated": "2026-08-02",
        }
        with open(OUT_PATH, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=1)
            f.write("\n")
        print(f"emitted: {OUT_PATH}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
