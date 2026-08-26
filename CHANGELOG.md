# Changelog

All notable changes to **Mobiscout**.

The format is based on [Keep a Changelog](https://keepachangelog.com/) and this
project adheres to [Semantic Versioning](https://semver.org/). Versioned releases
began at 0.9.0; everything before that is summarised under *Pre-release
development*, whose authoritative record is the PR-linked git history.

## [0.12.3] — 2026-08-26

Second deep-review pass: 57 independently verified defects. The headline is that a
generated kit now compiles on realistic input — several targets did not.

### Fixed — generated kits
- **A test kit no longer breaks on ordinary labels.** An element label containing a
  newline (common in Compose paragraphs) used to push text out of a comment as raw
  source, breaking the emitted Python, Java, Kotlin, JavaScript *and* Maestro files;
  a screen titled like "2FA Setup" produced a method name starting with a digit that
  Java and Kotlin reject. Verified with the real toolchains (`javac`, `node --check`,
  `ast.parse`, YAML): 11 failures before, none after.
- BDD kits: the locator registry no longer desyncs from the feature file's step
  arguments (a quoted or multi-line label caused a lookup failure at run time).
- Smoke kits no longer emit duplicate test names (Python silently lost tests; Java
  wouldn't compile), and page-object classes are named from sanitized screen titles.
- Espresso kits: long-press/scroll-to/deep-link/key-press are emitted or honestly
  reported as skipped instead of silently dropped, and the Activity import points at
  the real class.
- `launch_args` and the `MOBISCOUT_APPIUM_SERVER` override now work in every target,
  not only Python — the scaffold READMEs already promised both.

### Fixed — crawling and coverage
- A login gate reached **mid-crawl** left the entire post-auth area marked unreachable
  and generated no tests for it, while the coverage report said it was explored.
- Tests for a gated screen now include the steps that reach the login form; they used
  to start typing credentials on the launch screen and fail by construction.
- Diff-aware regeneration keeps launch args and toolkit; the manifest records the
  crawl, not the filtered delta; coverage no longer counts elements no test can target.

### Fixed — environment and reliability
- Windows: every device/tool command is read as UTF-8, and the engine pins its own
  stdio — a non-ASCII device name or profile path no longer breaks the connection.
- An SDK path that no longer exists is reported as broken instead of passing; an
  emulator that fails to launch is reported as failed instead of "starting"; a missing
  or timed-out `adb` says so instead of showing an empty device list.
- `mobiscout doctor` no longer fails on projects that aren't the framework's own repo.
- The MCP server survives a bad request instead of exiting.

### Fixed — security scanning
- The TLS check could never detect TLS 1.0/1.1 support on a modern OpenSSL — a silent
  false negative for the weakness it exists to find. Verified against a real
  TLS1.0-only server.
- Web-view crawling: a stale element tag could send a tap to the wrong element, and a
  failed web tap no longer falls back to a raw screen-coordinate tap.
- Element classification now feeds the model the fields it was trained on, and model
  auto-training is reproducible, so the same crawl generates the same kit everywhere.

## [0.12.2] — 2026-08-26

Project-wide review pass: crawl-safety, engine robustness, and honest UI.

### Fixed — crawler
- The screen behind a mid-crawl gate (a login/OTP reached by tapping into it) is now
  **explored**, not just recorded and abandoned — the whole post-auth app used to be
  mapped as a single unexplored node.
- Form fields are **cleared before typing**, so a negative-then-positive fill no longer
  concatenates into `invalid@valid` and tests both branches for real.
- A permission grant (and the blocking-dialog handler) never taps **"Don't Allow"**
  again — "allow" is a substring of both, so an affirmative-only match is used.
- A **money field revealed by scrolling** now re-arms the money gate, so a Send/Confirm
  below the fold stays blocked by default.
- Onboarding auto-skip no longer treats **"Done"** as a skip, so a real "Welcome back"
  screen with a Done button is left alone.
- After a failed return-to-parent the crawler **re-checks the live screen** instead of
  tapping a frame's now-stale coordinates.
- A TOTP waypoint with no secret is skipped instead of ending the crawl.

### Fixed — engine / daemon
- iOS swipe direction corrected (a finger-up swipe scrolls content the right way).
- Screenshot capture is platform-aware — a host without adb no longer crashes the
  request on iOS.
- An Android tap that the device rejects is reported as an error, not a fake success.
- TCP debug transport: log-stream notifications reach the connected client, and one
  client disconnecting no longer takes the daemon down.
- Stopping the log stream now actually stops it (terminate → kill → reap).
- The Rust-core ABI gate accepts 2-part and prerelease version strings.

### Fixed — IDE plugin
- Generate dialog no longer leaves a large dead area when **Advanced** is collapsed.
- The screen mirror scales to fit a short/narrow tool window; the Live toggle stops and
  warns once on a capture failure instead of storming a balloon every refresh.
- Engine start/stop, screenshot, refresh and detect actions report the real cause and
  never freeze the UI thread; a stopped engine clears the live session.
- Feature list trimmed to what's actually wired (tap, log streaming, a flat element
  inventory) — no more overclaimed swipe/type, log filtering, or an XML tree viewer.

### Fixed — packaging
- The frozen engine bundles `Appium-Python-Client` metadata, so an iOS/Appium crawl no
  longer fails with "No package metadata was found".

## [0.12.1] — 2026-08-25

Crawl-safety follow-ups.

### Fixed
- **Money-screen detection uses field-level evidence** — a transfer form whose amount input
  is recognisable only from its id (e.g. `…/amount_field`), with no visible currency symbol
  or hint word, is now treated as a money screen, so its "Send"/"Confirm" is blocked by
  default. The "is this an amount field" test is single-sourced with the form-fill logic so
  the two can't disagree. OTP ("Send code"), phone-OTP and messaging screens stay non-money
  and are still crawled.

### Changed
- `CHANGELOG.md` is now checked against `framework.__version__` in CI, so a version bump
  can't ship without a changelog entry (the two change-note homes can't drift again).

## [0.12.0] — 2026-08-25

Tool-window polish, safer-by-default crawls, and a hardened Python↔Rust engine seam.

### Added
- **Live screen mirror** — a "Live" toggle on the Screen panel auto-refreshes the device
  mirror while a session is active (the capability the removed "screenshot refresh interval"
  setting had only promised); the timer is tied to the tool-window lifecycle, so it never
  outlives it.
- **Inspector locators** — the Inspector is now a selectable element list: **Copy locator**
  (the most stable id/text/content-desc) and **Generate selector** (a ranked, self-healing
  selector via the engine's `selector/generate`) for the picked element.
- **`mobiscout doctor` native-core line** — reports the active backend: `Rust acceleration
  active (mobiscout_core x.y.z)` or a warning with the `maturin develop` fix.

### Changed
- **Native tool-window toolbars** — Devices, Screen, Logs and Inspector use real IDE
  `ActionToolbar`s (icons, tooltips, theme, keyboard); their actions enable/disable from
  state via `update()` instead of manual toggling.
- **Generate-kit dialog** — the rarely-used knobs collapse under an "Advanced" group; the
  output directory has a Browse button and resolves relative paths against the project;
  file pickers use the IDE chooser; the mislabeled "Language" field is now "Language /
  target"; validation (device↔platform, positive crawl limits, build-needs-device) runs
  before the dialog closes.
- **Honest progress & logs** — the crawl progress bar reflects the live stream instead of a
  frozen "Crawling…"; errors are non-modal balloons; the Logs view is bounded and only
  autoscrolls when already at the tail.
- **Rust core** — version-gated across the PyO3 seam (`mobiscout_core` 0.2.0); the SAST
  scanner splits lines once in Python so both backends agree exactly; ~1,200 lines of dead
  Rust (correlator/business-logic/io) removed from the shipped binary.

### Fixed
- **Never freezes the IDE** — every engine RPC runs off the EDT, asserted at the service
  boundary (`assertBackgroundThread`); menu Start/Stop and screenshot capture were the last
  offenders.
- **Crawl safety** — a default crawl never taps money-moving controls (Pay/Buy/Transfer/…
  always; Send/Confirm/Exchange only on a screen with a money field), while OTP "Send code",
  messaging and email-confirmation flows are still crawled; blocklist matching is now on word
  boundaries (no more `pay`→"PayPal"). Use `--allow-destructive` only on sandbox apps.
- **Kit output** lands in the project (not the IDE's working dir) with an "Open folder"
  action; the tool-window status dot stays honest when the engine is stopped from the menu;
  the device picker no longer mis-parses a name with parentheses ("iPad Pro (11-inch)").
- **CLI `--help`** keeps the Examples blocks on separate lines; removed four dead-on-arrival
  Tools-menu actions that called non-existent commands.

## [0.11.0] — 2026-08-23

A new codegen target, an AI-agent interface, and two crawl-intelligence artifacts.

### Added
- **Maestro codegen target** — a 9th target: declarative [Maestro](https://maestro.dev)
  YAML flows, cross-platform and Appium-free. Each test case becomes one `<case>.yaml`
  flow; selectors Maestro can't express (XPath / class-name) are honestly annotated as
  skipped, never faked.
- **MCP server** (`mobiscout mcp`) — a dependency-free
  [Model Context Protocol](https://modelcontextprotocol.io) server (JSON-RPC over stdio)
  that exposes the engine as tools (`list_targets`, `generate_tests`, `crawl_app`), so an
  AI agent can drive it. The engine stays deterministic and offline — no runtime LLM; MCP
  is only the interface.
- **Coverage artifact** — every kit now includes `coverage.md` + `coverage.json`: an honest
  map of what the crawl reached versus what the generated kit tests (reachable / unreachable
  / gated / dead-end screens, plus conservative element and screen coverage percentages).
- **Diff-aware regeneration** (`crawl --diff` / `--only-changed`) — a kit records a
  `manifest.json`; the next crawl writes a `CHANGES.md` classifying every test as
  added / changed / removed, and can emit just the delta instead of regenerating the whole
  app.

## [0.10.0] — 2026-08-22

One path, zero setup — plus a round of audit-driven correctness fixes.

### Added
- **Project autodetect** — "Detect from project…" reads the repo and fills the
  Generate form from the app(s) it finds (Android `applicationId`, iOS bundle id).
- **Multi-app generation** — a project's Android + iOS apps can be generated in one
  action, crawled in parallel, each on its own device (`kit/generateMany`).
- **Auto-boot a device** — when nothing is running for the app's platform, the
  Generate flow boots a candidate (an installed AVD, or a shut-down simulator) and
  waits for it, instead of returning an empty crawl. You're only asked when there is
  genuinely nothing to boot.
- **Persistent device pools** — `devices pool create` now registers real devices and
  persists pools (`MOBISCOUT_POOLS_PATH`), so `pool list` and allocation see them.

### Changed
- The setup wizard is gone: the engine self-installs and starts in the background.
- `load profile <test_path>` now runs your actual test(s) under the profiler instead
  of a placeholder sleep.
- Dashboard `POST /api/selectors/{id}/approve` now writes the healed selector into the
  source file (optionally git-committing) before marking it approved.

### Fixed
- **`python_pytest` TEST_DATA key collision** — a model with both a positive and a
  negative case on the same field kept only the negative value, so the flagship login
  journeys typed invalid credentials and failed. Keys are now unique per (field, value).

## [0.9.1] — 2026-08-20

### Fixed
- Android works when the IDE is launched from Finder/Dock — the engine resolves the
  Android SDK onto `PATH`, so `adb`/`emulator` are found.

### Changed
- Generate Test Kit: device is a dropdown of running devices; the form leads with the
  essentials and groups the rest under "Advanced".
- Devices tab shows running/connected devices first, with platform glyphs and coloured
  status. Errors and results use notification balloons; a 0-screen crawl is reported
  honestly as a warning, not a success.

## [0.9.0] — 2026-08-20

First public beta and first versioned release.

### Added
- Point the IDE at a running app and get an element inventory, an interaction graph,
  and runnable tests, without leaving the IDE.
- Zero-install engine: per-OS standalone binaries downloaded on first use.
- Runnable-project scaffolds for Java (Maven) and Kotlin (Gradle).
- Anti-flake generated tests: a `settle()` wait after each transition.
- Stream app logs and capture crashes into the kit.

## Pre-release development

Before 0.9.0 the project had no versioned releases; the record below groups the major
feature waves. It is a summary — the authoritative, dated, PR-linked history is in git
(`git log`), from the first commit on 2025-12-19 onward.

- **MVP foundation** — crawl → model → codegen skeleton; the first emitters and CLI.
- **Correlation & model building** — interaction graph, screen/element correlation.
- **Production features** — obstacle/gate handling, WebView crawling, resilience.
- **ML & advanced features** — hybrid ML + heuristic element typing.
- **Enterprise integration & deep analysis** — security/a11y analysis, API contract
  tests, source-aware analysis.
- **Self-healing tests & maintenance dashboard** — `FailureAnalyzer`,
  `SelectorDiscovery`, `ElementMatcher`, `FileUpdater`, `GitIntegration`, the
  `mobiscout heal` commands, and the FastAPI + SQLite maintenance dashboard.

[0.10.0]: https://github.com/VadimToptunov/Mobiscout/releases/tag/v0.10.0
[0.9.1]: https://github.com/VadimToptunov/Mobiscout/releases/tag/v0.9.1
[0.9.0]: https://github.com/VadimToptunov/Mobiscout/releases/tag/v0.9.0
