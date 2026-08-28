# Artifact contracts and quality gates

Read this reference when creating or reviewing pipeline artifacts.

## Specification contract

`docs/specs/<slug>.md` must contain:

1. Title, status, owner, base commit, and last-updated date.
2. Current behavior confirmed from code or a reproducible run.
3. Problem statement and user or research value.
4. In-scope and out-of-scope behavior.
5. Domain terms and ownership of state.
6. Numbered requirements such as `REQ-001`.
7. Invariants and explicit failure behavior.
8. Acceptance criteria mapped to requirement IDs.
9. Required observability, configuration, determinism, performance, persistence, and migration behavior.
10. Risks, assumptions, and open decisions, each marked blocking or non-blocking.

Use Given/When/Then where it makes behavior clearer. For statistical outcomes, define seeds, run length, sample size, metric, and threshold. Do not require a particular implementation unless it is itself a product constraint.

## Plan contract

`docs/plans/<slug>.md` must contain:

1. Links to the approved specification and base commit.
2. Existing execution paths and state affected.
3. Proposed boundaries, data flow, and state transitions.
4. Ordered vertical slices with dependencies.
5. A table mapping every requirement ID to code, tests or evaluation, and evidence.
6. Persistence, migration, concurrency, performance, and rollback considerations.
7. Exact validation commands and expected signals.
8. File ownership for each delegated slice.
9. Explicitly deferred work.

A plan is not approved when a requirement has no owner or evidence path.

## Verification contract

`docs/verification/<slug>.md` must contain:

1. Verdict: `PASS` or `FAIL`.
2. Commit or working-tree state evaluated.
3. A requirement-by-requirement evidence matrix.
4. Commands, seeds, configurations, and results actually observed.
5. Checks not run and why.
6. Blocking findings with reproduction steps and file or symbol references.
7. Non-blocking risks and explicitly deferred work.
8. Required remediation and which pipeline stage must repeat.

## Default severity

- **Blocker:** acceptance criterion fails; data may be corrupted; behavior is non-reproducible where determinism is required; a concurrency defect can invalidate state; or the change cannot be run.
- **Major:** likely behavioral regression, missing critical boundary coverage, unsupported migration, or material performance risk without sufficient evidence.
- **Minor:** maintainability or evidence weakness that does not invalidate an acceptance criterion.

Only blockers force a `FAIL`, but multiple major findings may also justify `FAIL` when they make the evidence insufficient.

## Evidence rules

- A command is evidence only when it actually ran against the evaluated working tree.
- A passing unit test supports only the behavior it asserts.
- A manual visual check is not evidence of long-run stability or statistical emergence.
- A benchmark without configuration, scale, warm-up conditions, and repeated measurements is anecdotal.
- A skipped, unavailable, flaky, or environment-blocked check is `NOT RUN`, not `PASS`.
- Roadmap aspirations do not become current acceptance criteria unless the approved specification brings them into scope.
