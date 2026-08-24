"""The native SAST line scanner (Rust RegexSet when present, Python fallback otherwise).
The two paths must return identical results — this is what lets the fast path be trusted."""

import pytest

from framework.analyzers import native


def test_scan_lines_matches_the_python_reference():
    contents = [
        "import MD5\nval token = random.random()\nsafe line",
        "no matches here\nSHA-1 is used",
    ]
    patterns = [r"\bMD5\b", r"random\.random", r"\bSHA[-_ ]?1\b"]
    got = native.scan_lines(contents, patterns, ignore_case=True)
    ref = native._scan_lines_py([c.splitlines() for c in contents], patterns, True)
    assert sorted(got) == sorted(ref)  # active path (Rust here) == the reference
    rules = set(got)
    assert (0, 1, 0) in rules  # MD5 on file 0, line 1
    assert (0, 2, 1) in rules  # random.random on file 0, line 2
    assert (1, 2, 2) in rules  # SHA-1 on file 1, line 2


def test_scan_lines_returns_file_line_rule_triples():
    got = native.scan_lines(["a\nDES cipher\nb"], [r"\bDES\b"], ignore_case=False)
    assert got == [(0, 2, 0)]  # (file_index, line_number, rule_index) — no line text (RC4)


def test_scan_lines_empty_inputs():
    assert native.scan_lines([], [r"x"], False) == []
    assert native.scan_lines(["some text"], [], False) == []


@pytest.mark.skipif(native._native_core() is None, reason="native wheel not installed / too old")
def test_rust_and_python_agree_on_unicode_line_boundaries():
    # Regression for RC1(a): the Rust side split with str::lines() (\n only) while Python
    # numbers by str.splitlines() (form-feed \x0c, U+2028, …), so a file with a form-feed
    # page break numbered findings differently per backend. Both now scan lines split once
    # in Python, so they agree exactly.
    #
    # V1: call the CORE directly, not native.scan_lines — the seam silently falls back to
    # Python on a stale/incompatible wheel, which would make this compare Python-with-Python
    # and pass vacuously. The direct call raises on a stale signature, failing loudly instead.
    form_feed, line_sep = chr(0x0C), chr(0x2028)
    text = f"md5{form_feed}md5{line_sep}md5\ndes"
    assert len(text.splitlines()) == 4  # \x0c and U+2028 both split; str::lines() saw 2
    patterns = [r"\bmd5\b", r"\bdes\b"]
    lines_per_file = [text.splitlines()]
    core = native._native_core()
    rust = [tuple(t) for t in core.scan_lines(lines_per_file, patterns, True)]  # the core, not the seam
    py = native._scan_lines_py(lines_per_file, patterns, True)
    assert sorted(rust) == sorted(py)
    assert sorted(rust) == [(0, 1, 0), (0, 2, 0), (0, 3, 0), (0, 4, 1)]
