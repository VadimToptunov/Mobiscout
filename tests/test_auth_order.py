"""Auth prefix runs in the order gates were *passed* (device-free): the config
lists waypoints most-specific-first (so the OTP matches before the login's generic
has_input), but a generated test must log in *before* entering the OTP."""

from framework.codegen.ir import ActionType
from framework.crawler.app_crawler import AppCrawler
from framework.crawler.to_codegen import build_test_model, waypoints_to_steps
from framework.crawler.waypoints import Waypoint
from tests.test_gate_chaining import APP, _ChainDriver

# Config order is specificity order: OTP first (its text match), login last.
_OTP = Waypoint(
    when={"text_contains": "enter the code"}, action="fill", data={"fields": {"code": "424242"}, "submit": "verify"}
)
_LOGIN = Waypoint(when={"has_input": True}, action="fill", data={"fields": {"user": "demo"}, "submit": "log in"})


def test_auth_sequence_records_fire_order_not_config_order():
    result = AppCrawler(_ChainDriver(), APP, waypoints=[_OTP, _LOGIN]).crawl()
    # login fired first (on the login screen), then OTP — the reverse of config.
    assert [wp.data["fields"] for wp in result.auth_sequence] == [{"user": "demo"}, {"code": "424242"}]


def test_generated_auth_prefix_logs_in_before_otp():
    result = AppCrawler(_ChainDriver(), APP, waypoints=[_OTP, _LOGIN]).crawl()
    model = build_test_model(result, APP, waypoints=[_OTP, _LOGIN])
    typed = [s.text for c in model.cases for s in c.steps if s.action == ActionType.TYPE]
    # "demo" (login) is entered before "424242" (OTP) in the generated steps.
    assert "demo" in typed and "424242" in typed
    assert typed.index("demo") < typed.index("424242")


def test_no_waypoints_no_auth_sequence():
    result = AppCrawler(_ChainDriver(), APP).crawl()
    assert result.auth_sequence == []
    # waypoints_to_steps still fine with the empty sequence.
    assert waypoints_to_steps(result.auth_sequence, "android") == []
