"""
Project Analysis CLI Commands

Commands for comprehensive project analysis that write results to target
test projects.
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any

import click
import yaml  # type: ignore
from pydantic import ValidationError

from framework.analyzers.business_logic_analyzer import BusinessLogicAnalyzer
from framework.cli.rich_output import (
    print_header,
    print_success,
    print_error,
    print_warning,
    print_info,
    print_section,
    print_summary,
    create_progress,
)
from framework.generators import page_object_gen, api_client_gen, bdd_gen
from framework.integration.model_enricher import ProjectIntegrator
from framework.model.app_model import AppModel
from framework.utils.error_handling import handle_cli_errors, validate_and_raise
from framework.utils.logger import get_logger, setup_logging
from framework.utils.sanitizer import sanitize_identifier, sanitize_class_name

# Setup logging
setup_logging(level="INFO")
logger = get_logger(__name__)


def transform_analysis_to_integration_format(analysis_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Transform BusinessLogicAnalysis export to format expected by ProjectIntegrator

    Args:
        analysis_data: Data from BusinessLogicAnalyzer.export_to_json()

    Returns:
        Dict in format expected by ModelEnricher
    """
    logger.info("Transforming analysis data to integration format")

    result = {
        "screens": [],
        "api_endpoints": [],
        "navigation": [],
        "business_logic": analysis_data,  # Preserve original for reference
    }

    # Transform API contracts to api_endpoints
    for contract in analysis_data.get("api_contracts", []):
        result["api_endpoints"].append(
            {
                "method": contract.get("method", "GET"),
                "path": contract.get("endpoint", ""),
                "function_name": contract.get("endpoint", "").replace("/", "_").replace("-", "_"),
                "interface_name": "APIService",
                "file_path": contract.get("source_file"),
            }
        )

    # Transform user flows to navigation
    for flow in analysis_data.get("user_flows", []):
        result["navigation"].append(
            {
                "name": flow.get("name"),
                "steps": flow.get("steps", []),
                "entry_point": flow.get("entry_point"),
            }
        )

    # Extract screens from user flows
    seen_screens = set()
    for flow in analysis_data.get("user_flows", []):
        entry_point = flow.get("entry_point")
        if entry_point and entry_point not in seen_screens:
            result["screens"].append(
                {
                    "name": entry_point,
                    "ui_elements": [],
                    "file_path": flow.get("source_files", [None])[0] if flow.get("source_files") else None,
                }
            )
            seen_screens.add(entry_point)

    logger.info(
        f"Transformed: {len(result['screens'])} screens, "
        f"{len(result['api_endpoints'])} API endpoints, "
        f"{len(result['navigation'])} flows"
    )

    return result


