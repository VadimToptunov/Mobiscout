"""Frozen entry point for the Mobiscout engine daemon (variant C: no user Python).

PyInstaller bundles this + the framework into a standalone per-platform binary the
JetBrains plugin launches; it speaks the same JSON-RPC over stdio as `mobiscout daemon`.

``--selftest`` makes the built binary prove it is complete (see :func:`_selftest`).
"""

import sys

from framework.cli.daemon_commands import JSONRPCServer


def _selftest() -> int:
    """Import every subpackage the engine needs and render one real template.

    The packaging guard this replaces grepped PyInstaller's log for
    "Failed to collect submodules", but ``collect_submodules`` only warns *once* and
    then silently ignores later failures — and it walks LIFO, so the knowingly-optional
    ``framework.dashboard`` (it needs uvicorn, absent from the lean install) always
    consumed that one warning. Every genuinely missing subpackage after it was dropped
    with no log line at all, which is exactly how a codegen/jinja2 drop would ship green.

    Asking the built binary instead is a positive check that cannot be defeated: a
    missing module raises here, and rendering through a real emitter proves the ``.j2``
    templates are bundled as data too (a hidden-import fix alone would not).
    """
    from framework.codegen.ir import (
        ActionType,
        AssertionType,
        Platform,
        Selector,
        SelectorStrategy,
        Step,
        TestCase,
        TestModel,
    )
    from framework.codegen.targets import available_targets, get_emitter

    # Subpackages the daemon reaches lazily, so a missing one only surfaces mid-run.
    for module in (
        "framework.crawler.app_crawler",
        "framework.crawler.classify",
        "framework.crawler.graph",
        "framework.crawler.to_codegen",
        "framework.crawler.pipeline",
        "framework.crawler.page_kit",
        "framework.devices.device_manager",
        "framework.health.preflight",
        "framework.analyzers.native",
        "framework.mcp.server",
    ):
        __import__(module)

    model = TestModel(
        name="SelfTest",
        app_package="com.example.app",
        platform=Platform.ANDROID,
        cases=[
            TestCase(
                name="self_test",
                description="packaging self-test",
                steps=[
                    Step(ActionType.LAUNCH, description="Open app"),
                    Step(
                        ActionType.ASSERT,
                        selector=Selector(strategy=SelectorStrategy.ID, value="com.example.app:id/ok", description="OK"),
                        assertion=AssertionType.VISIBLE,
                        description="OK is visible",
                    ),
                ],
            )
        ],
    )
    # Every registered target, so a template missing from the bundle fails here rather
    # than on the first user who picks that language.
    targets = [t.id for t in available_targets()]
    for target in targets:
        files = get_emitter(target).emit(model)
        if not files or not any(content.strip() for content in files.values()):
            print(f"SELFTEST FAIL: target {target} emitted nothing", file=sys.stderr)
            return 1
    print(f"SELFTEST OK: {len(targets)} targets rendered")
    return 0


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--selftest":
        sys.exit(_selftest())
    JSONRPCServer().run_stdio()
