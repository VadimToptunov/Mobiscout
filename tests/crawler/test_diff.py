"""Diff-aware regeneration: a crawl is diffed against a baseline manifest so a re-crawl
of an evolving app yields the delta (added/changed/removed), not the whole app again."""

from pathlib import Path

from framework.codegen.ir import ActionType, Platform, Selector, SelectorStrategy, Step, TestCase, TestModel
from framework.crawler.diff import (
    build_manifest,
    diff_models,
    filter_to_changed,
    load_manifest,
    write_manifest,
)


def _sel(value: str) -> Selector:
    return Selector(strategy=SelectorStrategy.ID, value=value)


def _case(name: str, locator: str, action: ActionType = ActionType.TAP) -> TestCase:
    return TestCase(name=name, steps=[Step(action=action, selector=_sel(locator))])


def _model(*cases: TestCase) -> TestModel:
    return TestModel(name="Suite", app_package="com.example.app", platform=Platform.ANDROID, cases=list(cases))


def test_first_run_has_no_baseline_and_keeps_everything():
    model = _model(_case("test_a", "a"), _case("test_b", "b"))
    report = diff_models(None, model)
    assert report.first_run is True
    assert report.added == ["test_a", "test_b"]
    # Nothing is dropped on a first run — every case is new.
    assert [c.name for c in filter_to_changed(model, report).cases] == ["test_a", "test_b"]
    assert "First run" in report.summary()


def test_added_changed_removed_unchanged_are_classified():
    baseline = build_manifest(_model(_case("test_stable", "s"), _case("test_edit", "old"), _case("test_gone", "g")))
    fresh = _model(
        _case("test_stable", "s"),  # identical → unchanged
        _case("test_edit", "new"),  # same name, different locator → changed
        _case("test_new", "n"),  # absent from baseline → added
        # test_gone dropped from the app → removed
    )
    report = diff_models(baseline, fresh)
    assert report.added == ["test_new"]
    assert report.changed == ["test_edit"]
    assert report.removed == ["test_gone"]
    assert report.unchanged == ["test_stable"]
    assert report.has_changes is True


def test_signature_ignores_description_but_tracks_steps():
    a = TestCase(name="t", description="first", steps=[Step(action=ActionType.TAP, selector=_sel("x"))])
    b = TestCase(name="t", description="reworded", steps=[Step(action=ActionType.TAP, selector=_sel("x"))])
    # Only the description differs → same signature → unchanged.
    assert diff_models(build_manifest(_model(a)), _model(b)).unchanged == ["t"]
    # Same for a step description and a selector score: a relabelled control ("Tap Cart" →
    # "Tap Cart (2)") and a re-scored locator are cosmetic, and marking such a case
    # "changed" churned CHANGES.md and regenerated tests for an app that hadn't moved.
    cosmetic = TestCase(
        name="t",
        steps=[
            Step(
                action=ActionType.TAP,
                selector=Selector(strategy=SelectorStrategy.ID, value="x", score=0.42, description="Cart (2)"),
                description="Tap Cart (2)",
            )
        ],
    )
    assert diff_models(build_manifest(_model(a)), _model(cosmetic)).unchanged == ["t"]
    # A different action on the same locator IS a real change.
    c = TestCase(name="t", steps=[Step(action=ActionType.LONG_PRESS, selector=_sel("x"))])
    assert diff_models(build_manifest(_model(a)), _model(c)).changed == ["t"]


def test_only_changed_keeps_just_added_and_changed():
    baseline = build_manifest(_model(_case("keep", "k"), _case("edit", "old")))
    fresh = _model(_case("keep", "k"), _case("edit", "new"), _case("brand_new", "z"))
    report = diff_models(baseline, fresh)
    kept = [c.name for c in filter_to_changed(fresh, report).cases]
    assert kept == ["edit", "brand_new"]  # "keep" (unchanged) is dropped from the delta kit


def test_no_changes_reports_clean():
    model = _model(_case("test_a", "a"))
    report = diff_models(build_manifest(model), model)
    assert report.has_changes is False
    assert "No test changes" in report.to_markdown("com.example.app")


def test_markdown_lists_each_bucket():
    baseline = build_manifest(_model(_case("edit", "old"), _case("gone", "g")))
    fresh = _model(_case("edit", "new"), _case("added", "a"))
    md = diff_models(baseline, fresh).to_markdown("com.example.app")
    assert "com.example.app" in md
    assert "Added" in md and "`added`" in md
    assert "Changed" in md and "`edit`" in md
    assert "Removed" in md and "`gone`" in md


def test_manifest_roundtrips_on_disk(tmp_path: Path):
    model = _model(_case("test_a", "a"), _case("test_b", "b"))
    write_manifest(tmp_path, model)
    # A directory path resolves to its manifest.json.
    loaded = load_manifest(tmp_path)
    assert loaded is not None
    assert set(loaded["cases"]) == {"test_a", "test_b"}
    # Re-diffing the same model against its own written baseline shows no changes.
    assert diff_models(loaded, model).has_changes is False


def test_missing_or_corrupt_baseline_is_a_first_run(tmp_path: Path):
    assert load_manifest(tmp_path / "nope") is None
    bad = tmp_path / "manifest.json"
    bad.write_text("{not json", encoding="utf-8")
    assert load_manifest(tmp_path) is None
