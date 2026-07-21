"""verifier.py was decomposed into a package (base + one module per language +
the orchestrator). It had no tests, so these are the safety net for the split:
the public import surface is intact, every language verifier still runs, and the
orchestrator dispatches by extension and aggregates. Behaviour, not just imports.
"""

from pathlib import Path

import pytest

# The historical import path must keep working (the shim re-exports the package).
from framework.verification.verifier import (
    GoVerifier,
    JavaScriptVerifier,
    KotlinVerifier,
    LanguageVerifier,
    MultiLanguageVerifier,
    PythonVerifier,
    RubyVerifier,
    SwiftVerifier,
    VerificationLevel,
    VerificationResult,
)


def test_public_import_surface_is_intact():
    # Everything __init__ advertised is still importable from the shim.
    from framework import verification

    for name in verification.__all__:
        assert hasattr(verification, name), name


ALL_VERIFIERS = [
    (PythonVerifier, "python", ".py"),
    (KotlinVerifier, "kotlin", ".kt"),
    (SwiftVerifier, "swift", ".swift"),
    (JavaScriptVerifier, "javascript", ".js"),
    (GoVerifier, "go", ".go"),
    (RubyVerifier, "ruby", ".rb"),
]


@pytest.mark.parametrize("cls,language,ext", ALL_VERIFIERS)
def test_each_verifier_reports_language_and_supports_its_extension(cls, language, ext):
    verifier = cls()
    assert isinstance(verifier, LanguageVerifier)
    assert verifier.language == language
    assert verifier.supports_file(Path(f"sample{ext}"))
    assert not verifier.supports_file(Path("sample.unknown"))


@pytest.mark.parametrize("cls,language,ext", ALL_VERIFIERS)
def test_each_verifier_runs_and_returns_a_result(cls, language, ext, tmp_path):
    sample = tmp_path / f"sample{ext}"
    sample.write_text("// placeholder test file\n", encoding="utf-8")
    result = cls().verify(sample)
    assert isinstance(result, VerificationResult)
    assert result.language == language
    result.to_dict()  # serializable


def test_python_verifier_flags_a_syntax_error(tmp_path):
    broken = tmp_path / "test_broken.py"
    broken.write_text("def test_x(:\n    pass\n", encoding="utf-8")
    result = PythonVerifier().verify(broken)
    assert not result.success
    assert result.error_count >= 1
    assert any(i.level == VerificationLevel.ERROR for i in result.issues)


def test_python_verifier_accepts_valid_source(tmp_path):
    good = tmp_path / "test_ok.py"
    good.write_text(
        "import pytest\n\n\ndef test_addition():\n    assert 1 + 1 == 2\n",
        encoding="utf-8",
    )
    result = PythonVerifier().verify(good)
    assert result.error_count == 0


def test_orchestrator_dispatches_by_extension_and_summarizes(tmp_path):
    (tmp_path / "test_a.py").write_text("def test_a():\n    assert True\n", encoding="utf-8")
    (tmp_path / "test_b.rb").write_text("def test_b\n  assert true\nend\n", encoding="utf-8")
    (tmp_path / "notes.unknown").write_text("ignored\n", encoding="utf-8")

    mlv = MultiLanguageVerifier()

    # Unknown extension -> no verifier -> None (not an error).
    assert mlv.verify_file(tmp_path / "notes.unknown") is None

    results = mlv.verify_directory(tmp_path, recursive=True)
    languages = {r.language for r in results}
    assert "python" in languages and "ruby" in languages

    summary = mlv.get_summary(results)
    assert summary["total_files"] == len(results)
    assert set(summary["by_language"]) == languages

    report_path = tmp_path / "report.json"
    mlv.export_report(results, report_path)
    assert report_path.exists()
