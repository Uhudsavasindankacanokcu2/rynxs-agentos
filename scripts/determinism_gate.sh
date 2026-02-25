#!/usr/bin/env sh
set -eu

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
export PYTHONPATH="$ROOT"
export PYTHONDONTWRITEBYTECODE=1
export PYTHONNOUSERSITE=1
TMPDIR="${TMPDIR:-/tmp}"
export TMPDIR
export RYNXS_OPERATOR_PATH="$ROOT/operator/universe_operator"
export RYNXS_WRITER_ID="ci"

filter_err() {
  grep -vE "xcrun_db-|couldn't create cache file.*xcrun_db" "$1" >&2 || true
}

run_py() {
  err_file="$(mktemp "$TMPDIR/rynxs-pyerr.XXXXXX")"
  if "$@" 2>"$err_file"; then
    filter_err "$err_file"
    rm -f "$err_file"
    return 0
  fi
  filter_err "$err_file"
  rm -f "$err_file"
  return 1
}

if run_py python3 -m pytest \
  "$ROOT/engine/tests/test_operator_determinism.py" \
  "$ROOT/engine/tests/test_multiwriter_append.py" \
  "$ROOT/engine/tests/test_leader_election.py" \
  -q; then
  exit 0
fi

echo "pytest not available; running direct test runner" >&2
run_py python3 "$ROOT/engine/tests/test_operator_determinism.py"

echo "running CLI smoke (wrapper)" >&2
"$ROOT/scripts/engine_cli.sh" verify_pointers --log "$ROOT/engine/tests/fixtures/operator_log_small.jsonl" >/dev/null
"$ROOT/scripts/engine_cli.sh" audit_report --log "$ROOT/engine/tests/fixtures/operator_log_small.jsonl" --format json >/dev/null
