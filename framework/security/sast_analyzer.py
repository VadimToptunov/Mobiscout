"""
SAST module — now split into the framework.security.sast package.

This shim preserves the historical import path
(`from framework.security.sast_analyzer import X`); the real code lives in one
module per analyzer under framework/security/sast/.
"""

from framework.security.sast import *  # noqa: F401,F403
from framework.security.sast import __all__  # noqa: F401
