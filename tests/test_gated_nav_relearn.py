"""A login-first app opens on a gate with no bottom bar, so the nav bar can only
be learned AFTER the gate is passed. Before the fix, _learn_nav_bar ran once on the
entry (login) screen, found nothing, and never re-ran — so a gated multi-tab app
fell to the plain _dfs and only ever explored the first tab. This pins that the bar
is (re-)learned from the post-auth screen."""

from framework.crawler.app_crawler import AppCrawler, parse_screen
from framework.crawler.models import CrawlResult

APP = "com.example.app"


def _btn(text, rid, bounds):
    x1, y1, x2, y2 = bounds
    return (
        f'<node class="android.widget.Button" resource-id="{rid}" text="{text}" content-desc="" '
        f'clickable="true" bounds="[{x1},{y1}][{x2},{y2}]"/>'
    )


def _hier(*nodes):
    return '<hierarchy rotation="0">' + "".join(nodes) + "</hierarchy>"


# Login: a single top-of-screen field/button, NO bottom bar.
LOGIN = _hier(_btn("Sign in", "id/signin", (0, 0, 1000, 120)))
# Post-auth home: content up top + a 3-entry bottom bar in the bottom 15% of a
# 1000px-tall screen (centers >= 850).
HOME = _hier(
    _btn("A note", "id/content", (0, 200, 1000, 320)),
    _btn("Home", "id/tab_home", (0, 900, 333, 990)),
    _btn("Search", "id/tab_search", (334, 900, 666, 990)),
    _btn("Profile", "id/tab_profile", (667, 900, 1000, 990)),
)


class GatedDriver:
    """Serves the login screen until the (stubbed) gate is passed, then the home."""

    def __init__(self):
        self.current = "login"
        self.pkg = APP

    def page_source(self):
        return HOME if self.current == "home" else LOGIN

    def current_package(self):
        return self.pkg

    def tap(self, x, y):
        pass  # taps go nowhere — we only care that the bar was learned

    def back(self):
        pass


def test_nav_bar_is_relearned_after_the_entry_gate():
    driver = GatedDriver()
    crawler = AppCrawler(driver, APP, max_steps=6)

    # Stand in for a login waypoint: report the gate passed and reveal the home.
    def _pass_gates(screen):
        driver.current = "home"
        return True

    crawler._pass_gates = _pass_gates  # type: ignore[assignment]
    crawler._explore(CrawlResult(screens={}, transitions=[]))

    # The three bottom-strip tabs must have been learned from the post-auth screen.
    home = parse_screen(HOME)
    tabs = [e for e in home.interactive() if e.resource_id.startswith("id/tab_")]
    learned = {crawler._element_key(e) for e in tabs}
    assert crawler._nav_keys, "nav bar was not learned after the gate — gated tab apps under-explored"
    assert learned <= crawler._nav_keys, "the post-auth tab bar was not the bar that got learned"
