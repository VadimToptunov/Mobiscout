"""PatternRecognizer mines frequent navigation flows from session events, marks
critical paths, flags anomalies (dead ends, loops, unusual paths) and turns
patterns into Gherkin test-scenario suggestions. Pure in-memory logic over lists
of event dicts. Expected values are derived from the module's mining thresholds
and heuristics, not assumed.
"""

from framework.ml.pattern_recognizer import (
    AnomalyDetection,
    FlowPattern,
    PatternRecognizer,
)


def _ev(session, screen, ts):
    return {"session_id": session, "to_screen": screen, "timestamp": ts}


def _sessions(seqs):
    """Build navigation events from {session_id: [screens...]} with timestamps."""
    events = []
    for sid, screens in seqs.items():
        for i, screen in enumerate(screens):
            events.append(_ev(sid, screen, i))
    return events


# --------------------------------------------------------------------------- #
# analyze_flows / sequential pattern mining
# --------------------------------------------------------------------------- #
def test_repeated_flow_is_detected_as_pattern():
    pr = PatternRecognizer(min_support=2, min_confidence=0.6)
    events = _sessions({"s1": ["login", "home", "checkout"], "s2": ["login", "home", "checkout"]})
    patterns = pr.analyze_flows(events)

    full = next(p for p in patterns if p.screens == ["login", "home", "checkout"])
    assert full.frequency == 2
    assert full.confidence == 1.0  # 2 of 2 sequences
    assert full.description == "login → home → checkout"
    # Also mines the length-2 sub-patterns.
    assert any(p.screens == ["login", "home"] for p in patterns)


def test_pattern_below_min_support_is_dropped():
    pr = PatternRecognizer(min_support=2, min_confidence=0.6)
    events = _sessions({"s1": ["a", "b"], "s2": ["c", "d"]})  # every pair occurs once
    assert pr.analyze_flows(events) == []


def test_pattern_below_min_confidence_is_dropped():
    # Pattern occurs in 2 of 4 sessions -> confidence 0.5 < 0.6.
    pr = PatternRecognizer(min_support=2, min_confidence=0.6)
    events = _sessions(
        {
            "s1": ["x", "y"],
            "s2": ["x", "y"],
            "s3": ["p", "q"],
            "s4": ["m", "n"],
        }
    )
    assert pr.analyze_flows(events) == []


def test_single_screen_sessions_yield_no_patterns():
    pr = PatternRecognizer(min_support=1, min_confidence=0.0)
    events = _sessions({"s1": ["only"], "s2": ["one"]})
    assert pr.analyze_flows(events) == []


def test_high_frequency_pattern_marked_critical():
    pr = PatternRecognizer(min_support=2, min_confidence=0.5)
    events = _sessions({"s1": ["a", "b", "c"], "s2": ["a", "b", "c"], "s3": ["a", "b", "c"]})
    patterns = pr.analyze_flows(events)
    # frequency_ratio 3/3 = 1.0 > 0.5 -> all critical.
    assert all(p.is_critical for p in patterns)


def test_entry_plus_critical_screen_marked_critical():
    # Appears in exactly half the sessions (ratio 0.5, not > 0.5) but starts at an
    # entry screen (login) and contains a critical screen (checkout).
    pr = PatternRecognizer(min_support=2, min_confidence=0.4)
    events = _sessions(
        {
            "s1": ["login", "checkout"],
            "s2": ["login", "checkout"],
            "s3": ["browse", "settings"],
            "s4": ["browse", "settings"],
        }
    )
    patterns = pr.analyze_flows(events)
    login_pat = next(p for p in patterns if p.screens == ["login", "checkout"])
    assert login_pat.is_critical is True
    settings_pat = next(p for p in patterns if p.screens == ["browse", "settings"])
    assert settings_pat.is_critical is False


