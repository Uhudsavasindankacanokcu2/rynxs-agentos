# Rynxs Security Architecture

Rynxs follows a multi-layered security model to ensure that providing an AI agent with "computer access" does not compromise the host cluster or sensitive data.

## 1. Sandbox Isolation (Horizontal Security)
Instead of executing tools directly in the agent's main runtime pod, high-risk tools like `shell` are spawned as independent Kubernetes Jobs.
- **Transient Nature**: Jobs are run-to-completion and automatically cleaned up via `ttlSecondsAfterFinished`.
- **Privilege Limits**: Sub-processes inherit strict security contexts (`allowPrivilegeEscalation: false`, Capability Drop).
- **Filesystem Boundaries**: Sandboxes mount only the necessary sub-paths of the workspace PVC, never the root.

## 2. Network Isolation (Vertical Security)
Rynxs enforces a "Deny-by-Default" egress policy for all agents and sandboxes.
- **NetworkPolicy**: Standard Kubernetes NetworkPolicies are used to isolate pods.
- **Allowlist Only**: Only approved endpoints (e.g., Inference API, DNS, specific Volume backends) are reachable.
- **Note**: This requires a CNI (like Cilium, Calico, or Antrea) that supports NetworkPolicy enforcement.

## 3. Policy Enforcement (Governance)
Behavioral constraints are enforced at the control plane level:
- **Rate Limiting**: Throttling tool calls to prevent resource exhaustion.
- **Tool Allowlisting**: Each agent spec defines exactly which tools it is authorized to call.
- **Universe Constraints**: The optional Universe model enforces macro-level rules such as mandatory sleep cycles and health-based snapshots.

## 4. Audit and Forensics
The `/workspace/audit.jsonl` provides an immutable-by-design (at the data plane level) trace of all actions.
- **Cryptographic Proof**: Parameters and results are hashed (SHA-256) to allow verification of what was executed without leaking secrets in the logs.
- **Sandbox Job Linkage**: Every sandbox tool call records the specific job name, allowing for retrospective log analysis of the sandbox output.

---

## Deployment Baseline (Hardening)
Production deployments should follow the [Pod Security Standards](https://kubernetes.io/docs/concepts/security/pod-security-standards/).

Recommended Namespace Labels:
```yaml
pod-security.kubernetes.io/enforce: restricted
pod-security.kubernetes.io/enforce-version: v1.31
```

Required SecurityContext:
```yaml
securityContext:
  runAsNonRoot: true
  seccompProfile:
    type: RuntimeDefault
  allowPrivilegeEscalation: false
  capabilities:
    drop: ["ALL"]
```
