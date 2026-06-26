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
        from framework.generators.page_object_gen import generate_page_object
        from framework.model.app_model import AppModel
        import yaml

        # Load model
        with open(model) as f:
            model_data = yaml.safe_load(f)

        app_model = AppModel(**model_data)
        output_path = Path(output)
        output_path.mkdir(parents=True, exist_ok=True)

        # Generate page objects
        generated = []
        for screen_name, screen in app_model.screens.items():
            output_file = generate_page_object(screen, output_path)
            generated.append(output_file)

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