# --------------------------------------------------------------------------- #
# _group_by_session / _extract_sequence
# --------------------------------------------------------------------------- #
def test_group_by_session_sorts_by_timestamp_and_drops_sessionless():
    pr = PatternRecognizer()
    events = [
        {"session_id": "s1", "to_screen": "b", "timestamp": 2},
        {"session_id": "s1", "to_screen": "a", "timestamp": 1},
        {"to_screen": "orphan", "timestamp": 0},  # no session id -> dropped
    ]
    grouped = pr._group_by_session(events)
    assert list(grouped.keys()) == ["s1"]
    assert [e["to_screen"] for e in grouped["s1"]] == ["a", "b"]


def test_group_by_session_accepts_camelcase_key():
    pr = PatternRecognizer()
    grouped = pr._group_by_session([{"sessionId": "s9", "to_screen": "home", "timestamp": 0}])
    assert "s9" in grouped


def test_extract_sequence_collapses_consecutive_duplicates():
    pr = PatternRecognizer()
    events = [
        {"to_screen": "a", "timestamp": 0},
        {"to_screen": "a", "timestamp": 1},
        {"to_screen": "b", "timestamp": 2},
        {"to_screen": "a", "timestamp": 3},
    ]
    assert pr._extract_sequence(events) == ["a", "b", "a"]


def test_extract_sequence_uses_screen_fallback_key():
    pr = PatternRecognizer()
    events = [{"screen": "home", "timestamp": 0}, {"screen": "detail", "timestamp": 1}]
    assert pr._extract_sequence(events) == ["home", "detail"]


# --------------------------------------------------------------------------- #
# Anomaly detection
# --------------------------------------------------------------------------- #
def test_dead_end_anomaly():
    pr = PatternRecognizer()
    events = _sessions({"s1": ["login", "search", "details"]})  # ends at non-exit, len 3 < 5
    anomalies = pr.detect_anomalies(events)
    assert any(a.anomaly_type == "dead_end" and a.severity == "medium" for a in anomalies)


def test_no_dead_end_when_ending_at_exit_screen():
    pr = PatternRecognizer()
    events = _sessions({"s1": ["login", "search", "home"]})  # ends at 'home' (exit)
    anomalies = pr.detect_anomalies(events)
    assert not any(a.anomaly_type == "dead_end" for a in anomalies)


def test_detect_dead_ends_directly_respects_length_window():
    pr = PatternRecognizer()
    assert pr._detect_dead_ends("s", ["a", "b"]) == []  # len 2, not > 2
    assert pr._detect_dead_ends("s", ["a", "b", "c", "d", "e"]) == []  # len 5, not < 5
    assert len(pr._detect_dead_ends("s", ["a", "b", "c"])) == 1


def test_navigation_loop_detected():
    pr = PatternRecognizer()
    # a,b alternating: no consecutive dups, 'a' visited 4 times -> low severity loop.
    events = _sessions({"s1": ["a", "b", "a", "b", "a", "b", "a"]})
    anomalies = pr.detect_anomalies(events)
    loop = next(a for a in anomalies if a.anomaly_type == "navigation_loop")
    assert "a" in loop.description
    assert loop.severity == "low"


def test_loop_severity_escalates_past_five_visits():
    pr = PatternRecognizer()
    seq = ["a", "b"] * 6 + ["a"]  # 'a' appears 7 times
    anomalies = pr._detect_loops("s", seq)
    a_loop = next(a for a in anomalies if "'a'" in a.description)
    assert a_loop.severity == "medium"


def test_unusual_path_flagged_against_known_patterns():
    pr = PatternRecognizer()
    known = [FlowPattern("p1", ["login", "home"], 5, 0.9, True, "login → home")]
    events = _sessions({"s1": ["settings", "billing", "invoice"]})  # matches nothing, len 3
    anomalies = pr.detect_anomalies(events, known_patterns=known)
    assert any(a.anomaly_type == "unusual_path" and a.severity == "low" for a in anomalies)


