# Agent work order

Use this brief for substantive delegated work. Keep it concise; do not require it for simple conversational answers.

```text
Objective:
Relevant context paths and contracts:
Owned files; baseline dirty edits to preserve:
Inputs and invariants:
Non-goals:
Acceptance commands:
Risk and required primary review:
Model and effort:
Stop after two unsuccessful repairs of the same failure; report evidence and next hypothesis.

Return: changed files, checks and exact outcomes, failures/repair attempts, and remaining uncertainty.
```

Bundle a coherent implementation with its targeted tests. Do not assign overlapping ownership or split work by file. The primary agent retains architecture, critical correctness decisions, integration, and final review.

## Usage measurement

If actual runtime metadata is available, record only measured values in ignored `artifacts/agent-costs/` and report them with the task. Set `measurement_scope` to `worker`, `primary`, or `aggregate` so a worker's usage is not mistaken for the whole task. Leave unavailable token and credit values, and their source, null; do not infer credits from API prices. Never add reasoning or cached tokens to input/output totals because that can double-count. Do not store prompts, credentials, or other secrets. This is a manual record, not billing integration.
