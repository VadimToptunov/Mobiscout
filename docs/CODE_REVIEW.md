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

## 2. Necessity map — 39 modules / 9 631 lines unreachable from the CLI (18%)

These form **parallel / aborted subsystems that reference only each other**. This
is *not* an automatic "delete" list — Mobiscout is open-core and some of these are
roadmap features documented ahead of their wiring (e.g. the Event Correlator is
documented as a Rust component in `docs/TECHNICAL_DESIGN.md`). Each needs a
public-API / pytest-fixture / dynamic-import check before removal. Verdict column:
**DUP** = duplicates a live module, **ROADMAP** = documented-but-unwired feature,
**GHOST** = built, tested, never referenced.

| Package | LoC | Modules | Verdict |
| --- | ---: | --- | --- |
| `ml/` (healing cluster) | 2638 | `selector_predictor`, `pattern_recognizer`, `selector_healer`, `visual_detector`, `analytics_dashboard`, `fallback_tracker`, `healing_strategies`, `next_step_recommender`, `element_scorer`, `ml_module`, `ml_base`, `healing_types`, `rico_extractor` | ROADMAP? — second ML system, parallel to the live `element_classifier`+`universal_model`+`classify` typing path |
| `correlation/` + `api_analyzer/` + `storage/event_store` | 1830 | `correlator`, `strategies`, `types`, `api_log_analyzer`, `event_store` | ROADMAP — API↔UI correlation; Rust twin documented |
| `utils/` | 785 | `code_quality`, `file_utils`, `validator` | GHOST — enterprise utils never wired |
| `selectors/` | 630 | `selector_builder`, `selector_optimizer`, `selector_scorer` | DUP of live `crawler/to_codegen` + `selectors/advanced_selector` |
| `analyzers/` | 585 | `android_analyzer`, `base_analyzer`, `analysis_result` | DUP of live `security/` |
| `flow/flow_discovery` | 524 | 1 | ROADMAP — flow mining not wired to CLI |
| `ci/` | 509 | `github_actions`, `gitlab_ci` | GHOST — CI-config generators |
| `analysis/security_analyzer` | 342 | 1 | DUP of `security/` |
| `security/config` | 341 | 1 | GHOST |
| `plugins/languages` | 330 | 1 | **DUP (confirmed dead)** — abandoned plugin-codegen, parallel to live `emitters/` registry, zero external imports |
| `core/exceptions` | 311 | 1 | GHOST — used only by the dead `utils/code_quality` |
| `cloud/browserstack` | 280 | 1 | GHOST/ROADMAP |
| `reporting/base_reporter` | 261 | 1 | GHOST |
| `fixtures/` | 166 | `camera`, `device` | check: may be pytest fixtures |
| `codegen/ir_builder` | 99 | 1 | **DUP (confirmed dead)** — its own docstring calls it the "explore→automate seam", but the live seam is `crawler/to_codegen.py`; superseded and abandoned |

**Sobering note for this session:** `code_quality`, `file_utils`, `flow_discovery`,
`event_store`, `browserstack`, `api_log_analyzer` were all made mypy-clean in
PRs #229–#231 — and every one of them is in the dead list above. ~2 000 lines of
corpses were polished. `unit-test-everything` also partly tests them, so the
coverage number is inflated by dead code.

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

1. **`framework/domain/` layer** — unify `Platform`/`TestStatus`/`Severity`/`TestResult`;
   kills the equality-trap bug class. *(Authorized; safe/additive.)*
2. **Decide dead-code fate** (§2) per cluster: delete GHOST/DUP, wire-up or `.coveragerc`-exclude
   ROADMAP. Blocked on owner decision for the ROADMAP clusters.
3. **`graph.py` O(n²) + double-compute** (§4) — speed.
4. **`_python_common.locator_value` inner-quote fix**, XPath escape in `selector_discovery`.
5. **Make mypy blocking** + tighten config; add per-module coverage floor so new code in
   low-coverage subsystems can't merge untested.
6. **CliRunner coverage** for the command layer (the "dead-on-arrival" class).
