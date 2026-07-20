"""Model enrichment + project integration: non-destructive merging of static
analysis results into an existing App Model, selector fallback merging, and
end-to-end integration against a project tree. Tests build small in-memory
models/analysis dicts and use tmp_path for the filesystem-touching paths, since
the module had no coverage."""

import yaml

from framework.integration.model_enricher import (
    EnrichmentResult,
    ModelEnricher,
    ProjectIntegrator,
)

# ---------------------------------------------------------------------------
# EnrichmentResult
# ---------------------------------------------------------------------------


def test_enrichment_result_defaults_are_zero_and_empty():
    result = EnrichmentResult()

    assert result.screens_enriched == 0
    assert result.elements_added == 0
    assert result.selectors_updated == 0
    assert result.api_endpoints_added == 0
    assert result.navigation_added == 0
    assert result.warnings == []
    assert result.errors == []


# ---------------------------------------------------------------------------
# ModelEnricher.enrich_model / _enrich_screens
# ---------------------------------------------------------------------------


def test_enrich_model_does_not_mutate_original():
    original = {"screens": [{"name": "Login", "elements": [{"id": "user"}]}]}
    analysis = {"screens": [{"name": "Login", "ui_elements": [{"id": "password"}]}]}

    enricher = ModelEnricher()
    enriched = enricher.enrich_model(original, analysis)

    # Original untouched (deep copy performed).
    assert len(original["screens"][0]["elements"]) == 1
    # Enriched has the new element.
    ids = {e["id"] for e in enriched["screens"][0]["elements"]}
    assert ids == {"user", "password"}


def test_enrich_screens_adds_new_element_with_full_metadata():
    model = {"screens": [{"name": "Login", "elements": []}]}
    analysis = {
        "screens": [
            {
                "name": "Login",
                "ui_elements": [
                    {
                        "id": "submit",
                        "type": "button",
                        "selector": {"android": "id/submit"},
                        "priority": "high",
                        "file_path": "LoginActivity.java",
                    }
                ],
            }
        ]
    }

    enricher = ModelEnricher()
    enriched = enricher.enrich_model(model, analysis)

    elem = enriched["screens"][0]["elements"][0]
    assert elem["id"] == "submit"
    assert elem["type"] == "button"
    assert elem["selector"] == {"android": "id/submit"}
    assert elem["test_priority"] == "high"
    assert elem["description"] == "Discovered from LoginActivity.java"
    assert enricher.result.elements_added == 1
    assert enricher.result.screens_enriched == 1


def test_enrich_screens_uses_defaults_when_metadata_missing():
    model = {"screens": [{"name": "Home", "elements": []}]}
    analysis = {"screens": [{"name": "Home", "ui_elements": [{"id": "banner"}]}]}

    enricher = ModelEnricher()
    enriched = enricher.enrich_model(model, analysis)

    elem = enriched["screens"][0]["elements"][0]
    assert elem["type"] == "generic"
    assert elem["selector"] == {}
    assert elem["test_priority"] == "medium"
    assert elem["description"] == "Discovered from source"


def test_enrich_screens_skips_existing_element_ids():
    model = {"screens": [{"name": "Login", "elements": [{"id": "user"}]}]}
    analysis = {"screens": [{"name": "Login", "ui_elements": [{"id": "user"}]}]}

    enricher = ModelEnricher()
    enriched = enricher.enrich_model(model, analysis)

    assert len(enriched["screens"][0]["elements"]) == 1
    assert enricher.result.elements_added == 0
    # No elements actually added -> screen not counted as enriched.
    assert enricher.result.screens_enriched == 0


def test_enrich_screens_dedups_duplicate_ids_within_analysis():
    model = {"screens": [{"name": "Login", "elements": []}]}
    analysis = {
        "screens": [
            {
                "name": "Login",
                "ui_elements": [{"id": "field"}, {"id": "field"}],
            }
        ]
    }

    enricher = ModelEnricher()
    enriched = enricher.enrich_model(model, analysis)

    assert len(enriched["screens"][0]["elements"]) == 1
    assert enricher.result.elements_added == 1
    assert enricher.result.screens_enriched == 1


