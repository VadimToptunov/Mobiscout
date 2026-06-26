"""
ML CLI commands

Commands for machine learning model training and element classification.
"""

import json
from pathlib import Path

import click
from rich.console import Console
from rich.table import Table

from framework.cli.rich_output import print_header, print_info, print_success, print_error, create_progress
from framework.ml.element_classifier import ElementClassifier
from framework.ml.training_data_generator import TrainingDataGenerator
from framework.ml.universal_model import UniversalModelBuilder

console = Console()


@click.group(name='ml')
def ml() -> None:
    """🤖 Machine Learning commands for element classification"""
    pass


@ml.command()
@click.option('--training-data', '-t', 'training_data_path', required=True,
              type=click.Path(exists=True), help='Path to training data (JSON)')
@click.option('--output', '-o', 'output_path', required=True,
              type=click.Path(), help='Output path for trained model (.pkl)')
@click.option('--test-split', default=0.2, type=float,
              help='Test set size (0.0-1.0)')
def train(training_data_path: str, output_path: str, test_split: float) -> None:
    """Train element classifier model"""
    print_header("Training Element Classifier")

    training_file = Path(training_data_path)
    output_file = Path(output_path)

    print_info(f"Training data: {training_file}")
    print_info(f"Output model: {output_file}")
    print_info(f"Test split: {test_split:.1%}")

    try:
        # Load training data
        with open(training_file, 'r') as f:
            training_data = json.load(f)

        print_info("Loaded " + str(len(training_data)) + " training examples")

        # Train model
        classifier = ElementClassifier()

        print_info("\n🔄 Training model...")
        accuracy = classifier.train_from_data(training_data, test_size=test_split)

        print_success(f"\n✅ Model trained!")  # noqa: F541
        print_info(f"Accuracy: {accuracy:.2%}")

        # Save model
        output_file.parent.mkdir(parents=True, exist_ok=True)
        classifier.save_model(output_file)

        print_success(f"✅ Model saved to: {output_file}")

    except Exception as e:
        print_error(f"Training failed: {e}")
        raise click.Abort()


@ml.command()
@click.option('--model', '-m', 'model_path', required=True,
              type=click.Path(exists=True), help='Path to trained model (.pkl)')
@click.option('--test-data', '-t', 'test_data_path', required=True,
              type=click.Path(exists=True), help='Path to test data (JSON)')
def evaluate(model_path: str, test_data_path: str) -> None:
    """Evaluate model accuracy on test data"""
    print_header("Evaluating Model")

    model_file = Path(model_path)
    test_file = Path(test_data_path)

    print_info(f"Model: {model_file}")
    print_info(f"Test data: {test_file}")

    try:
        # Load model
        classifier = ElementClassifier(model_path=model_file)

        if not classifier.trained:
            print_error("Model not trained or failed to load")
            raise click.Abort()

        # Load test data
        with open(test_file, 'r') as f:
            test_data = json.load(f)

        print_info("Loaded " + str(len(test_data)) + " test examples")

        # Evaluate
        print_info("\n🔄 Evaluating model...")

        correct = 0
        total = len(test_data)
        predictions_by_type = {}

        with create_progress() as progress:
            task = progress.add_task("Evaluating...", total=total)

            for item in test_data:
                element_type, confidence = classifier.predict(item['features'])
                expected_type = item.get('element_type', item.get('type'))

                if element_type.value == expected_type or element_type.name == expected_type:
                    correct += 1

                # Track by type
                if expected_type not in predictions_by_type:
                    predictions_by_type[expected_type] = {'correct': 0, 'total': 0}
                predictions_by_type[expected_type]['total'] += 1
                if element_type.value == expected_type or element_type.name == expected_type:
                    predictions_by_type[expected_type]['correct'] += 1

                progress.advance(task)

        # Display results
        accuracy = correct / total if total > 0 else 0
        print_success(f"\n✅ Overall Accuracy: {accuracy:.2%} ({correct}/{total})")

        # Show per-type accuracy
        if predictions_by_type:
            print_info("\n📊 Per-Type Accuracy:")

            table = Table(title="Classification Results")
            table.add_column("Element Type", style="cyan")
            table.add_column("Correct", style="green")
            table.add_column("Total", style="yellow")
            table.add_column("Accuracy", style="bold")

            for elem_type, stats in sorted(predictions_by_type.items()):
                type_accuracy = stats['correct'] / stats['total'] if stats['total'] > 0 else 0
                table.add_row(
                    elem_type,
                    str(stats['correct']),
                    str(stats['total']),
                    f"{type_accuracy:.1%}"
                )

            console.print(table)

    except Exception as e:
        print_error(f"Evaluation failed: {e}")
        raise click.Abort()


