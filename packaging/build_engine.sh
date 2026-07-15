#!/usr/bin/env bash
# Build the standalone Mobiscout engine binary for the current OS/arch (variant C).
# Requires: pip install pyinstaller. Output: dist/mobiscout-engine[.exe].
set -euo pipefail
cd "$(dirname "$0")/.."
pyinstaller packaging/mobiscout-engine.spec --noconfirm --clean
echo "Built: dist/mobiscout-engine (run 'echo <json-rpc> | dist/mobiscout-engine' to smoke-test)"
