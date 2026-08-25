"""Release gate: CHANGELOG.md must carry a section for the current version.

The 0.12.0 release bumped ``__version__`` and the Marketplace change-notes (plugin.xml) but
left CHANGELOG.md at 0.11.0 (RL1) — the two change-note homes drifted. This asserts they
can't again: the newest ``## [x.y.z]`` entry must equal ``framework.__version__``. It sits
in the same alignment-gate family as EngineProviderTest (ENGINE_VERSION == "v" + __version__).
"""

import re
from pathlib import Path

import framework


def test_changelog_top_entry_matches_version():
    changelog = Path(__file__).resolve().parent.parent / "CHANGELOG.md"
    text = changelog.read_text(encoding="utf-8")
    match = re.search(r"^## \[([0-9]+\.[0-9]+\.[0-9]+)\]", text, re.MULTILINE)
    assert match is not None, "no versioned '## [x.y.z]' section found in CHANGELOG.md"
    assert match.group(1) == framework.__version__, (
        f"CHANGELOG.md's newest entry is {match.group(1)} but framework.__version__ is "
        f"{framework.__version__} — add the release section to CHANGELOG.md (RL1)"
    )
