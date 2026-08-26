"""The suite classifies with the heuristic, on every machine.

tests/conftest.py pins MOBISCOUT_ML_MODEL and drops the classifier's module-level
cache around each test. Both halves are needed and neither raises when it stops
working — a stale cached model just silently changes what every crawl test sees —
so pin the outcome here: the classifier the rest of the suite runs against.
"""

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


def test_no_ml_model_is_loaded_for_the_suite():
    assert C._model_path() == C.Path("/nonexistent.pkl")  # the session pin is in force
    assert C._load_model() is None  # ...and the cache was cold enough to read it


def test_classification_comes_from_the_heuristic():
    assert C.classify(_button()) == ("button", 1.0, "heuristic")
