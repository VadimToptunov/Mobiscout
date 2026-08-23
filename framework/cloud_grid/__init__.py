"""Run generated kits on a cloud device grid — bring your own account.

Mobiscout needs no backend for this: a generated python_pytest kit already reads
``MOBISCOUT_APPIUM_SERVER`` (the Appium hub) and ``MOBISCOUT_EXTRA_CAPS`` (a JSON block of
extra capabilities) from the environment. This module turns a provider + device choice
into exactly those two values, filling credentials from environment variables at run time
(never stored, never written to a file), so the same kit that runs locally runs on
BrowserStack / Sauce Labs / LambdaTest unchanged.
"""

from framework.cloud_grid.providers import (
    GridProvider,
    PROVIDERS,
    UnknownProvider,
    MissingCredentials,
    grid_env,
)

__all__ = ["GridProvider", "PROVIDERS", "UnknownProvider", "MissingCredentials", "grid_env"]
