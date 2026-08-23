"""Cloud-grid provider mapping (framework/cloud_grid): a generated kit already reads
MOBISCOUT_APPIUM_SERVER + MOBISCOUT_EXTRA_CAPS, so grid_env just builds those from the
user's own credentials (from env vars) — nothing stored, no backend."""

import json

import pytest

from framework.cloud_grid import MissingCredentials, PROVIDERS, UnknownProvider, grid_env


@pytest.fixture(autouse=True)
def _clear_creds(monkeypatch):
    for p in PROVIDERS.values():
        monkeypatch.delenv(p.user_env, raising=False)
        monkeypatch.delenv(p.key_env, raising=False)


def test_grid_run_rejects_a_non_python_kit(tmp_path, monkeypatch):
    # `grid run` uses pytest, so a kit with no test_*.py (e.g. a maestro/java kit) must fail
    # with an actionable message rather than a confusing pytest error.
    from click.testing import CliRunner

    monkeypatch.setenv("BROWSERSTACK_USERNAME", "u")
    monkeypatch.setenv("BROWSERSTACK_ACCESS_KEY", "k")
    (tmp_path / "login.yaml").write_text("appId: com.x\n", encoding="utf-8")  # a maestro kit
    from framework.cli.grid_commands import grid

    result = CliRunner().invoke(grid, ["run", str(tmp_path), "--provider", "browserstack", "--device", "Pixel 7"])
    assert result.exit_code != 0
    assert "python_pytest kit" in result.output


def test_unknown_provider_raises():
    with pytest.raises(UnknownProvider):
        grid_env("nope", "android", "Pixel 7")


def test_missing_credentials_names_the_env_vars(monkeypatch):
    with pytest.raises(MissingCredentials) as exc:
        grid_env("browserstack", "android", "Google Pixel 7")
    assert "BROWSERSTACK_USERNAME" in str(exc.value) and "BROWSERSTACK_ACCESS_KEY" in str(exc.value)


def test_browserstack_embeds_creds_in_hub_and_sets_bstack_options(monkeypatch):
    monkeypatch.setenv("BROWSERSTACK_USERNAME", "alice")
    monkeypatch.setenv("BROWSERSTACK_ACCESS_KEY", "s3cr3t/key")
    env = grid_env("browserstack", "android", "Google Pixel 7", os_version="13", app="bs://abc")

    # creds embedded in the hub URL, URL-encoded (the '/' in the key is escaped)
    assert env["MOBISCOUT_APPIUM_SERVER"] == "https://alice:s3cr3t%2Fkey@hub-cloud.browserstack.com/wd/hub"
    caps = json.loads(env["MOBISCOUT_EXTRA_CAPS"])
    assert caps["platformName"] == "Android"
    assert caps["bstack:options"]["deviceName"] == "Google Pixel 7"
    assert caps["bstack:options"]["platformVersion"] == "13"
    assert caps["appium:app"] == "bs://abc"
    # credentials are NOT duplicated into caps for a URL-embedding provider
    assert "accessKey" not in caps["bstack:options"]


def test_saucelabs_keeps_creds_in_caps_not_url(monkeypatch):
    monkeypatch.setenv("SAUCE_USERNAME", "bob")
    monkeypatch.setenv("SAUCE_ACCESS_KEY", "k")
    env = grid_env("saucelabs", "ios", "iPhone 15", os_version="17")
    assert env["MOBISCOUT_APPIUM_SERVER"] == "https://ondemand.us-west-1.saucelabs.com/wd/hub"  # no creds in URL
    caps = json.loads(env["MOBISCOUT_EXTRA_CAPS"])
    assert caps["sauce:options"]["username"] == "bob" and caps["sauce:options"]["accessKey"] == "k"
    assert caps["platformName"] == "iOS"  # the exact casing grids expect, not "Ios"
    assert caps["appium:platformVersion"] == "17"


def test_lambdatest_maps_to_lt_options(monkeypatch):
    monkeypatch.setenv("LT_USERNAME", "carol")
    monkeypatch.setenv("LT_ACCESS_KEY", "k")
    env = grid_env("lambdatest", "android", "Galaxy S23")
    assert env["MOBISCOUT_APPIUM_SERVER"].endswith("@mobile-hub.lambdatest.com/wd/hub")
    caps = json.loads(env["MOBISCOUT_EXTRA_CAPS"])
    assert caps["lt:options"]["deviceName"] == "Galaxy S23"


def test_credentials_never_appear_in_extra_caps_for_url_providers(monkeypatch):
    # A URL-embedding provider must not also leak the key into the (loggable) caps JSON.
    monkeypatch.setenv("LT_USERNAME", "carol")
    monkeypatch.setenv("LT_ACCESS_KEY", "supersecret")
    env = grid_env("lambdatest", "android", "Galaxy S23")
    assert "supersecret" not in env["MOBISCOUT_EXTRA_CAPS"]
