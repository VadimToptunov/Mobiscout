---
name: crawl-kit
description: Drive a live device/simulator to a full crawl-kit (inventory + interaction graph + tests) for Android or iOS. Use when asked to crawl a real app or produce artifacts from a running app.
---

# crawl-kit

`mobiscout crawl` autonomously walks a *running* app and writes the kit:
`inventory.md/json` (elements + semantic types + locators), `graph.mmd/dot/json`
(interaction graph), and tests per codegen target. It refuses to run unless the
app is foreground. The element-typing model auto-trains on first run (~1s, cached).

## Android (over adb)
```
export PATH="$HOME/Library/Android/sdk/platform-tools:$PATH"
adb devices                                   # ensure an emulator/device is up
adb shell monkey -p <pkg> -c android.intent.category.LAUNCHER 1   # launch app
sleep 4
mobiscout crawl --package <pkg> --targets python_pytest,java_testng --output /tmp/kit
```
- Verify foreground: `adb shell dumpsys activity activities | grep -i ResumedActivity` (use `topResumedActivity`, NOT `mCurrentFocus` — it points at ANR/system dialogs).
- If `uiautomator dump` returns 0 bytes: the screen was mid-animation; retry after a short wait.

## iOS (over Appium + WebDriverAgent)
```
export DEVELOPER_DIR=/Applications/Xcode.app/Contents/Developer   # CLT alone lacks simctl
xcrun simctl boot "iPhone 17"; open -a Simulator
# one-time: npm install -g appium && appium driver install xcuitest
appium > /tmp/appium.log 2>&1 &                # first session builds WDA (slow, be patient)
xcrun simctl launch booted <bundleId>
mobiscout crawl --platform ios --package <bundleId> --udid <UDID> --targets python_pytest --output /tmp/ios-kit
```

## After
- Read `inventory.md` (type column, locators), the `## Interaction graph` section (Mermaid renders on GitHub; check dead-ends / unreachable), and the generated tests.
- The emulator/simulator here is flaky: adb/dumps sometimes hang — run device commands with a wait-loop and re-check, don't assume one call succeeded.
- Set `MOBISCOUT_ML_AUTOTRAIN=0` to force the heuristic (skip model training) for deterministic/fast runs.
