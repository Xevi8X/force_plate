#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

if command -v python3 >/dev/null 2>&1; then
    exec python3 start.py
fi

echo "Error: python3 is not installed or not in PATH."
exit 1
