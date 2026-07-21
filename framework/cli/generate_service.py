"""Service layer for ``mobiscout project generate``.

Loading and validating the app model, then emitting the test suite (Page
Objects, API client, BDD features, integration tests) is plain logic that used
to be tangled with ``click.echo`` calls inside the command. It lives here as
terminal-free functions so it can be unit-tested against a tmp project.

The command in :mod:`framework.cli.project_commands` stays a thin shell: it
finds the model file, calls :func:`load_app_model` / :func:`generate_suite`, and
renders the returned :class:`GenerateReport`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, List

import yaml  # type: ignore
from pydantic import ValidationError

from framework.model.app_model import AppModel
from framework.utils.logger import get_logger
from framework.utils.sanitizer import sanitize_class_name, sanitize_identifier

logger = get_logger(__name__)


class GenerateServiceError(Exception):
    """A model could not be loaded/validated. The message is ready to print."""


@dataclass
class StepResult:
    """One generation step's outcome, for the command to narrate.

    Attributes:
        title: Human title of the step (e.g. "Generating Page Objects").
        emoji: Leading marker the command prints before the title.
        items: Names of artifacts successfully written in this step.
        warnings: Non-fatal problems encountered during the step.
    """

    title: str
    emoji: str
    items: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)


@dataclass
class GenerateReport:
    """Everything :func:`generate_suite` produced, for the command to render.

    Attributes:
        stats: Counts per artifact kind (page_objects/tests/api_tests/features).
        steps: Ordered per-step results (only the steps that actually ran).
    """

    stats: Dict[str, int] = field(
        default_factory=lambda: {"page_objects": 0, "tests": 0, "api_tests": 0, "features": 0}
    )
    steps: List[StepResult] = field(default_factory=list)

    @property
    def nothing_generated(self) -> bool:
        """True if not a single artifact of any kind was written."""
        return all(v == 0 for v in self.stats.values())


def load_app_model(model_path: Path) -> AppModel:
    """Load and validate the app model YAML at ``model_path``.

    Missing structural fields are defaulted (a ``meta`` block, empty
    ``screens``/``api_calls``/``flows``) so a partial model still loads.

    Args:
        model_path: Path to the model YAML (already located by the caller).

    Returns:
        The validated :class:`AppModel`.

    Raises:
        GenerateServiceError: If the file is missing, not valid YAML, or fails
            model validation. The message is preformatted for display.
    """
    try:
        with open(model_path, "r", encoding="utf-8") as f:
            model_data = yaml.safe_load(f)

        if "meta" not in model_data:
            logger.warning("Model missing 'meta' field, adding default")
            model_data["meta"] = {
                "schema_version": "1.0.0",
                "app_version": "unknown",
                "platform": "cross-platform",
                "recorded_at": datetime.now().isoformat(),
            }

        model_data.setdefault("screens", {})
        model_data.setdefault("api_calls", {})
        model_data.setdefault("flows", [])

        return AppModel(**model_data)

    except FileNotFoundError:
        logger.error(f"Model file not found: {model_path}")
        raise GenerateServiceError(f"Model file not found: {model_path}")
    except yaml.YAMLError as e:
        logger.error(f"YAML parse error: {e}")
        raise GenerateServiceError(f"Invalid YAML format: {e}")
    except ValidationError as e:
        detail = "\n".join(f"   - {' -> '.join(str(x) for x in err['loc'])}: {err['msg']}" for err in e.errors())
        logger.error(f"Model validation error: {e}")
        raise GenerateServiceError("Invalid model format:\n" + detail)
    except Exception as e:
        logger.error(f"Unexpected error loading model: {e}", exc_info=True)
        raise GenerateServiceError(f"Failed to load model: {e}")


def _integration_test_source(screen_id: str, screen) -> str:
    """Render the integration-test source for one screen (Page-Object driven).

    Args:
        screen_id: The screen's id (used for file/module/function names).
        screen: The screen model (its ``name`` and first few ``elements``).

    Returns:
        Python source for a pytest test module targeting that screen.
    """
    class_name = sanitize_class_name(screen.name)
    page_module = sanitize_identifier(screen_id)
    ident = sanitize_identifier(screen_id)

    source = f'''"""
