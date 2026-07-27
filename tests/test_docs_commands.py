"""Behavior tests for the `docs` CLI group (documentation generation).

Runs the real DocGenerator / CodeParser over a tmp package: markdown + html
generation (asserting files land on disk), the code-structure `analyze`, single
file `inspect`, and `coverage` with a JSON report export.
"""

from pathlib import Path

import pytest
from click.testing import CliRunner

from framework.cli.docs_commands import docs


@pytest.fixture()
def runner():
    return CliRunner()


def _no_crash(result):
    assert result.exception is None or isinstance(
        result.exception, SystemExit
    ), f"command crashed: {result.exception!r}\n{result.output}"


def _package(tmp_path: Path) -> Path:
    src = tmp_path / "pkg"
    src.mkdir()
    (src / "module.py").write_text(
        '"""Module docstring."""\n\n\n'
        "class Greeter:\n"
        '    """A greeter."""\n\n'
        "    def greet(self, name):\n"
        '        """Return a greeting."""\n'
        "        return f'Hello {name}'\n\n\n"
        "def helper(x):\n"
        "    return x\n",
        encoding="utf-8",
    )
    return src


def test_generate_markdown_writes_output(runner, tmp_path):
    out = tmp_path / "docs_out"
    result = runner.invoke(docs, ["generate", str(_package(tmp_path)), "-o", str(out), "-f", "markdown"])
    _no_crash(result)
    assert result.exit_code == 0
    assert "generated successfully" in result.output
    # Markdown generation produces files in the output directory.
    assert out.exists() and any(out.rglob("*.md"))


def test_generate_html_writes_output(runner, tmp_path):
    out = tmp_path / "html_out"
    result = runner.invoke(docs, ["generate", str(_package(tmp_path)), "-o", str(out), "-f", "html"])
    _no_crash(result)
    assert result.exit_code == 0
    assert out.exists() and any(out.iterdir())


def test_analyze_reports_statistics(runner, tmp_path):
    result = runner.invoke(docs, ["analyze", str(_package(tmp_path))])
    _no_crash(result)
    assert result.exit_code == 0
    assert "Code Statistics" in result.output
    assert "Classes" in result.output


def test_inspect_shows_classes_and_functions(runner, tmp_path):
    module = _package(tmp_path) / "module.py"
    result = runner.invoke(docs, ["inspect", str(module)])
    _no_crash(result)
    assert result.exit_code == 0
    assert "Greeter" in result.output


def test_coverage_writes_report(runner, tmp_path):
    report = tmp_path / "coverage.json"
    result = runner.invoke(docs, ["coverage", str(_package(tmp_path)), "-o", str(report)])
    _no_crash(result)
    assert result.exit_code == 0
    assert "Overall Coverage" in result.output
    assert report.exists()
    import json

    data = json.loads(report.read_text(encoding="utf-8"))
    assert "overall_coverage" in data
    assert data["total_items"] > 0