def test_enrich_screens_creates_elements_list_when_absent():
    model = {"screens": [{"name": "Login"}]}
    analysis = {"screens": [{"name": "Login", "ui_elements": [{"id": "x"}]}]}

    enricher = ModelEnricher()
    enriched = enricher.enrich_model(model, analysis)

    assert enriched["screens"][0]["elements"][0]["id"] == "x"


def test_enrich_screens_ignores_elements_without_id():
    model = {"screens": [{"name": "Login", "elements": []}]}
    analysis = {"screens": [{"name": "Login", "ui_elements": [{"type": "button"}]}]}

    enricher = ModelEnricher()
    enriched = enricher.enrich_model(model, analysis)

    assert enriched["screens"][0]["elements"] == []
    assert enricher.result.elements_added == 0


def test_enrich_screens_preserve_existing_drops_unknown_screen():
    model = {"screens": [{"name": "Login", "elements": []}]}
    analysis = {"screens": [{"name": "Settings", "ui_elements": [{"id": "a"}]}]}

    enricher = ModelEnricher(preserve_existing=True)
    enriched = enricher.enrich_model(model, analysis)

    names = {s["name"] for s in enriched["screens"]}
    assert names == {"Login"}


def test_enrich_screens_non_preserve_adds_new_screen_skeleton():
    model = {"screens": [{"name": "Login", "elements": []}]}
    analysis = {
        "screens": [
            {
                "name": "SettingsScreen",
                "file_path": "Settings.kt",
                "ui_elements": [{"id": "a"}],
            }
        ]
    }

    enricher = ModelEnricher(preserve_existing=False)
    enriched = enricher.enrich_model(model, analysis)

    new = next(s for s in enriched["screens"] if s["name"] == "SettingsScreen")
    assert new["id"] == "settings"  # "screen" stripped, lowercased
    assert new["description"] == "Discovered from Settings.kt"
    assert new["elements"] == []


def test_enrich_screens_non_preserve_new_screen_default_file_path():
    model = {"screens": []}
    analysis = {"screens": [{"name": "Home"}]}

    enricher = ModelEnricher(preserve_existing=False)
    enriched = enricher.enrich_model(model, analysis)

    home = enriched["screens"][0]
    assert home["description"] == "Discovered from analysis"


# ---------------------------------------------------------------------------
# ModelEnricher._add_api_endpoints
# ---------------------------------------------------------------------------


def test_add_api_endpoints_appends_new_endpoint_with_metadata():
    model = {}
    analysis = {
        "api_endpoints": [
            {
                "method": "POST",
                "path": "/users",
                "function_name": "createUser",
                "interface_name": "UserService",
                "file_path": "UserApi.kt",
            }
        ]
    }

    enricher = ModelEnricher()
    enriched = enricher.enrich_model(model, analysis)

    ep = enriched["api_calls"][0]
    assert ep["name"] == "createUser"
    assert ep["method"] == "POST"
    assert ep["endpoint"] == "/users"  # already starts with "/"
    assert ep["description"] == "From UserService"
    assert ep["requires_auth"] is True
    assert ep["parameters"] == []
    assert ep["discovered_from"] == "UserApi.kt"
    assert enricher.result.api_endpoints_added == 1


def test_add_api_endpoints_prefixes_relative_path():
    model = {}
    analysis = {"api_endpoints": [{"method": "GET", "path": "profile"}]}

    enricher = ModelEnricher()
    enriched = enricher.enrich_model(model, analysis)

    assert enriched["api_calls"][0]["endpoint"] == "/api/v1/profile"