Integration tests for {screen.name}
Auto-generated from app model
"""
import pytest
from page_objects.{page_module}_page import {class_name}Page


class Test{class_name}:
    """Test suite for {screen.name}"""

    @pytest.fixture
    def page(self, driver):
        """Initialize page object"""
        return {class_name}Page(driver)

    def test_{ident}_loads(self, page):
        """Test that {screen.name} loads successfully"""
        assert page.is_displayed(), "{screen.name} should be displayed"
'''

    # Add element tests (limit to first 3 elements).
    for element in screen.elements[:3]:
        if "tappable" in element.capabilities:
            element_name = sanitize_identifier(element.id)
            source += f'''
    def test_{element_name}_clickable(self, page):
        """Test {element.id} is clickable"""
        assert page.{element_name}.is_clickable()
'''
    return source


def generate_suite(
    model: AppModel,
    project_path: Path,
    *,
    generate_page_objects: bool,
    generate_tests: bool,
    generate_api_tests: bool,
    generate_features: bool,
) -> GenerateReport:
    """Emit the requested test-suite artifacts into ``project_path``.

    Each enabled step writes its files and is isolated: a failure in one step is
    recorded as a warning on that step and does not abort the others.

    Args:
        model: The loaded app model.
        project_path: Target project root (subdirs are created as needed).
        generate_page_objects: Emit Page Objects from ``model.screens``.
        generate_tests: Emit integration tests from ``model.screens``.
        generate_api_tests: Emit an API client from ``model.api_calls``.
        generate_features: Emit BDD features from ``model.flows``.

    Returns:
        A :class:`GenerateReport` with per-artifact counts and per-step details.
    """
    report = GenerateReport()

    if generate_page_objects and model.screens:
        step = StepResult("Generating Page Objects", "1️⃣")
        report.steps.append(step)
        po_dir = project_path / "page_objects"
        po_dir.mkdir(exist_ok=True)
        try:
            from framework.codegen.page_object import emit_page_objects

            for filename, content in emit_page_objects(model).items():
                dest = po_dir / filename
                dest.write_text(content, encoding="utf-8", newline="\n")
                report.stats["page_objects"] += 1
                step.items.append(dest.name)
                logger.debug(f"Generated Page Object: {dest}")
        except Exception as e:
            step.warnings.append(f"Page Object generation failed: {e}")
            logger.error(f"Page Object generation failed: {e}", exc_info=True)

    if generate_api_tests and len(model.api_calls) > 0:
        step = StepResult("Generating API Client", "2️⃣")
        report.steps.append(step)
        api_dir = project_path / "tests" / "api"
        api_dir.mkdir(parents=True, exist_ok=True)
        try:
            from framework.codegen.api_client import emit_api_client

            for filename, content in emit_api_client(model).items():
                (api_dir / filename).write_text(content, encoding="utf-8", newline="\n")
            report.stats["api_tests"] = len(model.api_calls)
            step.items.append(f"API Client with {len(model.api_calls)} endpoints")
            logger.info(f"Generated API client in {api_dir}")
        except Exception as e:
            step.warnings.append(f"API client generation failed: {e}")
            logger.warning(f"API client generation failed: {e}")

    if generate_features and len(model.flows) > 0:
        step = StepResult("Generating BDD Features", "3️⃣")
        report.steps.append(step)
        features_dir = project_path / "features"
        features_dir.mkdir(exist_ok=True)
        try:
            from framework.codegen.bdd_feature import emit_feature_files

            for filename, content in emit_feature_files(model).items():
                try:
                    (features_dir / filename).write_text(content, encoding="utf-8", newline="\n")
                    report.stats["features"] += 1
                    step.items.append(filename)
                    logger.debug(f"Generated BDD feature: {features_dir / filename}")
                except Exception as e:
                    step.warnings.append(f"Failed to generate {filename}: {e}")
                    logger.warning(f"Failed to write BDD feature {filename}: {e}")
        except Exception as e:
            step.warnings.append(f"BDD feature generation failed: {e}")
            logger.error(f"BDD feature generation failed: {e}", exc_info=True)

    if generate_tests and model.screens:
        step = StepResult("Generating Integration Tests", "4️⃣")
        report.steps.append(step)
        tests_dir = project_path / "tests" / "integration"
        tests_dir.mkdir(parents=True, exist_ok=True)
        try:
            for screen_id, screen in model.screens.items():
                try:
                    test_file = tests_dir / f"test_{sanitize_identifier(screen_id)}.py"
                    with open(test_file, "w", encoding="utf-8") as f:
                        f.write(_integration_test_source(screen_id, screen))
                    report.stats["tests"] += 1
                    step.items.append(test_file.name)
                    logger.debug(f"Generated test: {test_file}")
                except Exception as e:
                    step.warnings.append(f"Failed to generate test for {screen_id}: {e}")
                    logger.warning(f"Failed to generate test for {screen_id}: {e}")
        except Exception as e:
            step.warnings.append(f"Test generation failed: {e}")
            logger.error(f"Test generation failed: {e}", exc_info=True)

    return report
