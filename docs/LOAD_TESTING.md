# Load Testing & Performance Profiling

Comprehensive load testing and performance profiling capabilities for mobile test automation.

## Features

### 🔥 Load Testing

- **Predefined Profiles**: smoke, light, medium, heavy, stress, spike
- **Virtual Users**: Simulate concurrent user load
- **Ramp-up Control**: Gradual user spawning
- **Response Time Analysis**: P50, P95, P99 percentiles
- **Throughput Measurement**: Tests per second
- **Error Tracking**: Detailed failure analysis
- **Fail-Fast Mode**: Stop on critical errors

### 🔬 Performance Profiling

- **CPU Profiling**: Identify performance bottlenecks
- **Memory Profiling**: Track memory allocations
- **Time Profiling**: Measure execution time
- **Top Functions**: Identify slowest operations
- **Profile Comparison**: Track performance regressions
- **HTML Reports**: Beautiful visualization

## Quick Start

### Load Testing

```bash
# Run load test with light profile
observe load run tests/test_login.py --profile light

# Run stress test with custom parameters
observe load run tests/ --profile stress --users 100 --duration 1800

# Run with fail-fast mode
observe load run tests/ --profile medium --fail-fast

# Save results to file
observe load run tests/ --profile heavy --output results/
```

### Performance Profiling

```bash
# Profile test performance
observe load profile tests/test_checkout.py

# Profile with CPU and memory
observe load profile tests/ --cpu --memory --top 30

# Generate HTML report
observe load profile tests/ --report profile_report.html

# Save profile data for comparison
observe load profile tests/ --output baseline_profile.json
```

### Profile Comparison

```bash
# Compare baseline vs current
observe load compare baseline_profile.json current_profile.json
```

## Load Profiles

| Profile    | Users | Duration | Ramp-up | Description          |
|------------|-------|----------|---------|----------------------|
| **smoke**  | 1     | 60s      | 0s      | Quick sanity check   |
| **light**  | 5     | 300s     | 30s     | Light load testing   |
| **medium** | 20    | 600s     | 60s     | Medium load testing  |
| **heavy**  | 50    | 900s     | 120s    | Heavy load testing   |
| **stress** | 100   | 1800s    | 300s    | Stress testing       |
| **spike**  | 50    | 300s     | 0s      | Sudden traffic spike |

List all profiles:

```bash
observe load profiles
```

## Configuration

### Load Test Config

```python
from framework.testing import LoadTester, LoadTestConfig, LoadProfile

# Custom profile
profile = LoadProfile(
    name="Custom",
    description="Custom load profile",
    virtual_users=30,
    duration_seconds=600,
    ramp_up_seconds=60,
    think_time_seconds=1.0,
)

# Configuration
config = LoadTestConfig(
    test_path=Path("tests/"),
    profile=profile,
    max_workers=10,
    timeout_seconds=300,
    fail_fast=True,
    collect_metrics=True,
)

# Run test
tester = LoadTester(config)
result = tester.run()
```

### Profiler Config

```python
from framework.testing import PerformanceProfiler, ProfilerConfig

# Configuration
config = ProfilerConfig(
    profile_cpu=True,
    profile_memory=True,
    profile_time=True,
    top_functions=30,
    sort_by="cumulative",  # or "time", "calls"
)

# Profile test
profiler = PerformanceProfiler(config)
result = profiler.profile_test(
    test_path=Path("tests/test.py"),
    test_function=my_test_function,
)
```

## Results Analysis

### Load Test Results

```python
result = tester.run()

print(f"Duration: {result.duration_seconds}s")
print(f"Total Tests: {result.total_tests}")
print(f"Passed: {result.passed_tests}")
print(f"Failed: {result.failed_tests}")
print(f"Throughput: {result.throughput:.2f} tests/sec")
print(f"Avg Response: {result.avg_response_time:.3f}s")
print(f"P95 Response: {result.p95_response_time:.3f}s")
print(f"P99 Response: {result.p99_response_time:.3f}s")

# Save to JSON
tester.save_results(result, Path("results.json"))
```

### Profile Results

```python
result = profiler.profile_test(...)

# CPU Profile
for func in result.cpu_profile["top_functions"]:
    print(f"{func['function']}: {func['total_time']:.4f}s")

# Memory Profile
for alloc in result.memory_profile["top_allocations"]:
    print(f"{alloc['filename']}: {alloc['size_mb']:.2f} MB")

# Generate HTML report
profiler.generate_report(result, Path("profile.html"))
```

## Use Cases

### 1. Stress Testing

Test system behavior under extreme load:

```bash
observe load run tests/ --profile stress --users 200 --duration 3600
```

### 2. Spike Testing

Test sudden traffic increases:

```bash
observe load run tests/ --profile spike --users 100 --ramp-up 0
```

### 3. Performance Regression Testing

Track performance over time:

```bash
# Baseline
observe load profile tests/ --output baseline.json

# After changes
observe load profile tests/ --output current.json

# Compare
observe load compare baseline.json current.json
```

### 4. Bottleneck Identification

Find performance bottlenecks:

```bash
observe load profile tests/slow_test.py --cpu --memory --top 50
```

### 5. CI/CD Integration

```yaml
# .github/workflows/load-test.yml
- name: Run load test
  run: |
    observe load run tests/ --profile medium --output results/
    
- name: Profile performance
  run: |
    observe load profile tests/ --report profile.html
    
- name: Upload results
  uses: actions/upload-artifact@v3
  with:
    name: load-test-results
    path: results/
```

## Metrics

### Response Time Percentiles

- **P50 (Median)**: 50% of requests faster than this
- **P95**: 95% of requests faster than this
- **P99**: 99% of requests faster than this

