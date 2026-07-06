---
name: new-codegen-target
description: Scaffold a new codegen emitter/target (e.g. Kaspresso, Maestro, XCUITest-Swift) following this repo's IR→emitter pattern. Use when adding a language/framework the tool can generate tests for.
---

# new-codegen-target

The tool generates from one language-agnostic IR (`framework/codegen/ir.py`:
`TestModel`/`TestCase`/`Step`/`Selector`) into many targets via template-driven
emitters. Adding a target = one emitter + one template + registration + a golden.

## Steps
1. **Study a sibling** in the same family as your target:
   - Appium/off-device → `emitters/python_pytest.py` + `templates/python_pytest/`
   - on-device Android → `emitters/kotlin_espresso.py` (+ `_espresso_common.py` matchers)
   Shared per-language rendering lives in `emitters/_<lang>_common.py` (string escaping, locator/selector rendering) — **reuse it**, don't re-implement locator mapping.
2. **Template** `templates/<target_id>/<file>.j2`:
   - Platform-aware driver setup: `{% if model.platform.value == "ios" %}` iOS caps (XCUITest, bundleId) `{% else %}` Android (UiAutomator2, appPackage).
   - Iterate `model.cases` → `case.steps`; map `step.action.value` (launch/tap/type/assert…) and `step.assertion.value` (visible/enabled/text_equals).
   - Render locators via the shared `_<lang>_common` helpers (they escape control chars and pick iOS predicate vs Android uiautomator).
3. **Emitter** `emitters/<target_id>.py`: subclass `Emitter`, register Jinja filters, `emit(model) -> {filename: content}`, then `register(Target(id=..., language=..., runner=..., binding=..., file_extension=..., description=...), <EmitterClass>)`.
4. **Golden test**: add the target id to `tests/codegen/test_emitters.py` parametrization; generate goldens with `UPDATE_GOLDENS=1 pytest tests/codegen/test_emitters.py`; eyeball the golden.
5. **Verify it compiles** (see `verify-codegen`). Then land via `ship-pr`.

## Notes
- Kaspresso is a thin layer over Espresso — reuse `_espresso_common.matcher_expr`, wrap in the Kaspresso `TestCase`/`run { step {...} }` DSL. Maestro is YAML flows. XCUITest-Swift is a fresh template.
- String literals MUST escape `\n`/`\r`/`\t`/quotes (element text can be multi-line) — the `_<lang>_common` `*_str` helper already does this; use it.
