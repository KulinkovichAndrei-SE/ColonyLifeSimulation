# Implementation plan: Colony Life Simulation roadmap

- **Specification:** [docs/specs/roadmap.md](../specs/roadmap.md)
- **Base commit:** `028a209` (Phase 1 foundation)
- **Working branch:** `codex/agent-development-foundation` (PR #6 head)
- **Plan status:** Phases 1–7 and Pygame integration completed; production-scale optimization remains follow-up work
- **Last updated:** 2026-08-28

## 1. Current execution paths and affected state

The legacy path is `PygameModule -> InitialGame -> Colony -> Human`. It is display-coupled, uses wall-clock timing, mutates class-level field state, and updates colonies/persons through nested thread pools. The active path is:

`main.py -> pygame_app.PygameSimulationApp -> colony_simulation.ColonySimulation -> clock / RNG / people / settlements / events`

The legacy modules remain untouched for comparison, while `main.py` is now an adapter over the deterministic engine. `headless_demo.py` and `colony_demo.py` remain display-free diagnostic consumers of the same explicit transition boundary.

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

`colony_simulation.py` owns people, settlements, resources, memory, learned policies, production, money, research, diplomacy, conflict, snapshots, and replay. `pygame_app.py` owns only input, layout, selection, and rendering. The only world-changing call made by the live UI loop is `simulation.step()`; the AI inside that step chooses resident and settlement actions.

### State transitions

1. Construction validates configuration and deterministically initializes people, settlements, resources, relations, and the owned random source.
2. `step()` advances one tick, processes needs/lifecycle, perception, movement, relationships, autonomous resident and settlement decisions, work, research, food, and invariants in stable order, and appends structured events.
3. `run(n)` repeats `step()` n times; `run(0)` does nothing. `run_until_winner()` stops when one settlement remains active.
4. `snapshot()` returns a JSON-compatible canonical state including schema version, people, settlements, jobs, events, and random-source state.
5. `save_json(path)` writes the versioned snapshot; `load_json(path)` parses and validates fields before replacing a new instance's state.
6. A resumed run consumes the stored RNG state and therefore matches an uninterrupted run from the same point; checkpoints expose state/event hashes for replay.
7. `pygame_app.py` renders movement, territory, resources, children, bonds, ledgers, active work, decisions, and learning. Space pauses/restarts, Up/Down adjust speed, and mouse selection only changes the inspector.

## 3. Ordered vertical slices

### Slice C1 — Core state, clock, seeded randomness, and probe transitions (completed)

- **Dependency:** approved specification and this plan.
- **Owner:** implementer agent.
- **Files:** `simulation_core.py` only.
- **Work:** implement validated dataclasses/classes, deterministic initialization, explicit clock, seeded RNG state, stable bounded movement, state transitions, and structured event log.
- **Requirements:** REQ-001 through REQ-004 and the domain portion of REQ-006.
- **Focused check:** display-free import and a direct same-seed operation sequence.

### Slice C2 — Versioned JSON snapshot and headless demo (completed)

- **Dependency:** C1.
- **Owner:** implementer agent, sequentially after C1.
- **Files:** `simulation_core.py` and `headless_demo.py` only. `simulation_core.py` remains owned by this same worker across C1/C2; no parallel worker may edit it.
- **Work:** implement JSON-safe snapshot save/load/resume and a deterministic CLI demonstration. Load validation must parse and validate all fields before mutating the target instance; the demo is only orchestration/output.
- **Requirements:** REQ-003, REQ-004, REQ-005, REQ-006, and REQ-007.
- **Focused check:** run the demo and verify a resumed trace equals uninterrupted output.

### Slice C3 — Deterministic regression coverage (completed and extended)

- **Dependency:** C1 and C2.
- **Owner:** test engineer agent.
- **Files:** `tests/test_simulation_core.py` and `tests/__init__.py` only.
- **Work:** add `unittest` tests for clock boundaries, same-seed repeatability, changed-seed behavior, bounded movement, event field/order and canonical JSON bytes, snapshot round-trip/resume, malformed/unsupported JSON rejection with unchanged target state, invalid config/step counts, and a subprocess no-display import that does not import Pygame, NumPy, or legacy modules.
- **Requirements:** REQ-001 through REQ-007.
- **Focused check:** `python -m unittest discover -s tests -v`.
- **Execution note:** the delegated test worker did not return after bounded completion prompts, so the primary agent owns this exact test-file slice for the current working tree; no production scope was expanded.

### Slice C4 — Documentation boundary (completed and maintained)

- **Dependency:** C1 through C3.
- **Owner:** primary agent.
- **Files:** `README.md` only.
- **Work:** document the implemented deterministic probe and multi-phase engine, the Pygame observation contract, autonomous AI ownership, and the remaining legacy migration/scale follow-up.
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

- **Persistence:** JSON snapshots are versioned and validated. The Phase 1 probe and full colony engine use separate schemas; no pickle is read or written by the new path.
- **Migration:** legacy chromosome files remain untouched and are not loaded as core snapshots. A later migration task must choose defaults and compatibility policy before connecting saves.
- **Concurrency:** the new core is single-owner and single-threaded. It introduces no thread pool or unsynchronized shared collection. Future parallelism must partition ownership first.
- **Performance:** Phase 7 records population/world/tick workload, warm-up, repetitions, runtime distribution, and peak memory. No approved production-scale threshold is claimed yet.
- **Rollback:** new files are isolated from legacy modules. If a defect is found, repair the owning slice, rerun its focused tests, then repeat the relevant evaluation and quality gate.

## 6. Exact validation commands

When Python is available:

```text
python -m unittest discover -s tests -v
python headless_demo.py
python colony_demo.py
python -m compileall simulation_core.py colony_simulation.py headless_demo.py colony_demo.py pygame_app.py main.py tests
SDL_VIDEODRIVER=dummy python main.py --frames 4
git diff --check
```

Expected signals:

- all deterministic engine and UI adapter tests pass;
- the demo prints stable JSON state/events and shows tick progression;
- the phase demo reports children, technology, replay, multi-seed, and benchmark evidence;
- a snapshot resumed from disk matches uninterrupted canonical output;
- compilation and diff checks complete without errors;
- the bounded dummy-display UI exits while showing the active deterministic path.

Repository baseline and graphical checks are separately reported. Bare `python` is not on the PowerShell PATH, but the bundled workspace runtime at `C:\\Users\\kulin\\.cache\\codex-runtimes\\codex-primary-runtime\\dependencies\\python\\python.exe` was used for the actual compile, test, demo, and graphical smoke checks.

## 7. Explicitly deferred work and next task

- Legacy-path migration: port the deterministic engine's people/settlement state into the old `Human`/`Colony` modules only if compatibility and persistence policy are approved.
- Richer learning: extend the active neural policies with recurrent memory and cross-run population selection while preserving explicit state ownership.
- Production scale: establish approved population/world/tick thresholds and optimize only after benchmark workloads and replay constraints are fixed.
- Richer visualization: add charts, timeline filters, and camera tooling without adding world-changing UI commands.

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
- **Work:** recipes, material reservation, labor ticks, bounded storage/logistics capacity, wallets, treasuries, demand records, cost-floor quotes, supply pressure, atomic purchases, incentive-driven specialization metrics, and event reconstruction.
- **Evidence:** missing-input/labor tests, cost-floor test, fixed-supply demand-price test, replenishment test, conservation and no-partial-side-effect trade tests.
- **Commit boundary:** Phase 4 commit.

### Slice P5 — Technology

- **Files:** `colony_simulation.py`, `tests/test_colony_simulation.py`.
- **Work:** prerequisite catalog, funded research jobs, deterministic completion/failure, rule effects, and treaty/contact-gated diffusion.
- **Evidence:** prerequisite rejection, research ticks/cost, deterministic success/failure, recipe effect, and diffusion ownership tests.
- **Commit boundary:** Phase 5 commit.

### Slice P6 — Diplomacy and conflict

- **Files:** `colony_simulation.py`, `tests/test_colony_simulation.py`.
- **Work:** territory claims, treaties, migration, trade gating, persistent inter-settlement memories, deterministic combat, injury/death, and territory transfer.
- **Evidence:** claim/treaty/migration/trade fixtures, relation-memory separation, combat casualty and money/resource conservation tests.
- **Commit boundary:** Phase 6 commit.

### Slice P7 — Scale, replay, and evaluation

- **Files:** `colony_simulation.py`, `tests/test_colony_simulation.py`, `colony_demo.py`, `README.md`, verification artifact.
- **Work:** full snapshots/checkpoints, event hashes, replay comparisons, explicit 32-seed reports with event/winner/specialization metrics, benchmark metadata, and bounded single-owner execution.
- **Evidence:** checkpoint immutability/equality, schema validation, 32-seed deterministic report, benchmark report fields, compile/test/demo commands.
- **Commit boundary:** Phase 7/final verification commit.

### Slice UI — Pygame presentation adapter

- **Files:** `pygame_app.py`, `main.py`, `tests/test_pygame_app.py`, `README.md`.
- **Work:** replace the old entry path with a renderer/input adapter that calls one explicit deterministic tick, renders map/territory/resources/agents/children, and exposes phase state through a read-only status panel and resident inspector. Keyboard input is limited to pause/restart and speed.
- **Evidence:** bounded `SDL_VIDEODRIVER=dummy` run exits successfully; UI imports only the new domain engine, does not expose action keys, and does not mutate domain rules directly.
- **Commit boundary:** UI integration commit after Phase 6 and before final Phase 7 gate.

## 9. End-to-end requirement traceability

| Requirement group | Production owner | Tests/evaluation |
| --- | --- | --- |
| REQ-P2-001..006 | `ColonySimulation` lifecycle and relationship transitions | `tests/test_colony_simulation.py` lifecycle, consent, birth, cleanup, replay cases |
| REQ-P3-001..005 | `update_perception`, `share_knowledge`, `learn`, agent memory fields | perception, retention, explicit sharing, and isolation tests |
| REQ-P4-001..007 | recipe/job/ledger/market/capacity/specialization methods | production, quote, demand, trade, conservation, capacity, specialization metrics, and event tests |
| REQ-P5-001..004 | technology catalog/research/diffusion methods | prerequisite, progress, effect, and treaty-gated diffusion tests |
| REQ-P6-001..004 | territory/diplomacy/migration/conflict methods | claim, treaty, migration, trade, memory, and combat tests |
| REQ-P7-001..004 | snapshot, invariants, `evaluate_seeds`, `benchmark` | replay, report-schema, multi-seed, and benchmark tests |

## 10. Phase execution validation

Each phase passed its focused deterministic tests before its phase commit. The final gate runs:

```text
python -m unittest discover -s tests -v
python colony_demo.py
python -m compileall .
git diff --check
```

The graphical smoke test is reported separately because a real display may be unavailable in CI; the bounded dummy-display run is the reproducible UI check. Pygame integration is complete for the active deterministic path, while migration of the legacy comparison loop remains deferred.
