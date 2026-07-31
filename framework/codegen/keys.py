"""
Android keycodes for the ``press_key`` action — the single source of truth.

Appium's ``press_keycode`` takes an integer; friendly names (BACK/HOME/…) map to
the platform keycode. That table used to be copied in three places (the Python
filter plus a hand-written literal inside each of the pytest-bdd and Cucumber.js
templates), so a change to one silently diverged the others. Everything now
derives from :data:`ANDROID_KEYCODES` here:

  * targets that translate at generation time (python_pytest, js_webdriverio)
    call :func:`keycode` via a Jinja filter — the emitted code carries the int;
  * targets whose generated glue resolves the name at its *own* runtime
    (python_pytest_bdd, js_cucumber) embed a literal, rendered from this same
    table by :func:`as_python_dict_literal` / :func:`as_js_object_literal`.

Java/Kotlin use ``AndroidKey.valueOf(NAME)`` and need no numeric table.
"""

from __future__ import annotations

# Friendly key name -> Android keycode
# (developer.android.com/reference/android/view/KeyEvent).
ANDROID_KEYCODES = {"BACK": 4, "HOME": 3, "ENTER": 66, "TAB": 61, "SEARCH": 84, "APP_SWITCH": 187, "DEL": 67}


def keycode(name: str) -> int:
    """Resolve a friendly key name (BACK/HOME/…) to its Android keycode, passing
    a numeric string straight through. An unknown name resolves to 0."""
    text = str(name)
    return int(text) if text.isdigit() else ANDROID_KEYCODES.get(text.upper(), 0)


def as_python_dict_literal() -> str:
    """The keycode table as a Python dict literal, for embedding in generated
    pytest-bdd glue that looks names up at its own runtime."""
    return "{" + ", ".join(f'"{k}": {v}' for k, v in ANDROID_KEYCODES.items()) + "}"


def as_js_object_literal() -> str:
    """The keycode table as a JS object literal, for embedding in generated
    Cucumber.js glue."""
    return "{ " + ", ".join(f"{k}: {v}" for k, v in ANDROID_KEYCODES.items()) + " }"
