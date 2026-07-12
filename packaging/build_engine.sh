#!/usr/bin/env bash
# Build the standalone Observe engine binary for the current OS/arch (variant C).
# Requires: pip install pyinstaller. Output: dist/observe-engine[.exe].
set -euo pipefail
cd "$(dirname "$0")/.."
pyinstaller packaging/observe-engine.spec --noconfirm --clean
echo "Built: dist/observe-engine (run 'echo <json-rpc> | dist/observe-engine' to smoke-test)"
