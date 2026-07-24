"""Canonical domain value objects, shared across every subsystem.

Before this package existed, core concepts were redefined per subsystem —
``Platform`` had three separate definitions, ``TestStatus`` four, ``Severity``
several — and they compared *unequal* to each other and, for the plain-``Enum``
variants, unequal to their own string value. That mismatch was a latent-bug
generator: it made ``severity == "critical"`` silently always-``False`` and forced
adapter code between otherwise-identical types.

Every value here is a ``str``-based ``Enum`` so that:

* ``Platform.ANDROID == "android"`` is ``True`` (string-friendly comparisons),
* ``.value`` still yields the wire string (``"android"``) for serialization,
* identity comparisons (``is Platform.IOS``) keep working,

and there is exactly **one** definition of each concept. Subsystems that used to
declare their own copy now re-export from here, so all instances share identity.

Only concepts with a *real* cross-subsystem duplication live here: ``Platform``
(was defined 3x) and ``TestStatus`` (4x). ``Severity`` is deliberately absent —
its only live definition already lives, consolidated, in ``security.types`` (as a
plain ``Enum`` whose serialization semantics that module intentionally preserves),
and the remaining ``RiskLevel`` is an *int*-valued score, a different value object.
Adding a Severity here with no second consumer would just be speculative generality.
"""

from framework.domain.platform import Platform
from framework.domain.status import TestStatus

__all__ = ["Platform", "TestStatus"]
