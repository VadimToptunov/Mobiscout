# Mobile Test Recorder - Quick Start Guide

> Get up and running in 10 minutes ⏱️

---

## Installation

```bash
# Clone repository
git clone https://github.com/VadimToptunov/mobile_test_recorder.git
cd mobile_test_recorder

# Create virtual environment
python3.13 -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
pip install -e .

# Verify installation
observe info
```

---

## Available Commands

The framework provides seven main command groups:

### 1. Business Logic Analysis

```bash
# Analyze Android/iOS source code for business rules, edge cases, and patterns
observe business analyze <source_path> --output analysis.json
observe business report analysis.json     # Human-readable report
observe business stats analysis.json      # Statistics summary
```

### 2. Project Integration

```bash
# Full automation: analyze + generate tests in one command
observe project fullcycle \
  --android-source path/to/android/src \
  --ios-source path/to/ios/src \
  --output ./tests/

# Individual steps:
observe project analyze <source_path> --output analysis.json
observe project integrate analysis.json --framework-path ./my-tests/
observe project generate analysis.json --output ./tests/
```

### 3. Dashboard & Analytics

```bash
# Start local web dashboard for test results visualization
observe dashboard start --port 8080

# Import test results
observe dashboard import-results --junit-xml results/junit.xml

# View statistics
observe dashboard stats --days 30

# Export metrics for monitoring
observe dashboard export --format prometheus --output metrics.txt
```

### 4. Self-Healing Tests

```bash
# Analyze test failures and suggest fixes
observe heal analyze --test-results results/junit.xml

# Automatically fix broken selectors
observe heal auto --test-results results/junit.xml --commit

# View healing history
observe heal history --limit 10

# Show healing statistics
observe heal stats
```

### 5. Device Management

```bash
# List available devices
observe devices list --platform android

# Check device health
observe devices health

# Create device pool
observe devices pool create --name android-pool --devices emulator-5554,emulator-5556

# List pools
observe devices pool list
```

### 6. Session Recording

```bash
# (Coming soon - SDK integration required)
observe record start --session-id my-session
observe record stop
observe record correlate <session_id>
```

### 7. Test Generation

```bash
# (Coming soon - generates from recorded sessions)
observe generate pages --model app-model.json --output tests/pages/
observe generate api --model app-model.json --output tests/api/
```

---

## Basic Workflow

### Scenario 1: Analyze Existing App

**Goal:** Extract business logic from your mobile app source code

```bash
# 1. Navigate to your project
cd /path/to/your/mobile/app

# 2. Analyze source code
observe business analyze ./src/main --output analysis.json

# 3. View results
observe business report analysis.json

# 4. See statistics
observe business stats analysis.json
```

**Output:**

- User flows discovered
- Business rules extracted
- Edge cases identified
- API contracts generated
- Negative test cases suggested

---

### Scenario 2: Generate Tests from Analysis

**Goal:** Auto-generate Page Objects and tests

```bash
# 1. Analyze Android app
observe project analyze ./android/src --platform android --output android-analysis.json

# 2. Generate complete test suite
observe project generate android-analysis.json \
  --output ./tests/ \
  --framework pytest-bdd

# 3. Run generated tests
pytest tests/ -v
```

**Generated:**

- `tests/pages/` - Page Objects
- `tests/api/` - API clients
- `tests/features/` - BDD scenarios (if applicable)

---

### Scenario 3: Dashboard for Test Results

**Goal:** Visualize test results and track test health

```bash
# 1. Import test results
observe dashboard import-results --junit-xml test-results/junit.xml

# 2. Start dashboard
observe dashboard start --port 8080
# Opens browser at http://localhost:8080

# 3. View statistics in terminal
observe dashboard stats --days 30
```

**Dashboard Features:**

- 📊 Test health tracking
- ⚡ Pass rate trends
- 🔄 Flaky test detection
- 🔧 Self-healing status

---

### Scenario 4: Auto-Healing Broken Tests

**Goal:** Automatically fix broken element selectors

```bash
# 1. Run tests and capture failures
pytest tests/ --junit-xml=results/junit.xml

# 2. Analyze failures
observe heal analyze --test-results results/junit.xml

# 3. Auto-fix selectors (dry-run first)
observe heal auto --test-results results/junit.xml --dry-run

# 4. Apply fixes and commit
observe heal auto --test-results results/junit.xml --commit

# 5. Check what was healed
observe heal history
observe heal stats
```

**Healing Process:**

1. ✅ Detects broken selectors from test failures
2. ✅ Finds alternative selectors using ML
3. ✅ Updates test files automatically
4. ✅ Commits changes to git (optional)
5. ✅ Tracks healing success rate

---

### Scenario 5: Device Management

**Goal:** Manage Android/iOS devices and device pools

```bash
# 1. List available devices
observe devices list --platform android

# 2. Check device health
observe devices health

# 3. Create device pool for parallel execution
observe devices pool create \
  --name android-test-pool \
  --devices emulator-5554,emulator-5556,emulator-5558 \
  --strategy round-robin

# 4. View pool info
observe devices pool info android-test-pool

# 5. Run tests on device pool (coming soon)
# pytest tests/ --pool android-test-pool
```

**Device Strategies:**

