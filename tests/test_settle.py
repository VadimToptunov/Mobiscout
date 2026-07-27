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


def test_settles_despite_ticking_numbers():
    # A live-updating screen whose only change is a ticking price/clock must count
    # as *settled* — the structure is identical, only volatile values differ. This
    # is the fast-crawl win: it no longer waits out max_wait on such screens.
    prices = iter(
        [
            '<Cell name="balance">€17,379.28</Cell>',
            '<Cell name="balance">€17,380.11</Cell>',  # only the number changed
            '<Cell name="balance">€17,381.02</Cell>',
        ]
    )
    calls = []

    def snap():
        v = next(prices)
        calls.append(v)
        return v

    result = settle_until_stable(snap, min_wait=0, poll=0, max_wait=1.0)
    # Settled on the second dump (same structure), not polled to exhaustion.
    assert len(calls) == 2
    assert result.startswith("<Cell")


def test_real_structural_change_is_not_settled():
    # A genuine layout change (new element) must NOT be seen as stable.
    seq = iter(
        [
            "<A/>",
            "<A/><B/>",  # structure changed -> keep polling
            "<A/><B/>",  # now stable
        ]
    )
    calls = []

    def snap():
        v = next(seq)
        calls.append(v)
        return v

    result = settle_until_stable(snap, min_wait=0, poll=0, max_wait=1.0)
    assert calls == ["<A/>", "<A/><B/>", "<A/><B/>"]
    assert result == "<A/><B/>"
