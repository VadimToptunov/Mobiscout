"""
Generate the example crawl-kit committed under examples/shop_demo/.

Deterministic and device-free: it builds a realistic CrawlResult for a small
shopping app (Login -> Catalog -> Product -> Cart) and writes the kit through the
same code path as `mobiscout crawl --style pom` (``write_kit``) — inventory,
interaction graph, coverage, and one runnable Page-Object project per target —
so the README can show exactly what the tool produces. Re-run to refresh:

    python examples/generate.py
"""

import shutil
from pathlib import Path

from framework.cli.crawl_service import write_kit
from framework.codegen import get_emitter
from framework.codegen.api_test import emit_api_tests
from framework.crawler.app_crawler import CrawlElement, CrawlResult, CrawlScreen
from framework.crawler.to_codegen import build_test_model

PKG = "com.example.shop"
ACTIVITY = ".MainActivity"
OUT = Path(__file__).parent / "shop_demo"
# Each becomes its own runnable project under shop_demo/<target>/.
TARGETS = (
    "python_pytest",
    "python_pytest_bdd",
    "python_behave",
    "java_testng",
    "kotlin_appium",
    "js_webdriverio",
    "js_cucumber",
)


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


def _write(root: Path, files: dict) -> None:
    for name, content in files.items():
        dest = root / name
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(content, encoding="utf-8", newline="\n")


def main():
    result = build_result()
    shutil.rmtree(OUT, ignore_errors=True)  # no stale files from an older layout

    # 1) The kit, exactly as `mobiscout crawl --style pom --targets ...` writes it.
    report = write_kit(
        result=result,
        output=str(OUT),
        package=PKG,
        targets=",".join(TARGETS),
        style="pom",
        scaffold=False,
        server="http://localhost:4723",
        app_activity=ACTIVITY,
        launch_args=(),
    )
    for line in report.warnings:
        print(f"warning: {line}")

    # 2) For comparison: the same crawl as a standalone file (`--style flat`).
    model = build_test_model(result, app_package=PKG, app_activity=ACTIVITY)
    _write(OUT / "flat" / "python_pytest", get_emitter("python_pytest").emit(model))

    # 3) API contract tests.
    _write(OUT / "api", emit_api_tests(_Api(), base_url="https://api.example-shop.com"))

    print(f"Wrote example kit to {OUT} ({len(model.cases)} test cases, {len(result.screens)} screens)")


if __name__ == "__main__":
    main()
