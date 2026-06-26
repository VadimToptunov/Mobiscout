# Parallel Test Execution

Execute tests in parallel across multiple workers for faster feedback and better resource utilization.

## Quick Start

### Basic Parallel Execution

```bash
# Run tests in parallel with 4 workers
observe parallel run tests/ --workers 4

# Use balanced sharding for optimal load distribution
observe parallel run tests/ --workers 4 --shard-strategy balanced

# Pass additional pytest arguments
observe parallel run tests/ --workers 4 --pytest-args "-v --tb=short"
```

## Features

### 1. Intelligent Test Sharding

Distribute tests across workers using different strategies:

**Round Robin** (Default)

- Simple distribution: test 1 → worker 1, test 2 → worker 2, etc.
- Good for tests with similar duration

**Balanced**

- Distributes based on estimated test duration
- Minimizes total execution time
- Best for mixed test suites

**By File**

- Keeps tests from same file together
- Good for test files with shared fixtures

### 2. Progress Tracking

Real-time progress display with Rich UI:

- Spinner animation
- Progress bar
- Time elapsed
- Tests completed/total

### 3. Result Aggregation

Comprehensive result summary:

- Total tests, passed, failed, skipped
- Pass rate percentage
- Total duration
- Parallelization speedup
- Per-shard breakdown

### 4. Multi-Device Support (Coming Soon)

Distribute tests across multiple physical devices:

```bash
# Run on all available Android devices
observe parallel on-devices tests/ --platform android

# Run on all iOS devices
observe parallel on-devices tests/ --platform ios

# Run on all devices (Android + iOS)
observe parallel on-devices tests/ --platform both
```

## CLI Commands

### `observe parallel run`

Run tests in parallel on a single device with multiple workers.

```bash
observe parallel run <test_dir> [OPTIONS]

Options:
  --workers, -w <N>            Number of parallel workers (default: 4)
  --shard-strategy <STRATEGY>  Sharding strategy (round_robin|balanced|by_file)
  --pytest-args <ARGS>         Additional pytest arguments
```

**Examples:**

```bash
# 8 workers with balanced sharding
observe parallel run tests/ -w 8 --shard-strategy balanced

# With verbose pytest output
observe parallel run tests/ --pytest-args "-v -s"

# Specific test markers
observe parallel run tests/ --pytest-args "-m smoke"
```

### `observe parallel create-shards`

Create test shards for manual distribution (useful for CI/CD).

```bash
observe parallel create-shards <test_dir> <num_shards> [OPTIONS]

Options:
  --strategy <STRATEGY>  Sharding strategy
  --output, -o <DIR>     Output directory for shard files
```

**Example:**

```bash
# Create 10 shards and save to files
observe parallel create-shards tests/ 10 --strategy balanced --output ./shards

# This creates:
# shards/shard_0.txt
# shards/shard_1.txt
# ...
# shards/shard_9.txt
```

### `observe parallel benchmark`

Benchmark different sharding strategies.

```bash
observe parallel benchmark [OPTIONS]

Options:
  --workers, -w <N>      Number of workers (default: 4)
  --test-count <N>       Number of simulated tests (default: 100)
```

**Example:**

```bash
observe parallel benchmark --workers 8 --test-count 500
```

Output:

```
╭─ Benchmark Results ─────────────────╮
│ Strategy    │ Duration │ Speedup    │
├─────────────┼──────────┼────────────┤
│ Round Robin │ 25.32s   │ 3.95x      │
│ Balanced    │ 23.18s   │ 4.31x      │
│ By File     │ 26.45s   │ 3.78x      │
╰─────────────┴──────────┴────────────╯
```

## Programmatic API

### Basic Usage

```python
from pathlib import Path
from framework.execution.parallel_executor import ParallelExecutor
from framework.execution.test_sharding import TestCase, create_shards, TestShardingStrategy

# Define tests
tests = [
    TestCase(
        file=Path("test_auth.py"),
        name="test_login",
        full_name="tests/test_auth.py::test_login",
        estimated_duration=2.5
    ),
    # ... more tests
]

# Create shards
shards = create_shards(
    tests,
    num_shards=4,
    strategy=TestShardingStrategy.BALANCED
)

# Execute in parallel
executor = ParallelExecutor(max_workers=4)
results = executor.execute_shards(shards, project_root=Path.cwd())

# Get summary
summary = executor.generate_summary(results)
print(summary)
```

### With Progress Callback

```python
def progress_callback(completed, total):
    print(f"Progress: {completed}/{total} shards")

executor = ParallelExecutor(max_workers=4)
results = executor.execute_shards(
    shards,
    project_root=Path.cwd(),
    progress_callback=progress_callback
)
```

### Custom Pytest Arguments

```python
executor = ParallelExecutor(
    max_workers=4,
    pytest_args=["-v", "--tb=short", "-m", "smoke"]
)
```

