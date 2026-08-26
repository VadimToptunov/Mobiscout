"""Diff-aware regeneration — regenerate only the tests that changed.

A kit is written together with a small ``manifest.json`` describing every case it
covers: a case name mapped to a signature of its *steps* (actions + locators +
inputs, not cosmetic descriptions). On the next crawl, diff the freshly built
model against that baseline manifest to classify every case as **added**,
**changed**, **removed**, or **unchanged**, write a human-readable ``CHANGES.md``,
and — in ``only_changed`` mode — keep just the added+changed cases so a re-crawl of
an evolving app yields tests for the *delta*, not the whole app regenerated.

    baseline = load_manifest(Path("kit/"))          # prior run, or None
    report = diff_models(baseline, model)            # what moved
    write_manifest(Path("kit/"), model)              # record the FULL model as the next baseline
    model = filter_to_changed(model, report)         # THEN, optionally, keep only added+changed

Order matters: ``write_manifest`` must record the **full** model (every case this crawl
produced) so the next diff is crawl-vs-crawl. Writing it after ``filter_to_changed`` would
persist only the delta, and every case dropped this run would look "removed" next run.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from framework.codegen.ir import Selector, Step, TestCase, TestModel

MANIFEST_NAME = "manifest.json"


def _selector_shape(selector: Selector) -> Dict[str, Any]:
    """How a selector *locates*: strategy + value, recursed into its fallbacks. The human
    description and the stability score are left out — neither changes what the step does."""
    return {
        "strategy": selector.strategy.value,
        "value": selector.value,
        "fallbacks": [_selector_shape(f) for f in selector.fallbacks],
    }


def _step_shape(step: Step) -> Dict[str, Any]:
    """What a step *does*: the action, its target, and the data it types or expects."""
    return {
        "action": step.action.value,
        "selector": _selector_shape(step.selector) if step.selector is not None else None,
        "text": step.text,
        "assertion": step.assertion.value if step.assertion is not None else None,
        "expected": step.expected,
        "direction": step.direction,
        "timeout": step.timeout,
    }


def _case_signature(case: TestCase) -> str:
    """A stable hash of a case's *steps* — actions, locators, and inputs. Changing a
    step (new locator, new action, different typed value) changes the signature; editing
    only a human description does not.

    Hashing ``Step.to_dict()`` would break that promise: it carries the step description
    and the selector's score, both of which move on cosmetic changes (a relabelled control
    lands in "Tap Cart (2)", a text locator re-scores when its text starts to look dynamic),
    so an unchanged case showed up as "changed" in CHANGES.md and was regenerated."""
    blob = json.dumps([_step_shape(s) for s in case.steps], sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]


def build_manifest(model: TestModel) -> Dict[str, object]:
    """The serializable baseline for ``model``: identity + case→signature map."""
    return {
        "app_package": model.app_package,
        "platform": getattr(model.platform, "value", str(model.platform)),
        "cases": {c.name: _case_signature(c) for c in model.cases},
    }


def write_manifest(out_dir: Union[str, Path], model: TestModel) -> Path:
    """Write ``manifest.json`` into ``out_dir`` (created if missing); return its path."""
    path = Path(out_dir) / MANIFEST_NAME
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(build_manifest(model), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return path


def load_manifest(path: Union[str, Path]) -> Optional[Dict[str, object]]:
    """Load a baseline manifest. ``path`` may be the file itself or the kit directory
    that contains it. Returns None when absent or unreadable (treated as a first run)."""
    p = Path(path)
    if p.is_dir():
        p = p / MANIFEST_NAME
    if not p.exists():
        return None
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


@dataclass
class DiffReport:
    """Which cases moved between the baseline and the fresh model."""

    added: List[str] = field(default_factory=list)
    removed: List[str] = field(default_factory=list)
    changed: List[str] = field(default_factory=list)
    unchanged: List[str] = field(default_factory=list)
    first_run: bool = False  # no baseline existed — everything is "new", nothing to diff

    @property
    def has_changes(self) -> bool:
        return bool(self.added or self.removed or self.changed)

    def summary(self) -> str:
        if self.first_run:
            return f"First run — no baseline to diff against; {len(self.added)} case(s) generated."
        return (
            f"{len(self.added)} added, {len(self.changed)} changed, "
            f"{len(self.removed)} removed, {len(self.unchanged)} unchanged."
        )

    def to_markdown(self, app_package: str = "") -> str:
        head = f"# Test changes{f' — {app_package}' if app_package else ''}\n\n{self.summary()}\n"
        if self.first_run:
            body = _section("Generated", self.added)
            return head + body

        def _sections() -> str:
            return (
                _section("➕ Added", self.added)
                + _section("✏️ Changed", self.changed)
                + _section("➖ Removed", self.removed)
            )

        if not self.has_changes:
            return head + "\nNo test changes since the baseline. ✅\n"
        return head + _sections()


def _section(title: str, names: List[str]) -> str:
    if not names:
        return ""
    return f"\n## {title}\n\n" + "".join(f"- `{n}`\n" for n in names)


def diff_models(baseline: Optional[Dict[str, object]], model: TestModel) -> DiffReport:
    """Classify every case in ``model`` against ``baseline`` (from :func:`load_manifest`)."""
    new = {c.name: _case_signature(c) for c in model.cases}
    if baseline is None:
        return DiffReport(added=sorted(new), first_run=True)

    raw_old = baseline.get("cases", {})
    old: Dict[str, str] = raw_old if isinstance(raw_old, dict) else {}
    report = DiffReport()
    for name in sorted(new):
        if name not in old:
            report.added.append(name)
        elif old[name] != new[name]:
            report.changed.append(name)
        else:
            report.unchanged.append(name)
    report.removed = sorted(name for name in old if name not in new)
    return report


def filter_to_changed(model: TestModel, report: DiffReport) -> TestModel:
    """A copy of ``model`` carrying only the added+changed cases. On a first run
    (no baseline) nothing is dropped — every case is new."""
    if report.first_run:
        return model
    keep = set(report.added) | set(report.changed)
    # ``replace`` (not a hand-listed TestModel) so nothing else on the model is silently
    # dropped: rebuilding it field by field reset toolkit to "native" and launch_args to
    # [], so an only-changed kit lost the crawl's launch arguments (an auth-bypass flag)
    # and the emitter's toolkit guidance — and any field added later would be lost too.
    return replace(model, cases=[c for c in model.cases if c.name in keep])
