#!/usr/bin/env sh
set -eu

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
LOG="$ROOT/engine/tests/fixtures/operator_log_small.jsonl"
export PYTHONDONTWRITEBYTECODE=1
export PYTHONNOUSERSITE=1
export TMPDIR="${TMPDIR:-/tmp/rynxs-tmp-$$}"
mkdir -p "$TMPDIR"

filter_err() {
  grep -vE "xcrun_db-|couldn't create cache file.*xcrun_db" "$1" >&2 || true
}

run_py() {
  err_file="$(mktemp "$TMPDIR/rynxs-smokeerr.XXXXXX")"
  if "$@" 2>"$err_file"; then
    filter_err "$err_file"
    rm -f "$err_file"
    return 0
  fi
  filter_err "$err_file"
  rm -f "$err_file"
  return 1
}

tmp_out="$(mktemp "$TMPDIR/rynxs-smokeout.XXXXXX")"
"$ROOT/scripts/engine_cli.sh" inspect --log "$LOG" > "$tmp_out"
OUT_FILE="$tmp_out" run_py python3 - <<'PY'
import json, os
with open(os.environ["OUT_FILE"], "r", encoding="utf-8") as f:
    data = json.load(f)
assert "agents" in data and "applied_events" in data
print("inspect ok")
PY
rm -f "$tmp_out"

tmp_out="$(mktemp "$TMPDIR/rynxs-smokeout.XXXXXX")"
"$ROOT/scripts/engine_cli.sh" audit_report --log "$LOG" --format json > "$tmp_out"
OUT_FILE="$tmp_out" run_py python3 - <<'PY'
import json, os
with open(os.environ["OUT_FILE"], "r", encoding="utf-8") as f:
    data = json.load(f)
assert "hash_chain" in data and "pointers" in data and "decisions" in data
print("audit_report ok")
PY
rm -f "$tmp_out"
