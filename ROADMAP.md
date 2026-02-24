# Rynxs Roadmap

## Now (v1.0.x hardening)
- gVisor/Kata RuntimeClass profiles for sandbox Jobs
- Gatekeeper/Kyverno policy templates (deny privileged, forbid hostPath, require runAsNonRoot)
- audit ingestion to immutable storage / SIEM (OTel Collector / Fluent Bit)

## Next (v1.1)
- Provider adapters + streaming (OpenAI/Anthropic/Gemini/local OAI-compat)
- WebSocket gateway + multi-channel inbox (Slack/Telegram/Web)
- Better “proof bundle” artifacts for releases (audit/outbox samples + commands)

## Phase 3 (Universe)
- Travel sessions (U1) + filtered memory bridge
- Stronger determinism controls (seed management + replay tooling)
- Zone evolution (community detection / re-sharding hysteresis)

## Links
- Repo: https://github.com/Uhudsavasindankacanokcu2/rynxs-agentos
- Release: https://github.com/Uhudsavasindankacanokcu2/rynxs-agentos/releases/tag/v1.0.0-beta.1
