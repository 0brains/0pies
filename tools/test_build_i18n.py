#!/usr/bin/env python3
"""Build-validation tests for the data/i18n/* pipeline in build_lab.py.

Run: python3 -m pytest tools/test_build_i18n.py -v
     (or python3 tools/test_build_i18n.py directly for a plain run)

Covers:
  - load_i18n() end-to-end against the real repo data (must pass clean)
  - validate_index(): key-parity rules for the landing page's idx.* dicts
    (full coverage for es/ar, partial-coverage-allowed for egy/kli)
  - diff_index_bundle(): the index.html bundle-sync check
  - load_index_bundle(): missing file -> None (skip, not error); malformed
    bundle -> SystemExit
  - _reject_markup applies to data/i18n/index/*.json via the normal
    load_json path (a '<' in an index string fails the build)
"""
import copy
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import build_lab


def test_load_i18n_real_data_clean():
    langs, ui, labs_tr, idx, errors = build_lab.load_i18n()
    assert errors == [], errors
    assert "en" in idx
    assert "es" in idx and "ar" in idx
    # egy/kli are landing-page-only jokes: present in data/i18n/index/ but
    # absent from languages.json (they're never a shipped ui/labs locale).
    assert "egy" in idx and "kli" in idx
    assert all(c["code"] != "egy" for c in langs)
    assert all(c["code"] != "kli" for c in langs)


def test_validate_index_clean_data_passes():
    idx = {
        "en": {"a": "1", "b": "2"},
        "es": {"a": "uno", "b": "dos"},
        "egy": {"a": "𓅱"},
    }
    assert build_lab.validate_index(idx, full_coverage={"es"}) == []


def test_validate_index_full_coverage_missing_key_is_blocking():
    idx = {"en": {"a": "1", "b": "2"}, "es": {"a": "uno"}}
    errors = build_lab.validate_index(idx, full_coverage={"es"})
    assert any("missing keys" in e and "es.json" in e for e in errors), errors


def test_validate_index_unknown_key_is_blocking_even_for_partial_coverage():
    # egy/kli are allowed to cover only a subset of en — but never a key
    # en doesn't have at all.
    idx = {"en": {"a": "1"}, "egy": {"a": "𓅱", "ghost": "𓆓"}}
    errors = build_lab.validate_index(idx, full_coverage=set())
    assert any("unknown keys" in e and "egy.json" in e for e in errors), errors


def test_validate_index_partial_coverage_missing_key_is_allowed():
    idx = {"en": {"a": "1", "b": "2"}, "egy": {"a": "𓅱"}}
    assert build_lab.validate_index(idx, full_coverage=set()) == []


def test_validate_index_missing_en_is_blocking():
    errors = build_lab.validate_index({"es": {"a": "uno"}}, full_coverage={"es"})
    assert any("index/en.json: missing" in e for e in errors), errors


def test_reject_markup_applies_to_index_files(tmp_path):
    bad = {"idx.card.aigp.badge": "not <b>allowed</b>"}
    p = tmp_path / "bad.json"
    p.write_text(json.dumps(bad), encoding="utf-8")
    # load_json only applies _reject_markup to paths under DECKS (data/) —
    # exercise the check function directly the way load_json does, since a
    # tmp_path file isn't under data/.
    try:
        build_lab._reject_markup(bad, "bad.json")
        raise AssertionError("expected SystemExit for markup in an index-shaped dict")
    except SystemExit as e:
        assert "markup" in str(e)


def test_reject_markup_applies_via_real_index_dir():
    # The real files must already be clean (this is the same check build()
    # runs); a genuine regression here would mean _reject_markup silently
    # stopped covering data/i18n/index/.
    for p in sorted((build_lab.I18N_DIR / "index").glob("*.json")):
        data = build_lab.load_json(p)  # raises SystemExit on any '<'
        assert isinstance(data, dict)


def test_diff_index_bundle_matching_passes():
    idx = {"en": {"a": "1"}, "es": {"a": "uno"}}
    bundle_ui = {"en": {"a": "1"}, "es": {"a": "uno"}}
    assert build_lab.diff_index_bundle(idx, bundle_ui) == []


