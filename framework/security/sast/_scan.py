"""Shared batch-scan helper for the regex-based SAST analyzers.

The crypto / insecure-api analyzers match a fixed set of rule patterns against every line.
Run them through :func:`framework.analyzers.native.scan_lines` — one ``RegexSet`` pass over
all lines, files scanned in parallel on the Rust core (falling back to compiled-regex Python
when the core isn't built). This returns, per file, a ``{line_number: {rule_index}}`` map the
analyzers consult instead of calling ``re.search`` per rule per line.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Dict, List, Set

from framework.analyzers.native import scan_lines


def regex_hits(contents: List[str], patterns: List[str], ignore_case: bool) -> List[Dict[int, Set[int]]]:
    """For each file in ``contents``, ``{line_number(1-based): set(rule_index)}`` of matches."""
    per_file: List[Dict[int, Set[int]]] = [defaultdict(set) for _ in contents]
    for file_idx, line_no, rule_idx in scan_lines(contents, patterns, ignore_case):
        per_file[file_idx][line_no].add(rule_idx)
    return per_file
