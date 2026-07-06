"""Auto-provisioning: the model ships as a *recipe*, not a committed binary.
ensure_model() trains it from synthetic data into a cache on first use, so an
end user gets real ML without any .pkl in the repo — and it degrades to the
heuristic when disabled."""

import tempfile
from pathlib import Path

from framework.crawler import classify as C
from framework.crawler.app_crawler import CrawlElement


def _button():
    return CrawlElement(
        resource_id="",
        text="Submit",
        content_desc="",
        class_name="android.widget.Button",
        clickable=True,
        bounds=(0, 0, 100, 50),
    )


def test_ensure_model_trains_then_classify_uses_ml(monkeypatch):
    with tempfile.TemporaryDirectory() as d:
        monkeypatch.setenv("OBSERVE_ML_MODEL", str(Path(d) / "m.pkl"))
        monkeypatch.delenv("OBSERVE_ML_AUTOTRAIN", raising=False)
        C.reset_cache()
        path = C.ensure_model()
        assert path is not None and path.exists(), "ensure_model should train a model on first use"
        etype, conf, source = C.classify(_button())
        assert etype == "button"
        assert source == "ml", "with a provisioned model, a confident button should come from ML"
    C.reset_cache()


def test_autotrain_disabled_falls_back_to_heuristic(monkeypatch):
    monkeypatch.setenv("OBSERVE_ML_MODEL", "/definitely/nonexistent.pkl")
    monkeypatch.setenv("OBSERVE_ML_AUTOTRAIN", "0")
    C.reset_cache()
    assert C.ensure_model() is None
    etype, _, source = C.classify(_button())
    assert etype == "button" and source == "heuristic"
    C.reset_cache()
