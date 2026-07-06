"""
Generate the example crawl-kit committed under examples/shop_demo/.

Deterministic and device-free: it builds a realistic CrawlResult for a small
shopping app (Login -> Catalog -> Product -> Cart) and runs the real pipeline —
element inventory, interaction graph, and multi-language tests — so the README
can show exactly what the tool produces. Re-run to refresh:

    python examples/generate.py
"""

from pathlib import Path

from framework.codegen import get_emitter
from framework.codegen.api_test import emit_api_tests
from framework.crawler.app_crawler import CrawlElement, CrawlResult, CrawlScreen
from framework.crawler.graph import build_graph, to_json, to_mermaid
from framework.crawler.page_kit import build_framework_kit
from framework.crawler.report import inventory_markdown
from framework.crawler.to_codegen import build_test_model

PKG = "com.example.shop"
OUT = Path(__file__).parent / "shop_demo"


def el(cls, text="", rid="", desc="", clickable=True):
    return CrawlElement(
        resource_id=(f"{PKG}:id/{rid}" if rid else ""),
        text=text,
        content_desc=desc,
        class_name=cls,
        clickable=clickable,
        bounds=(0, 0, 320, 64),
        package=PKG,
    )


def screen(fp, elements):
    return CrawlScreen(fingerprint=fp, elements=elements, platform="android", toolkit="native")


def build_result() -> CrawlResult:
    login = screen(
        "login",
        [
            el("android.widget.TextView", text="Welcome back", clickable=False),
            el("android.widget.EditText", rid="email", desc="Email"),
            el("android.widget.EditText", rid="password", desc="Password"),
            el("android.widget.CheckBox", text="Remember me", rid="remember"),
            el("android.widget.Button", text="Sign in", rid="signin"),
            el("android.widget.TextView", text="Forgot password?", rid="forgot"),
        ],
    )
    catalog = screen(
        "catalog",
        [
            el("android.widget.EditText", rid="search", desc="Search products"),
            el("android.widget.Button", text="Running Shoes", rid="p_shoes"),
            el("android.widget.Button", text="Backpack", rid="p_bag"),
            el("android.widget.ImageButton", rid="cart", desc="Cart"),
        ],
    )
    product = screen(
        "product",
        [
            el("android.widget.TextView", text="Running Shoes", clickable=False),
            el("android.widget.TextView", text="$89.00", clickable=False),
            el("android.widget.Button", text="Add to cart", rid="add"),
        ],
    )
    cart = screen(
        "cart",
        [
            el("android.widget.TextView", text="Your cart", clickable=False),
            el("android.widget.Button", text="Place order", rid="order"),
        ],
    )
    result = CrawlResult(screens={"login": login, "catalog": catalog, "product": product, "cart": cart})
    result.transitions = [
        ("login", el("android.widget.Button", text="Sign in", rid="signin"), "catalog"),
        ("catalog", el("android.widget.Button", text="Running Shoes", rid="p_shoes"), "product"),
        ("catalog", el("android.widget.ImageButton", rid="cart", desc="Cart"), "cart"),
        ("product", el("android.widget.Button", text="Add to cart", rid="add"), "cart"),
    ]
    return result


class _Api:
    """Minimal stand-in for an AppModel with recorded api_calls."""

    class Call:
        def __init__(self, name, method, endpoint, schema=None):
            self.name, self.method, self.endpoint, self.request_schema = name, method, endpoint, schema or {}

    api_calls = {
        "login": Call("login", "POST", "/auth/login", {"email": "", "password": ""}),
        "products": Call("list_products", "GET", "/products"),
        "add_to_cart": Call("add_to_cart", "POST", "/cart/items", {"product_id": "", "qty": 0}),
    }


def main():
    result = build_result()
    OUT.mkdir(parents=True, exist_ok=True)

    (OUT / "inventory.md").write_text(inventory_markdown(result, PKG), encoding="utf-8", newline="\n")

    graph = build_graph(result, PKG)
    (OUT / "graph.mmd").write_text(to_mermaid(graph), encoding="utf-8", newline="\n")
    (OUT / "graph.json").write_text(to_json(graph), encoding="utf-8", newline="\n")

    model = build_test_model(result, app_package=PKG, app_activity=".MainActivity")

    # 1) Framework-structured output — Page Objects + conftest + POM-style tests.
    for rel, content in build_framework_kit(result, model, PKG).items():
        dest = OUT / "framework" / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(content, encoding="utf-8", newline="\n")

    # 2) BDD — Gherkin .feature files + step definitions (Python + JS).
    for target in ("python_pytest_bdd", "js_cucumber"):
        for name, content in get_emitter(target).emit(model).items():
            dest = OUT / "bdd" / target / name
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(content, encoding="utf-8", newline="\n")

    # 3) Flat multi-language suites — same IR, many targets (for comparison).
    for target in ("python_pytest", "java_testng", "js_webdriverio"):
        for name, content in get_emitter(target).emit(model).items():
            dest = OUT / "flat" / target / name
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(content, encoding="utf-8", newline="\n")

    # 4) API contract tests.
    for name, content in emit_api_tests(_Api(), base_url="https://api.example-shop.com").items():
        (OUT / "api" / name).parent.mkdir(parents=True, exist_ok=True)
        (OUT / "api" / name).write_text(content, encoding="utf-8", newline="\n")

    print(f"Wrote example kit to {OUT} ({len(model.cases)} test cases, {len(graph.nodes)} screens)")


if __name__ == "__main__":
    main()