def test_diff_index_bundle_value_mismatch_is_blocking():
    idx = {"en": {"a": "1"}}
    bundle_ui = {"en": {"a": "DIFFERENT"}}
    errors = build_lab.diff_index_bundle(idx, bundle_ui)
    assert any("out of sync" in e and "'en'" in e for e in errors), errors


def test_diff_index_bundle_missing_language_is_blocking():
    idx = {"en": {"a": "1"}, "es": {"a": "uno"}}
    bundle_ui = {"en": {"a": "1"}}
    errors = build_lab.diff_index_bundle(idx, bundle_ui)
    assert any("missing language 'es'" in e for e in errors), errors


def test_diff_index_bundle_extra_language_is_blocking():
    idx = {"en": {"a": "1"}}
    bundle_ui = {"en": {"a": "1"}, "zz": {"a": "?"}}
    errors = build_lab.diff_index_bundle(idx, bundle_ui)
    assert any("language(s) present but not in" in e for e in errors), errors


def test_load_index_bundle_missing_file_returns_none(tmp_path):
    assert build_lab.load_index_bundle(tmp_path / "nope.html") is None


def test_load_index_bundle_parses_real_script_tag(tmp_path):
    html = ('<html><body>'
            '<script id="i18n" type="application/json">{"meta":{},"ui":{"en":{"k":"v"}}}</script>'
            '</body></html>')
    p = tmp_path / "index.html"
    p.write_text(html, encoding="utf-8")
    assert build_lab.load_index_bundle(p) == {"en": {"k": "v"}}


def test_load_index_bundle_no_script_tag_raises(tmp_path):
    p = tmp_path / "index.html"
    p.write_text("<html><body>no bundle here</body></html>", encoding="utf-8")
    try:
        build_lab.load_index_bundle(p)
        raise AssertionError("expected SystemExit for a missing i18n script tag")
    except SystemExit:
        pass


def test_load_index_bundle_malformed_json_raises(tmp_path):
    html = '<script id="i18n" type="application/json">{not valid json</script>'
    p = tmp_path / "index.html"
    p.write_text(html, encoding="utf-8")
    try:
        build_lab.load_index_bundle(p)
        raise AssertionError("expected SystemExit for malformed JSON")
    except SystemExit:
        pass


def test_end_to_end_bundle_matches_real_index_html():
    """The actual gamification/index.html in this repo, if present, must be byte-for-byte in sync with data/i18n/index/*.json —
    this is the same check main() runs before every build."""
    import os
    langs, ui, labs_tr, idx, errors = build_lab.load_i18n()
    assert errors == []
    default = build_lab.OUT / "index.html"
    path = Path(os.environ.get("INDEX_HTML") or default)
    bundle_ui = build_lab.load_index_bundle(path)
    if bundle_ui is None:
        import pytest
        pytest.skip(f"site index not found at {path}")
    sync_errors = build_lab.diff_index_bundle(idx, bundle_ui)
    assert sync_errors == [], sync_errors


if __name__ == "__main__":
    # Plain-script fallback, mirroring test_build_news.py's convention.
    import inspect
    mod = sys.modules[__name__]
    tests = [obj for name, obj in vars(mod).items() if name.startswith("test_") and callable(obj)]
    for fn in tests:
        sig = inspect.signature(fn)
        if sig.parameters:
            print(f"skip {fn.__name__} (needs a pytest fixture)")
            continue
        fn()
        print(f"ok {fn.__name__}")
    print("ALL OK")


# --- card-overlay gate: pending re-translation -------------------------------

def test_untranslated_path_with_unchanged_english_is_blocking():
    fields = {"why": "same English"}
    assert build_lab.untranslated_paths(fields, {}, {"why": "same English"}) == {"why"}


def test_corrected_english_may_drop_its_stale_translation():
    fields = {"why": "corrected English"}
    assert build_lab.untranslated_paths(fields, {}, {"why": "old English"}) == set()


def test_new_string_absent_from_snapshot_is_pending_not_blocking():
    assert build_lab.untranslated_paths({"note": "new"}, {}, {}) == set()


def test_translated_path_is_never_reported():
    fields = {"why": "x", "text": "y"}
    got = {"why": "traduit", "text": "traduit"}
    assert build_lab.untranslated_paths(fields, got, {"why": "x", "text": "y"}) == set()
