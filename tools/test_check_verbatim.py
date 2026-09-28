#!/usr/bin/env python3
"""Tests for tools/check_verbatim.py — the verbatim-similarity guard.

Run: cd tools && python3 -m pytest test_check_verbatim.py -q
"""
import check_verbatim


def test_long_shared_run_is_flagged():
    src = "the recovery time objective is the maximum tolerable time to restore a system after failure"
    card = "Remember: the recovery time objective is the maximum tolerable time to restore a system, so plan for it."
    assert check_verbatim.shared_run(card, [src], n=8)


def test_taxonomy_names_and_short_overlap_pass():
    src = "Broken Access Control means users act outside their intended permissions"
    card = "A junior admin edits payroll records their role never granted. Category: Broken Access Control."
    assert not check_verbatim.shared_run(card, [src], n=8)


def test_cache_is_not_keyed_by_object_id():
    """Regression for a stale-cache bug: keying `_NGRAM_CACHE` by id(sources)
    let Python's id reuse after garbage collection return a hit built from an
    unrelated, already-freed source list. A fresh list (even one that lands
    on a reused id) must be judged on its own content, never a prior list's.
    """
    hit_src = "the recovery time objective is the maximum tolerable time to restore a system after failure"
    card = "Remember: the recovery time objective is the maximum tolerable time to restore a system, so plan for it."

    # Warm the cache with a source list that DOES contain the shared run,
    # then let it go out of scope so its id is eligible for reuse.
    first_sources = [hit_src]
    assert check_verbatim.shared_run(card, first_sources, n=8)
    first_id = id(first_sources)
    del first_sources

    # Build fresh, unrelated source lists until one happens to land on the
    # freed id (CPython commonly reuses it immediately; looping makes the
    # test robust across implementations/allocators that don't).
    unrelated_src = "a completely different sentence about firewalls and access review logs entirely"
    found_reused_id = False
    for _ in range(1000):
        fresh_sources = [unrelated_src]
        if id(fresh_sources) == first_id:
            found_reused_id = True
        # Regardless of id reuse, content-keyed caching must judge this list
        # on its own text: it does not contain the RTO run, so no hit.
        assert check_verbatim.shared_run(card, fresh_sources, n=8) is None
        del fresh_sources

    # Not asserted as a hard requirement (id reuse is a CPython implementation
    # detail), but recorded so a future reader can see the repro shape landed.
    _ = found_reused_id
