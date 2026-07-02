"""
DAST module — now split into the framework.security.dast package.

Shim preserving `from framework.security.dast_analyzer import X`; real code lives
one module per analyzer under framework/security/dast/.
"""

from framework.security.dast import *  # noqa: F401,F403
from framework.security.dast import __all__  # noqa: F401
