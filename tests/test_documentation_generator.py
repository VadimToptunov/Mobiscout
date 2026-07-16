"""DocGenerator turns a source tree into API docs (markdown/html/json/sphinx) via
the CodeParser. Pure file I/O, so tests point it at a temp source dir and assert
the generated output — the module had no tests."""

import json

import pytest

from framework.documentation.generator import DocConfig, DocFormat, DocGenerator

_SAMPLE = '''
"""Sample module docstring."""


def greet(name: str) -> str:
    """Greet someone."""
    return f"hi {name}"


class Thing:
    """A thing."""

    def do(self) -> None:
        """Do it."""
        pass
'''


@pytest.fixture()
def src(tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "sample.py").write_text(_SAMPLE)
    (tmp_path / "src" / "__pycache__").mkdir()
    (tmp_path / "src" / "__pycache__" / "junk.py").write_text("x = 1")
    (tmp_path / "src" / "_private.py").write_text("y = 2")
    return tmp_path / "src"


def _run(src, out, fmt=DocFormat.MARKDOWN, **kw):
    gen = DocGenerator(DocConfig(source_dir=src, output_dir=out, format=fmt, **kw))
    gen.generate()
    return gen


def test_markdown_index_and_module(src, tmp_path):
    out = tmp_path / "docs"
    _run(src, out, title="My API")
    index = (out / "index.md").read_text()
    assert "# My API" in index
    assert "[sample](sample.md)" in index  # TOC entry
    module = (out / "sample.md").read_text()
    assert "Sample module docstring." in module
    assert "greet" in module and "Thing" in module


def test_should_process_skips_pycache_and_private(src, tmp_path):
    gen = _run(src, tmp_path / "d")
    parsed = {m.name for m in gen.modules}
    assert "sample" in parsed
    assert "junk" not in parsed  # __pycache__ excluded
    assert "_private" not in parsed  # private excluded by default


def test_include_private(src, tmp_path):
    gen = _run(src, tmp_path / "d", include_private=True)
    assert "_private" in {m.name for m in gen.modules}


def test_no_toc(src, tmp_path):
    out = tmp_path / "d"
    _run(src, out, include_toc=False)
    assert "Table of Contents" not in (out / "index.md").read_text()


def test_json_format(src, tmp_path):
    out = tmp_path / "d"
    _run(src, out, fmt=DocFormat.JSON)
    files = list(out.glob("*.json"))
    assert files
    data = json.loads(files[0].read_text())
    assert data  # some structured content emitted


def test_html_format(src, tmp_path):
    out = tmp_path / "d"
    _run(src, out, fmt=DocFormat.HTML)
    html = list(out.glob("*.html"))
    assert html
    assert "<html" in html[0].read_text().lower()


def test_sphinx_format(src, tmp_path):
    out = tmp_path / "d"
    _run(src, out, fmt=DocFormat.SPHINX)
    assert list(out.iterdir())  # produced something


def test_generate_tolerates_unparseable_file(tmp_path):
    (tmp_path / "s").mkdir()
    (tmp_path / "s" / "ok.py").write_text('"""ok."""\n')
    (tmp_path / "s" / "broken.py").write_text("def (:\n")  # syntax error
    gen = _run(tmp_path / "s", tmp_path / "d")
    assert "ok" in {m.name for m in gen.modules}  # broken one skipped, not fatal
