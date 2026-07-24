# Code Review — Mobiscout `framework/` (2026-07)

A ruthless, evidence-based review of the whole project. Every "dead" / "needed"
verdict here comes from a **static import-graph reachability analysis** (relative
imports + package re-exports resolved), not from guesswork; every "bug" is either
read first-hand at `file:line` or reproduced live. Where an earlier claim was
wrong, it is retracted explicitly — calibration is part of the review.

Method recap: parse every `framework/**/*.py` into an import graph, compute the set
reachable from the CLI entry point (`framework.cli.main`), and treat the complement
as dead-for-the-product. 223 / 290 modules are reachable.

---

## 1. The root cause: there is no domain layer

The same value concept is redefined per subsystem, so subsystems cannot talk to
each other without adapters — or worse, they compare unequal *silently*.

| Concept | Definitions | Locations |
| --- | --- | --- |
| `Platform` | **3** | `codegen/ir.py:166`, `model/enums.py:8`, `devices/device_layer.py:22` |
| `TestStatus` | **4** | `reporting/report_generator.py`, `dashboard/models.py`, `execution/parallel_executor.py`, `execution/test_runner.py` (`TestResultStatus`) |
| `TestResult` | **2+** | `dashboard/models.py`, `reporting/unified_reporter.py` |
| `Severity` / `RiskLevel` | **≥3** | `security/types.py`, `analysis/security_analyzer.py` (`SeverityLevel`), `security/advanced/base.py` (`RiskLevel`) |

**Reproduced live — the `Platform` equality trap:**

```
ir.Platform.ANDROID     == "android"                  → False
enums.Platform.ANDROID  == "android"                  → True    # it is a str-Enum
ir.Platform.ANDROID     == enums.Platform.ANDROID     → False   # never equal
```

