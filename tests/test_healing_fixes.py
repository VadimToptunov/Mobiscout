"""
Regression tests for healing/ML bug fixes (refactor pass).

Each test pins a specific bug found in review so it cannot silently return.
"""

import xml.etree.ElementTree as ET
from pathlib import Path

from framework.healing.orchestrator import HealingOrchestrator
from framework.healing.selector_discovery import (
    AlternativeSelector,
    SelectorDiscovery,
    SelectorStrategy,
)
from framework.ml.selector_healer import SelectorHealer


def test_generate_report_handles_no_results():
    """generate_report([]) must not raise ZeroDivisionError when nothing failed."""
    orch = HealingOrchestrator(repo_path=Path("."))
    report = orch.generate_report([])
    assert "0.0%" in report  # success percentage falls back to 0, no crash


def test_selector_healer_has_visual_based_stats():
    """visual_based counters must exist up front, or every visual heal KeyErrors."""
    healer = SelectorHealer()
    assert "visual_based" in healer.healing_stats
    assert healer.healing_stats["visual_based"] == {"successes": 0, "failures": 0}


def test_selector_discovery_parent_map_yields_indexed_xpath():
    """With the parent map built, _generate_xpath produces a positional, unique
    path instead of collapsing to //tag."""
    sd = SelectorDiscovery()
    root = ET.fromstring("<root><a><b/><b/></a></root>")
    sd._parent_map = {child: parent for parent in root.iter() for child in parent}

    second_b = list(root.iter("b"))[1]
    assert sd._get_parent(second_b) is not None
    assert sd._generate_xpath(second_b) == "//root/a/b[2]"


def test_filter_by_attributes_filters():
    """filter_by_attributes must actually filter, not always return []."""
    sd = SelectorDiscovery()
    sd.alternatives = [
        AlternativeSelector(SelectorStrategy.ID, "x", 0.9, {"class": "Button"}),
        AlternativeSelector(SelectorStrategy.ID, "y", 0.9, {"class": "Text"}),
    ]
    matched = sd.filter_by_attributes({"class": "Button"})
    assert [a.value for a in matched] == ["x"]
