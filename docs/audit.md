# Audit Events

Each tool invocation writes a JSON line to `/workspace/audit.jsonl`.

## Fields
- `t`: unix timestamp (float)
- `agent`: agent name
- `ns`: namespace
- `tool`: tool name
- `allowed`: boolean
- `reason`: string (if denied)
- `args_sha256`: hash of tool args (never store secrets raw)
- `sandbox_job`: job name (if sandbox)
- `stdout_sha256`: hash of stdout (if any)
- `stdout_preview`: first 200 chars (optional)
