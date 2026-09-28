# Codex project configuration

The project does not set a default model or reasoning effort. Select these per chat in Codex; specialized agent roles retain their explicitly configured profiles.

## Cost-aware delegation

The concise operating policy is in [`AGENTS.md`](../AGENTS.md). It keeps the chat model user-selected, defaults to one scoped Luna/low worker, caps parallel independent work at three, and preserves primary ownership of critical decisions and integration.

## Agent roles

All custom roles use Luna/low except the explicit `implementer_medium` profile (Luna/medium). Their distinct instructions and sandbox boundaries still apply: `explorer` maps repository areas read-only; `researcher` checks primary sources and licenses; `test_engineer` works in tests and fixtures; `mathematician` analyzes invariants and numerical risks; `geometry_reviewer` reviews geometry and topology; `verifier_reviewer` audits independence and common-mode risks. Use only roles that materially help the task. A solver and its independent verifier should not normally be assigned to the same implementation task.

The `implementer` role is for bounded execution with explicit file ownership. It preserves concurrent edits, runs the requested checks, does not silently change architecture, and does not spawn child agents.

Configured role model and effort are preferences, not a guarantee of credits or availability. The explicit `implementer_medium` profile is for coordinated work that needs more judgment; it does not trigger automatically. Already-loaded profiles may retain old settings until reloaded. Do not change global, cache, compaction, credential, or security settings.

Use [`docs/AGENT_WORK_ORDER.md`](../docs/AGENT_WORK_ORDER.md) for substantive delegated work and [`docs/AGENT_USAGE_RECORD.example.json`](../docs/AGENT_USAGE_RECORD.example.json) as an optional measurement template. Do not force templates on simple conversation. Usage values must come from runtime metadata; unknowns remain null. There is no automatic billing integration or guaranteed saving.

Project configuration intentionally does not set provider, credentials, telemetry, or notification settings. Those remain machine/user concerns. No external MCP service is required. A current-library documentation service such as Context7 may be added later only when a concrete dependency makes it useful; workspace filesystem access is not duplicated through MCP.

The [`hooks/README.md`](hooks/README.md) file defines the future lightweight completion-check boundary. It is documentation, not an enabled hook.
