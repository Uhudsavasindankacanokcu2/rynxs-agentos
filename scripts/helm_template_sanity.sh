#!/usr/bin/env sh
set -eu

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
VALUES_FILE="${1:-}"

if [ -z "$VALUES_FILE" ]; then
  echo "usage: $0 <values.yaml>" >&2
  exit 2
fi

if ! command -v helm >/dev/null 2>&1; then
  echo "helm not found" >&2
  exit 2
fi

OUT="$(mktemp /tmp/rynxs-helm.XXXXXX.yaml)"
helm template rynxs "$ROOT/helm/rynxs" -f "$VALUES_FILE" > "$OUT"

grep -q "kind: StatefulSet" "$OUT" || {
  echo "missing StatefulSet in rendered output" >&2
  exit 1
}

grep -q "kind: Service" "$OUT" || {
  echo "missing Service in rendered output" >&2
  exit 1
}

grep -q "RYNXS_WRITER_ID" "$OUT" || {
  echo "missing RYNXS_WRITER_ID env in rendered output" >&2
  exit 1
}

grep -q "RYNXS_HASH_VERSION" "$OUT" || {
  echo "missing RYNXS_HASH_VERSION env in rendered output" >&2
  exit 1
}

echo "helm template sanity ok"