def test_add_api_endpoints_generates_default_name_and_defaults():
    model = {}
    analysis = {"api_endpoints": [{"path": "a/b"}]}

    enricher = ModelEnricher()
    enriched = enricher.enrich_model(model, analysis)

    ep = enriched["api_calls"][0]
    assert ep["method"] == "GET"
    assert ep["name"] == "api_get_a_b"
    assert ep["description"] == "From service"
    assert ep["discovered_from"] == "analysis"


def test_add_api_endpoints_skips_duplicate_method_path_pair():
    model = {"api_calls": [{"method": "GET", "endpoint": "/x"}]}
    analysis = {"api_endpoints": [{"method": "GET", "path": "/x"}]}

    enricher = ModelEnricher()
    enriched = enricher.enrich_model(model, analysis)

    assert len(enriched["api_calls"]) == 1
    assert enricher.result.api_endpoints_added == 0


# ---------------------------------------------------------------------------
# ModelEnricher._add_navigation
# ---------------------------------------------------------------------------


def test_add_navigation_appends_all_flows():
    model = {}
    analysis = {"navigation": [{"from": "A", "to": "B"}, {"from": "B", "to": "C"}]}

    enricher = ModelEnricher()
    enriched = enricher.enrich_model(model, analysis)

    assert enriched["navigation"] == [{"from": "A", "to": "B"}, {"from": "B", "to": "C"}]
    assert enricher.result.navigation_added == 2


def test_add_navigation_extends_existing_list():
    model = {"navigation": [{"from": "X", "to": "Y"}]}
    analysis = {"navigation": [{"from": "A", "to": "B"}]}

    enricher = ModelEnricher()
    enriched = enricher.enrich_model(model, analysis)

    assert len(enriched["navigation"]) == 2
    assert enricher.result.navigation_added == 1


def test_enrich_model_handles_empty_analysis():
    model = {"screens": [{"name": "Login", "elements": []}]}

    enricher = ModelEnricher()
    enriched = enricher.enrich_model(model, {})

    assert enriched["api_calls"] == []
    assert enriched["navigation"] == []
    assert enricher.result.elements_added == 0


# ---------------------------------------------------------------------------
# ModelEnricher.merge_selectors
# ---------------------------------------------------------------------------


def test_merge_selectors_fills_missing_primary_selectors():
    enricher = ModelEnricher()
    merged = enricher.merge_selectors({}, {"android": "id/a", "ios": "name/b"})

    assert merged["android"] == "id/a"
    assert merged["ios"] == "name/b"
    # Primaries equal to the only discovered value -> not added as fallbacks.
    assert merged["android_fallback"] == []
    assert merged["ios_fallback"] == []
    assert enricher.result.selectors_updated == 0


def test_merge_selectors_adds_differing_value_as_fallback():
    enricher = ModelEnricher()
    existing = {"android": "id/primary", "ios": "name/primary"}
    merged = enricher.merge_selectors(existing, {"android": "id/other", "ios": "name/other"})

    assert merged["android"] == "id/primary"
    assert merged["android_fallback"] == ["id/other"]
    assert merged["ios_fallback"] == ["name/other"]
    assert enricher.result.selectors_updated == 2


def test_merge_selectors_does_not_duplicate_existing_fallback():
    enricher = ModelEnricher()
    existing = {"android": "id/primary", "android_fallback": ["id/other"]}
    merged = enricher.merge_selectors(existing, {"android": "id/other"})

    assert merged["android_fallback"] == ["id/other"]
    assert enricher.result.selectors_updated == 0


def test_merge_selectors_does_not_mutate_existing_input():
    enricher = ModelEnricher()
    existing = {"android": "id/primary"}
    enricher.merge_selectors(existing, {"android": "id/other"})

    assert "android_fallback" not in existing


def test_merge_selectors_ignores_empty_discovered():
    enricher = ModelEnricher()
    merged = enricher.merge_selectors({"android": "id/a"}, {})

    assert merged == {"android": "id/a"}
    assert enricher.result.selectors_updated == 0


