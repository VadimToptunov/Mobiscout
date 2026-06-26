# Contributing to Mobile Observe & Test Framework

Thank you for your interest in contributing! 🎉

## Getting Started

1. **Fork the repository**
2. **Clone your fork**:
   ```bash
   git clone https://github.com/your-username/mobile_test_recorder.git
   cd mobile_test_recorder
   ```
3. **Create a virtual environment**:
   ```bash
   python3.13 -m venv .venv
   source .venv/bin/activate
   ```
4. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   pip install -e .
   ```

## Development Workflow

1. **Create a feature branch**:
   ```bash
   git checkout -b feature/your-feature-name
   ```

2. **Make your changes**

3. **Test your changes**:
   ```bash
   pytest tests/ -v
   ```

4. **Commit with clear messages**:
   ```bash
   git commit -m "Add: feature description"
   ```

5. **Push to your fork**:
   ```bash
   git push origin feature/your-feature-name
   ```

6. **Open a Pull Request**

## Code Style

- **Python**: Follow PEP 8
- **Kotlin**: Follow Kotlin coding conventions
- **Swift**: Follow Swift API Design Guidelines
- Use meaningful variable names
- Add docstrings to functions and classes
- Keep functions small and focused

## Commit Message Format

```
Type: Brief description

Detailed explanation (optional)

Fixes #issue_number (if applicable)
```

**Types:**

- `Add` - New feature
- `Fix` - Bug fix
- `Update` - Update existing feature
- `Refactor` - Code refactoring
- `Docs` - Documentation changes
- `Test` - Adding or updating tests

## Testing

- Write tests for new features
- Ensure all tests pass before submitting PR
- Maintain or improve code coverage

## Documentation

- Update `USER_GUIDE.md` for user-facing changes
- Update docstrings for API changes
- Add examples for new features

## Questions?

- Check [USER_GUIDE.md](USER_GUIDE.md) first
- Search existing issues
- Open a new issue if needed

## Code of Conduct

Be respectful, constructive, and professional.

Thank you for contributing! 🚀

