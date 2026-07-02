"""
Supply chain module — now split into framework.security.supplychain.

Shim preserving `from framework.security.supply_chain import X`; real code lives
under framework/security/supplychain/.
"""

from framework.security.supplychain import *  # noqa: F401,F403
from framework.security.supplychain import __all__  # noqa: F401
