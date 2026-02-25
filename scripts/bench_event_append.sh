#!/usr/bin/env sh
set -eu

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
export PYTHONPATH="$ROOT"

N="${N:-100000}"
LOG_DIR="${LOG_DIR:-$ROOT/.bench}"
LOG_PATH="${LOG_PATH:-$LOG_DIR/event.log}"

mkdir -p "$LOG_DIR"
rm -f "$LOG_PATH"

python3 - <<'PY'
import os
import time

from engine.core.events import Event
from engine.log.file_store import FileEventStore

n = int(os.getenv("N", "100000"))
log_path = os.getenv("LOG_PATH")

store = FileEventStore(log_path)

start = time.perf_counter()
for i in range(n):
    store.append(Event(type="BENCH", aggregate_id="A", ts=i))
elapsed = time.perf_counter() - start

eps = n / elapsed if elapsed > 0 else 0
print(f"append: {n} events in {elapsed:.4f}s ({eps:.2f} events/s)")
print(f"log_path: {log_path}")
PY
