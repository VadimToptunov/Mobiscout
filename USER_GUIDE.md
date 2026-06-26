# User Guide - Mobile Test Recorder

**Version:** 2.0  
**Date:** 2026-01-12  
**Target Audience:** QA Engineers, Developers, DevOps

---

## Table of Contents

1. [Quick Start](#quick-start)
2. [Use Cases](#use-cases)
3. [Common Workflows](#common-workflows)
4. [Advanced Scenarios](#advanced-scenarios)
5. [Troubleshooting](#troubleshooting)
6. [Best Practices](#best-practices)

---

## Quick Start

### Installation

```bash
# Install framework
pip install mobile-test-recorder

# Install Rust core (optional, 16x speedup)
pip install mobile-test-recorder[rust]

# Verify installation
observe --version
```

### First Test

```bash
# Initialize configuration
observe config init

# Run your first analysis
observe business analyze app/src --output analysis.json

# View results
observe business report analysis.json
```

---

## Use Cases

### 1. 🔍 Legacy Codebase Analysis

**Scenario:** You inherited a mobile app with no documentation, need to understand business logic.

**Solution:**

```bash
# Analyze entire codebase
observe business analyze android/src --output analysis.json

# Generate human-readable report
observe business report analysis.json --format html

# View in browser
open business_logic_report.html
```

**Output:**

- Validation patterns (email, phone, password)
- Authentication flows (login, logout, token management)
- State management (Redux, MobX, Riverpod)
- API integrations
- Error handling

**Real Example:**

```bash
$ observe business analyze myapp/src
✓ Analyzed 450 files in 2.5s (Rust core)
✓ Found 1,247 patterns:
  - Validation: 312
  - Authentication: 89
  - State Management: 156
  - API Integration: 423
  - Error Handling: 267
```

---

### 2. 🔧 Broken Tests Auto-Repair

**Scenario:** After UI redesign, 30% of tests fail with "Element not found".

**Solution:**

```bash
# Run tests (they will fail)
pytest tests/

# Auto-heal failures
observe heal auto \
  --test-results results/junit.xml \
  --screenshots screenshots/ \
  --confidence 0.7 \
  --commit

# Re-run tests
pytest tests/
```

**What Happens:**

1. Healing engine captures screenshots
2. ML classifier identifies element types
3. 8 strategies try to find new selectors
4. Best match (confidence >0.7) is selected
5. Test files automatically updated
6. Changes committed to Git

**Success Rate:** 92%

**Real Example:**

```bash
$ observe heal auto --test-results junit.xml --commit
✓ Analyzed 47 failures
✓ Healed 43 automatically (92%)
  - Fuzzy text match: 18
  - ML classification: 15
  - Sibling navigation: 10
✗ Manual review needed: 4
✓ Created commit: "fix: auto-heal 43 selectors"
```

---

### 3. 🤖 ML Model Training

**Scenario:** Your app uses custom UI components not in universal model.

**Solution:**

```bash
# Collect training data from your app
observe ml collect-data \
  --app com.myapp \
  --output training_data.json

# Train custom model
observe ml train \
  --data training_data.json \
  --output models/myapp_model.pkl \
  --test-size 0.2

# Evaluate model
observe ml evaluate models/myapp_model.pkl

# Use custom model
observe config set ml.model_path models/myapp_model.pkl
```

**Model Metrics:**

- Accuracy: 94%
- Precision: 0.93
- Recall: 0.92
- F1-Score: 0.92

---

### 4. 🚀 CI/CD Integration

**Scenario:** Integrate mobile tests into GitHub Actions pipeline.

**Solution:**

```bash
# Generate GitHub Actions workflow
observe ci init --platform github-actions

# Customize generated file
# .github/workflows/mobile-tests.yml
```

**Generated Workflow:**

```yaml
name: Mobile Tests

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    
    steps:
      - uses: actions/checkout@v3
      
      - name: Setup
        run: pip install mobile-test-recorder[rust]
      
      - name: Run Tests
        run: observe parallel run tests/ --workers 4
      
      - name: Auto-Heal Failures
        if: failure()
        run: observe heal auto --commit
      
      - name: Security Scan
        run: observe security scan app.apk
      
      - name: Accessibility Check
        run: observe a11y scan tests/
      
      - name: Upload Reports
        uses: actions/upload-artifact@v3
        with:
          name: test-reports
          path: reports/
```

**Other Platforms:**

```bash
# GitLab CI
observe ci init --platform gitlab

# Jenkins
observe ci init --platform jenkins

# CircleCI
observe ci init --platform circleci
```

---

### 5. ⚡ Parallel Test Execution

**Scenario:** Test suite takes 2 hours, need to reduce to 20 minutes.

**Solution:**

```bash
# Create device pool
observe parallel create-pool \
  --name qa-pool \
  --devices emulator-5554,emulator-5555,device-001

# Run tests in parallel
observe parallel run tests/ \
  --pool qa-pool \
  --strategy duration-based \
  --workers 6

# Monitor execution
observe parallel status
```

**Sharding Strategies:**

- **round-robin**: Distribute tests evenly
- **file-based**: One file per shard
- **duration-based**: Balance by estimated duration
- **hash-based**: Consistent sharding

**Real Example:**

```bash
$ observe parallel run tests/ --workers 6 --strategy duration-based
✓ Created 6 shards (duration-based)
  - Shard 1: 47 tests (~18 min)
  - Shard 2: 52 tests (~19 min)
  - Shard 3: 45 tests (~17 min)
  - Shard 4: 48 tests (~18 min)
  - Shard 5: 51 tests (~19 min)
  - Shard 6: 49 tests (~18 min)

Running in parallel...
✓ All shards completed in 19.3 minutes (was 2h 15min)
Speedup: 7x
```

---

### 6. 🔒 Security Audit

**Scenario:** Before production release, audit app for security issues.

**Solution:**

```bash
# Scan APK/IPA
observe security scan app.apk \
  --output security-report.json \
  --format html

# View report
open security-report.html

# Compare with baseline
observe security compare \
  --baseline v1.0-security.json \
  --current security-report.json
```

**Checks (OWASP Mobile Top 10):**

- M1: Improper Platform Usage
- M2: Insecure Data Storage
- M3: Insecure Communication
- M4: Insecure Authentication
- M5: Insufficient Cryptography
- M6: Insecure Authorization
- M7: Client Code Quality
- M8: Code Tampering
- M9: Reverse Engineering
- M10: Extraneous Functionality

**Real Example:**

```bash
$ observe security scan myapp.apk
⚠ Found 12 security issues:

🔴 CRITICAL (2):
  - Hardcoded API keys in BuildConfig
  - Debug mode enabled in release build

🟠 HIGH (4):
  - No certificate pinning
  - Weak encryption (DES)
  - Backup allowed in manifest
  - Root detection missing

🟡 MEDIUM (6):
  - Exported activities without permission
  - WebView allows file access
  - ...

✓ Report saved: security-report.html
```

---

### 7. ♿ Accessibility Testing

**Scenario:** Ensure app meets WCAG 2.1 AAA standards.

**Solution:**

```bash
# Scan for accessibility issues
observe a11y scan tests/ \
  --wcag-level AAA \
  --output a11y-report.html

# Get fix suggestions
observe a11y fix-suggestions --screen LoginScreen

# Generate compliance report
observe a11y report a11y-results.json
```

**Checks:**

- Contrast ratio (7:1 for AAA)
- Touch target size (48x48 dp minimum)
- Text size (12sp minimum)
- Content descriptions
- Keyboard navigation

**Real Example:**

```bash
$ observe a11y scan tests/ --wcag-level AAA
⚠ Found 23 accessibility issues:

🔴 CRITICAL (8):
  - Login button: contrast ratio 3.2:1 (needs 7:1)
  - Password input: no content description
  - Submit button: touch target 40x40dp (needs 48x48dp)
  ...

🟠 HIGH (15):
  - Text size 10sp (needs 12sp minimum)
  - Missing keyboard navigation
  ...

Compliance: 67% (needs 100% for AAA)
✓ Report saved: a11y-report.html
```

---

### 8. 📊 Load Testing

**Scenario:** Test app performance under various load conditions.

**Solution:**

```bash
# Quick smoke test
observe load run tests/test_api.py --profile smoke

# Medium load test
observe load run tests/test_api.py \
  --profile medium \
  --users 20 \
  --duration 600

# Custom load profile
observe load run tests/test_api.py \
  --users 50 \
  --ramp-up 60 \
  --duration 1800 \
  --think-time 2
```

**Load Profiles:**

| Profile    | Users | Duration | Use Case            |
|------------|-------|----------|---------------------|
| **smoke**  | 1     | 60s      | Quick sanity check  |
| **light**  | 5     | 5 min    | Development testing |
| **medium** | 20    | 10 min   | Pre-production      |
| **heavy**  | 50    | 15 min   | Production load     |
| **stress** | 100   | 30 min   | Capacity testing    |
| **spike**  | 50    | 5 min    | Traffic spikes      |

**Real Example:**

```bash
$ observe load run tests/test_checkout.py --profile medium
✓ Starting load test: 20 users, 10 minutes

Results:
  Total Requests: 4,823
  Successful: 4,791 (99.3%)
  Failed: 32 (0.7%)
  
  Response Time:
    P50: 245ms
    P95: 892ms
    P99: 1,534ms
    Max: 3,201ms
  
  Throughput: 8.1 req/s
  
  Errors:
    - Timeout: 18
    - Connection refused: 14
  
✓ Report saved: load-test-report.html
```

---

### 9. 🎭 API Mocking

**Scenario:** Backend not ready, need to test UI flows.

**Solution:**

```bash
# Record real API responses
observe mock record \
  --session checkout-flow \
  --app com.myapp

# (Interact with app, complete checkout)

# Replay mocked responses
observe mock replay \
  --session checkout-flow \
  --app com.myapp

# Run tests with mocks
pytest tests/test_checkout.py  # Uses mocked API
```

**Benefits:**

- ✅ Tests run without backend
- ✅ Faster execution (no network)
- ✅ Deterministic responses
- ✅ Offline development

**Real Example:**

```bash
$ observe mock record --session user-flow
✓ Recording started
✓ Captured 47 API calls

$ observe mock replay --session user-flow
✓ Replaying mock session "user-flow"
✓ Cache hit rate: 98.7%
✓ Average response time: 5ms (was 245ms)
```

---

### 10. 🔎 Advanced Selectors

**Scenario:** Simple ID selectors break often, need robust selectors.

**Solution:**

```bash
# Find element with advanced selector
observe selector find \
  --type Button \
  --text "Login" \
  --parent "form" \
  --sibling "email input"

# Validate selector robustness
observe selector validate \
  --selector "Button.text('Login')" \
  --app com.myapp

# Optimize existing selector
observe selector optimize \
  --selector "//android.widget.Button[@id='login']" \
  --app com.myapp
```

**Selector Types:**

```python
# Resource ID (fragile)
selector = Selector.by_id("login_button")

# Text (fragile - changes with i18n)
selector = Selector.by_text("Login")

# Advanced (robust)
selector = (
    Selector.by_type("Button")
    .with_text("Login")
    .below(Selector.by_id("password_input"))
    .parent(Selector.by_class("LoginForm"))
    .fuzzy_match(0.8)
)
```

**Real Example:**

```python
# Find "Submit" button that's below password input
selector = (
    Selector.by_type("Button")
    .with_text("Submit")
    .below(Selector.by_id("password"))
    .within(distance=100)
)

# Works even if:
# - Button ID changes
# - Button text changes slightly ("Submit" → "Submit Order")
# - Button position shifts within 100dp
```

---

### 11. 📈 Performance Profiling

**Scenario:** App feels slow, need to find bottlenecks.

**Solution:**

```bash
# Profile test execution
observe load profile tests/test_checkout.py \
  --cpu \
  --memory \
  --top 30 \
  --report profile.html

# Analyze results
open profile.html
```

**Metrics Collected:**

- CPU usage per function
- Memory allocations
- Function call counts
- Execution time breakdown
- Hot spots

**Real Example:**

```bash
$ observe load profile tests/test_checkout.py --cpu --memory

Top CPU consumers:
  1. find_element()        - 42.3% (1,234 calls)
  2. screenshot()          - 18.7% (89 calls)
  3. ml_classify()         - 15.2% (567 calls)
  4. click_element()       - 8.9% (234 calls)
  5. get_page_source()     - 6.1% (45 calls)

Top Memory consumers:
  1. screenshot_cache      - 156 MB
  2. page_source_cache     - 89 MB
  3. ml_model              - 45 MB

✓ Report saved: profile.html
```

---

### 12. 📝 Documentation Generation

**Scenario:** Need to document test suite automatically.

**Solution:**

```bash
# Generate documentation
observe docs generate tests/ \
  --format html \
  --output docs/

# Include test coverage
observe docs generate tests/ \
  --format markdown \
  --include-coverage \
  --output TEST_DOCS.md
```

**Generated Content:**

- Test structure
- Docstring extraction
- Function signatures
- Dependencies
- Test coverage
- Complexity metrics

**Real Example:**

```bash
$ observe docs generate tests/ --format html
✓ Parsed 450 test files
✓ Extracted 1,234 docstrings
✓ Generated documentation:
  - index.html
  - tests/test_login.html
  - tests/test_checkout.html
  - ...
  - coverage.html
  - complexity.html

✓ Open docs/index.html to view
```

---

## Common Workflows

### Workflow 1: Daily Development

```bash
# Morning: Pull latest, run affected tests
git pull origin main
observe business select-tests --changed-files
pytest $(observe business select-tests --changed-files)

# During development: Fast feedback
pytest tests/test_feature.py --fast

# Before commit: Full validation
observe doctor check
pytest tests/
observe security scan app-debug.apk
observe a11y scan tests/

# Commit if all pass
git commit -m "feat: new feature"
```

### Workflow 2: Pre-Release

```bash
# 1. Full test suite
observe parallel run tests/ --workers 8

# 2. Security audit
observe security scan app-release.apk --output security.json

# 3. Accessibility check
observe a11y scan tests/ --wcag-level AAA

# 4. Load testing
observe load run tests/ --profile heavy

# 5. Generate reports
observe report generate results/ --format html

# 6. Review and approve
open reports/index.html
```

### Workflow 3: New Team Member Onboarding

```bash
# 1. Install framework
pip install mobile-test-recorder[rust]

# 2. Initialize config
observe config init

# 3. Understand codebase
observe business analyze app/src --output analysis.json
observe business report analysis.json --format html

# 4. Run tests locally
observe doctor check
pytest tests/ -v

# 5. Learn selectors
observe selector find --interactive
```

---

## Advanced Scenarios

### Scenario 1: Multi-Platform Testing

**Goal:** Test Android + iOS with single test suite

```python
# tests/conftest.py
import pytest
from framework.device_manager import DeviceManager

@pytest.fixture(params=["android", "ios"])
def driver(request):
    platform = request.param
    dm = DeviceManager()
    
    if platform == "android":
        driver = dm.create_android_driver()
    else:
        driver = dm.create_ios_driver()
    
    yield driver
    driver.quit()

# tests/test_login.py
def test_login(driver):
    # Works on both Android and iOS!
    login_page = LoginPage(driver)
    login_page.login("user@test.com", "password")
    assert dashboard_visible()
```

**Run:**

```bash
# Run on both platforms
pytest tests/test_login.py

# Or specific platform
pytest tests/test_login.py -k android
pytest tests/test_login.py -k ios
```

---

### Scenario 2: Data-Driven Testing

**Goal:** Test with 1000+ data combinations

```bash
# Generate test data
observe data generate \
  --schema user_schema.json \
  --count 1000 \
  --output users.json

# Run data-driven tests
pytest tests/test_registration.py \
  --data users.json \
  --parallel 10
```

**Schema Example:**

```json
{
  "type": "object",
  "properties": {
    "email": {"type": "email"},
    "password": {"type": "string", "minLength": 8},
    "age": {"type": "integer", "minimum": 18, "maximum": 99},
    "country": {"enum": ["US", "UK", "DE", "FR"]}
  }
}
```

---

### Scenario 3: Continuous Monitoring

**Goal:** Monitor app health in production

```bash
# Setup monitoring
observe observe metrics --port 9090 &

# Export to Prometheus
# prometheus.yml
scrape_configs:
  - job_name: 'mobile-tests'
    static_configs:
      - targets: ['localhost:9090']

# View metrics in Grafana
# - test_pass_rate
# - test_duration_seconds
# - healing_success_rate
# - ml_prediction_accuracy
```

---

### Scenario 4: Custom ML Model

**Goal:** Train model for domain-specific elements

```python
# collect_training_data.py
from framework.ml.data_collector import SelfLearningCollector

collector = SelfLearningCollector()

# Collect from your app
collector.start()
# ... interact with app ...
data = collector.get_collected_data()

# Label data
labeled_data = []
for element in data:
    print(f"Element: {element}")
    element_type = input("Type (Button/Input/Text): ")
    labeled_data.append({
        "features": element,
        "label": element_type
    })

# Save
save_json(labeled_data, "training_data.json")
```

```bash
# Train custom model
observe ml train \
  --data training_data.json \
  --output custom_model.pkl \
  --cv-folds 10

# Use custom model
observe config set ml.model_path custom_model.pkl
```

---

## Troubleshooting

### Issue 1: Tests Fail After App Update

**Symptom:** 30+ tests fail with "Element not found"

**Solution:**

```bash
# Option A: Auto-heal all
observe heal auto --test-results junit.xml --commit

# Option B: Dry-run first
observe heal auto --test-results junit.xml --dry-run
# Review changes
observe dashboard
# Apply if OK
observe heal auto --test-results junit.xml --commit

# Option C: Manual review
observe heal analyze junit.xml
observe dashboard  # Review in UI
# Approve/reject each change
```

---

### Issue 2: Slow Test Execution

**Symptom:** Test suite takes 2+ hours

**Solutions:**

```bash
# 1. Run in parallel
observe parallel run tests/ --workers 8

# 2. Use API mocking
observe mock record --session fast-flow
observe mock replay --session fast-flow

# 3. Smart test selection
observe business select-tests --changed-files
pytest $(observe business select-tests --changed-files)

# 4. Profile and optimize
observe load profile tests/ --cpu --memory
# Optimize hot spots
```

---

### Issue 3: Flaky Tests

**Symptom:** Tests pass/fail randomly

**Solutions:**

```bash
# Identify flaky tests
observe doctor check --detect-flaky

# Add retries
pytest tests/ --reruns 3 --reruns-delay 1

# Use explicit waits
# In code:
from selenium.webdriver.support.ui import WebDriverWait
wait = WebDriverWait(driver, 10)
element = wait.until(EC.element_to_be_clickable((By.ID, "button")))

# Add stability checks
observe selector validate --selector "..." --stability-check
```

---

### Issue 4: ML Model Poor Accuracy

**Symptom:** Model accuracy <80%

**Solutions:**

```bash
# 1. Collect more training data
observe ml collect-data --app com.myapp --samples 10000

# 2. Balance dataset
observe ml inspect-data training_data.json
# If imbalanced, sample more from minority classes

# 3. Try different algorithms
observe ml train --algorithm random-forest --n-estimators 200
observe ml train --algorithm gradient-boosting

# 4. Feature engineering
observe ml train --additional-features text_length,siblings_count
```

---

## Best Practices

### 1. Selector Strategy

❌ **Bad:**

```python
# Fragile - breaks on any ID change
driver.find_element_by_id("btn_login_submit_123")

# Breaks with i18n
driver.find_element_by_xpath("//button[text()='Login']")
```

✅ **Good:**

```python
# Robust selector with fallbacks
selector = (
    Selector.by_type("Button")
    .with_content_desc("login_button")  # Accessibility
    .or_text_fuzzy("Login", 0.8)        # Fuzzy text match
    .below(Selector.by_id("password"))  # Relationship
    .within(distance=100)               # Position
)
```

---

### 2. Test Organization

❌ **Bad:**

```
tests/
  test_everything.py  # 5000 lines, 200 tests
```

✅ **Good:**

```
tests/
  unit/
    test_login.py
    test_validation.py
  integration/
    test_checkout_flow.py
    test_profile_update.py
  e2e/
    test_complete_journey.py
  conftest.py  # Shared fixtures
```

---

### 3. Configuration Management

❌ **Bad:**

```python
# Hardcoded values
API_URL = "https://api.prod.com"
DEVICE_ID = "emulator-5554"
```

✅ **Good:**

```yaml
# config.yaml
environments:
  dev:
    api_url: "https://api.dev.com"
    device: "emulator-5554"
  prod:
    api_url: "https://api.prod.com"
    device: "real-device-001"

# Use:
observe config get environments.dev.api_url
```

---

### 4. CI/CD Integration

❌ **Bad:**

```yaml
# Run all tests always
- run: pytest tests/  # 2 hours
```

✅ **Good:**

```yaml
# Smart test selection
- run: |
    # Only affected tests
    CHANGED=$(git diff --name-only HEAD~1)
    TESTS=$(observe business select-tests --changed-files $CHANGED)
    pytest $TESTS
    
# Parallel execution
- run: observe parallel run tests/ --workers 10

# Auto-healing
- if: failure()
  run: observe heal auto --commit
```

---

### 5. Observability

❌ **Bad:**

```python
# No logging
def test_checkout():
    checkout()
    assert True
```

✅ **Good:**

```python
# Structured logging + metrics
import logging
from framework.observability import metrics

logger = logging.getLogger(__name__)

def test_checkout():
    logger.info("Starting checkout test", extra={"test_id": "T-123"})
    
    with metrics.timer("checkout_duration"):
        checkout()
    
    metrics.increment("tests_passed", tags=["suite:checkout"])
    logger.info("Checkout test passed")
```

---

## Next Steps

**Learn More:**

- [Architecture](docs/ARCHITECTURE.md) - System design
- [Technical Design](docs/TECHNICAL_DESIGN.md) - Implementation details
- [API Reference](docs/API_REFERENCE.md) - Complete API docs
- [Examples](examples/) - Real-world examples

**Get Help:**

- GitHub
  Issues: [github.com/VadimToptunov/mobile_test_recorder/issues](https://github.com/VadimToptunov/mobile_test_recorder/issues)
- Documentation: [Full docs](https://mobile-test-recorder.readthedocs.io)

**Contribute:**

- Fork the repo
- Create feature branch
- Submit PR

---

**Built with ❤️ and 🦀 by the Mobile Test Recorder team**
