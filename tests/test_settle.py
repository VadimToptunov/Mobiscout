"""Adaptive settle: return as soon as the UI is stable, cap at max_wait, and
never treat a failed dump as stable."""

from framework.crawler.settle import settle_until_stable


def test_returns_when_two_snapshots_match():
    # a -> b -> b : stabilises on the second "b"; should stop there.
    seq = iter(["a", "b", "b", "b", "b"])
    calls = []

    def snap():
        v = next(seq)
        calls.append(v)
        return v

    result = settle_until_stable(snap, min_wait=0, poll=0, max_wait=1.0)
    assert result == "b"
    assert calls == ["a", "b", "b"]  # stopped as soon as it settled, no extra polls


def test_caps_when_never_stable():
    # Always-changing UI never settles -> must return by max_wait, not hang.
    n = {"i": 0}

    def snap():
        n["i"] += 1
        return f"screen-{n['i']}"

    result = settle_until_stable(snap, min_wait=0, poll=0.01, max_wait=0.15)
    assert result.startswith("screen-")
    assert n["i"] >= 2  # it did poll a few times


def test_empty_dump_never_counts_as_stable():
    # Two empty dumps must NOT be treated as "stable" (flaky device) — it caps.
    n = {"i": 0}

    def snap():
        n["i"] += 1
        return ""

    settle_until_stable(snap, min_wait=0, poll=0.01, max_wait=0.1)
    assert n["i"] >= 2  # kept polling instead of accepting the empty dump


def test_on_snapshot_receives_every_dump():
    seq = iter(["x", "x"])
    seen = []
    settle_until_stable(lambda: next(seq), on_snapshot=seen.append, min_wait=0, poll=0, max_wait=1.0)
    assert seen == ["x", "x"]
