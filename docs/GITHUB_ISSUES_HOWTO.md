# How to Create GitHub Issues from Templates

This document provides copy-paste instructions for creating GitHub issues from the milestone templates.

## Issue Creation Steps

1. Go to: https://github.com/Uhudsavasindankacanokcu2/rynxs-agentos/issues/new
2. Copy the content from the corresponding issue template file
3. Paste into GitHub issue body
4. Add labels as specified at the end of each template
5. Assign to milestone (create "Deterministic Engine" milestone if needed)

## Issue Templates Location

All issue templates are in: `docs/issues/`

- `M1-deterministic-core.md` - Priority: Critical
- `M2-event-store.md` - Priority: Critical
- `M3-hash-chain-integrity.md` - Priority: Critical
- `M4-checkpoint-system.md` - Priority: High
- `M5-replay-system.md` - Priority: Critical

## Suggested Labels

Create these labels in GitHub repository if they don't exist:

- `milestone:M1`, `milestone:M2`, `milestone:M3`, `milestone:M4`, `milestone:M5`
- `priority:critical`, `priority:high`
- `type:core`, `type:storage`, `type:security`
- `deterministic-engine`

## Issue Titles

Use these exact titles when creating issues:

1. **M1: Deterministic Core**
2. **M2: Append-Only EventStore**
3. **M3: Hash-Chain Integrity**
4. **M4: Checkpoint System**
5. **M5: Replay System**

## Dependencies

When creating issues, note dependencies in GitHub:

- M2 depends on M1
- M3 depends on M2
- M4 depends on M3
- M5 depends on M1, M2, M3

Use "Depends on #N" in issue description to link dependencies.

## Milestone

Create GitHub milestone:

- Name: **Deterministic Engine v0.1**
- Due date: 8 weeks from start
- Description: Event-sourced, deterministic execution engine for replayable, verifiable, audit-ready AI workloads

## Project Board (Optional)

Create GitHub project board with columns:

- **Backlog** (M1-M5)
- **In Progress** (active work)
- **Review** (PR submitted)
- **Done** (merged)

## Quick Create Script

```bash
# Optional: Use GitHub CLI to create issues programmatically

gh issue create \
  --title "M1: Deterministic Core" \
  --body-file docs/issues/M1-deterministic-core.md \
  --label "milestone:M1,priority:critical,type:core,deterministic-engine"

gh issue create \
  --title "M2: Append-Only EventStore" \
  --body-file docs/issues/M2-event-store.md \
  --label "milestone:M2,priority:critical,type:storage,deterministic-engine"

gh issue create \
  --title "M3: Hash-Chain Integrity" \
  --body-file docs/issues/M3-hash-chain-integrity.md \
  --label "milestone:M3,priority:critical,type:security,deterministic-engine"

gh issue create \
  --title "M4: Checkpoint System" \
  --body-file docs/issues/M4-checkpoint-system.md \
  --label "milestone:M4,priority:high,type:security,deterministic-engine"

gh issue create \
  --title "M5: Replay System" \
  --body-file docs/issues/M5-replay-system.md \
  --label "milestone:M5,priority:critical,type:core,deterministic-engine"
```

## Next Steps

After creating issues:

1. Start with M1 (blocks everything else)
2. Create feature branch: `git checkout -b feature/m1-deterministic-core`
3. Implement according to acceptance criteria
4. Write tests (TDD approach recommended)
5. Create PR, reference issue number: "Closes #N"
6. Review, merge, move to M2
