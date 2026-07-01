"""
Advanced Security Module — now split into the framework.security.advanced package.

This shim preserves the historical import path
(`from framework.security.advanced_security import X`); the real code lives in
one module per analyzer under framework/security/advanced/.
"""

from framework.security.advanced import *  # noqa: F401,F403
from framework.security.advanced import __all__  # noqa: F401
