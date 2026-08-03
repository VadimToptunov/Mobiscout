"""Brace-matched block scoping for the static analyzers.

The analyzers are regex/heuristic; their weakest part was locating an element's
enclosing screen/function with a *fixed character window* (e.g. "test tags within
2000 chars of the function start", "the last @Composable before this point"),
which leaks elements across declaration boundaries. These helpers replace that
with real ``{...}`` brace matching — structurally correct without adding a native
parser.

Caveat vs a full AST: braces inside string/char literals or comments are not
skipped, so a ``"}"`` in a string could mislead. That's rare in the UI-declaration
code we scope, and this is still a large step up from a character window.
"""

from __future__ import annotations

from typing import Optional, Pattern, Tuple


def block_after(content: str, from_pos: int) -> Optional[Tuple[int, int]]:
    """``(open, close)`` indices of the ``{...}`` block whose ``{`` is the first at
    or after ``from_pos``, matched to its closing brace. ``None`` if there is no
    ``{`` after ``from_pos``. An unbalanced block runs to end-of-content."""
    open_i = content.find("{", from_pos)
    if open_i == -1:
        return None
    depth = 0
    for j in range(open_i, len(content)):
        if content[j] == "{":
            depth += 1
        elif content[j] == "}":
            depth -= 1
            if depth == 0:
                return (open_i, j)
    return (open_i, len(content))


def enclosing_block(content: str, pos: int) -> Optional[Tuple[int, int]]:
    """``(open, close)`` of the innermost ``{...}`` block containing ``pos``, or
    ``None`` if ``pos`` is not inside any block. Use it to scope a search to the
    statement/function a token lives in instead of a fixed character window."""
    stack = []
    for i in range(min(pos, len(content))):
        char = content[i]
        if char == "{":
            stack.append(i)
        elif char == "}" and stack:
            stack.pop()
    if not stack:
        return None
    return block_after(content, stack[-1])


def enclosing_declaration(content: str, pos: int, pattern: "Pattern[str]") -> Optional[str]:
    """Name (regex group 1) of the *tightest* declaration matched by ``pattern``
    whose body block ``{...}`` contains ``pos``, else ``None``.

    E.g. with a Composable/func or ``struct X: View`` pattern, the screen an
    element at ``pos`` actually lives in — never a sibling whose block already
    closed before ``pos``."""
    best_name: Optional[str] = None
    best_open = -1
    for match in pattern.finditer(content):
        if match.start() > pos:
            break
        block = block_after(content, match.end())
        if block and block[0] <= pos <= block[1] and block[0] > best_open:
            best_name, best_open = match.group(1), block[0]
    return best_name


def block_text_after(content: str, from_pos: int) -> str:
    """The source of the ``{...}`` block after ``from_pos`` (braces included), or
    ``""`` — for scanning a declaration's body instead of a fixed window."""
    block = block_after(content, from_pos)
    return content[block[0] : block[1] + 1] if block else ""
