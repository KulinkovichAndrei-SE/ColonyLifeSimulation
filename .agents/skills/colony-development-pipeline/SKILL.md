---
name: colony-development-pipeline
description: Orchestrate non-trivial colony-simulation features from evidence-based specification through planning, bounded implementation, deterministic testing, simulation evaluation, and an independent quality gate. Use for roadmap increments, cross-module changes, architectural refactors, or complex fixes; skip for tiny documentation-only edits.
---

# Colony Development Pipeline

Deliver one reviewable product increment while keeping requirements, implementation, and evidence traceable.

Before starting, read the repository `AGENTS.md`. For artifact formats and gates, read [references/artifact-contracts.md](references/artifact-contracts.md). Use the project custom agents in `.codex/agents/` when subagents are available.

## Establish the work item

Choose a stable kebab-case feature slug. Store durable artifacts at:

- `docs/specs/<slug>.md`
- `docs/plans/<slug>.md`
- `docs/verification/<slug>.md`

Reuse an existing artifact for the same feature instead of creating a competing version. Record the base commit and relevant branch in the specification.

## Run the gated workflow

### 1. Specification

Delegate repository inspection and specification drafting to `spec_analyst`. The parent agent reviews the result, resolves safe factual gaps from the code, and writes the spec artifact.

Do not proceed while a product decision would materially change scope, compatibility, simulation semantics, or acceptance thresholds. Ask the maintainer for that decision. Non-material assumptions may proceed when they are explicit and testable.

The specification gate passes when scope, non-goals, numbered requirements, invariants, and measurable acceptance criteria are complete and implemented behavior is clearly separated from desired behavior.

### 2. Technical plan

After the specification gate passes, delegate planning to `system_planner`. The parent writes the plan artifact after checking that every requirement maps to implementation work, tests or evaluation, and observable evidence.

The plan must define ordered slices, dependencies, affected state and interfaces, migration impact, validation commands, and exact file ownership for any proposed parallel edits.

The planning gate passes when all requirement IDs are covered and no implementation slice depends on an unresolved product decision.

### 3. Implementation

Dispatch `implementer` agents only for approved slices. Run dependent slices sequentially. Parallelize independent slices only when their owned files do not overlap and they do not mutate the same shared artifact.

The parent agent integrates and reviews all changes before testing. If an agent discovers a requirement conflict, stop that slice and return to the specification or plan instead of silently redefining behavior.

The implementation gate passes when all in-scope plan slices are integrated, targeted checks pass, documentation is updated, and the working tree contains no unrelated changes.

### 4. Tests and simulation evaluation

After integration, run these agents in parallel when both are relevant:

- `test_engineer` adds or updates deterministic automated tests within assigned test-file ownership.
- `simulation_evaluator` independently evaluates behavior, invariants, determinism, multi-seed results, and performance without editing files.

Integrate test-only changes, then rerun the complete relevant test set. Keep raw command output out of the main context when a concise evidence summary is sufficient.

The evidence gate passes when each acceptance criterion has a passing test or another reproducible observation. Label unavailable checks as not run, never as passed.

### 5. Independent quality gate

Delegate the final review to `quality_gate`. Give it the specification, plan, diff, test results, and simulation evidence. It must not edit or repair the change.

Write its decision and evidence matrix to the verification artifact. A FAIL returns only the affected findings to an implementation or test stage; rerun the affected checks and the final gate afterward. After two unsuccessful repair cycles for the same blocker, stop and ask the maintainer for direction with the evidence collected so far.

The pipeline completes only on PASS with no unresolved blocker.

## Parallelism rules

- Parallelize discovery, independent review, log analysis, and independent test execution.
- Parallelize code or test writing only with explicit, non-overlapping file ownership.
- Do not let multiple agents edit the specification, plan, verification report, shared configuration, or the same production module concurrently.
- The parent agent owns integration, conflict resolution, stage transitions, and final status.

## Handoff

Summarize the implemented behavior, changed files, verification results, remaining non-blocking risks, and the exact Git state. Do not push, open a pull request, merge, or change remote state unless the maintainer explicitly authorizes that action.
