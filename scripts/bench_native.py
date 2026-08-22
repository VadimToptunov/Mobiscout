#!/usr/bin/env python3
"""Benchmark the complexity analyzer: the optional Rust core vs the pure-Python fallback.

This is the harness behind any "Rust is N× faster" claim. It measures both backends on
the SAME inputs and prints a Markdown table with real, reproducible numbers — no figure
should appear in the docs that this script didn't produce on the machine cited.

    python scripts/bench_native.py                 # default corpus, 2000 iterations
    python scripts/bench_native.py --iterations 5000

When `mobiscout_core` (the Rust wheel) isn't installed, only the Python backend is timed
and the script says so — it never invents a speedup it couldn't measure. Build/install the
wheel first with `maturin develop --release` in `rust_core/` to get the Rust column.
"""

from __future__ import annotations

import argparse
import time
from typing import Callable, List, Tuple

from framework.analyzers import native

# A small, representative corpus. Kept inline so the benchmark is self-contained and the
# exact inputs behind a published number are visible in source control.
_SAMPLES: List[Tuple[str, str]] = [
    (
        "python",
        "class Service:\n"
        "    def handle(self, req):\n"
        "        if req.ok and req.size > 0:\n"
        "            for item in req.items:\n"
        "                try:\n"
        "                    process(item)\n"
        "                except ValueError:\n"
        "                    continue\n"
        "        return req\n",
    ),
    (
        "kotlin",
        "class Login {\n"
        "    fun submit(u: String, p: String) {\n"
        "        if (u.isNotEmpty() && p.length > 3) {\n"
        "            for (c in u) { validate(c) }\n"
        "        } else { showError() }\n"
        "    }\n"
        "}\n",
    ),
]


def _time(fn: Callable[[], object], iterations: int) -> float:
    """Median-ish wall time per iteration in microseconds (best of 3 batches)."""
    best = float("inf")
    for _ in range(3):
        start = time.perf_counter()
        for _ in range(iterations):
            fn()
        elapsed = time.perf_counter() - start
        best = min(best, elapsed)
    return (best / iterations) * 1_000_000


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--iterations", type=int, default=2000)
    args = parser.parse_args()

    has_rust = native.native_available()
    print(f"# Complexity analyzer benchmark ({args.iterations} iterations/sample)\n")
    print(f"Rust core available: **{has_rust}**\n")
    print("| Sample (lang) | Python (µs) | Rust (µs) | Speedup |")
    print("|---|---|---|---|")

    for lang, source in _SAMPLES:
        py_us = _time(lambda: native._python_fallback(source, lang), args.iterations)
        if has_rust:
            rust_us = _time(lambda: native.analyze_source_complexity(source, lang), args.iterations)
            speedup = f"{py_us / rust_us:.1f}×" if rust_us > 0 else "n/a"
            rust_col = f"{rust_us:.2f}"
        else:
            rust_col, speedup = "—", "—"
        print(f"| {lang} | {py_us:.2f} | {rust_col} | {speedup} |")

    if not has_rust:
        print(
            "\n_Rust column omitted: `mobiscout_core` is not installed. "
            "Run `maturin develop --release` in `rust_core/`, then re-run this script._"
        )


if __name__ == "__main__":
    main()
