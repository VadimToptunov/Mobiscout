"""
Runtime protection module — now split into framework.security.runtime.

Shim preserving `from framework.security.runtime_protection import X`; real code
lives one module per analyzer under framework/security/runtime/.
"""

from framework.security.runtime import *  # noqa: F401,F403
from framework.security.runtime import __all__  # noqa: F401
