#!/usr/bin/env sh
set -eu

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
export PYTHONPATH="$ROOT"

N="${N:-200000}"
LOG_DIR="${LOG_DIR:-$ROOT/.bench}"
LOG_PATH="${LOG_PATH:-$LOG_DIR/replay.log}"

mkdir -p "$LOG_DIR"
rm -f "$LOG_PATH"

python3 - <<'PY'
import os
import time

from engine.core.events import Event
from engine.core.reducer import Reducer
from engine.log.file_store import FileEventStore
from engine.replay.runner import replay

n = int(os.getenv("N", "200000"))
log_path = os.getenv("LOG_PATH")

store = FileEventStore(log_path)

# Build log
for i in range(n):
    store.append(Event(type="INC", aggregate_id="A", ts=i, payload={"inc": 1}))

# Reducer
r = Reducer()

def inc(cur, ev):
    cur = cur or {"n": 0}
    return {"n": cur["n"] + ev.payload["inc"]}

r.register("INC", inc)

# Full replay benchmark
start = time.perf_counter()
result = replay(store, r)
elapsed_full = time.perf_counter() - start

# Simulated checkpoint replay (from midpoint)
mid = n // 2
start = time.perf_counter()
mid_state = replay(store, r, to_seq=mid).state
tail_applied = 0
for ev in store.read(from_seq=mid + 1):
    mid_state = r.apply(mid_state, ev)
    tail_applied += 1
elapsed_tail = time.perf_counter() - start

eps_full = result.applied / elapsed_full if elapsed_full > 0 else 0
eps_tail = tail_applied / elapsed_tail if elapsed_tail > 0 else 0

print(f"replay-full: {result.applied} events in {elapsed_full:.4f}s ({eps_full:.2f} events/s)")
print(f"replay-from-checkpoint: {tail_applied} events in {elapsed_tail:.4f}s ({eps_tail:.2f} events/s)")
print(f"log_path: {log_path}")
PY
