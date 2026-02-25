#!/usr/bin/env sh
set -eu

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
python3 -m pytest "$ROOT/engine/tests/test_operator_determinism.py" -q
