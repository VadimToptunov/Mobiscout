"""
One table-driven string-literal escaper, shared by every language emitter.

Python, Java, Kotlin and JavaScript all render an element's text into a host
string literal the same way: escape the backslash, escape the delimiting quote,
and escape the control characters (newline/cr/tab) that would otherwise break
the literal across lines. They differ only in the quote character and a couple
of language extras (Kotlin escapes ``$`` because it begins a string template;
JavaScript uses single quotes). This module captures the common rule once so the
four escapers can never drift; each language module builds its function from it.
"""

from __future__ import annotations

import re
from typing import Callable, Dict, Optional

# Everything a line comment ends at. \n/\r are the obvious ones; U+2028/U+2029
# also terminate a line in JavaScript source, so a label containing one would
# end a ``//`` comment there too.
_LINE_BREAK = re.compile(r"[\r\n\u2028\u2029]+")


def single_line(value: Optional[str]) -> str:
    """Flatten a description/label onto one line, for the sites that need it:
    a ``#`` / ``//`` comment and a Gherkin ``Scenario:`` title.

    Element labels reach the emitters with their interior newlines intact (a
    Compose paragraph, a uiautomator dump that decoded ``&#10;``), and every
    imperative target renders a step description into a *line* comment. The
    label's second line would land in the file as bare source — the generated
    Python fails to parse, the Java/JS fails to compile and the Maestro YAML
    fails to scan. One space per break keeps the whole label on that one line.
    """
    return _LINE_BREAK.sub(" ", value or "")


def make_escaper(quote: str, extra: Optional[Dict[str, str]] = None) -> Callable[[Optional[str]], str]:
    """Build a string-literal escaper delimited by ``quote``.

    The returned function escapes, in order: the backslash (first, so the
    backslashes we introduce below are never re-escaped), the delimiting
    ``quote``, any language ``extra`` replacements, then the control characters
    ``\\n`` / ``\\r`` / ``\\t``. ``None`` renders as an empty literal.

    ``extra`` maps a raw substring to its escaped form (e.g. ``{"$": "\\\\$"}``
    for Kotlin string templates).
    """
    # Backslash MUST come first; the quote and control-char replacements all
    # introduce backslashes that would otherwise be doubled by a later pass.
    pairs = [("\\", "\\\\"), (quote, "\\" + quote)]
    if extra:
        pairs.extend(extra.items())
    pairs.extend([("\n", "\\n"), ("\r", "\\r"), ("\t", "\\t")])

    def escape(value: Optional[str]) -> str:
        text = value if value is not None else ""
        for old, new in pairs:
            text = text.replace(old, new)
        return quote + text + quote

    return escape
