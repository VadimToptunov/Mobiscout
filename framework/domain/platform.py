"""The mobile platform under test — the single canonical definition.

Supersedes the former per-subsystem copies in ``codegen.ir``, ``model.enums`` and
``devices.device_layer``, which now re-export this type.
"""

from enum import Enum


class Platform(str, Enum):
    """A mobile platform Mobiscout can crawl and generate tests for.

    ``str``-based so ``Platform.ANDROID == "android"`` holds and ``.value`` still
    returns the wire string used in serialized models and generated code.
    """

    ANDROID = "android"
    IOS = "ios"
    CROSS_PLATFORM = "cross-platform"
