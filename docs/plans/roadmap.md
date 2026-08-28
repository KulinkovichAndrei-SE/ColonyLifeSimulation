# Implementation plan: deterministic simulation core

- **Specification:** [docs/specs/roadmap.md](../specs/roadmap.md)
- **Base commit:** `028a209` (Phase 1 foundation)
- **Working branch:** `codex/agent-development-foundation` (PR #6 head)
- **Plan status:** Phases 1–4 completed; end-to-end Phase 5–7 execution is in progress
- **Last updated:** 2026-08-28

## 1. Current execution paths and affected state

The legacy path is `main.py -> PygameModule -> InitialGame -> Colony -> Human`. It is display-coupled, uses wall-clock timing, mutates class-level field state, and updates colonies/persons through nested thread pools. The new path is intentionally separate:

`headless_demo.py -> simulation_core.DeterministicSimulation -> clock / RNG / probe state / events / JSON snapshot`

No legacy production module is changed in this slice. This keeps the new deterministic seam reviewable and prevents the first core task from silently changing saved chromosome shapes or Pygame behavior.

## 2. Boundaries, data flow, and state transitions

### New domain boundary

`simulation_core.py` is standard-library-only. It owns:

- `SimulationConfig`: immutable validated seed, dimensions, and population configuration.
- `SimulationClock`: non-negative integer tick with explicit advance semantics.
- `SeededRandom`: deterministic random source owned by one simulation instance.
- Probe-agent state: stable IDs and bounded positions only; this is not a replacement for `Human`.
- `SimulationEvent` and event log: monotonically sequenced transition records.
- Versioned JSON snapshot envelope and strict load validation.

`headless_demo.py` is a thin executable consumer. It owns no domain state beyond constructing a configured simulation and printing its canonical output.

### State transitions

1. Construction validates configuration and deterministically initializes stable probe-agent positions from the owned seed source.
2. `step()` advances exactly one tick, processes probe agents in stable ID order, chooses a bounded movement direction from the owned source, updates positions within world bounds, and appends structured events.
3. `run(n)` repeats `step()` n times; `run(0)` does nothing.
4. `snapshot()` returns a JSON-compatible, canonical state including schema version, config, tick, positions, and random-source state.
5. `save_json(path)` writes the versioned snapshot; `load_json(path)` parses and validates all fields before replacing a new instance's state.
6. A resumed run consumes the stored RNG state and therefore matches an uninterrupted run from the same point.

## 3. Ordered vertical slices

### Slice C1 — Core state, clock, seeded randomness, and probe transitions

- **Dependency:** approved specification and this plan.
- **Owner:** implementer agent.
- **Files:** `simulation_core.py` only.
- **Work:** implement validated dataclasses/classes, deterministic initialization, explicit clock, seeded RNG state, stable bounded movement, state transitions, and structured event log.
- **Requirements:** REQ-001 through REQ-004 and the domain portion of REQ-006.
- **Focused check:** display-free import and a direct same-seed operation sequence.

### Slice C2 — Versioned JSON snapshot and headless demo

- **Dependency:** C1.
- **Owner:** implementer agent, sequentially after C1.
- **Files:** `simulation_core.py` and `headless_demo.py` only. `simulation_core.py` remains owned by this same worker across C1/C2; no parallel worker may edit it.
- **Work:** implement JSON-safe snapshot save/load/resume and a deterministic CLI demonstration. Load validation must parse and validate all fields before mutating the target instance; the demo is only orchestration/output.
- **Requirements:** REQ-003, REQ-004, REQ-005, REQ-006, and REQ-007.
- **Focused check:** run the demo and verify a resumed trace equals uninterrupted output.

### Slice C3 — Deterministic regression coverage

- **Dependency:** C1 and C2.
- **Owner:** test engineer agent.
- **Files:** `tests/test_simulation_core.py` and `tests/__init__.py` only.
- **Work:** add `unittest` tests for clock boundaries, same-seed repeatability, changed-seed behavior, bounded movement, event field/order and canonical JSON bytes, snapshot round-trip/resume, malformed/unsupported JSON rejection with unchanged target state, invalid config/step counts, and a subprocess no-display import that does not import Pygame, NumPy, or legacy modules.
- **Requirements:** REQ-001 through REQ-007.
- **Focused check:** `python -m unittest discover -s tests -v`.
- **Execution note:** the delegated test worker did not return after bounded completion prompts, so the primary agent owns this exact test-file slice for the current working tree; no production scope was expanded.

### Slice C4 — Documentation boundary

- **Dependency:** C1 through C3.
- **Owner:** primary agent.
- **Files:** `README.md` only.
- **Work:** document the implemented headless core probe and command; explicitly state that legacy Pygame behavior remains, Phase 2 love/reproduction/children are specified but not implemented, and Phase 4 money/market behavior is specified but not implemented.
- **Requirements:** REQ-007.

### Slice C5 — Independent evaluation and quality gate

- **Dependency:** integrated C1 through C4.
- **Owners:** simulation evaluator and quality gate agents; read-only.
- **Files:** no production/test edits; primary agent writes `docs/verification/roadmap.md`.
- **Work:** run deterministic checks, inspect no-display/module boundaries and JSON validation, evaluate requirement evidence, and record PASS/FAIL plus any remediation loop.

## 4. Requirement traceability

| Requirement | Production owner | Test/evaluation owner | Evidence |
| --- | --- | --- | --- |
| REQ-001 | `SimulationClock`, `DeterministicSimulation.step/run` | `tests/test_simulation_core.py`; evaluator | Exact tick deltas and zero-step no-op; invalid counts fail before mutation. |
| REQ-002 | `SeededRandom`, simulation initialization/step and restored RNG state | repeatability and changed-seed tests; evaluator | Equal same-seed traces and seed-sensitive probe trace, including resume. |
| REQ-003 | `simulation_core.py` import boundary; `headless_demo.py` | subprocess no-display import test; evaluator | No Pygame/NumPy/legacy imports. |
| REQ-004 | `SimulationEvent`, snapshot/canonical serialization | event-field/order and snapshot tests; evaluator | Stable event fields/order and canonical JSON bytes. |
| REQ-005 | `simulation_core.py` snapshot envelope and `load_json` validation | round-trip, resume, malformed-schema/unchanged-target tests | Versioned JSON rejects bad data before mutation and resumes deterministically. |
| REQ-006 | frozen `SimulationConfig` | validation tests | Invalid dimensions/population/seed and boolean-as-integer cases fail before state change. |
| REQ-007 | `headless_demo.py`, README, tests | test engineer/evaluator | Demo, tests, and docs distinguish implemented/deferred work; baseline checks recorded. |

## 5. Persistence, migration, concurrency, performance, and rollback

- **Persistence:** JSON snapshots are new, versioned, and validated. They contain only core probe state and RNG state; no pickle is read or written.
- **Migration:** legacy chromosome files remain untouched and are not loaded as core snapshots. A later migration task must choose defaults and compatibility policy before connecting saves.
- **Concurrency:** the new core is single-owner and single-threaded. It introduces no thread pool or unsynchronized shared collection. Future parallelism must partition ownership first.
- **Performance:** the probe is intentionally small and correctness-focused. No population-scale performance claim is made; Phase 7 will define benchmark workload and thresholds.
- **Rollback:** new files are isolated from legacy modules. If a defect is found, repair the owning slice, rerun its focused tests, then repeat the relevant evaluation and quality gate.

## 6. Exact validation commands

When Python is available:

```text
python -m unittest discover -s tests -v
python headless_demo.py
python -m compileall simulation_core.py headless_demo.py tests
```

Expected signals:

- all core tests pass;
- the demo prints stable JSON state/events and shows tick progression;
- a snapshot resumed from disk matches uninterrupted canonical output;
- compilation completes without errors.

Repository baseline and graphical checks are separately reported. Bare `python` is not on the PowerShell PATH, but the bundled workspace runtime at `C:\\Users\\kulin\\.cache\\codex-runtimes\\codex-primary-runtime\\dependencies\\python\\python.exe` was used for the actual compile, test, demo, and graphical smoke checks.

## 7. Explicitly deferred work and next task

- Phase 2 implementation: adult life stages, attraction/affinity/love, pair bonding, reproduction attempts, courtship, consent/rejection, pregnancy, gestation, child creation with distinct state, inheritance isolation, childcare, and lifecycle consequences. Before implementation, resolve directed/symmetric affinity, adult/fertility ages, gestation duration, childcare/resource costs, settlement capacity, and missing-partner behavior.
- Phase 3 cognition and separate memory model.
- Phase 4 money system: production material/time costs, wallets or treasury, supply/demand pricing, atomic exchange, and eventual legacy settlement integration. Money is not part of this first phase.
- Technology, diplomacy/conflict, and scale phases.

The implementation continues in this artifact with sequential phase-owned slices. The selected bounded defaults are directed affinity with mutual consent, configurable tick-based lifecycle thresholds, pregnancy retaining the partner genome if the partner disappears, individual wallets plus settlement treasuries, and single-owner deterministic execution.

## 8. End-to-end phase execution plan

The full engine is added beside `simulation_core.py` in `colony_simulation.py`. The Phase 1 probe remains a regression seam; the full engine uses a separate snapshot schema and never loads legacy pickle data.

### Slice P2 — Lifecycle and relationships

- **Files:** `colony_simulation.py`, `tests/test_colony_simulation.py`, `README.md`, roadmap artifacts.
- **Work:** tick-driven needs, injury/death cleanup, directed affinity, courtship/consent, bonds, gestation, birth, childcare, crossover/mutation, and atomic ownership updates.
- **Evidence:** exact-tick lifecycle fixtures, consent rejection, birth/inheritance isolation, partner-loss, cleanup, and snapshot/resume tests.
- **Commit boundary:** Phase 2 commit before cognition work.

### Slice P3 — Cognition and memory

- **Files:** `colony_simulation.py`, `tests/test_colony_simulation.py`.
- **Work:** bounded perception, episodic retention, semantic facts, explicit sharing, deterministic learning, and non-aliasing between personal and settlement knowledge.
- **Evidence:** hidden-resource perception and memory TTL tests, explicit-share-only test, learned-policy/genome isolation test.
- **Commit boundary:** Phase 3 commit.

### Slice P4 — Economy and money

- **Files:** `colony_simulation.py`, `tests/test_colony_simulation.py`, `colony_demo.py`.
- **Work:** recipes, material reservation, labor ticks, storage, wallets, treasuries, demand records, cost-floor quotes, supply pressure, atomic purchases, and event reconstruction.
- **Evidence:** missing-input/labor tests, cost-floor test, fixed-supply demand-price test, replenishment test, conservation and no-partial-side-effect trade tests.
- **Commit boundary:** Phase 4 commit.

### Slice P5 — Technology

- **Files:** `colony_simulation.py`, `tests/test_colony_simulation.py`.
- **Work:** prerequisite catalog, funded research jobs, deterministic completion, rule effects, and treaty/contact-gated diffusion.
- **Evidence:** prerequisite rejection, research ticks/cost, recipe effect, and diffusion ownership tests.
- **Commit boundary:** Phase 5 commit.

### Slice P6 — Diplomacy and conflict

- **Files:** `colony_simulation.py`, `tests/test_colony_simulation.py`.
- **Work:** territory claims, treaties, migration, trade gating, persistent inter-settlement memories, deterministic combat, injury/death, and territory transfer.
- **Evidence:** claim/treaty/migration/trade fixtures, relation-memory separation, combat casualty and money/resource conservation tests.
- **Commit boundary:** Phase 6 commit.

### Slice P7 — Scale, replay, and evaluation

- **Files:** `colony_simulation.py`, `tests/test_colony_simulation.py`, `colony_demo.py`, `README.md`, verification artifact.
- **Work:** full snapshots/checkpoints, event hashes, replay comparisons, multi-seed reports, benchmark metadata, and bounded single-owner execution.
- **Evidence:** checkpoint byte equality, schema validation, explicit 32-seed report, benchmark report fields, compile/test/demo commands.
- **Commit boundary:** Phase 7/final verification commit.

## 9. End-to-end requirement traceability

| Requirement group | Production owner | Tests/evaluation |
| --- | --- | --- |
| REQ-P2-001..006 | `ColonySimulation` lifecycle and relationship transitions | `tests/test_colony_simulation.py` lifecycle, consent, birth, cleanup, replay cases |
| REQ-P3-001..005 | `update_perception`, `share_knowledge`, `learn`, agent memory fields | perception, retention, explicit sharing, and isolation tests |
| REQ-P4-001..007 | recipe/job/ledger/market methods | production, quote, demand, trade, conservation, and event tests |
| REQ-P5-001..004 | technology catalog/research/diffusion methods | prerequisite, progress, effect, and treaty-gated diffusion tests |
| REQ-P6-001..004 | territory/diplomacy/migration/conflict methods | claim, treaty, migration, trade, memory, and combat tests |
| REQ-P7-001..004 | snapshot, invariants, `evaluate_seeds`, `benchmark` | replay, report-schema, multi-seed, and benchmark tests |

## 10. Phase execution validation

Each phase must pass its focused unittest module before its commit. The final gate runs:

```text
python -m unittest discover -s tests -v
python colony_demo.py
python -m compileall .
git diff --check
```

The graphical `python main.py` smoke test remains optional and is reported separately because the legacy loop requires a display. No phase may claim that Pygame integration is complete until a later adapter task is implemented.
