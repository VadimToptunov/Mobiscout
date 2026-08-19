# Mobiscout — Release Roadmap

_Reality-check: 2026-08-19. Goal: ship a free, genuinely useful **1.0** to the
JetBrains Marketplace soon, then grow it open-core._

This is the **product / release** roadmap — what to ship and in what order. For the
detailed, honest engineering status of the plugin + engine, see
[JETBRAINS_PLUGIN_ROADMAP.md](JETBRAINS_PLUGIN_ROADMAP.md).

Mobiscout is **open-core**: this repository is the MIT-licensed engine + plugin and
stays fully functional on its own; a separate private layer (cloud grid, in-run
network mocking, licensing) adds team/CI capabilities. The public engine is never
crippled — that's the top of the funnel.

---

## Where we are

- **Engine — mature.** Autonomous crawl → kit (inventory + interaction graph +
  runnable tests), 10 codegen targets (pytest / Espresso / XCUITest-Kotlin /
  TestNG / WebdriverIO / Cucumber ×2 / page-object / api), WebView (context-switch)
  crawling, obstacle handling, gate chaining (login/OTP/biometric), deeplink
  seeding, opt-in device prep, mock-layer generation, auth-in-tests. 185 test
  files; CI green across Linux/macOS/Windows + Rust core + plugin build + security
  scan. Proven live (AntennaPod ran green; Compose apps built from source).
- **Plugin — pre-1.0.** `0.5.0-SNAPSHOT`. Shell, devices, screenshot + click-to-tap,
  session, wizard, JSON-RPC bridge all work; first-run UX and packaging are the gap.

The gap to a public release is **packaging, activation, and go-to-market — not more
engine cleverness.** Finish and ship the current depth (principles: simplicity,
depth-before-breadth).

---

## Phase R0 — Free 1.0 (ship the funnel)

The one job: a stranger installs it and gets a runnable test kit in minutes.

**Activation & first-run**
- [ ] Actionable empty states / onboarding in the tool window (PR #323).
- [ ] Native `ActionToolbar` + tabbed IA — a plugin that looks native (PR #325).
- [ ] Runnable-project scaffolders (Java, Kotlin) so output is a project you can run,
      not loose files (PR #327).
- [ ] A 5-minute quick start that goes install → point at an app → green kit, using
      the AntennaPod / a bundled sample story as the tutorial.

**Release engineering**
- [ ] Bump `0.5.0-SNAPSHOT` → `1.0.0`; produce a real release build.
- [ ] `verifyPlugin` = Compatible on IntelliJ IDEA + Android Studio + PyCharm.
- [ ] Marketplace listing: name, description, screenshots, a short demo GIF, correct
      categories, and a **working** support channel (live email or GitHub Issues).

**Dogfood gate (the real quality bar)**
- [ ] Used end-to-end on ≥1 real app at work; the generated kit runs **green in CI**.
      Bugs found here block the release — dogfooding is the test plan.

**Listing model:** a **free** plugin listing (ordinary publisher account — no paid
seller onboarding, so the release isn't blocked on it). Monetization comes in R2.

---

## Phase R1 — Quality & retention (right after launch)

What keeps people using it and protects the rating.

- [ ] 3-beat `settle()` wait after each transition — fewer flaky generated tests
      (PR #331). "Our generated tests actually pass in CI" is the core promise.
- [ ] Stream app logs + capture crashes into the kit (PR #328) — debugging value.
- [ ] Triage the incoming Marketplace reviews/issues; fix the top activation snags.

---

## Phase R2 — PRO (open-core monetization)

Turn premium features into a paid tier **once the free funnel shows demand** —
monetization is deliberately last. Sold as a **JetBrains freemium** plugin so there
is **no backend to run** — JetBrains handles billing, trials, and licence delivery.

- [ ] Decide the free / PRO feature line (kept out of this public repo) and enforce it
      via the licensing seam (`framework.licensing`: `cap_*` / `allow_targets` /
      `has_feature`) — no-ops in the OSS engine, honoured only when the PRO provider
      installs limits.
- [ ] Convert the listing to **freemium**: one plugin, free base + paid features
      unlocked by a JetBrains-managed licence (Product Code with `optional=true`,
      verified in-plugin via `LicensingFacade`). JetBrains runs billing / the 30-day
      trial / licence issuance and takes its fee; requires verified-seller onboarding.
- [ ] Keep PRO features **local / in-IDE** so no server is needed — multi-target
      export, lifted scale caps, in-run network mocking, advanced codegen. The OSS
      engine stays whole.
- [ ] Cloud-grid execution needs a backend and is **out of scope** while we avoid
      running servers — deferred (a much-later optional add-on, if ever).

---

## Phase R3 — Moats & distribution

Where durable advantage compounds.

- **Anti-flake story.** Lean into it: 3-beat waits, mock/replay, deterministic runs —
  the differentiator vs record-replay tools.
- **Incremental / diff-aware regeneration.** Regenerate tests only for changed
  screens; PR-aware. Team CI value.
- **Coverage artifact.** "What the crawl reached and what it didn't" — sells to QA leads.
- **Distribution.** Free VS Code port as a top-of-funnel multiplier (keep paid on
  JetBrains); content funnel (training → article → plugin).

---

## Release checklist (free 1.0)

```
[ ] R0 activation PRs merged (#323, #325, #327)
[ ] 5-minute quick start written + verified
[ ] version 1.0.0, release build produced
[ ] verifyPlugin Compatible on IntelliJ + Android Studio + PyCharm
[ ] Marketplace listing drafted (copy, screenshots, GIF, support channel)
[ ] dogfood: real app at work → kit green in CI
[ ] publish free listing
```