def _analyze_platform(platform_name: str, source_path: Path, output_path: Path, format: str) -> Optional[Path]:
    """
    Analyze a platform and save results

    Args:
        platform_name: Platform name for display (Android/iOS)
        source_path: Path to source code
        output_path: Output directory
        format: Output format (yaml/json)

    Returns:
        Path to output file, or None if failed
    """
    try:
        logger.info(f"Starting {platform_name} analysis: {source_path}")
        print_section(f"🔍 {platform_name} Analysis")

        with create_progress() as progress:
            task = progress.add_task(f"[cyan]Analyzing {platform_name}...", total=100)

            analyzer = BusinessLogicAnalyzer(source_path)
            progress.update(task, advance=20)

            result = analyzer.analyze()
            progress.update(task, advance=60)

            # Save results
            output_file = output_path / f"{platform_name.lower()}_analysis.{format}"
            data = analyzer.export_to_json()

            if format == "yaml":
                with open(output_file, "w", encoding="utf-8") as f:
                    yaml.dump(data, f, default_flow_style=False, sort_keys=False, allow_unicode=True)
            else:
                with open(output_file, "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=2, ensure_ascii=False)

            progress.update(task, advance=20)

        # Print beautiful summary
        stats = {
            "user_flows": len(result.user_flows),
            "business_rules": len(result.business_rules),
            "api_endpoints": len(result.api_contracts),
            "state_machines": len(result.state_machines),
            "edge_cases": len(result.edge_cases),
        }
        print_summary(f"{platform_name} Results", stats)
        print_success(f"Saved to: {output_file}")

        logger.info(f"{platform_name} analysis completed: {output_file}")
        return output_file

    except Exception as e:
        logger.error(f"{platform_name} analysis failed: {e}", exc_info=True)
        print_error(f"{platform_name} analysis failed: {e}")
        return None


def _find_app_model(project_path: Path) -> Optional[Path]:
    """
    Find app model YAML file in project

    Args:
        project_path: Project root path

    Returns:
        Path to model file, or None if not found
    """
    config_dir = project_path / "config"
    if not config_dir.exists():
        return None

    # Try specific names first
    candidates = [
        config_dir / "app_model_enriched.yaml",
        config_dir / "app_model.yaml",
    ]

    for candidate in candidates:
        if candidate.exists():
            return candidate

    # Try glob pattern
    yaml_files = list(config_dir.glob("*_app_model*.yaml"))
    if yaml_files:
        # Return most recently modified
        return max(yaml_files, key=lambda p: p.stat().st_mtime)

    return None


@click.group()
def project() -> None:
    """
    Comprehensive project analysis commands

    Analyze source code and integrate results into test frameworks
    """
    pass


@project.command()
@click.option(
    "--android-source",
    type=click.Path(exists=True),
    help="Path to Android source code",
)
@click.option(
    "--ios-source",
    type=click.Path(exists=True),
    help="Path to iOS source code",
)
@click.option(
    "--output-dir",
    type=click.Path(),
    required=True,
    help="Output directory for analysis results (in test project)",
)
@click.option(
    "--format",
    type=click.Choice(["yaml", "json"], case_sensitive=False),
    default="yaml",
    help="Output format",
)
@handle_cli_errors(exit_on_error=True)
def analyze(
        android_source: Optional[str],
        ios_source: Optional[str],
        output_dir: str,
        format: str,
) -> None:
    """
    Comprehensive project analysis

    Analyzes Android/iOS source code and writes results to test project.

    Example:
        observe project analyze \\
            --android-source ~/MobileProjects/android-mono/flykk/src/main \\
            --ios-source ~/MobileProjects/new-flykk-ios/flykk \\
            --output-dir ~/flykk-test-automation/analysis
    """
    print_header("📱 Comprehensive Project Analysis", "Analyzing mobile application source code")

    # Validation: At least one source required
    validate_and_raise(
        android_source is not None or ios_source is not None,
        "At least one source (--android-source or --ios-source) must be provided",
    )

    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    logger.info(f"Starting project analysis: android={android_source}, ios={ios_source}, output={output_dir}")

    results: Dict[str, Path] = {}

    # Android Analysis
    if android_source:
        result_file = _analyze_platform("Android", Path(android_source), output_path, format)
        if result_file:
            results["android"] = result_file

    # iOS Analysis
    if ios_source:
        result_file = _analyze_platform("iOS", Path(ios_source), output_path, format)
        if result_file:
            results["ios"] = result_file

    if results:
        print_success("Analysis complete!")
        print_summary(
            "Analysis Results",
            {
                "platforms_analyzed": len(results),
                "output_directory": str(output_path),
                "format": format.upper(),
            },
        )
        print_section("Next Steps")
        print_info("Integrate results into test framework:")
        for file in results.values():
            print(f"   observe project integrate --analysis {file} --project <test-project-path>")
        logger.info(f"Analysis completed successfully: {len(results)} platforms")
    else:
        print_error("Analysis failed - no results generated")
        print_warning("Check logs for details")
        logger.error("All platform analyses failed")


@project.command()
@click.option(
    "--analysis",
    type=click.Path(exists=True),
    required=True,
    help="Path to analysis file (yaml/json)",
)
@click.option("--project", type=click.Path(exists=True), required=True, help="Path to test project")
@click.option("--preserve-existing/--replace-all", default=True, help="Preserve existing elements or replace")
def integrate(analysis: str, project: str, preserve_existing: bool) -> None:
    """
    Integrate analysis results into test project

    Enriches test framework with discovered elements and APIs.

    Example:
        observe project integrate \\
            --analysis ~/flykk-test-automation/analysis/android_analysis.yaml \\
            --project ~/flykk-test-automation
    """
    logger.info(f"Starting integration: analysis={analysis}, project={project}")

    click.echo("🔄 Integrating Analysis into Test Project...")
    click.echo("=" * 70)

    project_path = Path(project)
    analysis_file = Path(analysis)

    click.echo(f"\n📖 Analysis: {analysis_file.name}")
    click.echo(f"📁 Project: {project_path.name}")
    click.echo(f"🔧 Mode: {'Preserve existing' if preserve_existing else 'Replace all'}")

    # Load analysis results from file with error handling
    try:
        with open(analysis_file, "r", encoding="utf-8") as f:
            if analysis_file.suffix == ".json":
                analysis_data = json.load(f)
            else:
                analysis_data = yaml.safe_load(f)
    except FileNotFoundError:
        click.echo(f"❌ Error: Analysis file not found: {analysis_file}")
        logger.error(f"Analysis file not found: {analysis_file}")
        return
    except (json.JSONDecodeError, yaml.YAMLError) as e:
        click.echo(f"❌ Error: Invalid file format: {e}")
        logger.error(f"Failed to parse analysis file: {e}")
        return
    except Exception as e:
        click.echo(f"❌ Error: Failed to read analysis file: {e}")
        logger.error(f"Unexpected error reading analysis file: {e}", exc_info=True)
        return

    # Transform analysis data to integration format
    try:
        analysis_results = transform_analysis_to_integration_format(analysis_data)
    except Exception as e:
        click.echo(f"⚠️  Warning: Could not transform analysis data: {e}")
        logger.warning(f"Using raw analysis data: {e}")
        analysis_results = analysis_data

    # Integrate
    try:
        integrator = ProjectIntegrator(project_path)
        result = integrator.integrate(analysis_results=analysis_results, preserve_existing=preserve_existing)
    except Exception as e:
        click.echo(f"❌ Error: Integration failed: {e}")
        logger.error(f"Integration failed: {e}", exc_info=True)
        return

    click.echo("\n✅ Integration complete!")
    click.echo(f"   📊 Screens enriched: {result.screens_enriched}")
    click.echo(f"   📊 Elements added: {result.elements_added}")
    click.echo(f"   📊 API endpoints added: {result.api_endpoints_added}")

    if result.warnings:
        click.echo("\n⚠️  Warnings:")
        for warning in result.warnings:
            click.echo(f"   - {warning}")

    if result.errors:
        click.echo("\n❌ Errors:")
        for error in result.errors:
            click.echo(f"   - {error}")

    click.echo("\n" + "=" * 70)
    click.echo("🚀 Next step: Generate code")
    click.echo("=" * 70)
    click.echo(f"\n   cd {project_path}")
    click.echo("   observe project generate --project .")

    logger.info(f"Integration completed: {result.screens_enriched} screens, {result.elements_added} elements")


@project.command()
@click.option("--project", type=click.Path(exists=True), required=True, help="Path to test project")
@click.option("--generate-page-objects/--no-page-objects", default=True, help="Generate Page Objects")
@click.option("--generate-tests/--no-tests", default=True, help="Generate integration tests")
@click.option("--generate-api-tests/--no-api-tests", default=True, help="Generate API tests")
@click.option("--generate-features/--no-features", default=True, help="Generate BDD features")
def generate(
        project: str,
        generate_page_objects: bool,
        generate_tests: bool,
        generate_api_tests: bool,
        generate_features: bool,
) -> None:
    """
    Generate complete test suite from enriched model

    Creates Page Objects, tests, and BDD features.

    Example:
        observe project generate --project ~/flykk-test-automation
    """
    logger.info(f"Starting code generation: project={project}")

    project_path = Path(project)

    click.echo("🏭 Generating Complete Test Suite...")
    click.echo("=" * 70)

    # Find model file
    model_path = _find_app_model(project_path)

    if not model_path:
        click.echo(f"❌ Error: No app model found in {project_path / 'config'}")
        click.echo("\n💡 Tip: Run 'observe project integrate' first to create the model")
        logger.error(f"No app model found in {project_path / 'config'}")
        return

    click.echo(f"\n📖 Loading model: {model_path.name}")

    # Load and validate model
    try:
        with open(model_path, "r", encoding="utf-8") as f:
            model_data = yaml.safe_load(f)

        # Ensure meta field exists
        if "meta" not in model_data:
            logger.warning("Model missing 'meta' field, adding default")
            model_data["meta"] = {
                "schema_version": "1.0.0",
                "app_version": "unknown",
                "platform": "cross-platform",
                "recorded_at": datetime.now().isoformat(),
            }

        # Ensure other required fields exist
        model_data.setdefault("screens", {})
        model_data.setdefault("api_calls", {})
        model_data.setdefault("flows", [])

        model = AppModel(**model_data)

    except FileNotFoundError:
        click.echo(f"❌ Error: Model file not found: {model_path}")
        logger.error(f"Model file not found: {model_path}")
        return
    except yaml.YAMLError as e:
        click.echo(f"❌ Error: Invalid YAML format: {e}")
        logger.error(f"YAML parse error: {e}")
        return
    except ValidationError as e:
        click.echo("❌ Error: Invalid model format:")
        for error in e.errors():
            field = " -> ".join(str(x) for x in error["loc"])
            click.echo(f"   - {field}: {error['msg']}")
        logger.error(f"Model validation error: {e}")
        return
    except Exception as e:
        click.echo(f"❌ Error: Failed to load model: {e}")
        logger.error(f"Unexpected error loading model: {e}", exc_info=True)
        return

    stats = {"page_objects": 0, "tests": 0, "api_tests": 0, "features": 0}

    # Generate Page Objects
    if generate_page_objects and model.screens:
        click.echo("\n1️⃣  Generating Page Objects...")
        po_dir = project_path / "page_objects"
        po_dir.mkdir(exist_ok=True)

        try:
            for screen_id, screen in model.screens.items():
                try:
                    # Use the function API directly
                    output_file = page_object_gen.generate_page_object(screen, po_dir)
                    if output_file:
                        stats["page_objects"] += 1
                        click.echo(f"   ✅ {screen.name}Page -> {output_file.name}")
                        logger.debug(f"Generated Page Object: {output_file}")
                except Exception as e:
                    click.echo(f"   ⚠️  Failed to generate {screen.name}: {e}")
                    logger.warning(f"Failed to generate Page Object for {screen.name}: {e}")
        except Exception as e:
            click.echo(f"   ❌ Page Object generation failed: {e}")
            logger.error(f"Page Object generation failed: {e}", exc_info=True)

    # Generate API Client
    if generate_api_tests and len(model.api_calls) > 0:
        click.echo("\n2️⃣  Generating API Client...")
        api_dir = project_path / "tests" / "api"
        api_dir.mkdir(parents=True, exist_ok=True)

        try:
            # Use the function API directly with List of APICall objects
            api_calls_list = list(model.api_calls.values())
            output_file = api_dir / "api_client.py"

            api_file = api_client_gen.generate_api_client(api_calls_list, output_file)

            if api_file:
                stats["api_tests"] = len(model.api_calls)
                click.echo(f"   ✅ API Client with {len(model.api_calls)} endpoints")
                logger.info(f"Generated API client: {api_file}")
        except Exception as e:
            click.echo(f"   ⚠️  API client generation failed: {e}")
            logger.warning(f"API client generation failed: {e}")

    # Generate BDD Features
    if generate_features and len(model.flows) > 0:
        click.echo("\n3️⃣  Generating BDD Features...")
        features_dir = project_path / "features"
        features_dir.mkdir(exist_ok=True)

        try:
            for flow in model.flows:
                try:
                    # Use the function API directly
                    feature_path = bdd_gen.generate_feature_file(flow, features_dir)
                    if feature_path:
                        stats["features"] += 1
                        click.echo(f"   ✅ {flow.name}.feature")
                        logger.debug(f"Generated BDD feature: {feature_path}")
                except Exception as e:
                    click.echo(f"   ⚠️  Failed to generate {flow.name}: {e}")
                    logger.warning(f"Failed to generate BDD feature for {flow.name}: {e}")
        except Exception as e:
            click.echo(f"   ❌ BDD feature generation failed: {e}")
            logger.error(f"BDD feature generation failed: {e}", exc_info=True)

    # Generate Integration Tests
    if generate_tests and model.screens:
        click.echo("\n4️⃣  Generating Integration Tests...")
        tests_dir = project_path / "tests" / "integration"
        tests_dir.mkdir(parents=True, exist_ok=True)

        try:
            for screen_id, screen in model.screens.items():
                try:
                    test_file = tests_dir / f"test_{sanitize_identifier(screen_id)}.py"

                    # Sanitize names for valid Python code
                    class_name = sanitize_class_name(screen.name)
                    page_module = sanitize_identifier(screen_id)

                    print_info(f"Generating test for {screen.name} → {class_name}Page")

                    # Simple test template
                    test_content = f'''"""
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

    def test_{sanitize_identifier(screen_id)}_loads(self, page):
        """Test that {screen.name} loads successfully"""
        assert page.is_displayed(), "{screen.name} should be displayed"
'''

                    # Add element tests (limit to first 3 elements)
                    for element in screen.elements[:3]:
                        if "tappable" in element.capabilities:
                            element_name = sanitize_identifier(element.id)
                            test_content += f'''
    def test_{element_name}_clickable(self, page):
        """Test {element.id} is clickable"""
        assert page.{element_name}.is_clickable()
'''

                    with open(test_file, "w", encoding="utf-8") as f:
                        f.write(test_content)

                    stats["tests"] += 1
                    click.echo(f"   ✅ test_{sanitize_identifier(screen_id)}.py")
                    logger.debug(f"Generated test: {test_file}")

                except Exception as e:
                    click.echo(f"   ⚠️  Failed to generate test for {screen_id}: {e}")
                    logger.warning(f"Failed to generate test for {screen_id}: {e}")
        except Exception as e:
            click.echo(f"   ❌ Test generation failed: {e}")
            logger.error(f"Test generation failed: {e}", exc_info=True)

    # Summary
    click.echo("\n" + "=" * 70)
    click.echo("✅ Test Suite Generation Complete!")
    click.echo("=" * 70)
    click.echo("\n📊 Generated:")
    if stats["page_objects"] > 0:
        click.echo(f"   📄 {stats['page_objects']} Page Objects")
    if stats["tests"] > 0:
        click.echo(f"   🧪 {stats['tests']} Integration Tests")
    if stats["api_tests"] > 0:
        click.echo(f"   🌐 {stats['api_tests']} API Endpoints")
    if stats["features"] > 0:
        click.echo(f"   📝 {stats['features']} BDD Features")

    if all(v == 0 for v in stats.values()):
        click.echo("   ⚠️  No code was generated. Check if model contains data.")

    click.echo(f"\n📁 Output: {project_path}")
    click.echo("\n🚀 Next steps:")
    click.echo("   cd " + str(project_path))
    click.echo("   pytest tests/integration -v")
    if stats["features"] > 0:
        click.echo("   pytest --bdd features/")

    logger.info(f"Code generation completed: {stats}")


@project.command(name="fullcycle")
@click.option(
    "--android-path",
    type=click.Path(exists=True),
    help="Path to Android source code",
)
@click.option(
    "--ios-path",
    type=click.Path(exists=True),
    help="Path to iOS source code",
)
@click.option(
    "--project",
    type=click.Path(),
    required=True,
    help="Path to test project",
)
@click.option(
    "--output-dir",
    type=click.Path(),
    default="analysis",
    help="Output directory for analysis results",
)
def fullcycle(
        android_path: Optional[str],
        ios_path: Optional[str],
        project: str,
        output_dir: str,
) -> None:
    """
    Complete analysis and generation pipeline

    Analyzes source code, integrates results, and generates tests.

    Example:
        observe project fullcycle \\
            --android-path ~/android-project \\
            --ios-path ~/ios-project \\
            --project ~/test-automation
    """
    logger.info(f"Starting fullcycle: android={android_path}, ios={ios_path}, project={project}")

    # Validation: At least one source required
    if not android_path and not ios_path:
        click.echo("❌ Error: At least one source (--android-path or --ios-path) must be provided")
        logger.error("fullcycle command called without sources")
        return

    project_path = Path(project)
    output_path = project_path / output_dir
    output_path.mkdir(parents=True, exist_ok=True)

    click.echo("🚀 Full Cycle: Analysis → Integration → Generation")
    click.echo("=" * 70)

    analysis_results: Dict[str, Path] = {}

    # Phase 1: Analysis
    if android_path:
        try:
            click.echo("\n📱 Phase 1a: Analyzing Android Source...")
            analyzer = BusinessLogicAnalyzer(Path(android_path))
            analyzer.analyze()

            android_out = output_path / "android_analysis.yaml"
            data = analyzer.export_to_json()
            with open(android_out, "w", encoding="utf-8") as f:
                yaml.dump(data, f, default_flow_style=False, sort_keys=False, allow_unicode=True)

            analysis_results["android"] = android_out
            logger.info(f"Android analysis saved: {android_out}")
        except Exception as e:
            click.echo(f"   ⚠️  Android analysis failed: {e}")
            logger.error(f"Android analysis failed: {e}", exc_info=True)

    if ios_path:
        try:
            click.echo("\n🍎 Phase 1b: Analyzing iOS Source...")
            analyzer = BusinessLogicAnalyzer(Path(ios_path))
            analyzer.analyze()

            ios_out = output_path / "ios_analysis.yaml"
            data = analyzer.export_to_json()
            with open(ios_out, "w", encoding="utf-8") as f:
                yaml.dump(data, f, default_flow_style=False, sort_keys=False, allow_unicode=True)

            analysis_results["ios"] = ios_out
            logger.info(f"iOS analysis saved: {ios_out}")
        except Exception as e:
            click.echo(f"   ⚠️  iOS analysis failed: {e}")
            logger.error(f"iOS analysis failed: {e}", exc_info=True)

    if not analysis_results:
        click.echo("\n❌ All analyses failed. Cannot proceed with integration.")
        logger.error("All platform analyses failed in fullcycle")
        return

    # Phase 2: Integration
    click.echo("\n🔄 Phase 2: Integrating Analysis Results...")

    ctx = click.get_current_context()

    for platform, analysis_file in analysis_results.items():
        try:
            logger.info(f"Integrating {platform} analysis")
            ctx.invoke(
                integrate,
                analysis=str(analysis_file),
                project=project,
                preserve_existing=True,
            )
        except Exception as e:
            click.echo(f"   ⚠️  {platform.capitalize()} integration failed: {e}")
            logger.error(f"{platform} integration failed: {e}", exc_info=True)

    # Phase 3: Generation
    click.echo("\n🏭 Phase 3: Generating Test Suite...")
    try:
        ctx.invoke(
            generate,
            project=project,
            generate_page_objects=True,
            generate_tests=True,
            generate_api_tests=True,
            generate_features=True,
        )
    except Exception as e:
        click.echo(f"   ⚠️  Code generation failed: {e}")
        logger.error(f"Code generation failed: {e}", exc_info=True)

    click.echo("\n" + "=" * 70)
    click.echo("✅ Full Cycle Complete!")
    click.echo("=" * 70)
    click.echo(f"\n📁 Project: {project_path}")
    click.echo(f"📊 Analysis: {output_path}")
    click.echo("\n🧪 Run tests:")
    click.echo(f"   cd {project_path}")
    click.echo("   pytest tests/ -v")

    logger.info("Fullcycle completed")
