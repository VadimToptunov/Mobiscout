# Mobile Test Recorder → JetBrains IDE Plugin: Roadmap

_Last reality-check: 2026-07-07. Target: a polished, sellable product by ~September 2026._

This roadmap is kept honest: it describes what actually exists in the code, not
what we hope to build. Quality over speed — each item ships tested and documented
before the next begins.

---

## Vision

A **JetBrains IDE plugin** (works in every JetBrains IDE via the platform SDK)
backed by a local Python + Rust engine. You point it at a running app, say what
you want by parameters, and get the artifacts a tester needs — an element
inventory, an interaction graph, structural findings, and runnable tests — into a
new or existing framework, without leaving the IDE. Local-first: no servers, no
SaaS.

Supported today: **4 languages** (Python, Java, Kotlin, JavaScript), each
imperative **or** BDD; **Appium** (Android UiAutomator2 + iOS XCUITest) and
on-device **Espresso**.

---

## Status at a glance

| Area | State |
|---|---|
| Plugin shell (ToolWindow, devices, screenshot+click-to-tap, session, settings, wizard) | ✅ done |
| Daemon bridge (JSON-RPC) | ⚠️ partial — 11 methods; the codegen/analysis half needs wiring |
| Autonomous crawl → kit (inventory + graph + tests) | ✅ done, proven live (Compose app, iOS Settings) |
| Interaction graph + Mermaid/DOT/JSON + structural invariants | ✅ done |
| Multi-language codegen (8 targets, POM + BDD, 11 IR actions) | ✅ done |
| Gates layer (TOTP, biometric, QR/document scan, permissions) — provider-aware | ✅ done |
| Crawler waypoints (pass login/OTP/biometric to explore behind gates) | ✅ done |
| Coverage-diff (generate only what isn't already tested) | ✅ done |
| Security (OWASP), accessibility (WCAG), fuzzing | ✅ done |
| ML element typing (hybrid RF + heuristic, auto-provisioned) | ✅ done |
| Environment intelligence (Appium/driver/SDK version checks) | ❌ not started |
| Self-healing wired into the flow (`selector_healer` module exists but isolated) | ⚠️ island |
| Rust-core benchmarks (the perf numbers are unmeasured) | ❌ not started |
| Static analysis: flow reconstruction from source | ❌ not started |
| LSP (flow-aware autocomplete, go-to-screen) | ❌ not started |
| Monetization / licensing | ❌ explicitly LAST |

---

## What's built (the engine + plugin)

**Plugin (Kotlin, all JetBrains IDEs):** ToolWindow with Devices / Screen /
Inspector / Logs; live screenshot with click-to-tap; session management; a Setup
Wizard + settings that capture the user's context (app, source path, platform,
language/framework, credentials, output dir); a JSON-RPC client to the engine.

**Engine (Python + `rust_core`):** one parameterized entry (`run_kit`) drives
both the CLI and the plugin. From a running app it produces:

- a per-screen **element inventory** (semantic type + ranked, self-healing locator);
- the **interaction graph** (reachability, depth, cycles, dead-ends, hubs) exported
  as Mermaid / DOT / JSON, plus **structural invariants** (unreachable / dead-end /
  no-return screens);
- **runnable tests** in 4 languages × imperative/BDD, flat **or** framework-structured
  (Page Objects + conftest), including **multi-step, form-filling paths**;
- **API contract tests** from an OpenAPI/Swagger file or URL;
- an **accessibility audit** and an **APK/IPA security scan** (OWASP-mapped).

Cross-cutting: a **gates/fixtures** layer (TOTP, biometric, QR/document scan,
permissions — provider-aware for emulator / BrowserStack / real device),
**crawler waypoints** to explore behind gates, and **coverage-diff** to generate
only what a team's existing tests don't already cover.

---

## Remaining work to September 2026 (prioritized, quality-first)

The order favours hardening and the plugin's real usefulness first, features next,
monetization last.

### 1. Hardening — live end-to-end + clean+cover
- Run the whole kit on real apps (Android Compose + iOS) and **actually execute**
  the generated tests; fix what device-reality surfaces.
- Remove vaporware/stubs (`observe record` print-stubs, the unimplemented `mock
  record` proxy, the dead self-learning upload endpoint, unused `backends/`),
  making the docs honest and raising **real** test coverage.
- Ratchet the docstring + coverage gates up.

### 2. Daemon protocol completion (unblocks the plugin doing real work)
- Wire the engine's power through the daemon: `codegen/generate` (via `run_kit`),
  `flow/getGraph` (via the interaction graph), `environment/detect`,
  device start/stop, log streaming, `selector/generate`.
- Fix `ui/getTree` (currently a hardcoded mock) and `session/start` (no real
  Appium session) to return real data.

### 3. Environment Intelligence (roadmap Phase 4)
- Detect installed Appium server + drivers (uiautomator2/xcuitest), Android SDK,
  Xcode; compare against latest; flag incompatibilities and **deprecated Appium
  APIs**; offer copy-paste install/fix commands. An Environment panel in the IDE.

### 4. Wire self-healing (roadmap Phase 6)
- Connect the existing `selector_healer` to the real flow (as ML typing and the
  graph were): when a locator breaks, heal from the inventory / fallback chain;
  surface healing + stability hints in the IDE editor.

### 5. Honest Rust benchmarks (roadmap Phase 5)
- Criterion benchmarks for the Rust modules; publish measured numbers and delete
  the unverified "16x" claims (or back them with data).

### 6. Static analysis: flow-from-source (roadmap Phase 9)
- When source is available, reconstruct flows and identify edge/fuzz points, to
  complement the runtime crawl. (Security/fuzzing already exist.)

### 7. LSP (roadmap Phase 10)
- A language server for flow-aware autocomplete of screen/action names and
  go-to-screen navigation in the IDE.

### 8. Monetization (roadmap Phase 11) — LAST
- Offline license keys + PRO/Enterprise feature gating, and configurable CI/CD +
  **TestRail** result reporting. Not started until the above are solid.

---

## Monetization (when the product is ready)

One-time purchase, no subscriptions, no servers.

| Tier | Price | Adds |
|---|---|---|
| Free | — | device control, inspector, basic crawl |
| Individual (PRO) | $79 | multi-language codegen, framework-structured output, healing, flow analysis |
| Team (5 seats) | $299 | shared flow models, team policies |
| Enterprise | $1,499 | static analysis, security audit, TestRail/CI reporting, priority support |

Distribution: JetBrains Marketplace (primary) + direct sales for Enterprise.

---

## Principles

1. **Quality > speed.** Each item is production-ready — tested, documented, honest —
   before the next.
2. **Local-first.** Everything runs on the user's machine.
3. **Parameterized, not magic.** The user configures what they want; the tool
   doesn't guess or force upgrades.
4. **One IR, many targets.** Adding a language/framework is adding an emitter.
5. **Rust for genuine hot paths only** (`rust_core`); Python for orchestration and
   ML; the tool is device/IO-bound, so no rewrite is warranted.
6. **Honest docs.** No claimed feature without working code behind it.

---

## Success metrics (measured, not aspirational)

- Generated code compiles/parses across all targets — **enforced in CI**.
- Every module unit-tested; coverage + docstring gates ratcheting up — **enforced**.
- Crawl → kit proven live on real Android + iOS apps — **partially done, expanding**.
- Rust-core latency — **TODO: benchmark, then state real numbers**.
- Selector healing success rate — **TODO: wire healing, then measure**.
