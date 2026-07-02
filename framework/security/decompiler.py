"""
Decompiler module — now split into the framework.security.decompile package.

This shim preserves `from framework.security.decompiler import X`; the real code
lives one module per analyzer under framework/security/decompile/.
"""

from framework.security.decompile import *  # noqa: F401,F403
from framework.security.decompile import __all__  # noqa: F401
