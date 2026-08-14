#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
ruff check app tests
ruff format --check app tests
mypy
pytest tests/unit tests/security
echo "Wave 1 local checks passed."
