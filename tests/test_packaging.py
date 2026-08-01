"""Packaging guard.

`pip install mobiscout` (non-editable — what any downstream consumer, e.g.
Mobiscout-PRO's CI, actually does) must ship the whole ``framework`` tree. A bare
``packages = ["framework"]`` once shipped only ``framework/__init__.py`` — which
imports ``framework.model`` — so a real install was broken and non-importable,
while editable installs (dev/CI) silently worked. This asserts the configured
distribution packages cover every ``framework`` subpackage on disk.
"""

from __future__ import annotations

import os
import tomllib

from setuptools import find_packages


def _configured_packages() -> set[str]:
    with open("pyproject.toml", "rb") as fh:
        setuptools_cfg = tomllib.load(fh)["tool"]["setuptools"]
    pkgs = setuptools_cfg.get("packages")
    if isinstance(pkgs, list):  # explicit list form
        return set(pkgs)
    find = (pkgs or {}).get("find", {}) if isinstance(pkgs, dict) else {}
    return set(find_packages(where=".", include=find.get("include", ["*"]), exclude=find.get("exclude", [])))


def _framework_packages_on_disk() -> set[str]:
    return {
        root.replace(os.sep, ".")
        for root, _dirs, files in os.walk("framework")
        if "__init__.py" in files and "__pycache__" not in root
    }


def test_distribution_ships_every_framework_subpackage():
    missing = _framework_packages_on_disk() - _configured_packages()
    assert not missing, (
        "pyproject.toml would not package these subpackages (a plain `pip install` "
        f"would then fail to import them): {sorted(missing)}"
    )


def test_core_subpackages_are_packaged():
    """Spot-check the ones framework/__init__ imports at module load — the exact
    modules whose absence broke the install before."""
    configured = _configured_packages()
    for pkg in ("framework", "framework.model", "framework.crawler", "framework.codegen", "framework.licensing"):
        assert pkg in configured, f"{pkg} is not in the distribution"
