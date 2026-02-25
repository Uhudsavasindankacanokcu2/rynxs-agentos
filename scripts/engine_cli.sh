#!/usr/bin/env sh
set -eu

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
export PYTHONPATH="$ROOT"
export PYTHONDONTWRITEBYTECODE=1
export PYTHONNOUSERSITE=1
export TMPDIR="${TMPDIR:-/tmp/rynxs-tmp-$$}"
mkdir -p "$TMPDIR"

if [ "$#" -lt 1 ]; then
  echo "usage: scripts/engine_cli.sh <command> [args...]" >&2
  exit 2
fi

cmd="$1"
shift

err_file="$(mktemp "$TMPDIR/rynxs-clierr.XXXXXX")"
filter_err() {
  grep -vE "xcrun_db-|couldn't create cache file.*xcrun_db" "$1" >&2 || true
}
if python3 -m "engine.cli.${cmd}" "$@" 2>"$err_file"; then
  filter_err "$err_file"
  rm -f "$err_file"
  exit 0
fi
filter_err "$err_file"
rm -f "$err_file"
exit 1
