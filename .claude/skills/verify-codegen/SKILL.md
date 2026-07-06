---
name: verify-codegen
description: Compile/parse-gate generated test code across languages (Python/JS/Java/Kotlin) locally, mirroring CI's toolchain gates. Use after changing any emitter or template, before pushing.
---

# verify-codegen

CI runs toolchain gates on generated output; catch breakage locally first. A
template change can produce code that passes unit tests but does not compile.

## Generate a sample and check each language
```python
# generate.py — emit iOS + Android for the targets you touched
from framework.crawler.app_crawler import parse_screen, CrawlResult
from framework.crawler.to_codegen import build_test_model
from framework.codegen import get_emitter
IOS='<XCUIElementTypeApplication type="XCUIElementTypeApplication" name="A" x="0" y="0" width="390" height="844"><XCUIElementTypeButton type="XCUIElementTypeButton" name="b" label="Go" enabled="true" x="0" y="0" width="50" height="20"/></XCUIElementTypeApplication>'
AND='<hierarchy><node class="android.widget.Button" resource-id="com.x:id/b" text="Go" clickable="true" bounds="[0,0][50,20]" package="com.x"/></hierarchy>'
for name,xml,pkg in [("ios",IOS,"com.x"),("and",AND,"com.x")]:
    m=build_test_model(CrawlResult(screens={(s:=parse_screen(xml)).fingerprint:s}),app_package=pkg)
    for tgt in ["python_pytest","java_testng","js_webdriverio"]:
        for fn,c in get_emitter(tgt).emit(m).items():
            open(f"/tmp/gen_{name}_{tgt.split('_')[0]}_{fn}","w").write(c)
```
Then gate:
```
python -m py_compile /tmp/gen_*python*.py        # Python
node --check /tmp/gen_*js*.js                    # JavaScript
javac -d /tmp /tmp/gen_*java*.java   || true      # Java (needs appium-java-client on classpath; CI has it)
kotlinc /tmp/gen_*kotlin*.kt -d /tmp || true      # Kotlin (if kotlinc present)
```

## Common breakages
- **Unterminated string literal**: element text had a `\n` — the `_<lang>_common` `*_str` helper must escape control chars. Both iOS and Android paths.
- **Wrong Appium client for the platform**: iOS emitting `UiAutomator2Options`/`appPackage` instead of `XCUITestOptions`/`bundleId` (or vice versa) — check the `{% if model.platform.value == "ios" %}` branches.
- Java field type must be `AppiumDriver` (base) when a template serves both `AndroidDriver` and `IOSDriver`.
