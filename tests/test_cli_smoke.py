"""A safety net against the "dead-on-arrival" class of bug — a CLI command that
crashes the moment it is invoked (bad import, malformed option, wrong wiring).

Walks the whole click command tree and asserts every group and subcommand's
`--help` works: it imports cleanly and its options parse. One failing command
fails only its own parametrised case, so a regression is pinpointed.
"""

import pytest
from click.testing import CliRunner

from framework.cli.main import cli


def _walk(command, path=()):
    """Yield (path, command) for the command and, recursively, every subcommand."""
    yield path, command
    for name, sub in getattr(command, "commands", {}).items():
        yield from _walk(sub, path + (name,))


_ALL = list(_walk(cli))


@pytest.mark.parametrize("path,command", _ALL, ids=[" ".join(p) or "cli" for p, _ in _ALL])
def test_command_help_never_crashes(path, command):
    result = CliRunner().invoke(cli, list(path) + ["--help"])
    assert result.exit_code == 0, f"`{' '.join(path)} --help` failed:\n{result.output}"
    assert result.exception is None, result.exception


def test_cli_tree_is_non_trivial():
    # Guard the guard: if the traversal silently found nothing, the parametrised
    # test would vacuously pass.
    assert len(_ALL) > 30  # ~34 groups plus their subcommands


def test_unknown_command_errors_cleanly():
    result = CliRunner().invoke(cli, ["definitely-not-a-command"])
    assert result.exit_code != 0
    assert result.exception is None or isinstance(result.exception, SystemExit)
