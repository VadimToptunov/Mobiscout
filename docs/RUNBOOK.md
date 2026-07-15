# Runbook — automate tests for both platforms tomorrow

A step-by-step for: point at your app on **Android and iOS**, generate tests, and
either **drop them into an existing framework** or **scaffold a new runnable
project**. Written for **JavaScript + WebdriverIO + Appium**; swap `--targets` for
another language (Python/Java/Kotlin) any time.

## 0. Prerequisites (once)

```bash
pip install -e .                       # the observe CLI (from source; not published to PyPI)
npm i -g appium                        # Appium 2 server
appium driver install uiautomator2     # Android
appium driver install xcuitest         # iOS
appium &                               # start the server (http://localhost:4723)
```

Have a **booted** device/emulator per platform and the **app launched** in the
foreground before crawling (the crawler refuses to run otherwise).

---

## A. New framework — scaffold a runnable project

`--scaffold` wraps the generated specs in a ready-to-run project (package.json,
wdio.conf.js, README). Run the crawl **once per platform, into its own dir**.

### Android
```bash
adb shell monkey -p com.yourcompany.app -c android.intent.category.LAUNCHER 1
observe crawl --platform android --package com.yourcompany.app \
  --targets js_webdriverio --scaffold --output mobile-tests-android

cd mobile-tests-android && npm install && npm test
```

### iOS
```bash
xcrun simctl launch booted com.yourcompany.app
observe crawl --platform ios --package com.yourcompany.app --udid <UDID> \
  --targets js_webdriverio --scaffold --output mobile-tests-ios

cd mobile-tests-ios && npm install && npm test
```

Each folder is a self-contained WebdriverIO project (correct UiAutomator2 /
XCUITest capabilities baked into `wdio.conf.js`).

---

## B. Existing framework — drop specs in

Point `--output` at your repo's spec folder and **omit** `--scaffold` — only the
test files are written, your `wdio.conf.js`/`conftest`/pages are untouched.

```bash
observe crawl --platform android --package com.yourcompany.app \
  --targets js_webdriverio --output ./e2e/specs
# -> specs land in ./e2e/specs/js_webdriverio/ ; wire them into your existing config
```

Repeat with `--platform ios` for the iOS specs.

---

## What you also get every run (alongside the tests)

In the output dir: `inventory.md` (every element + type + locator),
`graph.mmd`/`graph.json` (the app's interaction graph — opens in the IDE Markdown
preview), plus an accessibility section. Great for reviewing coverage or writing
tests by hand.

## Other languages

Same commands, different `--targets`:
`python_pytest` · `python_pytest_bdd` · `java_testng` · `java_cucumber` ·
`js_webdriverio` · `js_cucumber` · `kotlin_appium` · `kotlin_espresso`.
`--scaffold` currently builds a runnable shell for the **JS** and **Python**
targets; others still emit the specs to drop into your framework.

## Troubleshooting

- *"App … is not in the foreground"* — launch the app first (see the monkey /
  simctl commands above); the crawler stays inside the app under test.
- iOS first run builds WebDriverAgent — it's slow once, then cached.
- Empty inventory on a Jetpack Compose screen mid-animation — re-run; the crawler
  reads the tree once it settles.
