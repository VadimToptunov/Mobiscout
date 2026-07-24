"""The domain layer exists to end the `Platform`/`TestStatus`/`Severity`
per-subsystem duplication that silently broke equality (see docs/CODE_REVIEW.md).
This pins the invariant: every subsystem's Platform is the ONE canonical type.
"""

from framework.domain import Platform


def test_platform_is_str_enum():
    # The whole point: string-friendly comparison + wire value preserved.
    assert Platform.ANDROID == "android"
    assert Platform.ANDROID.value == "android"
    assert Platform("android") is Platform.ANDROID


def test_all_subsystems_share_one_platform():
    from framework.codegen.ir import Platform as ir_p
    from framework.model.enums import Platform as model_p
    from framework.devices.device_layer import Platform as dev_p

    assert ir_p is model_p is dev_p is Platform
    # Cross-subsystem comparison used to be silently False; now it holds.
    assert ir_p.ANDROID == model_p.ANDROID == "android"
