# Release Checklist (Deterministic Engine)

## Determinism & Replay
- [ ] Decision layer remains pure (no I/O, no randomness, no system time)
- [ ] No nondeterministic data added to events or feedback
- [ ] Canonical serialization used for event payloads and action params
- [ ] Action ordering deterministic and stable
- [ ] Replay equality tested (live vs replay decisions)

## Event Translation
- [ ] K8s nondeterministic fields stripped
- [ ] K8s defaulting equivalence covered (implicit vs explicit defaults)
- [ ] Spec normalization updated if CRD defaults changed

## Event Log Integrity
- [ ] Hash chain integrity preserved
- [ ] Single-writer append (lock) verified
- [ ] Checkpoint verification unchanged or updated with tests

## Tests
- [ ] Determinism tests run
- [ ] Replay tests run
- [ ] Integrity tests run
- [ ] Relevant unit tests updated
- [ ] Determinism gate run: `scripts/determinism_gate.sh`

## Release Hygiene
- [ ] Release notes written (use `docs/RELEASE_NOTES_TEMPLATE.md`)
- [ ] Changelog updated if required
- [ ] Backwards compatibility assessed
