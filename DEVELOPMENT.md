# Development Setup Guide

This guide will help you set up the development environment for Mobile Test Recorder.

## Prerequisites

- Python 3.13 or higher
- Rust 1.70+ (optional, for performance improvements)
- Node.js 18+ (for demo apps)
- Android SDK (for Android testing)
- Xcode (for iOS testing, macOS only)
- JDK 17 (for JetBrains plugin development)

## Quick Setup

### 1. Clone and Setup Python Environment

```bash
# Clone repository
git clone https://github.com/vadimtoptunov/mobile_test_recorder.git
cd mobile_test_recorder

# Create virtual environment
python3.13 -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate

# Install dependencies
pip install --upgrade pip
pip install -r requirements.txt

# Install in development mode
pip install -e .

# Verify installation
observe info
observe health
```

### 2. Configure Environment Variables

```bash
# Copy example environment file
cp .env.example .env

# Edit .env with your settings
nano .env  # or your preferred editor
```

**Important Environment Variables:**

- `TEST_USER_PASSWORD` - Password for generated test users
- `APPIUM_SERVER_URL` - Appium server URL (default: http://localhost:4723)
- `LOG_LEVEL` - Logging level (DEBUG, INFO, WARNING, ERROR)

### 3. Build Rust Core (Optional but Recommended)

For 16-90x performance improvement:

```bash
# Install Rust
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh

# Install maturin
pip install maturin

# Build Rust core
cd rust_core
maturin develop --release
cd ..

# Verify Rust core is loaded
python -c "from rust_core import RustCorrelator; print('Rust core available!')"
```

### 4. Setup Pre-commit Hooks

```bash
# Install pre-commit
pip install pre-commit

# Install hooks
pre-commit install

# Test hooks
pre-commit run --all-files
```

### 5. Run Tests

```bash
# Run all tests
pytest tests/ -v

# Run with coverage
pytest tests/ --cov=framework --cov-report=html

# Run specific test categories
pytest tests/ -k "test_selector"
pytest tests/ -k "test_security"

# Open coverage report
open htmlcov/index.html  # macOS
xdg-open htmlcov/index.html  # Linux
start htmlcov/index.html  # Windows
```

## Development Workflow

### Running the CLI in Development Mode

```bash
# All commands work after pip install -e .
observe --help
observe record --help
observe generate --help

# Or run directly
python -m framework.cli.main --help
```

### Code Quality Checks

```bash
# Format code
black framework tests

# Lint
flake8 framework

# Type check
mypy framework --ignore-missing-imports

# All checks at once
pre-commit run --all-files
```

### Testing Workflow

1. **Write tests** in `tests/` directory
2. **Run tests** with `pytest`
3. **Check coverage** - aim for >80%
4. **Fix any failures** before committing

### Debugging

```bash
# Enable debug logging
export DEBUG_MODE=true
export LOG_LEVEL=DEBUG

# Run with verbose output
observe record --device emulator-5554 --verbose

# Use Python debugger
python -m pdb -m framework.cli.main record --device emulator-5554
```

## JetBrains Plugin Development

### Setup

```bash
cd jetbrains-plugin

# Build plugin
./gradlew buildPlugin

# Run IDE with plugin
./gradlew runIde

# Verify plugin
./gradlew verifyPlugin
```

### Testing Plugin

```bash
# Run plugin tests
./gradlew test

# Build distribution
./gradlew buildPlugin

# Output: build/distributions/mobile-test-recorder-*.zip
```

## Demo App Setup

### Android Demo App

```bash
cd demo-app/android

# Build app
./gradlew assembleDebug

# Install on device
adb install app/build/outputs/apk/debug/app-debug.apk

# Run app
adb shell am start -n com.findemo/.MainActivity
```

### iOS Demo App

```bash
cd demo-app/ios

# Open in Xcode
open FinDemo.xcodeproj

# Or build from command line
xcodebuild -project FinDemo.xcodeproj -scheme FinDemo -configuration Debug
```

### Mock Backend

```bash
cd demo-app/mock-backend

# Install dependencies
pip install fastapi uvicorn sqlalchemy

# Run server
python main.py

# Server runs on http://localhost:8000
# API docs: http://localhost:8000/docs
```

## Common Issues & Solutions

### Issue: Import errors when running CLI

```bash
# Solution: Reinstall in development mode
pip install -e .
```

### Issue: Rust core not loading

```bash
# Solution: Rebuild Rust core
cd rust_core
maturin develop --release
cd ..
```

### Issue: Tests failing

```bash
# Solution: Update dependencies
pip install --upgrade -r requirements.txt

# Clear pytest cache
rm -rf .pytest_cache

# Run tests with verbose output
pytest tests/ -vv
```

### Issue: Pre-commit hooks failing

```bash
# Skip hooks temporarily (NOT recommended)
git commit --no-verify

# Update hooks
pre-commit autoupdate

# Clear hook cache
pre-commit clean
```

## Performance Optimization

### Enable Rust Core

For best performance, always use Rust core:

```bash
cd rust_core
maturin develop --release
```

Expected speedup:

- Event correlation: **16-90x faster**
- AST analysis: **20-50x faster**
- Business logic detection: **10-30x faster**

### Profile Performance

```bash
# Profile Python code
python -m cProfile -o profile.stats -m framework.cli.main record --device emulator-5554

# View results
python -m pstats profile.stats
# Type 'sort cumulative' then 'stats 20'

# Profile with line_profiler
pip install line_profiler
kernprof -l -v script.py
```

## Contributing

### Before Submitting PR

1. **Run all tests**: `pytest tests/ -v`
2. **Check coverage**: `pytest --cov=framework`
3. **Run linters**: `pre-commit run --all-files`
4. **Update documentation** if needed
5. **Add tests** for new features
6. **Write clear commit messages**

### Commit Message Format

```
type(scope): brief description

Longer description if needed.

Fixes #123
```

Types: `feat`, `fix`, `docs`, `style`, `refactor`, `test`, `chore`

## Documentation

### Generate API Documentation

```bash
# Install dependencies
pip install sphinx sphinx-rtd-theme

# Generate docs
cd docs
make html

# View docs
open _build/html/index.html
```

### Update README

When adding features:

1. Update `README.md` with usage examples
2. Update `QUICKSTART.md` if workflow changes
3. Add entry to `CHANGELOG.md`

## Release Process

### Version Bump

```bash
# Update version in pyproject.toml
# Update version in framework/__init__.py
# Update version in jetbrains-plugin/build.gradle.kts

# Commit changes
git add .
git commit -m "chore: bump version to X.Y.Z"

# Create tag
git tag -a vX.Y.Z -m "Release vX.Y.Z"

# Push
git push origin main --tags
```

### Publishing

GitHub Actions automatically publishes on tag push:

- PyPI package
- JetBrains plugin
- GitHub release

## Need Help?

- **Documentation**: [docs/](docs/)
- **Issues**: [GitHub Issues](https://github.com/vadimtoptunov/mobile_test_recorder/issues)
- **Discussions**: [GitHub Discussions](https://github.com/vadimtoptunov/mobile_test_recorder/discussions)
- **Email**: vtoptunov88@gmail.com

## License

MIT License - see [LICENSE](LICENSE) file for details.
