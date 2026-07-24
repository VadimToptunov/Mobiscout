"""The base error type for the whole project.

Harvested from the (dead) ``core/exceptions`` module, which defined a 21-class
hierarchy rooted at ``MobileTestError`` that nothing live used. Rather than
relocate all 21 speculative subclasses — the same speculative-generality smell the
review flags elsewhere — we keep only the *base*, renamed to the product, and give
it a real consumer: the live CLI service errors inherit from it, so the CLI can
``except MobiscoutError`` at its boundary and report any of them uniformly.

Add a typed subclass here only when a call site actually needs to distinguish it
(e.g. to recover differently) — not preemptively.
"""


class MobiscoutError(Exception):
    """Base class for every error Mobiscout raises deliberately.

    Catch this at the CLI boundary to separate expected, reportable failures
    (a missing device, an unparseable model) from genuine bugs, which should
    surface with a traceback.
    """
