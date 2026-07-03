"""
Code generation commands for creating test artifacts.
"""

from pathlib import Path

import click

from framework.cli.rich_output import print_header, print_success, print_error, print_info
from framework.utils.logger import get_logger

logger = get_logger(__name__)


@click.group()
def generate():
    """Generate test code"""
    pass


@generate.command()
@click.option("--model", required=True, type=click.Path(exists=True), help="App model YAML file")
@click.option("--output", default="tests/pages", help="Output directory for page objects")
@click.option("--platform", type=click.Choice(["android", "ios", "cross"]), default="cross")
def pages(model: str, output: str, platform: str):
    """
    Generate Page Object classes from app model

    Example:
        observe generate pages --model app_model.yaml --output tests/pages
    """
    print_header("📄 Generating Page Objects", f"Platform: {platform}")

    try:
        from framework.codegen.page_object import emit_page_objects
        from framework.model.app_model import AppModel
        import yaml

        # Load model
        with open(model) as f:
            model_data = yaml.safe_load(f)

        app_model = AppModel(**model_data)
        output_path = Path(output)
        output_path.mkdir(parents=True, exist_ok=True)

        # Generate page objects via the codegen pipeline
        generated = []
        for filename, content in emit_page_objects(app_model).items():
            dest = output_path / filename
            dest.write_text(content, encoding="utf-8", newline="\n")
            generated.append(dest)

        print_success(f"Generated {len(generated)} page objects")
        print_info(f"Output directory: {output_path.absolute()}")

        logger.info(f"Generated {len(generated)} page objects from {model}")

    except Exception as e:
        print_error(f"Generation failed: {e}")
        logger.error(f"Page object generation failed: {e}", exc_info=True)
        raise click.Abort()


@generate.command()
@click.option("--model", required=True, type=click.Path(exists=True), help="App model YAML file")
@click.option("--output", default="tests/api", help="Output directory for API clients")
def api(model: str, output: str):
    """Generate API client classes"""
    print_header("🌐 Generating API Clients")

    try:
        from framework.generators.api_client_gen import generate_api_client
        from framework.model.app_model import AppModel
        import yaml

        with open(model) as f:
            model_data = yaml.safe_load(f)

        app_model = AppModel(**model_data)
        output_path = Path(output)
        output_path.mkdir(parents=True, exist_ok=True)

        # Generate API client
        api_calls = list(app_model.api_calls.values())
        if api_calls:
            output_file = generate_api_client(api_calls, output_path / "api_client.py")
            print_success(f"Generated API client with {len(api_calls)} endpoints")
            print_info(f"Output file: {output_file}")
        else:
            print_error("No API calls found in model")

        logger.info(f"Generated API client from {model}")

    except Exception as e:
        print_error(f"Generation failed: {e}")
        logger.error(f"API client generation failed: {e}", exc_info=True)
        raise click.Abort()


@generate.command()
@click.option("--model", required=True, type=click.Path(exists=True), help="App model YAML file")
@click.option("--output", default="tests/features", help="Output directory for BDD features")
def features(model: str, output: str):
    """Generate BDD feature files"""
    print_header("🥒 Generating BDD Features")

    try:
        from framework.generators.bdd_gen import generate_feature_file
        from framework.model.app_model import AppModel
        import yaml

        with open(model) as f:
            model_data = yaml.safe_load(f)

        app_model = AppModel(**model_data)
        output_path = Path(output)
        output_path.mkdir(parents=True, exist_ok=True)

        # Generate feature files
        generated = []
        for flow in app_model.flows:
            output_file = generate_feature_file(flow, output_path)
            generated.append(output_file)

        print_success(f"Generated {len(generated)} feature files")
        print_info(f"Output directory: {output_path.absolute()}")

        logger.info(f"Generated {len(generated)} feature files from {model}")

    except Exception as e:
        print_error(f"Generation failed: {e}")
        logger.error(f"BDD feature generation failed: {e}", exc_info=True)
        raise click.Abort()


@generate.command()
@click.option("--model", required=True, type=click.Path(exists=True), help="App model YAML file")
@click.option("--app-package", required=True, help="App under test, e.g. com.example.app")
@click.option("--target", default="python_pytest", help="Codegen target (see --list-targets)")
@click.option("--output", default="tests/generated", help="Output directory")
@click.option("--app-activity", default=None, help="Android entry activity, e.g. .MainActivity")
@click.option("--suite-name", default="SmokeFlow", help="Generated suite/class name")
@click.option("--list-targets", is_flag=True, help="List available codegen targets and exit")
def tests(model, app_package, target, output, app_activity, suite_name, list_targets):
    """
    Generate runnable test code in any supported language from an app model.

    Uses the language-agnostic codegen pipeline (one IR, many emitters), so the
    same model can produce Python/Java/JS/Kotlin, imperative or BDD.

    Example:
        observe generate tests --model app.yaml --app-package com.x.app \\
            --target java_testng --output tests/java
    """
    from framework.codegen import available_targets, get_emitter
    from framework.codegen.app_model_adapter import build_smoke_model
    from framework.model.app_model import AppModel
    import yaml

    if list_targets:
        print_header("🎯 Available codegen targets")
        for t in available_targets():
            print_info(f"{t.id}  —  {t.description}")
        return

    target_ids = [t.id for t in available_targets()]
    if target not in target_ids:
        print_error(f"Unknown target '{target}'. Available: {', '.join(sorted(target_ids))}")
        raise click.Abort()

    print_header("🧪 Generating tests", f"Target: {target}")

    try:
        with open(model) as f:
            app_model = AppModel(**yaml.safe_load(f))

        test_model = build_smoke_model(
            app_model, app_package=app_package, suite_name=suite_name, app_activity=app_activity
        )
        if not test_model.cases:
            print_error("App model produced no test cases (no locatable elements found).")
            raise click.Abort()

        output_path = Path(output)
        files = get_emitter(target).emit(test_model)
        for rel_path, content in files.items():
            dest = output_path / rel_path
            dest.parent.mkdir(parents=True, exist_ok=True)
            # utf-8 + LF: generated code contains non-ASCII (em dash) and the
            # emitter produces LF; the platform default (cp1252 on Windows) would
            # corrupt it.
            dest.write_text(content, encoding="utf-8", newline="\n")

        print_success(f"Generated {len(files)} file(s) for {len(test_model.cases)} screen(s)")
        print_info(f"Output directory: {output_path.absolute()}")
        logger.info(f"Generated {len(files)} {target} files from {model}")

    except click.Abort:
        raise
    except Exception as e:
        print_error(f"Generation failed: {e}")
        logger.error(f"Test generation failed: {e}", exc_info=True)
        raise click.Abort()
