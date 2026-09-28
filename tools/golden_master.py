#!/usr/bin/env python3
"""Golden-master regression for the built labs.

    python3 tools/golden_master.py --record     # snapshot the current build
    python3 tools/golden_master.py --check      # fail if any byte moved

Harness work — a new validator, a shared-engine change, a refactor of
build_lab.py — touches code that every already-shipped lab runs through. The
labs are the product; the harness is not. So the contract is: a harness change
must leave every previously shipped lab **byte-identical** unless the change is
explicitly about that lab's content.

This builds every lab and container into a throwaway directory and compares a
sha256 per output file against tools/golden/master.json. It never writes to the
real site output, so it is safe to run at any point.

The build is a deploy build (LAB_OUT is set), which means build_lab.py insists
on an index.html to bundle-check against; that file is hand-maintained in the
site's gamification/ in this repo and is not produced here. INDEX_HTML points at
it — by default this repo's gamification/index.html.

Re-record only when a diff is intended, and say so in the commit message.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
BASELINE = REPO / "tools" / "golden" / "master.json"
DEFAULT_INDEX = REPO / "gamification" / "index.html"


def build_snapshot(out_dir: Path) -> dict[str, str]:
    """Build every lab + container into out_dir; return {relpath: sha256}."""
    index_html = Path(os.environ.get("INDEX_HTML") or DEFAULT_INDEX)
    if not index_html.is_file():
        raise SystemExit(
            f"golden master: index.html not found at {index_html}\n"
            "The build's bundle-sync gate needs the hand-maintained landing page. "
            "Point INDEX_HTML at your site clone's gamification/index.html."
        )

    env = {**os.environ, "LAB_OUT": str(out_dir), "INDEX_HTML": str(index_html)}
    proc = subprocess.run(
        [sys.executable, str(REPO / "tools" / "build_lab.py"), "--all"],
        cwd=REPO, env=env, capture_output=True, text=True,
    )
    if proc.returncode != 0:
        sys.stderr.write(proc.stdout)
        sys.stderr.write(proc.stderr)
        raise SystemExit("golden master: build failed — fix the build before comparing bytes")

    snapshot: dict[str, str] = {}
    for path in sorted(out_dir.rglob("*")):
        if not path.is_file():
            continue
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        snapshot[str(path.relative_to(out_dir))] = digest
    if not snapshot:
        raise SystemExit("golden master: the build produced no files")
    return snapshot


def record() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        snapshot = build_snapshot(Path(tmp))
    BASELINE.parent.mkdir(parents=True, exist_ok=True)
    BASELINE.write_text(json.dumps(snapshot, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    print(f"✓ recorded {len(snapshot)} file(s) → {BASELINE.relative_to(REPO)}")
    return 0


def check() -> int:
    if not BASELINE.is_file():
        raise SystemExit(
            f"golden master: no baseline at {BASELINE.relative_to(REPO)} — "
            "run `python3 tools/golden_master.py --record` on a known-good tree first"
        )
    baseline = json.loads(BASELINE.read_text(encoding="utf-8"))
    with tempfile.TemporaryDirectory() as tmp:
        snapshot = build_snapshot(Path(tmp))

    added = sorted(set(snapshot) - set(baseline))
    removed = sorted(set(baseline) - set(snapshot))
    changed = sorted(k for k in set(baseline) & set(snapshot) if baseline[k] != snapshot[k])

    if not (added or removed or changed):
        print(f"✓ golden master clean — {len(snapshot)} file(s) byte-identical")
        return 0

    print(f"GOLDEN MASTER FAILED — {len(changed)} changed, {len(added)} added, "
          f"{len(removed)} removed:", file=sys.stderr)
    for k in changed:
        print(f"  ✗ changed: {k}", file=sys.stderr)
    for k in added:
        print(f"  + added:   {k}", file=sys.stderr)
    for k in removed:
        print(f"  - removed: {k}", file=sys.stderr)
    print("\nIf the diff is intended, re-record with --record and say so in the commit.",
          file=sys.stderr)
    return 1


def main() -> int:
    ap = argparse.ArgumentParser()
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument("--record", action="store_true", help="snapshot the current build as the baseline")
    mode.add_argument("--check", action="store_true", help="fail if any built byte differs from the baseline")
    args = ap.parse_args()
    return record() if args.record else check()


if __name__ == "__main__":
    sys.exit(main())
