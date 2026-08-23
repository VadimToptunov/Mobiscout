"""SASTAnalyzer.analyze_directory batches the crypto + insecure-API regex scans through one
native.scan_lines pass (Rust RegexSet when built, Python otherwise). It must produce exactly
the same findings, per file and in the same order, as scanning each file on its own."""

import textwrap
from collections import defaultdict

from framework.security.sast.analyzer import SASTAnalyzer


def _finding_key(f):
    return (f.vulnerability_type.value, f.file_path, f.line_number, f.title)


def _seed(tmp_path):
    (tmp_path / "crypto.kt").write_text(
        textwrap.dedent("""
            val digest = MessageDigest.getInstance("MD5")
            val nonce = Math.random()
            webView.settings.setJavaScriptEnabled(true)
            val key = "SECRETVALUE1234"
            // MD5 mentioned only in a comment must NOT be flagged
            """),
        encoding="utf-8",
    )
    (tmp_path / "more.java").write_text(
        "TrustManager tm = insecureTrustManager();\nString bad = SHA-1;\n",
        encoding="utf-8",
    )
    return tmp_path


def test_analyze_directory_matches_per_file_exactly(tmp_path):
    _seed(tmp_path)
    analyzer = SASTAnalyzer()

    batched = analyzer.analyze_directory(tmp_path)
    assert batched, "fixture should produce findings"

    by_file = defaultdict(list)
    for finding in batched:
        by_file[finding.file_path].append(finding)

    for path in sorted(p for p in tmp_path.glob("**/*") if p.is_file()):
        reference = analyzer.analyze_file(path)
        got = by_file.get(str(path), [])
        # Same findings, same order, for this file — the batched path can't drift from per-file.
        assert [_finding_key(f) for f in got] == [_finding_key(f) for f in reference], f"mismatch in {path.name}"


def test_comment_only_weak_algorithm_is_not_flagged(tmp_path):
    (tmp_path / "c.kt").write_text("// uses MD5 historically\nval x = 1\n", encoding="utf-8")
    findings = SASTAnalyzer().analyze_directory(tmp_path)
    assert not any("MD5" in f.title for f in findings)
