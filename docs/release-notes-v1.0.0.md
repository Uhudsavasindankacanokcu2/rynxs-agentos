# v1.0.0-beta.1 - Proof-Ready Beta

This beta establishes the first proof milestone for Universe AgentOS: AI agents can run commands in isolated computers on Kubernetes, under enforceable policy, with auditable traces.

## Highlights
- **Kubernetes-native Operator**
  - Agent CRD manages ServiceAccount, Role/Binding, ConfigMap, PVC, and Deployment.
- **Sandbox execution**
  - `sandbox.shell` runs as hardened Kubernetes Jobs.
  - Results are returned to the agent and logged.
  - Support for gvisor/kata via runtimeClassName.
- **Memory invariants**
  - RAM: /workspace/state/ram.json (volatile; wiped on death).
  - Volume: /workspace/state/volume.json (persistent; survives respawn).
  - Bucket: /workspace/state/bucket/snap-<ts>.json (atomic deep sleep snapshots).
- **Audit trail**
  - /workspace/audit.jsonl tracks events: BIRTH, STATE_DRIFT, LIGHT_SLEEP, DEEP_SLEEP, LUCK_*, DEATH, RESPAWN.
  - Hashed arguments and output (SHA-256) for audit integrity.

## Notes
- This is a beta release. Security recommendations are documented in docs/security.md.
- Future work focuses on NetworkPolicies, Gatekeeper templates, and multi-channel gateways.

## Docker Images
- universe-operator:v1.0.0-beta.1
- universe-agent-runtime:v1.0.0-beta.1
