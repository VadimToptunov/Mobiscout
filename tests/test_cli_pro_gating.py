"""The optional / PRO CLI lanes (security, a11y, fuzz, load) are gated by the licensing
seam: free on the open-core engine (UNLIMITED entitlements), locked under a limited PRO
tier. The group callback runs the gate before any subcommand, so `<lane> <cmd> --help`
exercises it without doing real work.
"""

import pytest
from click.testing import CliRunner

from framework.cli.a11y_commands import a11y
from framework.cli.fuzz_commands import fuzz
from framework.cli.load_commands import load
from framework.cli.security.base import security
from framework.licensing import Entitlements, Tier, reset_provider, set_provider

# (group, a real subcommand, the label the upsell must mention)
LANES = [
    (security, "secrets", "Security scanning"),
    (a11y, "list", "Accessibility auditing"),
    (fuzz, "generate", "Fuzz testing"),
    (load, "profiles", "Load testing"),
]


@pytest.fixture(autouse=True)
def _reset_license():
    yield
    reset_provider()


@pytest.mark.parametrize("group,subcmd,_label", LANES)
def test_lane_is_free_on_open_core(group, subcmd, _label):
    # Default UNLIMITED entitlements: the gate is a no-op, so the lane is not blocked.
    result = CliRunner().invoke(group, [subcmd, "--help"])
    assert result.exit_code == 0
    assert "PRO feature" not in result.output


@pytest.mark.parametrize("group,subcmd,label", LANES)
def test_lane_is_locked_under_a_limited_tier(group, subcmd, label):
    set_provider(lambda: Entitlements(tier=Tier.FREE, features=frozenset()))
    result = CliRunner().invoke(group, [subcmd, "--help"])
    assert result.exit_code != 0
    assert "PRO feature" in result.output
    assert label in result.output
