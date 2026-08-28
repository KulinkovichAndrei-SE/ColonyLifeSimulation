# Repository agent guide

## Mission

Evolve this legacy Python/Pygame prototype into a deterministic, observable artificial-life simulation in which individual and settlement behavior can emerge from environment rules, cognition, learning, and selection.

Keep three things distinct in every artifact:

- **Implemented:** behavior confirmed in the current code and, when possible, by a reproducible check.
- **Specified:** behavior accepted for the current change but not necessarily implemented yet.
- **Roadmap:** long-term intent that is not part of the current change.

Do not describe roadmap ideas as working features.

## Current baseline

- The base branch is `master`.
- The application starts with `python main.py` after installing `pygame` and `numpy` and creating `save/`.
- The active prototype is coupled to Pygame, time-based randomness, class-level mutable state, and nested thread pools.
- There is currently no automated test suite, packaging metadata, CI, deterministic headless runner, or migration-safe save format.

Treat these as facts to improve incrementally, not patterns to copy into new code.

## Product invariants

- Prefer emergent behavior over hard-coded stories or labels. Encode incentives, constraints, perception, and consequences; do not directly script an interesting outcome unless the approved specification requires it.
- Keep individual state, individual memory, inherited genome, learned behavior, and settlement knowledge conceptually separate.
- A simulation result must be attributable to explicit state transitions. Avoid hidden wall-clock dependencies in domain logic.
- New stochastic behavior must accept a controlled random source or seed so tests and replays can reproduce it.
- Rendering is a consumer of simulation state. New domain behavior must not require a display, Pygame event loop, or sprite to execute.
- New concurrent code needs explicit state ownership or synchronization. Do not add unsynchronized writes to shared collections.
- Save formats must be versioned and validated before they become compatibility commitments. Never load untrusted pickle data.

## Required workflow

Use `$colony-development-pipeline` for any non-trivial feature, architectural refactor, cross-module bug fix, or roadmap increment.

The required stage order is:

1. Inspect current behavior and write a specification.
2. Resolve product decisions that materially affect scope.
3. Write a technical plan that traces every requirement to code and tests.
4. Implement bounded slices.
5. Add and run deterministic tests; evaluate simulation-level behavior across explicit seeds when relevant.
6. Run the independent quality gate against the specification.

Store durable artifacts at:

- `docs/specs/<feature-slug>.md`
- `docs/plans/<feature-slug>.md`
- `docs/verification/<feature-slug>.md`

Create the directories when the first artifact of that kind is needed. Do not create empty placeholders.

## Agent orchestration

- The primary agent owns requirements, delegation, integration, and the final answer.
- Use the project custom agents in `.codex/agents/` for their named roles.
- Parallelize read-heavy exploration, independent reviews, and independent test runs.
- Parallel code edits are allowed only after the plan assigns non-overlapping file ownership. If ownership overlaps, run those slices sequentially.
- Each subagent must receive a bounded task, relevant artifact paths, exact ownership, and the evidence it must return.
- Wait for all required agents in a stage before crossing that stage's gate.
- The final verifier must not implement its own findings. Failed requirements return to an implementation step and then repeat the affected checks.

## Engineering standards

- Preserve existing user-visible behavior unless the specification intentionally changes it.
- Prefer small modules with explicit dependencies over wildcard imports, cyclic imports, and mutable class globals.
- Keep simulation rules separate from UI, persistence, and orchestration.
- Name units and tick semantics explicitly. Avoid tuning constants with no documented meaning.
- Add type hints to new public boundaries where they clarify state contracts; do not perform repository-wide typing cleanup as part of an unrelated feature.
- Avoid speculative abstractions. Introduce interfaces at real seams such as clock, random source, persistence, policy, and renderer.
- Update the README when setup, controls, architecture, or implemented capabilities change.

## Testing and evidence

- First reproduce or characterize the relevant baseline. Do not silently turn an unknown behavior into an asserted requirement.
- Prefer deterministic unit tests for rules and state transitions.
- Add integration tests for interactions between people, settlements, resources, buildings, persistence, and the simulation clock.
- For emergent or statistical claims, run multiple explicit seeds and report distributions or thresholds. A visually convincing single run is not proof.
- Keep tests independent of display hardware whenever possible.
- Record exact commands, seeds, configuration, and outcomes in the verification artifact.
- Do not claim a test, visual check, performance result, or long-running simulation was completed unless it actually ran.

Until project tooling supersedes it, use these baseline checks:

```bash
python -m compileall .
python main.py
```

The graphical smoke test is optional when the environment has no display; report it as not run rather than treating it as passed.

## Git and review

- Start work from `master` unless the maintainer names another integration branch.
- Use focused branches; default to `codex/<task-name>` for agent-created branches.
- Preserve unrelated user changes and avoid history-rewriting commands.
- Do not push, open a pull request, merge, or modify remote state without explicit maintainer authorization for that action.
- Keep generated saves, caches, virtual environments, and test artifacts out of commits.
- Review priorities are correctness, determinism, data integrity, concurrency safety, behavioral regressions, performance at scale, and missing tests. Style-only findings are secondary.

## Definition of done

A change is done only when:

- the approved specification has no unresolved blocking decision;
- every requirement is implemented or explicitly deferred;
- acceptance criteria map to passing automated tests or documented reproducible evidence;
- affected documentation is current;
- the quality gate reports no unresolved blocker;
- the diff contains no unrelated changes;
- no push or PR is performed before maintainer review and authorization.
