"""
Framework Extension - Integration with Existing Test Frameworks

This module extends mobile-observe-test-framework with:
1. Ability to enrich existing App Models
2. Merge analysis results with existing test artifacts
3. Non-destructive integration
4. Backward compatibility
"""

from copy import deepcopy
from pathlib import Path
from typing import Dict, List, Optional

import yaml
from pydantic import BaseModel


class EnrichmentResult(BaseModel):
    """Result of enrichment operation"""

    screens_enriched: int = 0
    elements_added: int = 0
    selectors_updated: int = 0
    api_endpoints_added: int = 0
    navigation_added: int = 0
    warnings: List[str] = []
    errors: List[str] = []


class ModelEnricher:
    """
    Enriches existing App Models with analysis results

    Features:
    - Non-destructive merging
    - Conflict resolution
    - Selector fallback addition
    - API endpoint discovery
    """

    def __init__(self, preserve_existing: bool = True):
        self.preserve_existing = preserve_existing
        self.result = EnrichmentResult()

    def enrich_model(self, existing_model: Dict, analysis_result: Dict) -> Dict:
        """
        Enrich existing model with analysis results

        Args:
            existing_model: Current App Model
            analysis_result: Static analysis results

        Returns:
            Enriched model (deep copy, original unchanged)
        """
        enriched = deepcopy(existing_model)

        # Enrich screens
        enriched = self._enrich_screens(enriched, analysis_result)

        # Add API endpoints
        enriched = self._add_api_endpoints(enriched, analysis_result)

        # Add navigation flows
        enriched = self._add_navigation(enriched, analysis_result)

        return enriched

    def _enrich_screens(self, model: Dict, analysis: Dict) -> Dict:
        """Enrich screen definitions"""

        existing_screens = {s["name"]: s for s in model.get("screens", [])}

        # Process discovered screens
        for screen_data in analysis.get("screens", []):
            screen_name = screen_data.get("name")

            if screen_name in existing_screens:
                # Enrich existing screen
                screen = existing_screens[screen_name]

                # Add new elements
                existing_elem_ids = {e["id"] for e in screen.get("elements", [])}
                elements_added_to_screen = 0

                for elem in screen_data.get("ui_elements", []):
                    elem_id = elem.get("id")
                    if elem_id and elem_id not in existing_elem_ids:
                        screen.setdefault("elements", []).append(
                            {
                                "id": elem_id,
                                "type": elem.get("type", "generic"),
                                "selector": elem.get("selector", {}),
                                "test_priority": elem.get("priority", "medium"),
                                "description": f"Discovered from {elem.get('file_path', 'source')}",
                            }
                        )
                        self.result.elements_added += 1
                        elements_added_to_screen += 1
                        # Update the set to prevent duplicates from analysis data
                        existing_elem_ids.add(elem_id)

                # Only increment if we actually added elements to this screen
                if elements_added_to_screen > 0:
                    self.result.screens_enriched += 1
            else:
                # Optionally add new screen
                if not self.preserve_existing:
                    model.setdefault("screens", []).append(
                        {
                            "name": screen_name,
                            "id": screen_name.lower().replace("screen", ""),
                            "description": f"Discovered from {screen_data.get('file_path', 'analysis')}",
                            "elements": [],
                        }
                    )

        return model

    def _add_api_endpoints(self, model: Dict, analysis: Dict) -> Dict:
        """Add discovered API endpoints"""

        if "api_calls" not in model:
            model["api_calls"] = []

        existing_endpoints = {
            f"{ep.get('method', 'GET')} {ep.get('endpoint', '')}" for ep in model["api_calls"]
        }

        # Add discovered endpoints
        for ep_data in analysis.get("api_endpoints", []):
            method = ep_data.get("method", "GET")
            path = ep_data.get("path", "")
            endpoint_key = f"{method} {path}"

            if endpoint_key not in existing_endpoints:
                model["api_calls"].append(
                    {
                        "name": ep_data.get(
                            "function_name", f"api_{method.lower()}_{path.replace('/', '_')}"
                        ),
                        "method": method,
                        "endpoint": f"/api/v1/{path}" if not path.startswith("/") else path,
                        "description": f"From {ep_data.get('interface_name', 'service')}",
                        "requires_auth": True,
                        "parameters": [],
                        "discovered_from": ep_data.get("file_path", "analysis"),
                    }
                )
                self.result.api_endpoints_added += 1

        return model

    def _add_navigation(self, model: Dict, analysis: Dict) -> Dict:
        """Add navigation flows"""

        if "navigation" not in model:
            model["navigation"] = []

        for nav in analysis.get("navigation", []):
            model["navigation"].append(nav)
            self.result.navigation_added += 1

        return model

    def merge_selectors(self, existing: Dict, discovered: Dict) -> Dict:
        """
        Merge selectors with fallback strategy

        Args:
            existing: Current selector
            discovered: Newly discovered selector

        Returns:
            Merged selector with fallbacks
        """
        merged = existing.copy()

        # Add primary selectors if missing
        if not merged.get("android") and discovered.get("android"):
            merged["android"] = discovered["android"]

        if not merged.get("ios") and discovered.get("ios"):
            merged["ios"] = discovered["ios"]

        # Add to fallback lists
        if discovered.get("android"):
            fallbacks = merged.setdefault("android_fallback", [])
            if discovered["android"] not in fallbacks and discovered["android"] != merged.get(
                    "android"
            ):
                fallbacks.append(discovered["android"])
                self.result.selectors_updated += 1

        if discovered.get("ios"):
            fallbacks = merged.setdefault("ios_fallback", [])
            if discovered["ios"] not in fallbacks and discovered["ios"] != merged.get("ios"):
                fallbacks.append(discovered["ios"])
                self.result.selectors_updated += 1

        return merged


