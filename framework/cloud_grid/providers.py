"""Cloud-grid providers: turn a (provider, device) choice into the Appium hub URL and the
capability block a generated kit needs. Credentials are read from environment variables
(BYO account) at call time and never persisted."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any, Dict, Optional
from urllib.parse import quote


class UnknownProvider(ValueError):
    pass


class MissingCredentials(RuntimeError):
    pass


@dataclass(frozen=True)
class GridProvider:
    """One cloud grid. ``user_env``/``key_env`` are the env vars the user sets with their
    own account credentials; nothing here stores or logs them."""

    name: str
    user_env: str
    key_env: str
    options_key: str  # provider capability namespace, e.g. "bstack:options"
    #: hub host; {user}/{key} are URL-encoded and substituted when the provider embeds
    #: credentials in the URL, otherwise they go into the options block.
    hub: str
    embed_creds_in_url: bool

    def credentials(self) -> tuple:
        user = os.environ.get(self.user_env)
        key = os.environ.get(self.key_env)
        if not user or not key:
            raise MissingCredentials(
                f"{self.name} needs {self.user_env} and {self.key_env} set to your account "
                f"credentials (bring your own account — Mobiscout never stores them)."
            )
        return user, key


PROVIDERS: Dict[str, GridProvider] = {
    "browserstack": GridProvider(
        name="browserstack",
        user_env="BROWSERSTACK_USERNAME",
        key_env="BROWSERSTACK_ACCESS_KEY",
        options_key="bstack:options",
        hub="hub-cloud.browserstack.com/wd/hub",
        embed_creds_in_url=True,
    ),
    "saucelabs": GridProvider(
        name="saucelabs",
        user_env="SAUCE_USERNAME",
        key_env="SAUCE_ACCESS_KEY",
        options_key="sauce:options",
        hub="ondemand.us-west-1.saucelabs.com/wd/hub",
        embed_creds_in_url=False,
    ),
    "lambdatest": GridProvider(
        name="lambdatest",
        user_env="LT_USERNAME",
        key_env="LT_ACCESS_KEY",
        options_key="lt:options",
        hub="mobile-hub.lambdatest.com/wd/hub",
        embed_creds_in_url=True,
    ),
}


def _hub_url(provider: GridProvider, user: str, key: str) -> str:
    if provider.embed_creds_in_url:
        return f"https://{quote(user, safe='')}:{quote(key, safe='')}@{provider.hub}"
    return f"https://{provider.hub}"


def _options_block(
    provider: GridProvider, user: str, key: str, device: str, os_version: Optional[str]
) -> Dict[str, Any]:
    """The provider's capability namespace. Credentials are included only when the provider
    expects them in caps rather than the URL (Sauce)."""
    opts: Dict[str, Any] = {"deviceName": device, "realMobile": True}
    if os_version:
        opts["platformVersion"] = os_version
    if not provider.embed_creds_in_url:
        opts["username"] = user
        opts["accessKey"] = key
    return opts


def grid_env(
    provider_name: str,
    platform: str,
    device: str,
    os_version: Optional[str] = None,
    app: Optional[str] = None,
) -> Dict[str, str]:
    """The environment a generated kit needs to run on ``provider_name``:
    ``{"MOBISCOUT_APPIUM_SERVER": <hub url>, "MOBISCOUT_EXTRA_CAPS": <json caps>}``.

    ``app`` is the provider's own app identifier (e.g. ``bs://…``, ``storage:…``,
    ``lt://…``) for an already-uploaded build. Raises :class:`UnknownProvider` or
    :class:`MissingCredentials`.
    """
    provider = PROVIDERS.get(provider_name.lower())
    if provider is None:
        raise UnknownProvider(f"Unknown grid provider '{provider_name}'. Known: {', '.join(sorted(PROVIDERS))}")
    user, key = provider.credentials()

    caps: Dict[str, Any] = {
        "platformName": platform.capitalize(),
        provider.options_key: _options_block(provider, user, key, device, os_version),
        # Also expose device/version under the W3C appium: prefix that most grids accept.
        "appium:deviceName": device,
    }
    if os_version:
        caps["appium:platformVersion"] = os_version
    if app:
        caps["appium:app"] = app

    return {
        "MOBISCOUT_APPIUM_SERVER": _hub_url(provider, user, key),
        "MOBISCOUT_EXTRA_CAPS": json.dumps(caps),
    }