# ---------------------------------------------------------------------------
# ProjectIntegrator.detect_framework
# ---------------------------------------------------------------------------


def test_detect_framework_pytest(tmp_path):
    (tmp_path / "pytest.ini").write_text("[pytest]\n")
    assert ProjectIntegrator(tmp_path).detect_framework() == "pytest"


def test_detect_framework_unittest(tmp_path):
    (tmp_path / "setup.py").write_text("")
    assert ProjectIntegrator(tmp_path).detect_framework() == "unittest"


def test_detect_framework_robot(tmp_path):
    (tmp_path / "robot").mkdir()
    assert ProjectIntegrator(tmp_path).detect_framework() == "robot"


def test_detect_framework_unknown(tmp_path):
    assert ProjectIntegrator(tmp_path).detect_framework() == "unknown"


# ---------------------------------------------------------------------------
# ProjectIntegrator.find_page_objects / extract_elements_from_page_objects
# ---------------------------------------------------------------------------


def test_find_page_objects_matches_known_patterns(tmp_path):
    po_dir = tmp_path / "page_objects"
    po_dir.mkdir()
    (po_dir / "login_page.py").write_text("x = 1\n")
    pages_dir = tmp_path / "pages"
    pages_dir.mkdir()
    (pages_dir / "home.py").write_text("y = 2\n")

    found = ProjectIntegrator(tmp_path).find_page_objects()
    names = {p.name for p in found}
    assert names == {"login_page.py", "home.py"}


def test_extract_elements_skips_files_without_locators(tmp_path):
    po_file = tmp_path / "empty_po.py"
    po_file.write_text("class Foo:\n    pass\n")

    integrator = ProjectIntegrator(tmp_path)
    screens = integrator.extract_elements_from_page_objects([po_file])

    assert screens == {}


# ---------------------------------------------------------------------------
# ProjectIntegrator.integrate (end-to-end)
# ---------------------------------------------------------------------------


def test_integrate_loads_existing_model_and_writes_default_output(tmp_path):
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    model = {"name": "App", "screens": [{"name": "Login", "elements": []}]}
    (config_dir / "app_model.yaml").write_text(yaml.dump(model))

    analysis = {"screens": [{"name": "Login", "ui_elements": [{"id": "user"}]}]}

    integrator = ProjectIntegrator(tmp_path)
    result = integrator.integrate(analysis)

    assert isinstance(result, EnrichmentResult)
    assert result.elements_added == 1

    out_path = config_dir / "app_model_enriched.yaml"
    assert out_path.exists()
    written = yaml.safe_load(out_path.read_text())
    ids = {e["id"] for e in written["screens"][0]["elements"]}
    assert "user" in ids


def test_integrate_creates_model_from_page_objects_when_no_model_file(tmp_path):
    po_dir = tmp_path / "page_objects"
    po_dir.mkdir()
    (po_dir / "login_page.py").write_text('username = ("id", "user_field")\n')

    integrator = ProjectIntegrator(tmp_path)
    result = integrator.integrate({}, preserve_existing=False)

    assert isinstance(result, EnrichmentResult)
    out_path = tmp_path / "config" / "app_model_enriched.yaml"
    written = yaml.safe_load(out_path.read_text())
    names = {s["name"] for s in written["screens"]}
    assert "login" in names
    login = next(s for s in written["screens"] if s["name"] == "login")
    assert login["description"] == "Extracted from existing Page Object"


def test_integrate_writes_to_custom_output_path(tmp_path):
    analysis = {"screens": []}
    custom = tmp_path / "out" / "custom_model.yaml"

    integrator = ProjectIntegrator(tmp_path)
    integrator.integrate(analysis, output_path=custom)

    assert custom.exists()


def test_integrate_sets_detected_framework_type(tmp_path):
    (tmp_path / "pytest.ini").write_text("[pytest]\n")

    integrator = ProjectIntegrator(tmp_path)
    integrator.integrate({})

    assert integrator.framework_type == "pytest"
