"""The native SAST line scanner (Rust RegexSet when present, Python fallback otherwise).
The two paths must return identical results — this is what lets the fast path be trusted."""

from framework.analyzers import native


def test_scan_lines_matches_the_python_reference():
    contents = [
        "import MD5\nval token = random.random()\nsafe line",
        "no matches here\nSHA-1 is used",
    ]
    patterns = [r"\bMD5\b", r"random\.random", r"\bSHA[-_ ]?1\b"]
    got = native.scan_lines(contents, patterns, ignore_case=True)
    ref = native._scan_lines_py(contents, patterns, True)
    assert sorted(got) == sorted(ref)  # active path (Rust here) == the reference
    rules = {(fi, ln, ri) for (fi, ln, ri, _line) in got}
    assert (0, 1, 0) in rules  # MD5 on file 0, line 1
    assert (0, 2, 1) in rules  # random.random on file 0, line 2
    assert (1, 2, 2) in rules  # SHA-1 on file 1, line 2


def test_scan_lines_reports_the_matched_line_text():
    got = native.scan_lines(["a\nDES cipher\nb"], [r"\bDES\b"], ignore_case=False)
    assert got == [(0, 2, 0, "DES cipher")]


def test_scan_lines_empty_inputs():
    assert native.scan_lines([], [r"x"], False) == []
    assert native.scan_lines(["some text"], [], False) == []
