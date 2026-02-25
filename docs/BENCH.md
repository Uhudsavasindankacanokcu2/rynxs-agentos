# Benchmark Harness

This is a lightweight benchmark harness for paper-grade and product-grade reporting.

## Append Throughput

```
N=100000 LOG_DIR=/tmp/rynxs-bench ./scripts/bench_event_append.sh
```

Example output:
```
append: 100000 events in 1.2345s (80959.23 events/s)
log_path: /tmp/rynxs-bench/event.log
```

## Replay Throughput + Checkpoint Speedup (Simulated)

```
N=200000 LOG_DIR=/tmp/rynxs-bench ./scripts/bench_replay.sh
```

Example output:
```
replay-full: 200000 events in 2.3456s (85261.10 events/s)
replay-from-checkpoint: 100000 events in 1.1011s (90817.32 events/s)
log_path: /tmp/rynxs-bench/replay.log
```

## Notes
- These numbers are machine-dependent; include CPU/OS details in any report.
- `replay-from-checkpoint` simulates a mid-log checkpoint by replaying only the tail.
