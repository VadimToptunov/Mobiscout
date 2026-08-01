"""Packaging guard.

`pip install mobiscout` (non-editable — what any downstream consumer, e.g.
Mobiscout-PRO's CI, actually does) must ship the whole ``framework`` tree. A bare
``packages = ["framework"]`` once shipped only ``framework/__init__.py`` — which
imports ``framework.model`` — so a real install was broken and non-importable,
while editable installs (dev/CI) silently worked. This asserts the configured
distribution would package every ``framework`` subpackage on disk.

Deliberately depends only on the stdlib (``tomllib`` + ``fnmatch``): the test
runtime doesn't install setuptools, and this guard must run in CI.
"""

from __future__ import annotations

import os
import tomllib
from fnmatch import fnmatch


def _setuptools_cfg() -> dict:
    with open("pyproject.toml", "rb") as fh:
        return tomllib.load(fh)["tool"]["setuptools"]


def _is_shipped(package: str, cfg: dict) -> bool:
    """Whether ``package`` (a dotted name) would be included by the pyproject
    ``[tool.setuptools]`` config — handling both the explicit ``packages = [...]``
    list and the ``packages.find`` include/exclude glob form. ``fnmatch``'s ``*``
    spans dots, matching setuptools' own ``find`` include semantics."""
    pkgs = cfg.get("packages")
    if isinstance(pkgs, list):  # explicit list form
        return package in pkgs
    find = (pkgs or {}).get("find", {}) if isinstance(pkgs, dict) else {}
    include = find.get("include", ["*"])
    exclude = find.get("exclude", [])
    return any(fnmatch(package, g) for g in include) and not any(fnmatch(package, g) for g in exclude)


def _framework_packages_on_disk() -> set[str]:
    return {
        root.replace(os.sep, ".")
        for root, _dirs, files in os.walk("framework")
        if "__init__.py" in files and "__pycache__" not in root
    }


def test_distribution_ships_every_framework_subpackage():
    cfg = _setuptools_cfg()
    missing = sorted(p for p in _framework_packages_on_disk() if not _is_shipped(p, cfg))
    assert not missing, (
        "pyproject.toml would not package these subpackages (a plain `pip install` "
        f"would then fail to import them): {missing}"
    )


def test_core_subpackages_are_packaged():
    """Spot-check the ones framework/__init__ imports at module load — the exact
    modules whose absence broke the install before."""
    cfg = _setuptools_cfg()
    for pkg in ("framework", "framework.model", "framework.crawler", "framework.codegen", "framework.licensing"):
        assert _is_shipped(pkg, cfg), f"{pkg} is not in the distribution"
