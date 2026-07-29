"""Tests for the hoisted runtime protection base logic (item-3 de-duplication).

``_find_patterns`` and ``_analyze_category`` used to be byte-identical in the
Android and iOS analyzers; they now live once on ``BaseProtectionAnalyzer``.
These tests cover the shared logic directly and confirm both platform analyzers
inherit it (and only supply their own EXTENSIONS + pattern dicts).
"""

from framework.security.runtime.base import (
    BaseProtectionAnalyzer,
    ImplementationQuality,
    ProtectionCategory,
    ProtectionIndicator,
)
from framework.security.runtime.android import AndroidProtectionAnalyzer
from framework.security.runtime.ios import IOSProtectionAnalyzer


# --------------------------------------------------------------------------- #
# Both subclasses inherit the shared implementation
# --------------------------------------------------------------------------- #
class TestInheritance:
    def test_android_and_ios_subclass_base(self):
        assert issubclass(AndroidProtectionAnalyzer, BaseProtectionAnalyzer)
        assert issubclass(IOSProtectionAnalyzer, BaseProtectionAnalyzer)

    def test_shared_methods_are_not_overridden(self):
        # Exactly one implementation of each method, on the base class.
        assert AndroidProtectionAnalyzer._find_patterns is BaseProtectionAnalyzer._find_patterns
        assert IOSProtectionAnalyzer._find_patterns is BaseProtectionAnalyzer._find_patterns
        assert AndroidProtectionAnalyzer._analyze_category is BaseProtectionAnalyzer._analyze_category
        assert IOSProtectionAnalyzer._analyze_category is BaseProtectionAnalyzer._analyze_category

    def test_platforms_supply_distinct_extensions(self):
        assert AndroidProtectionAnalyzer.EXTENSIONS == [".java", ".kt", ".xml", ".smali"]
        assert IOSProtectionAnalyzer.EXTENSIONS == [".swift", ".m", ".h", ".plist"]


# --------------------------------------------------------------------------- #
# _find_patterns — extension-scoped source scan
# --------------------------------------------------------------------------- #
class TestFindPatterns:
    def test_matches_only_configured_extensions(self, tmp_path):
        (tmp_path / "A.java").write_text("if (isRooted()) block();\n", encoding="utf-8")
        # Same token in a file type Android does not scan -> ignored.
        (tmp_path / "A.swift").write_text("if isRooted() { block() }\n", encoding="utf-8")

        analyzer = AndroidProtectionAnalyzer()
        indicators = analyzer._find_patterns(
            tmp_path,
            {r"isRooted|checkRoot|detectRoot": ("Root detection method", "moderate")},
            ProtectionCategory.ROOT_DETECTION,
        )

        assert len(indicators) == 1
        ind = indicators[0]
        assert ind.category is ProtectionCategory.ROOT_DETECTION
        assert ind.location.endswith("A.java")
        assert ind.line_number == 1
        assert ind.bypass_difficulty == "moderate"

    def test_unreadable_file_does_not_abort(self, tmp_path):
        # A directory named like a source file makes read_text raise OSError.
        (tmp_path / "bad.java").mkdir()
        (tmp_path / "good.java").write_text("ptrace(0);\n", encoding="utf-8")

        analyzer = AndroidProtectionAnalyzer()
        indicators = analyzer._find_patterns(
            tmp_path, {r"ptrace": ("Ptrace detection", "hard")}, ProtectionCategory.DEBUG_DETECTION
        )

        assert [i.location for i in indicators] == [str(tmp_path / "good.java")]


# --------------------------------------------------------------------------- #
# _analyze_category — quality scoring
# --------------------------------------------------------------------------- #
class TestAnalyzeCategory:
    def _ind(self, difficulty):
        return ProtectionIndicator(
            category=ProtectionCategory.ROOT_DETECTION,
            indicator="x",
            location="f",
            line_number=1,
            description="d",
            bypass_difficulty=difficulty,
        )

    def test_no_indicators_is_none_quality(self):
        analyzer = IOSProtectionAnalyzer()
        result = analyzer._analyze_category(ProtectionCategory.SSL_PINNING, [], ["rec-a", "rec-b"])
        assert result.implemented is False
        assert result.quality is ImplementationQuality.NONE
        assert result.score == 0.0
        assert result.recommendations == ["rec-a", "rec-b"]

    def test_all_hard_indicators_scores_strong(self):
        analyzer = AndroidProtectionAnalyzer()
        result = analyzer._analyze_category(
            ProtectionCategory.ROOT_DETECTION, [self._ind("hard"), self._ind("hard")], ["r1", "r2", "r3", "r4"]
        )
        assert result.implemented is True
        assert result.quality is ImplementationQuality.STRONG
        assert result.score == 100.0
        # Strong implementations drop the remaining recommendations.
        assert result.recommendations == []

    def test_all_easy_indicators_scores_weak_and_keeps_three_recs(self):
        analyzer = AndroidProtectionAnalyzer()
        result = analyzer._analyze_category(
            ProtectionCategory.ROOT_DETECTION, [self._ind("easy")], ["r1", "r2", "r3", "r4"]
        )
        assert result.quality is ImplementationQuality.WEAK
        assert round(result.score, 2) == round(100 / 3, 2)
        assert result.recommendations == ["r1", "r2", "r3"]


# --------------------------------------------------------------------------- #
# End-to-end through the platform analyzers (shared logic in situ)
# --------------------------------------------------------------------------- #
class TestPlatformAnalyzeSource:
    def test_android_source_analysis_uses_shared_logic(self, tmp_path):
        (tmp_path / "Sec.java").write_text(
            "if (isRooted()) return;\nCertificatePinner p = new CertificatePinner();\n", encoding="utf-8"
        )
        analyses = AndroidProtectionAnalyzer().analyze_source(tmp_path)

        implemented = {a.category for a in analyses if a.implemented}
        assert ProtectionCategory.ROOT_DETECTION in implemented
        assert ProtectionCategory.SSL_PINNING in implemented

    def test_ios_source_analysis_uses_shared_logic(self, tmp_path):
        (tmp_path / "Sec.swift").write_text(
            'let c = "/Applications/Cydia.app"\nlet t = TrustKit.self\n', encoding="utf-8"
        )
        analyses = IOSProtectionAnalyzer().analyze_source(tmp_path)

        implemented = {a.category for a in analyses if a.implemented}
        assert ProtectionCategory.JAILBREAK_DETECTION in implemented
        assert ProtectionCategory.SSL_PINNING in implemented
