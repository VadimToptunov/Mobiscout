"""Static interaction graph from source (framework/crawler/source_graph.py).

Builds the crawler's own graph shape from an AnalysisResult with no device, so the
existing build_graph / exporters work on a predicted (source-first) graph.
"""

from framework.analyzers.analysis_result import (
    AnalysisResult,
    NavigationCandidate,
    ScreenCandidate,
    UIElementCandidate,
)
from framework.crawler.source_graph import analyze_source_tree, source_crawl_result, source_graph


def _analysis() -> AnalysisResult:
    # HomeScreen --navigate("details/{id}")--> DetailsScreen (registered via a sealed route),
    # HomeScreen --navigate("settings")--> SettingsScreen (screen carries its own route).
    return AnalysisResult(
        platform="android",
        source_path="/x",
        screens=[
            ScreenCandidate(name="HomeScreen", file_path="a.kt", line_number=1),
            ScreenCandidate(name="DetailsScreen", file_path="b.kt", line_number=1),
            ScreenCandidate(name="SettingsScreen", file_path="c.kt", line_number=1, route="settings"),
        ],
        ui_elements=[
            UIElementCandidate(
                id="open_details", type="Button", screen="HomeScreen", file_path="a.kt", line_number=2, test_tag="open"
            ),
        ],
        navigation=[
            # sealed-class registry: route "details" -> screen NAME "DetailsScreen"
            NavigationCandidate(
                from_screen=None, to_screen="DetailsScreen", route="details", file_path="n.kt", line_number=1
            ),
            # call sites (from a screen, to a route)
            NavigationCandidate(
                from_screen="HomeScreen",
                to_screen="details/{id}",
                route="details/{id}",
                trigger="Open",
                file_path="a.kt",
                line_number=3,
            ),
            NavigationCandidate(
                from_screen="HomeScreen", to_screen="settings", route="settings", file_path="a.kt", line_number=4
            ),
        ],
    )


def test_source_crawl_result_maps_screens_and_resolves_routes():
    crawl = source_crawl_result(_analysis())
    # three detected screens are nodes, keyed by name
    assert set(crawl.screens) == {"HomeScreen", "DetailsScreen", "SettingsScreen"}
    # the HomeScreen node carries its discovered element
    assert any(e.resource_id == "open" for e in crawl.screens["HomeScreen"].elements)
    # navigate("details/{id}") resolved through the sealed route registry to the screen name
    edges = {(t.src, t.dst) for t in crawl.transitions}
    assert ("HomeScreen", "DetailsScreen") in edges
    # navigate("settings") resolved via the screen's own route
    assert ("HomeScreen", "SettingsScreen") in edges
    # the sealed registry entry (from_screen None) is NOT an edge
    assert all(t.src for t in crawl.transitions)


def test_source_graph_is_named_and_analysable():
    graph = source_graph(_analysis())
    names = {n.name for n in graph.nodes}
    assert {"HomeScreen", "DetailsScreen", "SettingsScreen"} <= names
    # the exporters read the names, not opaque "Screen N"
    mermaid = __import__("framework.crawler.graph", fromlist=["to_mermaid"]).to_mermaid(graph)
    assert "HomeScreen" in mermaid
    # DetailsScreen and SettingsScreen are reachable from the entry (HomeScreen)
    assert graph.unreachable() == []


def test_unresolved_route_becomes_its_own_node():
    # A navigate() to a route with no screen and no registry entry still shows the
    # destination — by the route string — instead of dropping the edge.
    analysis = AnalysisResult(
        platform="android",
        source_path="/x",
        screens=[ScreenCandidate(name="HomeScreen", file_path="a.kt", line_number=1)],
        navigation=[
            NavigationCandidate(
                from_screen="HomeScreen", to_screen="checkout", route="checkout", file_path="a.kt", line_number=2
            ),
        ],
    )
    crawl = source_crawl_result(analysis)
    assert "checkout" in crawl.screens
    assert ("HomeScreen", "checkout") in {(t.src, t.dst) for t in crawl.transitions}


def test_analyze_source_tree_end_to_end(tmp_path):
    # A tiny Compose project through the real analyzer -> a named, connected graph.
    (tmp_path / "Home.kt").write_text(
        """
        @Composable
        fun HomeScreen(navController: NavController) {
            Button(modifier = Modifier.testTag("go"), onClick = { navController.navigate("details") }) {
                Text("Go")
            }
        }

        @Composable
        fun DetailsScreen() { Text("Details") }
        """,
        encoding="utf-8",
    )
    graph = source_graph(analyze_source_tree(str(tmp_path)))
    names = {n.name for n in graph.nodes}
    assert "HomeScreen" in names and "DetailsScreen" in names
    assert ("HomeScreen", "DetailsScreen") in {
        (graph.nodes[e.src - 1].name, graph.nodes[e.dst - 1].name) for e in graph.edges
    }
