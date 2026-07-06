"""
Coverage-diff — generate only what isn't already tested.

You already have a framework with tests; a new feature ships and you want tests
for *that feature only*, not the whole app regenerated. This compares a freshly
crawled model against your existing tests and keeps only the new part.

The check is deliberately language-agnostic: a locator is "already covered" if its
value (an accessibility id, resource id, visible text, …) appears anywhere in your
existing test sources — regardless of framework or language. A generated test
*case* is kept only if it touches at least one locator you don't already test.

    covered = existing_test_text(Path("tests/"))
    new_model, report = filter_to_new(model, covered)
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Set, Tuple

from framework.codegen.ir import Selector, Step, TestCase, TestModel

# Files that plausibly contain tests / page objects across the languages we emit.
_TEST_SUFFIXES = (".py", ".java", ".kt", ".js", ".ts", ".feature", ".rb", ".swift", ".cs")


def existing_test_text(path: Path) -> str:
    """Concatenate every test/page-object source under ``path`` (recursively) into
    one blob to search locator values against. Missing path -> empty."""
    root = Path(path)
    if not root.exists():
        return ""
    if root.is_file():
        return _read(root)
    return "\n".join(_read(p) for p in root.rglob("*") if p.is_file() and p.suffix in _TEST_SUFFIXES)


def _read(p: Path) -> str:
    try:
        return p.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return ""


def _selector_values(selector: Selector) -> Set[str]:
    """The locator value plus its fallbacks — a selector is covered only if all of
    them are; new if any is absent."""
    values = {selector.value.strip()}
    for fb in selector.fallbacks:
        values.add(fb.value.strip())
    # A visible-text locator is often stored on `description`; count it too.
    if selector.description:
        values.add(selector.description.strip())
    return {v for v in values if v}


def _step_is_new(step: Step, covered_text: str) -> bool:
    if step.selector is None:
        return False
    return any(value not in covered_text for value in _selector_values(step.selector))


def case_is_new(case: TestCase, covered_text: str) -> bool:
    """A case is new iff it touches at least one locator not present in the
    existing tests (a pure re-test of known elements is dropped)."""
    return any(_step_is_new(step, covered_text) for step in case.steps)


@dataclass
class GapReport:
    total_cases: int
    new_cases: int
    covered_cases: int
    new_case_names: List[str]

    def summary(self) -> str:
        return (
            f"{self.new_cases}/{self.total_cases} case(s) are new "
            f"({self.covered_cases} already covered by existing tests)."
        )


def filter_to_new(model: TestModel, covered_text: str) -> Tuple[TestModel, GapReport]:
    """Return a copy of ``model`` with only the cases that exercise something not
    already in ``covered_text``, plus a gap report."""
    kept: List[TestCase] = [c for c in model.cases if case_is_new(c, covered_text)]
    report = GapReport(
        total_cases=len(model.cases),
        new_cases=len(kept),
        covered_cases=len(model.cases) - len(kept),
        new_case_names=[c.name for c in kept],
    )
    trimmed = TestModel(
        name=model.name,
        app_package=model.app_package,
        platform=model.platform,
        app_activity=model.app_activity,
        cases=kept,
        description=model.description,
    )
    return trimmed, report


def new_locators(selectors: Iterable[Selector], covered_text: str) -> List[str]:
    """Locator values from ``selectors`` that are NOT already tested — the concrete
    'here's what's new in this feature' list for a gap report."""
    out: List[str] = []
    for sel in selectors:
        for value in _selector_values(sel):
            if value not in covered_text and value not in out:
                out.append(value)
    return out
