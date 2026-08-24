# Review — R-backlog verification + first Rust-core review (2026-08-24, evening)

Fifth evidence-based pass. [REVIEW_2026-08-24_UX.md](REVIEW_2026-08-24_UX.md) left a
7-item backlog (R1–R7); this pass **verifies its same-day remediation (#455–#461) at
`file:line`** and then covers the one part of the codebase no review had ever read:
**`rust_core/`** — which stopped being optional the moment #430 made it mandatory in the
shipped engine and #432 put it on the SAST hot path. Both headline findings below were
**reproduced by execution**, not inferred; the repro commands are inline. Finding IDs are
RC1–RC4 for commit references.

## Gates (measured on this tree)

| Gate | Result |
| --- | --- |
| `pytest tests/` | green (exit 0) — the R1 red test is fixed |
| flake8 C901 ratchet | **turned 22 → 21** (#461), 0 violations |

(mypy/black/interrogate not re-run this round: since the last pass only Kotlin and two
ratchet-covered CLI files changed.)

## R1–R7 remediation — verified, all real

| ID | Verification |
| --- | --- |
| R1 | ✓ #455 — the env-dependent native-backend test now monkeypatches `_native_core` instead of assuming the wheel is absent, with the mirror test ("rust with the real wheel") under `skipif` — exactly the proposed shape; suite fully green |
| R2 | ✓ #456 — the dialog loads via `DeviceList.load("all").filter { it.status != "shutdown" }`; `DeviceItem` gained `status`; the module docstring was rewritten honestly (the editable-String combo is now explicitly described, not overclaimed) |
| R3 | ✓ #457 — `doValidate` catches platform↔device mismatch (only for engine-listed devices — correct caveat for hand-typed UDIDs) and rejects garbage in Max steps/depth via `positiveIntError` instead of silently coercing to 40/8 |
| R4 | ✓ #459 — `LiveToggleAction` (`ToggleAction` + `javax.swing.Timer`), drops itself when the session ends; the commit ties it back to the deleted dead setting |
| R5 | ✓ #458 — the daemon tags the app-log stream `source="device"` (`daemon_commands.py:752`); `liveProgressListener` filters it out |
| R6 | ✓ #460 — Inspector actions on a native ActionToolbar |
| R7 | ✓ #461 — `ci validate` split into per-system helpers; the ratchet actually turned (22 → 21, 0 violations) — the written lower-as-you-go plan is being executed |

Second consecutive fully-real remediation round, including the discipline item (turning
the ratchet immediately after the refactor that enabled it).

---

## New findings — the Rust core

### RC1 — P1: "Results are identical either way" is false, twice (both reproduced)

**(a) `scan_lines` — the two backends split lines differently.**
The Python fallback uses `str.splitlines()` (splits on `\x0c`, `\u2028`, `\u2029`,
`\x85`, …); the Rust side uses `str::lines()` (splits on `\n` only). Reproduced:

```python
tricky = "md5\x0cmd5\u2028md5\ndes"
core.scan_lines([tricky], [r"\bmd5\b", r"\bdes\b"], True)
# rust: [(0, 1, 0, 'md5\x0cmd5\u2028md5'), (0, 2, 1, 'des')]   — 2 "lines", 2 hits
# py  : [(0,1,..), (0,2,..), (0,3,..), (0,4,..)]               — 4 lines,   4 hits
```

For a file containing form-feed page breaks (`^L` — a real convention in Python source)
or U+2028, a SAST finding's `line_number` **and the number of findings** differ by
backend. [`native.py:72`](../framework/analyzers/native.py) claims "Results are
identical either way".

**(b) `analyze_source_complexity` — the numbers diverge materially.**
Same snippet through both backends:

```
rust (tree-sitter): cognitive=14  nesting=4
py   (stdlib ast):  cognitive=4   nesting=2     (cyclomatic/loc/fn/cls agree)
```

`SourceComplexity.risk_level` bands on cognitive at 15/30 — project-analysis verdicts
**flip depending on whether the wheel is installed**.

The good news, also verified by execution: all 40 real SAST rule patterns (12 crypto +
28 insecure-api) compile in Rust's `RegexSet` — no silent whole-batch degradation to the
Python path today. One landmine for later: `patterns.py:74` (`CONFIG_PASSWORD`) uses a
negative lookahead `(?!…)` the Rust regex crate cannot compile; it is not in the batched
set now, but adding it would silently drop the whole batch to Python (the `except
Exception` fallback in `native.scan_lines` hides it).

**Fix direction:** normalize line-splitting on one side — simplest is to split in Python
and pass line lists, which eliminates divergence (a) entirely; add a cross-backend
parity test gated with `skipif` when the wheel is present (the mirror of #455's
technique); for (b), either align the counters or stop claiming parity and pick one
backend per metric. Also worth logging (once) when the Rust batch path falls back, so a
future incompatible pattern doesn't silently cost the 35x.

### RC2 — P2: ~1,170 lines of dead Rust ship in the now-mandatory binary

`correlator.rs` (535 lines), `business_logic.rs` (339), `io.rs` (299) are registered in
the pymodule — and have **zero Python consumers** (grep for `RustCorrelator`,
`RustBusinessLogicAnalyzer`, `read_file_fast`, `read_files_parallel`, `find_files`, … —
empty). Since #430 every release binary compiles and carries them. This is the same
dead-exposed-API class the July review purged from the Python side; `lib.rs`'s header
still advertises all three. Also `test_module_loads` is `assert!(true)` — the
tautological-test class P2.11 removed from the Python suite. The live parts of the core
are `ast_analyzer` (real tree-sitter parsers, not heuristics) and `sast_scan`.
**Fix:** delete (git keeps them) or wire them; either way stop advertising them.

### RC3 — P2: a third EDT-blocking entry point — `CaptureScreenshotAction`

[`CaptureScreenshotAction.kt`](../jetbrains-plugin/src/main/kotlin/com/mobiletest/recorder/actions/CaptureScreenshotAction.kt)
calls `daemonService.getScreenshot(…)` synchronously in `actionPerformed` — a blocking
RPC (an Appium screenshot takes seconds; the client's timeout backstop is 600 s). Third
uncovering of this class (P0.4b, U2, now here) — so fix the class, not the instance:
assert `ThreadingAssertions.assertBackgroundThread()` inside the service's RPC wrappers,
so the next EDT call fails loudly in dev instead of waiting for a review to find it.

### RC4 — minor: `scan_lines` returns dead payload

Each hit carries `line.to_string()`; the only consumer
([`_scan.py:21`](../framework/security/sast/_scan.py)) discards it (`_line`). One
allocation per match for a field nobody reads — drop it from the tuple (or gate it
behind a flag) next time the signature is touched.

## Backlog, in order

1. [ ] RC1 — backend parity: split lines on one side; cross-backend parity test
       (`skipif`-gated); align or de-claim the complexity counters; log the silent
       Rust-batch fallback.
2. [ ] RC3 — background-thread assertion in the daemon-service RPC wrappers, then move
       `CaptureScreenshotAction`'s RPC off the EDT.
3. [ ] RC2 — delete or wire the dead Rust modules; fix `lib.rs`'s header; replace the
       tautological Rust test.
4. [ ] RC4 — drop the unused line text from the `scan_lines` tuple.

## Calibration

**By execution:** the full pytest suite; both flake8 passes; the RC1 line-splitting and
complexity divergences (commands above); the RegexSet compatibility check of all 40
batched SAST patterns.

**By reading at `file:line`:** every R-verification; RC2's consumer search; RC3.

**Not checked:** the Rust core's behaviour on non-UTF-8 input (PyO3 `Vec<String>`
implies valid UTF-8 at the boundary — what the Python side does with undecodable files
before the call was not traced); `analyze_directory`'s parallel path (unused from
Python today); the plugin at runtime inside an IDE.
