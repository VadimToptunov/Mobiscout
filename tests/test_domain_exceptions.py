"""The domain layer gives every deliberate Mobiscout failure a single base,
`MobiscoutError`, so the CLI boundary can catch them uniformly. This pins that the
live CLI service errors actually inherit it (harvested from the dead
core/exceptions — see docs/CODE_REVIEW.md §2 group 3).
"""

from framework.domain import MobiscoutError
from framework.cli.crawl_service import CrawlServiceError
from framework.cli.generate_service import GenerateServiceError


def test_service_errors_share_the_domain_base():
    assert issubclass(CrawlServiceError, MobiscoutError)
    assert issubclass(GenerateServiceError, MobiscoutError)


def test_can_catch_any_service_error_uniformly():
    for exc in (CrawlServiceError("boom"), GenerateServiceError("bad model")):
        try:
            raise exc
        except MobiscoutError as caught:
            assert str(caught)  # message preserved
        else:  # pragma: no cover - the except must fire
            raise AssertionError(f"{type(exc).__name__} was not caught as MobiscoutError")