def test_known_path_is_not_flagged_as_unusual():
    pr = PatternRecognizer()
    known = [FlowPattern("p1", ["login", "home"], 5, 0.9, True, "login → home")]
    events = _sessions({"s1": ["login", "home", "profile"]})  # contains known subsequence
    anomalies = pr.detect_anomalies(events, known_patterns=known)
    assert not any(a.anomaly_type == "unusual_path" for a in anomalies)


def test_sequence_contains_pattern_helper():
    pr = PatternRecognizer()
    assert pr._sequence_contains_pattern(["a", "b", "c", "d"], ["b", "c"]) is True
    assert pr._sequence_contains_pattern(["a", "b", "c"], ["b", "d"]) is False


# --------------------------------------------------------------------------- #
# Test scenario suggestions & Gherkin
# --------------------------------------------------------------------------- #
def test_suggest_scenarios_prioritises_critical_patterns():
    pr = PatternRecognizer()
    critical = FlowPattern("p1", ["login", "home", "checkout"], 10, 1.0, True, "login → home → checkout")
    scenarios = pr.suggest_test_scenarios([critical])
    assert len(scenarios) == 1
    s = scenarios[0]
    assert s["priority"] == "critical"
    assert s["steps"] == ["login", "home", "checkout"]
    assert "Scenario:" in s["gherkin"]


def test_suggest_scenarios_includes_frequent_non_critical():
    pr = PatternRecognizer(min_support=2)  # threshold is min_support*2 = 4
    frequent = FlowPattern("p2", ["a", "b"], 5, 0.8, False, "a → b")
    rare = FlowPattern("p3", ["c", "d"], 3, 0.7, False, "c → d")  # 3 <= 4 -> excluded
    scenarios = pr.suggest_test_scenarios([frequent, rare])
    ids = {s["pattern_id"] for s in scenarios}
    assert "p2" in ids
    assert "p3" not in ids


def test_suggest_scenarios_defaults_to_detected_patterns():
    pr = PatternRecognizer()
    pr.detected_patterns = [FlowPattern("p1", ["login", "home"], 9, 1.0, True, "login → home")]
    scenarios = pr.suggest_test_scenarios()  # no arg -> uses self.detected_patterns
    assert [s["pattern_id"] for s in scenarios] == ["p1"]


def test_generate_gherkin_structure():
    pr = PatternRecognizer()
    pattern = FlowPattern("p1", ["login", "home", "checkout"], 3, 1.0, True, "login → home → checkout")
    gherkin = pr._generate_gherkin(pattern)
    assert gherkin.splitlines() == [
        "Scenario: User navigates login to home to checkout",
        "  Given user is on login screen",
        "  When user navigates to home screen",
        "  Then user should see checkout screen",
    ]


# --------------------------------------------------------------------------- #
# Stats
# --------------------------------------------------------------------------- #
def test_pattern_stats_empty():
    assert PatternRecognizer().get_pattern_stats() == {
        "total_patterns": 0,
        "critical_patterns": 0,
        "avg_frequency": 0.0,
        "avg_confidence": 0.0,
    }


def test_pattern_stats_aggregate():
    pr = PatternRecognizer()
    pr.detected_patterns = [
        FlowPattern("p1", ["a", "b"], 4, 0.8, True, "a → b"),
        FlowPattern("p2", ["a", "b", "c"], 2, 0.6, False, "a → b → c"),
    ]
    stats = pr.get_pattern_stats()
    assert stats["total_patterns"] == 2
    assert stats["critical_patterns"] == 1
    assert stats["avg_frequency"] == 3.0
    assert stats["avg_confidence"] == 0.7
    assert stats["patterns_by_length"] == {2: 1, 3: 1}


# --------------------------------------------------------------------------- #
# Dataclasses
# --------------------------------------------------------------------------- #
def test_dataclasses_hold_fields():
    fp = FlowPattern("p", ["a"], 1, 0.5, False, "a")
    assert fp.pattern_id == "p" and fp.screens == ["a"]
    ad = AnomalyDetection("s", 0, "loop", "desc", "high")
    assert ad.session_id == "s" and ad.severity == "high"