`model/enums.Platform` is `class Platform(str, Enum)`; the other two are plain
`Enum`. Any `if platform == "android"` works with one and silently fails with
another. This is the exact bug class that made `severity == "critical"` always
`False` in the security CLI (fixed in #218) and that made `dashboard import-results`
dead-on-arrival (fixed in #231). It is a latent-bug *generator*, not a style nit.

**Fix (authorized, in progress): a single `framework/domain/` package** holding
`Platform`, `TestStatus`, `Severity`, and the canonical `TestResult`, each a
`str`-based `Enum` / typed model, imported everywhere. Value-Object pattern.

- *What breaks if the duplicates are deleted and unified?* Nothing — the values are
  identical. A whole class of equality/adaptor bugs disappears.

---

## 2. Necessity map — what is *truly* dead vs merely un-wired

**Correction (important).** A first pass reported "39 modules / 9 631 lines
unreachable from the CLI". That over-counted: the reachability graph did not model
Python's rule that *importing a submodule executes every ancestor package
`__init__`*. Many packages (`ml/`, `selectors/`, `analyzers/`, `fixtures/`) have an
`__init__` that eagerly imports their whole cluster, so those modules **are loaded
at runtime** whenever the package is touched — they are the package's public API,
not corpses. Re-running the analysis with ancestor-`__init__` side-effects credited
gives the accurate figure:

> **14 modules / 4 449 lines are never imported at all** (the rest are loaded via a
> package `__init__` but simply not invoked from a CLI command).

"Dead" therefore splits three ways, and *unreachable ≠ unneeded*:

**(1) Abandoned predecessors — DELETE (a debt, not a loss):**

| Module | LoC | Why |
| --- | ---: | --- |
| `codegen/ir_builder` | 99 | superseded by the live `crawler/to_codegen.py` seam (its own docstring mislabels it) |
| `plugins/languages` | 330 | superseded by the live `codegen/emitters/` registry; zero imports |
| `correlation/{correlator,strategies,types}` | 759 | **superseded by the real Rust correlator** — verified: `rust_core/src/correlator.rs`, exported from `lib.rs` as `RustCorrelator`. The Python copy is a fallback. |
| `utils/code_quality`, `utils/file_utils` | 613 | YAGNI ghost utils (retry/ResultCollector/file wrappers); stdlib / `tenacity` / `pathlib` do it better; `file_utils` is only named in a docstring |
| `ci/{github_actions,gitlab_ci}` | 509 | generator classes superseded by the live template approach (`ci/templates.py`, used by `cli/ci_commands.py`) |
| `analysis/security_analyzer` | 342 | pale duplicate of the mature `security/` subsystem |

**(2) Roadmap-ahead — KEEP (encodes real product intent; wire it, don't delete):**

| Cluster | LoC | Capability (no live equivalent) |
| --- | ---: | --- |
| `ml/` healing cluster | 2638 | ML self-healing. Real, complete parts: `fallback_tracker` (auto-promote a proven fallback to primary — unique), `healing_strategies`, `pattern_recognizer` (flow mining + Gherkin), `visual_detector` (OpenCV/OCR). Stubs to drop: `selector_predictor` (TF/PyTorch `NotImplementedError`), `element_scorer`, `next_step_recommender`, `ml_module`, `analytics_dashboard` (mock data). |
| `api_analyzer/api_log_analyzer` + `storage/event_store` | 1071 | API↔UI assertion synthesis + session persistence/replay — additive, tested |
| `cloud/browserstack` | 280 | cloud device grid (real client; crawl already supports grids via `--cap`) |
| `ml/rico_extractor` | 121 | RICO training-data pipeline → the "raise ML accuracy" roadmap |
| `analyzers/android_analyzer` | 585 | source-structure analysis to *plan a crawl* — a different kind of analysis from `security/` |

**(3) Good ideas in the wrong place — HARVEST into the live path:**

| Module | LoC | Harvest what → where |
| --- | ---: | --- |
| `core/exceptions` | 311 | a well-designed exception hierarchy → fold into the new `framework/domain/` (it is an earlier aborted attempt at exactly that shared layer) |
| `selectors/selector_scorer` (+ builder/optimizer) | 630 | 0..1 selector ranking with XPath-depth / dynamic-text penalties → richer than the live `to_codegen._selector_for` hard-coded scores; lift it in |
| `flow/flow_discovery` | 524 | edge-case detection (error/loading/permission/empty screens) + ML hooks → `graph.py` (the live flow successor), then delete the rest |
| `security/config` | 341 | argon2 hashing + secret-pattern list → the live `security/` |

`reporting/base_reporter` (261) is an abstract base the live `unified_reporter`
should inherit from but reimplements — refactor, don't delete. `fixtures/{camera,
device}` are **not dead**: they are the shipped fixture library that *generated*
test projects import (loaded via `fixtures/__init__`, which the live crawler
`waypoints` reaches). KEEP.

**Sobering note for this session:** `code_quality`, `file_utils`, `flow_discovery`,
`event_store`, `browserstack`, `api_log_analyzer` were all made mypy-clean in
PRs #229–#231 — and every one is in the dead/un-wired set. ~2 000 lines of corpses
were polished, and `unit-test-everything` partly tests them, so the coverage number
is inflated by code the product never runs.

**Decision (owner, 2026-07-24):** update this doc first (done), then **wire the
roadmap-ahead clusters to the CLI one by one** rather than park or delete them.

---

## 3. Live-code findings (calibrated)

### Confirmed / real
- **`selectors/_python_common.py:48` — broken UiSelector TEXT strategy.**
  `locator_value` interpolates `sel.value` raw into `new UiSelector().text("{value}")`
  *before* `py_str` escaping. The outer Python literal is valid, but text containing
  `"` breaks the inner UiSelector DSL (unbalanced quotes → Appium mis-parses).
- **`selector_discovery.py:205` — XPath injection.** `f"//{cls}[@text='{text}']"`
  unescaped; text with `'` yields invalid XPath, healing fails silently. (This module
  is in the dead cluster, so severity is contingent on it being wired.)
- **mypy config is lax.** `disallow_untyped_defs=true` + `warn_return_any=true` are
  good, but `ignore_missing_imports=true` and no `check_untyped_defs`,
  `no_implicit_optional`, `warn_unreachable`, `disallow_any_generics`. "mypy = 0" is
  weaker than it sounds, and mypy is `continue-on-error` in CI (does not block).

### Retracted (were overstated by the first agent sweep)
- **`graph.py:168` `id(e)` dedup — NOT a correctness bug.** `covered.add(id(x))`
  (line 179) is populated; edge objects live for the whole call, so `id()` is stable
  within and across runs. Downgraded from HIGH to cosmetic (prefer content identity).
- **Codegen string injection — mostly a non-issue.** `kotlin_str`/`py_str` escape
  backslash, quote, `$` (Kotlin templates), and control chars correctly. Good code.
- **"TYPE_CHECKING forest ⇒ circular dependencies" — false.** Only 6 files use it;
  normal, not a smell.

### What is genuinely good
- No god-objects: the largest file is 638 lines.
- The live seam `crawler → to_codegen → IR → emitters` is clean; the emitter registry
  self-registers, so a new codegen target is trivial (see `skills/new-codegen-target`).
- Golden-file + multi-language compile gates for all 8 emitter targets.

---

## 4. Algorithms & performance (live modules)

- **`graph.py:324` — O(n²) maximal-path filter.** `any(other[:len(p)]==p …)` over all
  path pairs; for deep crawls (~1000 paths) ≈ 1e6 comparisons. Sort by length once and
  linear-scan to drop prefixes → O(n log n). Matters given the "speed" priority.
- **`graph.py:323` vs `:328` — `edge_coverage_paths()` computed twice.** Cache it.
- **`to_codegen.selector_for` — no per-screen memoization.** The Compose fallback runs
  a contains-loop per element; called repeatedly per screen (O(n²)). Cache
  `{element_id: selector}` within a screen.

---

## 5. Concurrency (spot-check)
`mocking/proxy.py` uses `ThreadingHTTPServer` + a `threading.Lock` (line 223) with a
daemon serve thread — basic discipline is present. A full audit of the daemon /
dashboard-server / proxy shared state is a targeted follow-up, not yet done.

---

## 6. Prioritized backlog

Landed: `framework/domain/` (Platform ×3 + TestStatus ×4) — #232; `graph.py`
O(n²)→O(Σlen) + single edge-paths call — #233; systemic `ua_escape` for UiAutomator
selectors — #234.

Remaining, in order:

1. **Wire the roadmap-ahead clusters (§2 group 2) to the CLI one by one** *(owner
   decision, 2026-07-24)* — ML self-healing, `api_log_analyzer`, `event_store`,
   `cloud/browserstack`, `rico_extractor`. Each gets a real command + tests; drop the
   stubs inside `ml/` as they are reached.
2. **Harvest the good-ideas-wrong-place (§2 group 3):** `core/exceptions` → `domain/`;
   `selector_scorer` ranking → `to_codegen`; `flow_discovery` edge-case detection →
   `graph.py`; `security/config` argon2/secret-patterns → `security/`.
3. **Delete the abandoned predecessors (§2 group 1):** `ir_builder`, `plugins/languages`,
   `correlation/*` (Rust-superseded), `code_quality`/`file_utils`, `ci/{github_actions,
   gitlab_ci}`, `analysis/security_analyzer` — with their now-dead tests.
4. **Make mypy blocking** + tighten config; add a per-module coverage floor so new code
   in low-coverage subsystems can't merge untested.
5. **CliRunner coverage** for the command layer (the "dead-on-arrival" class).
6. **XPath escape** in `healing/selector_discovery` (once healing is wired); full
   concurrency audit of daemon / dashboard-server / proxy.