## Sharding Strategies

### Strategy Comparison

| Strategy        | Use Case        | Pros                         | Cons                            |
|-----------------|-----------------|------------------------------|---------------------------------|
| **Round Robin** | Uniform tests   | Simple, predictable          | Poor load balance if tests vary |
| **Balanced**    | Mixed duration  | Optimal load balance         | Requires duration estimates     |
| **By File**     | Shared fixtures | Keeps related tests together | May create unbalanced shards    |

### When to Use Each Strategy

**Round Robin**

- All tests have similar duration
- Simple test suite
- No shared state between tests

**Balanced** (Recommended)

- Tests have varying durations
- Want to minimize total execution time
- Have test duration history

**By File**

- Tests in same file share expensive fixtures
- Setup/teardown per file
- Want to minimize fixture overhead

## Performance

### Speedup Examples

| Tests | Sequential | 4 Workers | 8 Workers | Speedup (8w) |
|-------|------------|-----------|-----------|--------------|
| 10    | 50s        | 15s       | 10s       | 5x           |
| 50    | 250s       | 70s       | 40s       | 6.25x        |
| 100   | 500s       | 140s      | 80s       | 6.25x        |
| 500   | 2500s      | 700s      | 400s      | 6.25x        |

*Assuming balanced load and minimal overhead*

### Factors Affecting Performance

**Positive:**

- More workers (up to CPU count)
- Balanced load distribution
- Independent tests
- Fast test execution

**Negative:**

- Shared resources (database, files)
- Test dependencies
- Heavy setup/teardown
- I/O bottlenecks

## CI/CD Integration

### GitHub Actions

```yaml
name: Parallel Tests

on: [push]

jobs:
  test:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        shard: [0, 1, 2, 3]  # 4 parallel jobs
    steps:
      - uses: actions/checkout@v2
      - name: Run shard ${{ matrix.shard }}
        run: |
          observe parallel create-shards tests/ 4 --output shards
          pytest $(cat shards/shard_${{ matrix.shard }}.txt)
```

### GitLab CI

```yaml
test:
  parallel: 4
  script:
    - observe parallel create-shards tests/ 4 --output shards
    - pytest $(cat shards/shard_${CI_NODE_INDEX}.txt)
```

## Best Practices

### 1. Isolate Tests

Ensure tests are independent:

```python
# Good: Each test has own setup
@pytest.fixture
def user(db):
    return db.create_user(f"user_{uuid.uuid4()}")

# Bad: Shared state
global_user = None

def test_login():
    global global_user
    global_user = create_user()
```

### 2. Optimize Slow Tests

Profile and optimize slow tests first:

```bash
# Find slow tests
pytest --durations=10

# Run slow tests on more workers
observe parallel run tests/ --workers 8 --pytest-args "-m slow"
```

### 3. Use Test Markers

Group related tests:

```python
@pytest.mark.smoke
def test_critical_path():
    pass

@pytest.mark.integration
def test_external_api():
    pass
```

```bash
# Run only smoke tests in parallel
observe parallel run tests/ --pytest-args "-m smoke"
```

### 4. Monitor Resource Usage

Don't exceed available resources:

```bash
# Check CPU count
python -c "import os; print(os.cpu_count())"

# Use workers ≤ CPU count
observe parallel run tests/ --workers 8  # for 8-core CPU
```

### 5. Balance Load

Use balanced strategy for mixed test suites:

```bash
observe parallel run tests/ --shard-strategy balanced
```

## Troubleshooting

### Tests Fail in Parallel But Pass Sequential

**Cause:** Shared state or race conditions

**Fix:**

- Use unique identifiers per test
- Avoid global variables
- Use proper fixtures

### Poor Speedup

**Cause:** Unbalanced load or I/O bottlenecks

**Fix:**

```bash
# Try balanced strategy
observe parallel run tests/ --shard-strategy balanced

# Reduce workers to avoid I/O contention
observe parallel run tests/ --workers 2
```

### Database Conflicts

**Cause:** Tests using same database

**Fix:**

```python
# Use unique database per worker
@pytest.fixture(scope="session")
def db(worker_id):
    return create_db(f"test_db_{worker_id}")
```

## Roadmap

### Phase 1 (Complete)

- ✅ Multi-worker execution
- ✅ Intelligent sharding
- ✅ Progress tracking
- ✅ Result aggregation

### Phase 2 (In Progress)

- 🔄 Multi-device support
- 🔄 Device pool management
- 🔄 Cross-platform distribution

### Phase 3 (Planned)

- 📋 Test history-based sharding
- 📋 Automatic retry on failure
- 📋 Distributed execution dashboard

## Examples

See `tests/test_parallel_execution.py` for comprehensive examples.

## Support

- **CLI Help**: `observe parallel --help`
- **Benchmark**: `observe parallel benchmark`
- **Tests**: `pytest tests/test_parallel_execution.py -v`
