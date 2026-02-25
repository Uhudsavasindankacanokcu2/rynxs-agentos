#!/usr/bin/env sh
set -eu

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
export PYTHONPATH="$ROOT"

if python3 -m pytest "$ROOT/engine/tests/test_operator_determinism.py" -q; then
  exit 0
fi

echo "pytest not available; running direct test runner" >&2
python3 "$ROOT/engine/tests/test_operator_determinism.py"
