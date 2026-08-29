# Neural Policy Learning — implementation plan

Status: implemented plan for `codex/agent-development-foundation`.
Owner: Maintainer / primary agent
Base commit: `cf894816fc6c7c5b197318205904afde0574cd4b`
Last updated: 2026-08-29
Specification: `docs/specs/neural-policy-learning.md`.

## Slice 1 — deterministic neural primitive

Owner: `neuralnetwork.py`, `tests/test_neuralnetwork.py`.

- Preserve the legacy `NNetwork(inputs, *layers)` constructor and forward-pass API.
- Add validated explicit-weight construction, stable non-mutating ReLU/softmax inference, and a small policy-gradient update for a chosen output and scalar reward.
- Keep all randomness outside the primitive for the active engine; the engine supplies seeded weights.
- Test output shape/probability normalization, positive/negative update direction, and exact weight-count validation.

Traces: REQ-001, REQ-002, REQ-003, REQ-008.

## Slice 2 — individual and settlement brain state and active decisions

Owner: `colony_simulation.py`, focused simulation tests.

- Add fixed architecture/action constants and individual/settlement-owned `brain_weights` fields separate from biological `genome`, episodic memory, skills, and telemetry.
- Seed initial weights from `SeededRandom`; create a normalized observation vector from needs, surroundings, jobs, social context, and settlement resources.
- Replace resident action selection in `_run_agent_ai()` with network inference. Keep world operations and reward calculation as environment consequences, not a second action selector.
- Replace settlement high-level action selection in `_run_settlement_ai()` with its own network/action space and reward update; keep resource, treaty, and capacity checks as environmental feasibility constraints.
- Apply the reward to the selected network output, store updated weights, and emit probabilities, reward, `network=True`, and weight delta in observable events.
- Keep `learned_policy` as compatibility telemetry only; it must no longer determine the action.

Traces: REQ-001, REQ-002, REQ-003, REQ-006, REQ-007.

## Slice 3 — genetic reproduction

Owner: `colony_simulation.py`, reproduction tests.

- At birth, produce child brain weights from both parents using deterministic per-weight crossover and bounded mutation from the simulation RNG.
- Preserve parent weights and biological genomes; start child episodic memory and scalar policy telemetry empty.
- Ensure child brain architecture is valid and mutation/crossover is included in canonical state.
- At each headless training-generation boundary, rank adult residents by explicit fitness, retain an elite subset, and replace non-elite policy weights with elite crossover/mutation while preserving resident identity and non-policy state.

Traces: REQ-005, REQ-008.

## Slice 4 — snapshot migration and shared runtime path

Owner: `colony_simulation.py`, `pygame_app.py`, snapshot/UI tests.

- Bump snapshots to schema 5 and persist/validate finite neural weights.
- Accept schema 4 snapshots and deterministically synthesize missing resident and settlement brains from seed plus actor identity without changing the saved random stream; reject unsupported versions and malformed dimensions.
- Ensure Pygame and `run_training()` both invoke `step()` and therefore the same neural path. Make the UI status explicitly say neural learning is enabled.

Traces: REQ-004, REQ-006, REQ-007, REQ-008.

## Slice 5 — evaluation and quality gate

Owner: `tests/`, `docs/verification/neural-policy-learning.md`.

- Add active-network, snapshot, migration, replay, reproduction, and headless multi-generation tests.
- Run focused neural tests, the full suite, `python -m compileall .`, and a fixed-seed headless run with an explicit generation count. Run a Pygame smoke check only when a display is available; otherwise record it as not run.
- Have an independent quality gate review every REQ against the specification and verification evidence. Do not claim genetic or neural learning beyond the recorded checks.

Traces: REQ-002, REQ-004, REQ-008 and all acceptance criteria.

## File ownership and integration order

1. `neuralnetwork.py` and its tests.
2. `colony_simulation.py` and simulation tests.
3. UI text/tests and snapshot migration tests.
4. Verification artifact and quality gate.

No concurrent edits overlap these files. Existing fast-training changes and docs are preserved.
