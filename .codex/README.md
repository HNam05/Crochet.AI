# Codex project configuration

The project default is GPT-5.6 Terra with medium reasoning. This balances implementation quality and credit use for ordinary milestone work.

## Escalation policy

- Use `explorer` (Luna/low, read-only) for narrow repository mapping.
- Use `researcher` (Terra/medium, read-only) for primary-source research and license checks.
- Use `test_engineer` (Terra/high) when adversarial, stateful, or property tests materially improve confidence.
- Use `mathematician` (Sol/high, read-only) only for difficult solver formulation, formal invariants, counterexamples, or numerical analysis.
- Use `geometry_reviewer` (Sol/high, read-only) for risky geometry/topology/stability review.
- Use `verifier_reviewer` (Sol/high, read-only) for critical independence and common-mode audits.

Do not invoke every agent on every task. Routine contained changes should stay with the primary agent. A solver and its independent verifier should not normally be delegated to the same implementation task.

Project configuration intentionally does not set provider, credentials, telemetry, or notification settings. Those remain machine/user concerns. No external MCP service is required. A current-library documentation service such as Context7 may be added later only when a concrete dependency makes it useful; workspace filesystem access is not duplicated through MCP.

The [`hooks/README.md`](hooks/README.md) file defines the future lightweight completion-check boundary. It is documentation, not an enabled hook.
