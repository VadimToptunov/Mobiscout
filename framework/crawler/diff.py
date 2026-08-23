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
    model = filter_to_changed(model, report)         # keep only added+changed
    write_manifest(Path("kit/"), model)              # baseline for next time
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Union

from framework.codegen.ir import TestCase, TestModel

MANIFEST_NAME = "manifest.json"


def _case_signature(case: TestCase) -> str:
    """A stable hash of a case's *steps* — actions, locators, and inputs. Changing a
    step (new locator, new action, different typed value) changes the signature; editing
    only a human description does not."""
    blob = json.dumps([s.to_dict() for s in case.steps], sort_keys=True, ensure_ascii=False)
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
    return TestModel(
        name=model.name,
        app_package=model.app_package,
        platform=model.platform,
        app_activity=model.app_activity,
        cases=[c for c in model.cases if c.name in keep],
        description=model.description,
    )