- `round-robin` - Distribute tests evenly
- `least-busy` - Use least busy device
- `random` - Random device selection

---

### Scenario 6: Full Automation (Android + iOS)

**Goal:** One command to analyze and generate everything

```bash
observe project fullcycle \
  --android-source ./android/app/src/main \
  --ios-source ./ios/MyApp \
  --output ./tests/ \
  --platform both
```

**What happens:**

1. ✅ Analyzes Android source code
2. ✅ Analyzes iOS source code
3. ✅ Extracts API contracts
4. ✅ Generates Page Objects
5. ✅ Creates integration tests
6. ✅ Produces BDD features

**Time:** ~2-5 minutes for typical app

---

## Understanding the Analysis

### Business Logic Analysis Output

```json
{
  "user_flows": [
    {
      "name": "User Login",
      "steps": ["Launch app", "Enter email", "Enter password", "Submit"],
      "priority": "high"
    }
  ],
  "edge_cases": [
    {
      "type": "boundary",
      "description": "Age check: age >= 18",
      "test_data": [17, 18, 19, 100],
      "severity": "high"
    }
  ],
  "api_contracts": [
    {
      "endpoint": "/api/v1/auth/login",
      "method": "POST",
      "request_schema": {"email": "string", "password": "string"},
      "expected_responses": [200, 401, 400]
    }
  ]
}
```

---

## Command Reference

### Business Logic Commands

| Command   | Description                    | Example                                               |
|-----------|--------------------------------|-------------------------------------------------------|
| `analyze` | Analyze source code            | `observe business analyze ./src --output result.json` |
| `report`  | Generate human-readable report | `observe business report result.json`                 |
| `stats`   | Show statistics summary        | `observe business stats result.json`                  |

### Project Commands

| Command     | Description                   | Example                                                                     |
|-------------|-------------------------------|-----------------------------------------------------------------------------|
| `analyze`   | Analyze project source        | `observe project analyze ./src --platform android`                          |
| `integrate` | Integrate with existing tests | `observe project integrate analysis.json --framework-path ./tests`          |
| `generate`  | Generate test artifacts       | `observe project generate analysis.json --output ./tests`                   |
| `fullcycle` | Do everything at once         | `observe project fullcycle --android-source ./android/src --output ./tests` |

---

## Common Use Cases

### 1. Audit Existing App

```bash
# Quick analysis to understand app structure
observe business analyze ./src --output audit.json
observe business report audit.json > audit-report.txt

# Share report with team
cat audit-report.txt
```

### 2. Add Tests to Legacy App

```bash
# Generate tests from existing codebase
observe project fullcycle \
  --android-source ./app/src/main \
  --output ./tests/generated/

# Review generated tests
ls -la tests/generated/
```

### 3. API Contract Extraction

```bash
# Extract all API endpoints
observe business analyze ./src --output api-analysis.json

# View API contracts
observe business report api-analysis.json | grep -A 10 "API Contracts"
```

---

## Next Steps

1. **Read Full Documentation:** [USER_GUIDE.md](USER_GUIDE.md)
2. **Try Demo Apps:** `cd demo-app/` (Android & iOS examples included)
3. **View Examples:** Check `tests/` directory for sample outputs
4. **Report Issues:** [GitHub Issues](https://github.com/VadimToptunov/mobile_test_recorder/issues)

---

## Troubleshooting

### Issue: "No business logic detected"

**Cause:** Source path doesn't contain Kotlin/Swift/Java files

**Solution:**

```bash
# Check if files exist
find ./src -name "*.kt" -o -name "*.swift" -o -name "*.java"

# Use correct source path
observe business analyze ./app/src/main  # Android
observe business analyze ./MyApp/MyApp   # iOS
```

### Issue: "Command not found: observe"

**Cause:** Framework not installed in PATH

**Solution:**

```bash
# Activate virtual environment
source .venv/bin/activate

# Reinstall in editable mode
pip install -e .

# Verify
observe info
```

### Issue: "Empty analysis result"

**Cause:** Unsupported file type or parsing error

**Solution:**

```bash
# Enable debug logging
export OBSERVE_LOG_LEVEL=DEBUG
observe business analyze ./src --output result.json

# Check logs
cat ~/.observe/logs/observe.log
```

---

## Tips for Best Results

✅ **Do:**

- Use actual project source code (not compiled binaries)
- Point to source directories (e.g., `./app/src/main`)
- Review generated tests before committing
- Iterate: analyze → review → refine → re-generate

❌ **Don't:**

- Point to build directories (`./build`, `./out`)
- Analyze compiled files (`.apk`, `.ipa`)
- Skip reviewing auto-generated code
- Expect 100% perfect generation (it's AI-assisted, not magic!)

---

## Getting Help

### Quick Help

```bash
observe --help                    # All commands
observe business --help     # Business logic commands
observe project --help            # Project commands
```

### Resources

- **Documentation:** [USER_GUIDE.md](USER_GUIDE.md) (complete reference)
- **Examples:** `demo-app/` directory
- **Issues:** [GitHub Issues](https://github.com/VadimToptunov/mobile_test_recorder/issues)

---

**Ready to automate your testing!** 🚀

For detailed scenarios and advanced features, see the [complete user guide](USER_GUIDE.md).