@ml.command()
@click.option('--model', '-m', 'model_path', required=True,
              type=click.Path(exists=True), help='Path to trained model (.pkl)')
@click.option('--element', '-e', 'element_data', required=True,
              help='Element data as JSON string or file path')
def predict(model_path: str, element_data: str) -> None:
    """Predict element type for given element data"""
    print_header("Element Type Prediction")

    model_file = Path(model_path)
    print_info(f"Model: {model_file}")

    try:
        # Load model
        classifier = ElementClassifier(model_path=model_file)

        if not classifier.trained:
            print_error("Model not trained or failed to load")
            raise click.Abort()

        # Parse element data
        if Path(element_data).exists():
            with open(element_data, 'r') as f:
                element = json.load(f)
        else:
            element = json.loads(element_data)

        # Predict
        element_type, confidence = classifier.predict(element)

        # Display result
        print_success(f"\n✅ Prediction:")  # noqa: F541
        print_info(f"  Type: {element_type.value}")
        print_info(f"  Confidence: {confidence:.2%}")

        if confidence < 0.5:
            print_error("  ⚠️  Low confidence - prediction may be unreliable")
        elif confidence < 0.7:
            print_info("  ⚠️  Medium confidence")
        else:
            print_success("  ✅ High confidence")

    except json.JSONDecodeError:
        print_error("Invalid JSON data")
        raise click.Abort()
    except Exception as e:
        print_error(f"Prediction failed: {e}")
        raise click.Abort()


@ml.command(name='create-universal-model')
@click.option('--output', '-o', 'output_path', required=True,
              type=click.Path(), help='Output path for model (.pkl)')
@click.option('--samples-per-type', default=1000, type=int,
              help='Number of synthetic samples per element type')
def create_universal_model(output_path: str, samples_per_type: int) -> None:
    """Create universal pre-trained model for any mobile app"""
    print_header("Creating Universal Model")

    output_file = Path(output_path)

    print_info(f"Output: {output_file}")
    print_info(f"Samples per type: {samples_per_type}")

    try:
        # Generate synthetic training data
        print_info("\n🔄 Generating synthetic training data...")

        builder = UniversalModelBuilder()
        training_data_path = builder.generate_training_data(samples_per_type=samples_per_type)

        # Load the training data from the generated file
        import json
        with open(training_data_path, 'r') as f:
            training_data = json.load(f)

        print_info(f"Generated {len(training_data)} training samples")

        # Train model
        print_info("\n🔄 Training universal model...")

        classifier = ElementClassifier()
        accuracy = classifier.train_from_data(training_data, test_size=0.2)

        print_success(f"\n✅ Universal model trained!")  # noqa: F541
        print_info(f"Accuracy: {accuracy:.2%}")

        # Save model
        output_file.parent.mkdir(parents=True, exist_ok=True)
        classifier.save_model(output_file)

        print_success(f"✅ Model saved to: {output_file}")
        print_info("\nℹ️  This model works for:")
        print_info("  • Android (Native, Jetpack Compose)")
        print_info("  • iOS (UIKit, SwiftUI)")
        print_info("  • Flutter")
        print_info("  • React Native")

    except Exception as e:
        print_error(f"Model creation failed: {e}")
        raise click.Abort()


@ml.command(name='generate-training-data')
@click.option('--app-model', '-a', 'app_model_path', required=True,
              type=click.Path(exists=True), help='Path to app model (JSON)')
@click.option('--output', '-o', 'output_path', required=True,
              type=click.Path(), help='Output path for training data (JSON)')
def generate_training_data(app_model_path: str, output_path: str) -> None:
    """Generate training data from app model"""
    print_header("Generating Training Data")

    model_file = Path(app_model_path)
    output_file = Path(output_path)

    print_info(f"App model: {model_file}")
    print_info(f"Output: {output_file}")

    try:
        # Load app model
        with open(model_file, 'r') as f:
            app_model_data = json.load(f)

        # Generate training data
        generator = TrainingDataGenerator()
        training_data_path = generator.generate_from_app_model(app_model_data, output_path=output_file)

        # Load to get count for display
        with open(training_data_path, 'r') as f:
            training_data = json.load(f)

        print_info(f"\nGenerated {len(training_data)} training examples")

        print_success(f"✅ Training data saved to: {output_file}")

    except Exception as e:
        print_error(f"Generation failed: {e}")
        raise click.Abort()


if __name__ == '__main__':
    ml()