class ProjectIntegrator:
    """
    Integrates framework with existing test projects

    Capabilities:
    - Detect existing test framework
    - Map existing Page Objects to screens
    - Generate missing artifacts
    - Update existing artifacts
    """

    def __init__(self, project_path: Path):
        self.project_path = Path(project_path)
        self.framework_type = None

    def detect_framework(self) -> str:
        """
        Detect existing test framework

        Returns:
            Framework type (pytest, unittest, robot, etc.)
        """
        if (self.project_path / "pytest.ini").exists():
            return "pytest"
        elif (self.project_path / "setup.py").exists():
            return "unittest"
        elif (self.project_path / "robot").exists():
            return "robot"
        else:
            return "unknown"

    def find_page_objects(self) -> List[Path]:
        """Find existing Page Object files"""
        page_object_files = []

        # Common patterns
        patterns = ["page_objects/**/*.py", "pages/**/*.py", "pom/**/*.py", "pageobjects/**/*.py"]

        for pattern in patterns:
            page_object_files.extend(self.project_path.glob(pattern))

        return page_object_files

    def extract_elements_from_page_objects(
            self, page_object_files: List[Path]
    ) -> Dict[str, List[Dict]]:
        """
        Extract element definitions from existing Page Objects

        Returns:
            Dict mapping screen names to element lists
        """
        screens = {}

        for po_file in page_object_files:
            screen_name = po_file.stem.replace("_page", "").replace("_po", "")

            # Basic parsing - can be enhanced
            content = po_file.read_text()

            # Look for locator patterns
            import re

            locators = re.findall(
                r'(\w+)\s*=\s*\(["\'](\w+)["\']\s*,\s*["\']([^"\']+)["\']\)', content
            )

            elements = []
            for name, by, value in locators:
                elements.append(
                    {
                        "id": name.lower(),
                        "selector": {
                            "xpath": value if by == "xpath" else None,
                            "android": value if by == "id" else None,
                        },
                    }
                )

            if elements:
                screens[screen_name] = elements

        return screens

    def integrate(
            self,
            analysis_results: Dict,
            output_path: Optional[Path] = None,
            preserve_existing: bool = True,
    ) -> EnrichmentResult:
        """
        Perform full integration

        Args:
            analysis_results: Static analysis results
            output_path: Optional output path for enriched model
            preserve_existing: Whether to preserve existing elements (default: True)

        Returns:
            Enrichment result
        """
        enricher = ModelEnricher(preserve_existing=preserve_existing)

        # Detect framework
        self.framework_type = self.detect_framework()
        print(f"Detected framework: {self.framework_type}")

        # Find existing artifacts
        page_objects = self.find_page_objects()
        print(f"Found {len(page_objects)} Page Object files")

        # Extract existing model elements from Page Objects
        existing_elements = self.extract_elements_from_page_objects(page_objects)

        # Create or load App Model
        model_path = self.project_path / "config" / "app_model.yaml"
        if model_path.exists():
            with open(model_path) as f:
                existing_model = yaml.safe_load(f)
        else:
            # Create new model with elements extracted from Page Objects
            existing_model = {"name": "Mobile App", "version": "1.0.0", "screens": []}

            # Add screens from existing Page Objects if no model file exists
            if existing_elements:
                for screen_name, elements in existing_elements.items():
                    existing_model["screens"].append(
                        {
                            "name": screen_name,
                            "id": screen_name.lower(),
                            "description": "Extracted from existing Page Object",
                            "elements": elements,
                        }
                    )
                print(f"Extracted {len(existing_elements)} screens from Page Objects")

        # Enrich model
        enriched_model = enricher.enrich_model(existing_model, analysis_results)

        # Save enriched model (use custom output path if provided)
        if output_path is None:
            output_path = self.project_path / "config" / "app_model_enriched.yaml"
        else:
            output_path = Path(output_path)

        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w") as f:
            yaml.dump(enriched_model, f, default_flow_style=False, sort_keys=False)

        print(f"Enriched model saved: {output_path}")

        return enricher.result
