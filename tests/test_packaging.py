"""Packaging guard.

`pip install mobiscout` (non-editable — what any downstream consumer, e.g.
Mobiscout-PRO's CI, actually does) must ship the whole ``framework`` tree. A bare
``packages = ["framework"]`` once shipped only ``framework/__init__.py`` — which
imports ``framework.model`` — so a real install was broken and non-importable,
while editable installs (dev/CI) silently worked. This asserts the configured
distribution would package every ``framework`` subpackage on disk.

Deliberately depends only on the stdlib (``tomllib`` + ``fnmatch`` + ``glob``): the
test runtime doesn't install setuptools, and this guard must run in CI.
"""

from __future__ import annotations

import glob
import os
import tomllib
from fnmatch import fnmatch

import framework


def _pyproject() -> dict:
    with open("pyproject.toml", "rb") as fh:
        return tomllib.load(fh)


def _setuptools_cfg() -> dict:
    return _pyproject()["tool"]["setuptools"]


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


def _package_data_files() -> set[str]:
    """Every file the ``[tool.setuptools.package-data]`` globs would ship, as paths
    relative to ``framework/``. Resolved with ``glob(..., recursive=True)`` because
    that is literally how setuptools expands these patterns — ``fnmatch`` would get
    ``**`` wrong."""
    cfg = _setuptools_cfg().get("package-data", {})
    return {
        match.replace(os.sep, "/")
        for pattern in cfg.get("framework", [])
        for match in glob.glob(pattern, root_dir="framework", recursive=True)
    }


def test_every_runtime_asset_is_in_package_data():
    """Companion guard to the package list: a non-``.py`` file under ``framework/`` is
    loaded by path at runtime, so it only reaches users if a package-data glob matches
    it. This already shipped broken once (see the pyproject comment) and CI cannot
    notice — every job installs editable, which reads the source tree. Assert instead
    of trusting the two hardcoded globs to keep covering whatever gets added."""
    on_disk = {
        os.path.relpath(os.path.join(root, name), "framework").replace(os.sep, "/")
        for root, _dirs, files in os.walk("framework")
        if "__pycache__" not in root
        for name in files
        if not name.endswith(".py")
    }
    missing = sorted(on_disk - _package_data_files())
    assert not missing, (
        "these runtime assets match no [tool.setuptools.package-data] glob, so a real "
        f"`pip install` (and the frozen engine) would ship without them: {missing}"
    )


def test_project_version_matches_framework_version():
    """`[project].version` is the fourth release pin (with framework.__version__,
    jetbrains-plugin/build.gradle.kts and EngineProvider.ENGINE_VERSION). It is what the
    built wheel self-identifies as, and it silently sat three releases behind because no
    gate compared it — same drift class as tests/test_changelog_version.py."""
    project_version = _pyproject()["project"]["version"]
    assert project_version == framework.__version__, (
        f"pyproject.toml [project].version is {project_version} but framework.__version__ is "
        f"{framework.__version__} — bump both together or the released wheel is misversioned"
    )
