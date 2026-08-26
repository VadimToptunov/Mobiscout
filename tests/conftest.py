"""Suite-wide setup.

Several test files declared their own ``_heuristic_only`` fixture pinning
``MOBISCOUT_ML_MODEL`` at a nonexistent path so crawl/codegen tests classify with
the heuristic. The pin never took effect: ``framework.crawler.classify`` caches
the loaded model in a module global and returns it without re-reading the env, so
once any earlier test in the same worker had classified an element the pin could
no longer dislodge it. Which backend actually ran therefore depended on whether
the machine had ~/.cache/mobiscout/universal_element_classifier.pkl (a dev box
does, CI does not) and on how pytest-xdist happened to split the files — the
tests were machine- and order-dependent.

So pin the env for the whole session, and clear the classifier cache around every
test so the pin is read.
"""

import os

import pytest


@pytest.fixture(scope="session", autouse=True)
def _pin_heuristic_classifier():
    previous = {k: os.environ.get(k) for k in ("MOBISCOUT_ML_MODEL", "MOBISCOUT_ML_AUTOTRAIN")}
    os.environ["MOBISCOUT_ML_MODEL"] = "/nonexistent.pkl"
    os.environ["MOBISCOUT_ML_AUTOTRAIN"] = "0"
    yield
    for key, value in previous.items():
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value


@pytest.fixture(autouse=True)
def _reset_classifier_cache():
    """Both sides of the test: cold going in, so the pin above is honoured, and cold
    coming out, so a test that deliberately trains a real model (test_ml_provision)
    cannot leak it into whatever runs next."""
    from framework.crawler import classify

    classify.reset_cache()
    yield
    classify.reset_cache()
