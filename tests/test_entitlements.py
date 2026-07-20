"""Open-core entitlements: the public engine is unlimited by default (no paywall),
but a paid layer can plug in real limits via set_provider, and the enforcement
helpers honour them. A broken provider must never brick the free engine."""

import pytest

from framework.licensing import (
    Entitlements,
    Tier,
    allow_targets,
    cap_screens,
    cap_tests,
    entitlements,
    has_feature,
    reset_provider,
    set_provider,
)


@pytest.fixture(autouse=True)
def _restore():
    yield
    reset_provider()


def test_default_is_unlimited_no_paywall():
    e = entitlements()
    assert e.max_screens is None and e.max_targets is None and e.max_tests is None
    assert has_feature("anything")  # "*" unlocks everything
    # helpers are no-ops
    assert cap_screens(999) == 999
    assert cap_tests(999) == 999
    assert allow_targets(["python_pytest", "java_testng", "kotlin_appium"]) == [
        "python_pytest",
        "java_testng",
        "kotlin_appium",
    ]


def test_a_paid_layer_can_install_limits():
    set_provider(
        lambda: Entitlements(tier=Tier.FREE, max_screens=15, max_tests=40, max_targets=2, features=frozenset())
    )
    assert cap_screens(100) == 15
    assert cap_tests(100) == 40
    assert allow_targets(["python_pytest", "js_webdriverio", "java_testng", "kotlin_appium"]) == [
        "python_pytest",
        "js_webdriverio",
    ]
    assert not has_feature("cloud_grid")


def test_pro_feature_flag_unlocks():
    set_provider(lambda: Entitlements(tier=Tier.PRO, features=frozenset({"cloud_grid", "auto_recrawl"})))
    assert has_feature("cloud_grid") and has_feature("auto_recrawl")
    assert not has_feature("nonexistent")


def test_broken_provider_degrades_to_unlimited():
    def boom():
        raise RuntimeError("paid layer bug")

    set_provider(boom)
    # must not raise; free engine keeps working, unlimited
    assert entitlements().max_screens is None
    assert cap_screens(500) == 500