### Throughput

Number of tests executed per second:

```
throughput = total_tests / duration_seconds
```

### Error Rate

Percentage of failed tests:

```
error_rate = (failed_tests / total_tests) * 100
```

## Best Practices

### 1. Start Small

Always start with smoke or light profiles before running heavy tests.

### 2. Use Ramp-up

Gradual user spawning prevents overwhelming the system:

```bash
observe load run tests/ --profile medium --ramp-up 120
```

### 3. Monitor Resources

Watch CPU, memory, and network during load tests.

### 4. Set Realistic Goals

Define performance targets:

- Response time < 2s for 95% of requests
- Throughput > 100 tests/sec
- Error rate < 1%

### 5. Regular Profiling

Profile performance regularly to catch regressions early:

```bash
# Weekly performance check
observe load profile tests/ --output weekly_profile_$(date +%Y%m%d).json
```

### 6. Fail-Fast for CI

Use fail-fast mode in CI to save resources:

```bash
observe load run tests/ --profile light --fail-fast
```

## Advanced Usage

### Custom Progress Callback

```python
def progress_callback(message: str):
    print(f"[{datetime.now()}] {message}")

result = tester.run(progress_callback=progress_callback)
```

### Profile Comparison

```python
baseline = profiler.load_profile(Path("baseline.json"))
current = profiler.load_profile(Path("current.json"))

comparison = profiler.compare_profiles(baseline, current)

if comparison["changes"]["duration"]["regression"]:
    print("⚠️ Performance regression detected!")
```

### Custom Load Profiles

```python
# Soak test - long duration, constant load
soak_profile = LoadProfile(
    name="Soak Test",
    description="24-hour soak test",
    virtual_users=10,
    duration_seconds=86400,  # 24 hours
    ramp_up_seconds=600,
)

# Breakpoint test - find maximum capacity
breakpoint_profile = LoadProfile(
    name="Breakpoint",
    description="Find breaking point",
    virtual_users=500,
    duration_seconds=3600,
    ramp_up_seconds=1800,  # 30 min ramp-up
)
```

## Troubleshooting

### High Failure Rate

If tests fail frequently:

1. Check device availability
2. Increase think time between iterations
3. Reduce concurrent users
4. Check network connectivity

### Memory Issues

If profiler shows high memory usage:

1. Look for memory leaks in test code
2. Clear caches between iterations
3. Reduce concurrent workers

### Timeouts

If tests timeout:

1. Increase timeout value
2. Reduce load intensity
3. Check device performance

## Examples

### Complete Load Test

```python
from framework.testing import LoadTester, LoadTestConfig, LoadProfile
from pathlib import Path

# Create custom profile
profile = LoadProfile(
    name="API Load Test",
    description="Test API endpoints",
    virtual_users=50,
    duration_seconds=600,
    ramp_up_seconds=60,
    think_time_seconds=0.5,
)

# Configure test
config = LoadTestConfig(
    test_path=Path("tests/api_tests.py"),
    profile=profile,
    max_workers=20,
    fail_fast=False,
    output_dir=Path("results/"),
)

# Run test
tester = LoadTester(config)

def progress(msg):
    print(f"[LOAD TEST] {msg}")

result = tester.run(progress_callback=progress)

# Analyze results
print(f"\n{'='*60}")
print(f"LOAD TEST RESULTS")
print(f"{'='*60}")
print(f"Duration: {result.duration_seconds:.2f}s")
print(f"Throughput: {result.throughput:.2f} tests/sec")
print(f"Success Rate: {result.passed_tests/result.total_tests*100:.1f}%")
print(f"Avg Response: {result.avg_response_time:.3f}s")
print(f"P95 Response: {result.p95_response_time:.3f}s")

if result.failed_tests > 0:
    print(f"\n⚠️ {result.failed_tests} tests failed!")
    for error in result.errors[:5]:
        print(f"  - User {error['user_id']}: {error['error']}")
```

### Complete Performance Profile

```python
from framework.testing import PerformanceProfiler, ProfilerConfig
from pathlib import Path

# Configure profiler
config = ProfilerConfig(
    profile_cpu=True,
    profile_memory=True,
    top_functions=30,
    sort_by="cumulative",
)

# Create profiler
profiler = PerformanceProfiler(config)

# Profile function
def my_test():
    # Your test code here
    pass

result = profiler.profile_test(
    Path("tests/my_test.py"),
    my_test,
)

# Generate reports
profiler.save_profile(result, Path("profile.json"))
profiler.generate_report(result, Path("profile.html"))

# Analyze
print(f"\n{'='*60}")
print(f"PERFORMANCE PROFILE")
print(f"{'='*60}")
print(f"Duration: {result.duration_seconds:.3f}s")

if result.cpu_profile:
    print(f"\nTop 5 CPU-intensive functions:")
    for i, func in enumerate(result.cpu_profile["top_functions"][:5], 1):
        print(f"  {i}. {func['function']}: {func['total_time']:.4f}s")

if result.memory_profile:
    print(f"\nMemory: {result.memory_profile['total_size_mb']:.2f} MB")
    print(f"Top 5 memory allocations:")
    for i, alloc in enumerate(result.memory_profile["top_allocations"][:5], 1):
        print(f"  {i}. {alloc['filename']}: {alloc['size_mb']:.2f} MB")
```

## See Also

- [Parallel Execution](PARALLEL_EXECUTION.md) - Run tests in parallel
- [Performance Analysis](../framework/analysis/performance_analyzer.py) - App performance monitoring
- [Doctor Command](../framework/cli/doctor_command.py) - System health checks
