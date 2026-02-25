# Release Checklist (Deterministic Engine)

## Determinism & Replay
- [ ] Decision layer remains pure (no I/O, no randomness, no system time)
- [ ] No nondeterministic data added to events or feedback
- [ ] Canonical serialization used for event payloads and action params
- [ ] Action ordering deterministic and stable
- [ ] Replay equality tested (live vs replay decisions)
- [ ] ActionsDecided trigger pointers verify against hash chain

## Event Translation
- [ ] K8s nondeterministic fields stripped
- [ ] K8s defaulting equivalence covered (implicit vs explicit defaults)
- [ ] Spec normalization updated if CRD defaults changed

## Event Log Integrity
- [ ] Hash chain integrity preserved
- [ ] CAS append conflict behavior verified (no write on conflict)
- [ ] Segmented log boundary verify passes (cross-segment pointers valid)
- [ ] Checkpoint verification unchanged or updated with tests

## Hash Versioning
- [ ] Default remains v1 unless explicitly opting into v2
- [ ] v1 fixtures pass: `RYNXS_FIXTURE_SET=v1 scripts/determinism_gate.sh`
- [ ] v2 fixtures pass: `RYNXS_FIXTURE_SET=v2 RYNXS_HASH_VERSION=v2 scripts/determinism_gate.sh`
- [ ] writer_id policy confirmed (CI uses `RYNXS_WRITER_ID=ci`)

## CI Gates
- [ ] Required checks enforced: `determinism (v1)` and `determinism (v2)`
- [ ] Smoke CLI passes: `scripts/smoke_cli.sh`
- [ ] Helm template sanity passes: `scripts/helm_template_sanity.sh docs/examples/values-staging.yaml`

## HA / Leader Election
- [ ] Leader election enabled in prod values
- [ ] Non-leader reconciles are skipped (no append, no execute)
- [ ] Failover test: delete leader pod, new leader elected <30s, chain remains valid

## Audit / Proof
- [ ] Pointer verify passes on staging log: `scripts/engine_cli.sh verify_pointers --log <path>`
- [ ] Proof export works: `scripts/engine_cli.sh audit_report --log <path> --proof --format json`

## Release Hygiene
- [ ] Release notes written (use `docs/RELEASE_NOTES_TEMPLATE.md`)
- [ ] Changelog updated if required
- [ ] Backwards compatibility assessed

## Rollout (Staging → Canary → Prod)
- [ ] Staging v2 opt-in deploy validated (24h observation)
- [ ] Canary v2 opt-in validated (7 days, no pointer mismatch)
- [ ] Prod rollout completed with monitoring in place
- [ ] Rollback plan validated (set `operator.hashVersion: ""`)
