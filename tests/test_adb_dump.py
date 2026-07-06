"""`uiautomator dump /dev/tty` streams XML plus a trailing status line; the
extractor must return clean hierarchy XML, or None so the driver falls back."""

from framework.crawler.adb_driver import _extract_hierarchy


def test_strips_trailing_status_line():
    raw = '<?xml version="1.0"?><hierarchy rotation="0"><node/></hierarchy>\nUI hierarchy dumped to: /dev/tty'
    xml = _extract_hierarchy(raw)
    assert xml == '<?xml version="1.0"?><hierarchy rotation="0"><node/></hierarchy>'


def test_drops_leading_noise_before_xml():
    raw = "WARNING: linker\n<hierarchy><node/></hierarchy>\nUI hierarchy dumped to: /dev/tty"
    assert _extract_hierarchy(raw) == "<hierarchy><node/></hierarchy>"


def test_none_when_no_hierarchy():
    assert _extract_hierarchy("ERROR: could not get idle state") is None
    assert _extract_hierarchy("") is None
