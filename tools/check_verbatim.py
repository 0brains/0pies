#!/usr/bin/env python3
"""Verbatim-similarity guard for authored gameset decks.

The project's #1 content constraint is that authored deck text must never
share a long verbatim run with source material (a lab's question bank or
study notes) — cards are freshly authored,
citing sources for *concept* provenance only, never copying their prose.

This is the machine guard for that constraint: it walks every string in a
deck JSON, tokenizes it, and flags any card string that shares a >= n-token
(default 8) contiguous run with any source text. Short overlaps are fine —
taxonomy names ("Broken Access Control"), domain terms, etc. legitimately
repeat between cards and sources; the n=8 threshold is chosen so those pass
while lifted sentences do not.

Usage:
    python3 tools/check_verbatim.py <deck.json> [<deck.json> ...]
    python3 tools/check_verbatim.py <deck.json> --sources <file_or_dir> [...]

With no --sources, defaults to the CISSP lab's private source set
(DEFAULT_SOURCE_IDS). Private sources are not in this public repo: a source
ref of the form "private:<lab>/<name>" is resolved through the mapping file
site-sources.json at SOURCES_ROOT (default: the sibling private checkout,
../ExamSimulator). SKIP_VERBATIM=1 lets a build without that checkout run,
loudly, with the guard off.

Exit 0 if clean, exit 1 printing one line per hit:
    <deck-id> <card-path>: "<matched run>"
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

PRIVATE_PREFIX = "private:"
SOURCE_MAP_NAME = "site-sources.json"
# The CISSP lab's source set: its question bank, the domain study notes, and
# the taxonomy sources the decks cite for concept provenance (OWASP Top 10
# 2025, MITRE ATT&CK tactics). Taxonomy *names* sit under the 8-token
# threshold, so guarding against them costs nothing legitimate while catching
# a lifted definition sentence.
DEFAULT_SOURCE_IDS = (
    "private:cissp/question-bank",
    "private:cissp/study-notes",
    "private:cissp/owasp-top10",
    "private:cissp/mitre-attack",
)


def sources_root() -> Path:
    return Path(os.environ.get("SOURCES_ROOT") or REPO.parent / "ExamSimulator")


def verbatim_skipped() -> bool:
    return os.environ.get("SKIP_VERBATIM") == "1"


def resolve_source(ref: str) -> Path | None:
    """Repo-relative path for a public ref; mapped path for a private one.

    Returns None when a private ref cannot be mapped (no SOURCES_ROOT checkout,
    or no entry for it) — callers turn that into a build error.
    """
    if not ref.startswith(PRIVATE_PREFIX):
        return REPO / ref
    root = sources_root()
    mapping = root / SOURCE_MAP_NAME
    if not mapping.exists():
        return None
    rel = json.loads(mapping.read_text(encoding="utf-8")).get("sources", {}).get(ref)
    return root / rel if rel else None


_TOKEN_RE = re.compile(r"[a-z0-9]+")


def tokenize(text: str) -> list[str]:
    """Lowercase and strip punctuation, tokenizing on whitespace/word chars."""
    return _TOKEN_RE.findall(text.lower())


def ngrams(tokens: list[str], n: int) -> set[tuple[str, ...]]:
    if len(tokens) < n:
        return set()
    return {tuple(tokens[i : i + n]) for i in range(len(tokens) - n + 1)}


def walk_strings(obj, path: str = "$"):
    """Yield (path, string) for every string value nested in obj.

    Same walk pattern as build_lab.py's _reject_markup: recurse through
    dicts and lists, yielding every string leaf with its JSON path.
    """
    if isinstance(obj, str):
        yield path, obj
    elif isinstance(obj, dict):
        for k, v in obj.items():
            yield from walk_strings(v, f"{path}.{k}")
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            yield from walk_strings(v, f"{path}[{i}]")


# Module-level cache: build the source n-gram index once per (source text,
# n) pair. Source corpora are ~2MB + dozens of Moore files, and the guard
# runs over every deck in a lab on every build — caching by content avoids
# re-tokenizing the same source strings every call.
#
# Keyed on a content hash of the joined source texts, NOT id(sources): a
# caller that builds a fresh sources list per call (e.g. build_lab.py, which
# assembles a per-lab source list rather than the long-lived list this CLI
# builds once) can have Python reuse an object id after the previous list is
# garbage-collected, which would silently return a stale cache entry built
# from unrelated source content. Hashing the actual text is the only key
# that can't alias across distinct source lists.
#
# The index is ONE flat set of hashed n-grams across all sources, not a set
# per source. Per-source sets meant every deck string paid an intersection
# against each of ~20k corpus strings — 94 seconds for the CISSP decks,
# which is why the guard was a tool you ran by hand instead of a build step.
# Flattened, each deck string costs one pass over its own n-grams. Hashing
# the tuples rather than storing them keeps the index around 25 MB instead
# of ~100 MB; the matched run is reconstructed from the *deck* tokens on a
# hit, so nothing is lost by not keeping the source tuples.
_NGRAM_CACHE: dict[tuple[str, int], frozenset[int]] = {}


def _sources_key(sources: list[str]) -> str:
    h = hashlib.sha256()
    for s in sources:
        h.update(s.encode("utf-8", "surrogatepass"))
        h.update(b"\x00")
    return h.hexdigest()


def source_index(sources: list[str], n: int = 8) -> frozenset[int]:
    """Hashed n-grams of every source text, flattened into one set.

    Build this ONCE per source set and hand it to shared_run: the content-hash
    cache below still guards against stale reuse, but computing that key means
    sha256 over the whole corpus, so paying it per card string is its own
    performance bug.
    """
    key = (_sources_key(sources), n)
    cached = _NGRAM_CACHE.get(key)
    if cached is not None:
        return cached
    index: set[int] = set()
    for s in sources:
        tokens = tokenize(s)
        for i in range(len(tokens) - n + 1):
            index.add(hash(tuple(tokens[i : i + n])))
    frozen = frozenset(index)
    _NGRAM_CACHE[key] = frozen
    return frozen


def shared_run(text: str, sources: list[str] | frozenset[int], n: int = 8) -> str | None:
    """Return the first n-token run in `text` that also appears in `sources`.

    `sources` is either a list of source text strings or a prebuilt index from
    source_index(). Returns the matched run as a space-joined string, or None
    if no run of length >= n is shared. The run returned is the leftmost one in
    `text`, so the message points at the start of the lifted passage rather
    than an arbitrary point inside it.
    """
    tokens = tokenize(text)
    if len(tokens) < n:
        return None
    index = sources if isinstance(sources, frozenset) else source_index(sources, n)
    for i in range(len(tokens) - n + 1):
        gram = tuple(tokens[i : i + n])
        if hash(gram) in index:
            return " ".join(gram)
    return None


def load_corpus_strings(path: Path) -> list[str]:
    """Extract every string value from a source JSON (e.g. a question bank).

    The relevant source text is every string value in it — question
    stems, choices, reference text — extracted with the same walk used for
    deck strings.
    """
    data = json.loads(path.read_text(encoding="utf-8"))
    return [s for _, s in walk_strings(data)]


def load_moore_strings(moore_dir: Path) -> list[str]:
    """Return the full text of every .md file under moore_dir, recursively."""
    return [p.read_text(encoding="utf-8") for p in sorted(moore_dir.rglob("*.md"))]


def default_sources() -> list[str]:
    paths = [resolve_source(ref) for ref in DEFAULT_SOURCE_IDS]
    return load_sources([str(p) for p in paths if p is not None and p.exists()])


def load_sources(paths: list[str]) -> list[str]:
    """Load source text from an explicit list of files/dirs (--sources)."""
    sources: list[str] = []
    for raw in paths:
        p = Path(raw)
        if p.is_dir():
            sources.extend(load_moore_strings(p))
        elif p.suffix == ".json":
            sources.extend(load_corpus_strings(p))
        else:
            sources.append(p.read_text(encoding="utf-8"))
    return sources


def check_deck(deck_path: Path, sources: list[str] | frozenset[int],
               n: int = 8) -> list[tuple[str, str, str]]:
    """Return a list of (deck-id, card-path, matched-run) hits for one deck."""
    data = json.loads(deck_path.read_text(encoding="utf-8"))
    deck_id = data.get("id", deck_path.stem) if isinstance(data, dict) else deck_path.stem
    return check_data(data, deck_id, sources, n=n)


def check_data(data, deck_id: str, sources: list[str] | frozenset[int],
               n: int = 8) -> list[tuple[str, str, str]]:
    """Same check against already-loaded deck data.

    build_lab.py has every deck in memory by the time the guard runs; re-reading
    them from disk to check them would be the only reason to keep a path.
    """
    index = sources if isinstance(sources, frozenset) else source_index(sources, n)
    hits: list[tuple[str, str, str]] = []
    for path, s in walk_strings(data):
        run = shared_run(s, index, n=n)
        if run:
            hits.append((deck_id, path, run))
    return hits


def main(argv: list[str]) -> int:
    if not argv:
        print("usage: check_verbatim.py <deck.json> [<deck.json> ...] [--sources <file_or_dir> ...]", file=sys.stderr)
        return 2

    deck_args: list[str] = []
    source_args: list[str] = []
    target = deck_args
    for arg in argv:
        if arg == "--sources":
            target = source_args
            continue
        target.append(arg)

    if not deck_args:
        print("usage: check_verbatim.py <deck.json> [<deck.json> ...] [--sources <file_or_dir> ...]", file=sys.stderr)
        return 2

    sources = source_index(load_sources(source_args) if source_args else default_sources())

    exit_code = 0
    for deck_arg in deck_args:
        deck_path = Path(deck_arg)
        hits = check_deck(deck_path, sources)
        for deck_id, path, run in hits:
            print(f'{deck_id} {path}: "{run}"')
            exit_code = 1
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
