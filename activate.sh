#!/bin/bash

# Activation script for Mobile Test Recorder virtual environment

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_PATH="$PROJECT_ROOT/.venv"

if [ ! -d "$VENV_PATH" ]; then
    echo " Virtual environment not found!"
    echo "Run: python3 -m venv .venv && pip install -r requirements.txt"
    exit 1
fi

# Activate virtual environment
source "$VENV_PATH/bin/activate"

# Activate local Rust toolchain
export RUSTUP_HOME="$VENV_PATH/rustup"
export CARGO_HOME="$VENV_PATH/cargo"
export PATH="$CARGO_HOME/bin:$PATH"

echo "✅ Virtual environment activated!"
RUST_VERSION=$(rustc --version 2>/dev/null | awk '{print $2}' || echo 'not found')
echo "🦀 Rust toolchain activated (version: $RUST_VERSION)"
echo ""
echo " Available commands:"
echo "  mobiscout --help              # Show CLI help"
echo "  mobiscout info                # Show framework info"
echo "  mobiscout init                # Initialize new project"
echo ""
echo "🧪 Run tests:"
echo "  pytest                      # Run all tests"
echo "  pytest -v                   # Verbose mode"
echo ""
echo " Code quality:"
echo "  black .                     # Format code"
echo "  flake8 .                    # Lint code"
echo "  mypy framework              # Type check"
echo ""
echo " To deactivate: type 'deactivate'"
echo ""

