"""
Test Data CLI commands

Commands for generating and managing test data.
"""

import json
from pathlib import Path
from typing import Optional

import click
from rich.console import Console

from framework.cli.rich_output import print_header, print_info, print_success, print_error
from framework.data.generator import TestDataGenerator

console = Console()


@click.group(name='data')
def data() -> None:
    """📊 Test data management commands"""
    pass


@data.command()
@click.option('--type', '-t', 'data_type',
              type=click.Choice(['user', 'product', 'transaction', 'card', 'address']),
              required=True, help='Type of data to generate')
@click.option('--count', '-c', type=int, default=10, help='Number of records to generate')
@click.option('--output', '-o', type=click.Path(), required=True, help='Output JSON file')
@click.option('--seed', '-s', type=int, help='Random seed for reproducibility')
def generate(data_type: str, count: int, output: str, seed: Optional[int]) -> None:
    """Generate test data"""
    print_header(f"Generate Test Data: {data_type}")

    print_info(f"Type: {data_type}")
    print_info(f"Count: {count}")
    print_info(f"Output: {output}")
    if seed:
        print_info(f"Seed: {seed}")

    # Initialize generator
    generator = TestDataGenerator(seed=seed)

    # Generate data
    print_info("\n🔄 Generating data...")

    if data_type == 'user':
        data = generator.generate_users(count)
    elif data_type == 'product':
        data = generator.generate_products(count)
    elif data_type == 'transaction':
        data = generator.generate_transactions(count)
    elif data_type == 'card':
        data = generator.generate_cards(count)
    elif data_type == 'address':
        data = generator.generate_addresses(count)
    else:
        print_error(f"Unknown data type: {data_type}")
        raise click.Abort()

    # Export to JSON
    output_path = Path(output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    generator.export_json(data, str(output_path))

    print_success(f"\n✅ Generated {len(data)} {data_type} records")
    print_info(f"Saved to: {output_path}")

    # Show sample
    if data:
        print_info("\n📋 Sample record:")
        sample = generator._to_dict(data[0])
        console.print_json(json.dumps(sample, indent=2))


@data.command()
@click.argument('file', type=click.Path(exists=True))
def inspect(file: str) -> None:
    """Inspect test data file"""
    print_header("Inspect Test Data")

    file_path = Path(file)
    print_info(f"File: {file_path}")

    try:
        with open(file_path, 'r') as f:
            data = json.load(f)

        if not isinstance(data, list):
            print_error("Data file must contain a JSON array")
            raise click.Abort()

        print_info(f"Records: {len(data)}")

        if not data:
            print_info("File is empty")
            return

        # Analyze structure
        first_record = data[0]
        fields = list(first_record.keys()) if isinstance(first_record, dict) else []

        print_info(f"\n📋 Fields ({len(fields)}):")
        for field in fields:
            print_info(f"  • {field}")

        # Show sample records
        print_info("\n📝 Sample records:")
        for i, record in enumerate(data[:3], 1):
            print_info(f"\n  Record {i}:")
            console.print_json(json.dumps(record, indent=2))

    except Exception as e:
        print_error(f"Failed to inspect file: {e}")
        raise click.Abort()


@data.command()
@click.argument('files', nargs=-1, type=click.Path(exists=True), required=True)
@click.option('--output', '-o', type=click.Path(), required=True, help='Output merged file')
def merge(files: tuple, output: str) -> None:
    """Merge multiple test data files"""
    print_header("Merge Test Data")

    print_info(f"Input files: {len(files)}")
    for f in files:
        print_info(f"  • {f}")

    all_data = []

    for file in files:
        try:
            with open(file, 'r') as f:
                data = json.load(f)
                if isinstance(data, list):
                    all_data.extend(data)
                else:
                    all_data.append(data)
        except Exception as e:
            print_error(f"Failed to read {file}: {e}")
            raise click.Abort()

    # Write merged data
    output_path = Path(output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, 'w') as f:
        json.dump(all_data, f, indent=2)

    print_success(f"\n✅ Merged {len(all_data)} records")
    print_info(f"Output: {output_path}")


@data.command()
@click.argument('file', type=click.Path(exists=True))
@click.option('--field', '-f', required=True, help='Field to filter by')
@click.option('--value', '-v', required=True, help='Value to filter for')
@click.option('--output', '-o', type=click.Path(), required=True, help='Output filtered file')
def filter_data(file: str, field: str, value: str, output: str) -> None:
    """Filter test data by field value"""
    print_header("Filter Test Data")

    print_info(f"Input: {file}")
    print_info(f"Filter: {field} = {value}")

    try:
        with open(file, 'r') as f:
            data = json.load(f)

        if not isinstance(data, list):
            print_error("Data file must contain a JSON array")
            raise click.Abort()

        # Filter data
        filtered = [record for record in data if record.get(field) == value]

        # Write filtered data
        output_path = Path(output)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        with open(output_path, 'w') as f:
            json.dump(filtered, f, indent=2)

        print_success(f"\n✅ Filtered {len(filtered)} / {len(data)} records")
        print_info(f"Output: {output_path}")

    except Exception as e:
        print_error(f"Failed to filter data: {e}")
        raise click.Abort()


@data.command()
@click.argument('file', type=click.Path(exists=True))
@click.option('--sample-size', '-n', type=int, required=True, help='Number of records to sample')
@click.option('--output', '-o', type=click.Path(), required=True, help='Output sampled file')
@click.option('--seed', '-s', type=int, help='Random seed')
def sample(file: str, sample_size: int, output: str, seed: Optional[int]) -> None:
    """Sample random subset of test data"""
    print_header("Sample Test Data")

    import random
    if seed:
        random.seed(seed)

    try:
        with open(file, 'r') as f:
            data = json.load(f)

        if not isinstance(data, list):
            print_error("Data file must contain a JSON array")
            raise click.Abort()

        if sample_size > len(data):
            print_error(f"Sample size ({sample_size}) exceeds data size ({len(data)})")
            raise click.Abort()

        # Sample data
        sampled = random.sample(data, sample_size)

        # Write sampled data
        output_path = Path(output)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        with open(output_path, 'w') as f:
            json.dump(sampled, f, indent=2)

        print_success(f"\n✅ Sampled {len(sampled)} / {len(data)} records")
        print_info(f"Output: {output_path}")

    except Exception as e:
        print_error(f"Failed to sample data: {e}")
        raise click.Abort()


@data.command()
@click.argument('file', type=click.Path(exists=True))
def validate(file: str) -> None:
    """Validate test data format"""
    print_header("Validate Test Data")

    file_path = Path(file)
    print_info(f"File: {file_path}")

    try:
        with open(file_path, 'r') as f:
            data = json.load(f)

        if not isinstance(data, list):
            print_error("❌ Data must be a JSON array")
            raise click.Abort()

        print_success("✅ Valid JSON array")
        print_info(f"Records: {len(data)}")

        if not data:
            print_info("⚠️  File is empty")
            return

        # Check structure consistency
        if isinstance(data[0], dict):
            first_keys = set(data[0].keys())
            print_info(f"Fields: {len(first_keys)}")

            inconsistent = []
            for i, record in enumerate(data[1:], 1):
                if isinstance(record, dict):
                    if set(record.keys()) != first_keys:
                        inconsistent.append(i)

            if inconsistent:
                print_error(f"⚠️  {len(inconsistent)} records have inconsistent fields")
                print_info(f"Inconsistent records: {inconsistent[:10]}")
            else:
                print_success("✅ All records have consistent structure")

        print_success("\n✅ Validation passed")

    except json.JSONDecodeError as e:
        print_error(f"❌ Invalid JSON: {e}")
        raise click.Abort()
    except Exception as e:
        print_error(f"❌ Validation failed: {e}")
        raise click.Abort()


if __name__ == '__main__':
    data()
