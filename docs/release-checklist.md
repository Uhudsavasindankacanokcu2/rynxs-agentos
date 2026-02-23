# Release checklist (beta)

- [ ] sandbox.shell runs as K8s Job and returns stdout
- [ ] audit.jsonl is written for allow/deny cases
- [ ] deny-all egress NetworkPolicy applied for agent + sandbox
- [ ] README demo section verified on kind/minikube
- [ ] GitHub Actions build+push on tag works
- [ ] Tag release: v1.0.0-beta.1
- [ ] Docker Hub images exist:
  - universe-operator:v1.0.0-beta.1
  - universe-agent-runtime:v1.0.0-beta.1
