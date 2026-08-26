"""Jetpack Compose exposes every tappable control as an anonymous `android.view.View`
whose visible caption sits on a NON-clickable child::

    [clickable] android.view.View  ""
        TextView  "Add plant"

Read literally, such a control has no label — so it gets no locator, generated tests
can't target it, and coverage reports 0% on an app the crawl actually walked. Found by
crawling Google's Sunflower on a real emulator: 2 screens, 0% element coverage. Lifting
the descendant's caption onto the clickable node took the same app to 4 screens / 94%.

Compose is the default for new Android apps, so these pin that behaviour.
"""

from framework.crawler.coverage_report import COMPOSE_TESTTAG_DOCS, IOS_A11Y_DOCS, locator_advice
from framework.crawler.models import CrawlElement, CrawlResult, CrawlScreen
from framework.crawler.parse import parse_screen


def _compose_button(caption: str, bounds: str, tag: str = "TextView") -> str:
    """A Compose control: anonymous clickable wrapper + labelled, non-clickable child."""
    return (
        f'<node class="android.view.View" resource-id="" text="" content-desc="" '
        f'clickable="true" bounds="{bounds}">'
        f'<node class="android.widget.{tag}" resource-id="" text="{caption}" content-desc="" '
        f'clickable="false" bounds="{bounds}"/>'
        f"</node>"
    )


def _screen(*nodes: str) -> str:
    return '<hierarchy rotation="0">' + "".join(nodes) + "</hierarchy>"


def test_compose_control_takes_the_caption_from_its_child():
    screen = parse_screen(_screen(_compose_button("Add plant", "[0,0][300,80]")))
    tappable = screen.interactive()
    assert [e.label for e in tappable] == ["Add plant"]


def test_caption_is_read_through_an_intermediate_wrapper():
    # Compose nests several layout views between the clickable node and the text.
    nested = (
        '<node class="android.view.View" resource-id="" text="" content-desc="" '
        'clickable="true" bounds="[0,0][300,80]">'
        '<node class="android.view.View" resource-id="" text="" content-desc="" '
        'clickable="false" bounds="[0,0][300,80]">'
        '<node class="android.widget.TextView" resource-id="" text="Plant list" content-desc="" '
        'clickable="false" bounds="[0,0][300,80]"/>'
        "</node></node>"
    )
    assert [e.label for e in parse_screen(_screen(nested)).interactive()] == ["Plant list"]


def test_a_nested_control_keeps_its_own_caption():
    # A clickable inside a clickable (a row with its own action button): the outer node
    # must not steal the inner one's label, or both tests would target the same control.
    outer = (
        '<node class="android.view.View" resource-id="" text="" content-desc="" '
        'clickable="true" bounds="[0,0][300,80]">'
        '<node class="android.view.View" resource-id="" text="" content-desc="" '
        'clickable="true" bounds="[200,0][300,80]">'
        '<node class="android.widget.TextView" resource-id="" text="Share" content-desc="" '
        'clickable="false" bounds="[200,0][300,80]"/>'
        "</node></node>"
    )
    labels = [e.label for e in parse_screen(_screen(outer)).interactive()]
    assert "Share" in labels  # the inner control keeps it
    assert labels.count("Share") == 1  # and the outer one did not take it too


def test_a_control_with_its_own_label_is_untouched():
    native = (
        '<node class="android.widget.Button" resource-id="id/ok" text="OK" content-desc="" '
        'clickable="true" bounds="[0,0][100,40]"/>'
    )
    element = parse_screen(_screen(native)).interactive()[0]
    assert element.label == "OK" and element.content_desc == ""


def _ios_result(identified: int, total: int) -> CrawlResult:
    """An iOS screen where `identified` of `total` controls carry a real identifier.
    XCUITest echoes the label into `name` when the app sets none — that is the un-identified
    case, and it is what the advice is about."""
    elements = []
    for i in range(total):
        label = f"Button {i}"
        elements.append(
            CrawlElement(
                resource_id=f"btn_{i}" if i < identified else label,  # echo == no identifier
                text="",
                content_desc=label,
                class_name="XCUIElementTypeButton",
                clickable=True,
                bounds=(0, i * 40, 100, i * 40 + 40),
            )
        )
    return CrawlResult(screens={"fp": CrawlScreen("fp", elements, platform="ios")})


def test_ios_advice_fires_when_controls_only_echo_their_label():
    advice = locator_advice("native", "ios", _ios_result(identified=0, total=6))
    assert IOS_A11Y_DOCS in advice and "accessibilityIdentifier" in advice


def test_ios_advice_is_silent_when_the_app_sets_identifiers():
    assert locator_advice("native", "ios", _ios_result(identified=6, total=6)) == ""


def test_compose_advice_names_the_debug_variant_only():
    advice = locator_advice("compose", "android", CrawlResult())
    assert COMPOSE_TESTTAG_DOCS in advice
    # Publishing internal tags as resource-ids is a test-build concern, never a release one.
    assert "debug/test build variant only" in advice


def test_no_advice_for_a_plain_android_app():
    assert locator_advice("native", "android", CrawlResult()) == ""
