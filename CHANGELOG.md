# Changelog

All notable changes to **Mobiscout**.

The format is based on [Keep a Changelog](https://keepachangelog.com/) and this
project adheres to [Semantic Versioning](https://semver.org/). Versioned releases
began at 0.9.0; everything before that is summarised under *Pre-release
development*, whose authoritative record is the PR-linked git history.

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
