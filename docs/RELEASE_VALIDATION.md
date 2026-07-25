# Release / Demo Validation Runbook

The automated suite proves the code paths with fakes (`FakeDriver`, mocked HTTP,
synthetic images). Before presenting Mobiscout to people, run this once on a **real
device / simulator with a real app** — the headline claim ("point at an app, get a
passing test kit") lives or dies here, and only a real run exercises the device
seams (adb/Appium, screen capture, timing, flaky-device handling).

Budget ~30–45 min. Do it on 2–3 apps of increasing messiness (a simple form app, a
Compose app, a real store app). Record the outcomes in the table at the bottom.

## 0. Prerequisites
- [ ] `pip install -e .` in a clean venv; `mobiscout info` prints version and exits 0.
- [ ] A device is reachable: `adb devices` (Android) or a booted simulator/`xcrun simctl list` (iOS).
- [ ] The app under test is installed and launchable by hand.
- [ ] Optional for the full security check: `apktool` and `androguard` on PATH.

## 1. The core happy path (the demo) — per app
- [ ] **Crawl:** `mobiscout crawl --package <pkg> --targets python_pytest,java_testng`
  - [ ] It reaches the foreground on its own (or reports a clear, correct hint if not).
  - [ ] It finishes within the step/depth budget without hanging on a blank/ANR screen.
  - [ ] "Discovered N screen(s), M transition(s)" — N and M are plausible for the app.
- [ ] **Inventory** (`crawl-kit/inventory.*`): element types look right (buttons are
      buttons, inputs are inputs); locators are sensible (accessibility-id/resource-id
      preferred over text); dynamic text (prices/counts) is scored lower.
- [ ] **Interaction graph** (`crawl-kit/graph.*`): the Mermaid/JSON graph matches the
      app's real navigation; special screens (error/loading/permission) are flagged.
- [ ] **Generated tests actually run and pass** against the live app:
  - [ ] `cd crawl-kit && pip install -r requirements.txt` (or open the POM project).
  - [ ] `pytest` (with the device/Appium up) — the generated suite is **green**, not
        just syntactically valid. This is the single most important check.
- [ ] **iOS parity** (if demoing iOS): repeat with `--platform ios --udid <UDID>`.

## 2. Opt-in / adjacent features (device-free or light)
- [ ] **Record → test:** `mobiscout record --package <pkg>`, tap a few things, Ctrl+C;
      the generated test replays those taps.
- [ ] **Event recording:** `mobiscout crawl --package <pkg> --record-events s.db` then
      `mobiscout events timeline s.db` shows the taps/transitions in order.
- [ ] **Self-healing:** break a selector in a generated test, run `mobiscout heal ...`,
      confirm it proposes/writes a working locator.
- [ ] **API analysis:** capture traffic to a HAR (proxy/DevTools) →
      `mobiscout api analyze capture.har` yields real assertions.
- [ ] **Source planning:** `mobiscout source analyze <src>` maps screens/routes/APIs.

## 3. Honesty spot-checks (so nothing over-claims live)
- [ ] **Security:** `mobiscout security scan <app.apk>` — on an app with a known
      embedded secret it is **found**; with no apktool the report shows the explicit
      "Partial analysis — not a clean bill of health" note (never a silent "secure").
- [ ] **Fuzz (API):** point `mobiscout fuzz api <url>` at a real endpoint — crashes
      correspond to real 5xx/timeouts. UI fuzz with no device prints the SIMULATED
      warning (no invented crashes).
- [ ] **Visual:** two genuinely different screenshots report a non-zero diff and a
      bounding box; identical ones report 0%.
- [ ] **A11y:** `mobiscout a11y scan hierarchy.json --screenshot shot.png` — contrast
      is actually checked; without `--screenshot` it reports "not checked", not a pass.

## 4. Robustness (the flaky-device reality)
- [ ] Kill/restart the app mid-crawl once — the crawler recovers or fails with a clear
      message (no infinite hang, no stack trace dump).
- [ ] Run the crawl twice on the same app — screens/graph are stable (deterministic).
- [ ] Time the crawl — it stays within the "fast" expectation (no fixed sleeps stalling
      it; scroll/refresh/dismiss are bounded).

## 5. Onboarding (what a new person hits)
- [ ] Follow `QUICKSTART.md` verbatim, copy-paste — every command works as written.
- [ ] The JetBrains plugin: build, install, start daemon, load devices, tap a screen.

---

## Results

| App | Crawl OK | Tests green | Notes |
| --- | --- | --- | --- |
| (simple form) | | | |
| (Compose) | | | |
| (real store) | | | |

**Blocking issues found:** _(list; each becomes an issue before presenting)_

> If §1 "generated tests actually run and pass" fails on real apps, that is a
> release blocker — everything else is secondary to the core promise working live.
