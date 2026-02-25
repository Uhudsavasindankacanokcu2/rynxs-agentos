#!/usr/bin/env sh
set -eu

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
export PYTHONPATH="$ROOT"
export PYTHONDONTWRITEBYTECODE=1
export PYTHONNOUSERSITE=1
TMPDIR="${TMPDIR:-/tmp}"
export TMPDIR

run_py() {
  err_file="$(mktemp "$TMPDIR/rynxs-pyerr.XXXXXX")"
  if "$@" 2>"$err_file"; then
    grep -v "xcrun_db" "$err_file" >&2 || true
    rm -f "$err_file"
    return 0
  fi
  grep -v "xcrun_db" "$err_file" >&2 || true
  rm -f "$err_file"
  return 1
}

if run_py python3 -m pytest "$ROOT/engine/tests/test_operator_determinism.py" -q; then
  exit 0
fi

echo "pytest not available; running direct test runner" >&2
run_py python3 "$ROOT/engine/tests/test_operator_determinism.py"
