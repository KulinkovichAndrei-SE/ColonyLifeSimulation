# Fast headless training implementation plan

Specification: [`docs/specs/fast-training.md`](../specs/fast-training.md)
Base commit: `cf89481`
Status: approved implementation plan
Last updated: 2026-08-29

## Existing execution path and state

`ColonySimulation` owns the clock, seeded random source, agents, settlements,
jobs, resources, and ordered events. `step()` performs one complete domain
transition and checks invariants; `run()` is an unconditional tick loop. The
existing `invariants()`, `winner`, `game_over`, `state_hash()`, and
`event_hash()` methods provide the observation surfaces needed at window
boundaries. `simulation_core.canonical_json()` supplies stable JSON encoding.

The new runner will not alter snapshots, `ColonyConfig`, UI behavior, or legacy
modules. It will observe and advance one simulation instance only.

## Vertical slices and ownership

| Order | Slice | Owned files | Dependency |
|---|---|---|---|
| 1 | Training API and report assembly | `colony_simulation.py` | None |
| 2 | CLI adapter and argument/config validation | `fast_training.py` | Slice 1 |
| 3 | Deterministic API and subprocess tests | `tests/test_fast_training.py` | Slices 1–2 |
| 4 | Explicit UI learning enablement | `pygame_app.py`, `tests/test_pygame_app.py` | Slice 1 |
| 5 | User documentation | `README.md` | Slices 1–4 |
| 6 | Verification evidence | `docs/verification/fast-training.md` | All slices |

No slices edit overlapping files in parallel. The API and CLI are sequential;
tests follow both. Quality review is read-only after integration.

## Data flow and state transitions

```text
CLI arguments
  -> strict parser + allowlisted ColonyConfig overrides
  -> one ColonySimulation(ai_enabled=True)
  -> run_training(generations, ticks_per_generation)
  -> JSON-compatible report
  -> canonical_json(report)
  -> one stdout document
```

`run_training()` validates a non-negative window count and positive window size,
captures the starting tick and event cursor, advances only through `step()`, and
records a boundary after each executed window. It accepts an explicit terminal
mode: compatibility `diagnostic_stop` checks `game_over` before each tick, while
`continue_after_game_over` runs every requested tick. Event deltas count
`child_born` and `agent_died`; cumulative counts are derived from the whole event
stream. The returned report includes schema version 1, effective config, terminal
mode/first-terminal metadata (including the first winning settlement),
requested/executed/completed windows, actual and post-terminal ticks, ordered
records, terminal reason, winner, final metrics, and final hashes.

“Generation” is a public compatibility term for the requested training window;
the report uses `training_window` fields and includes no biological generation
counter.

## Requirement traceability

| Requirement | Code owner | Test/evaluation evidence |
|---|---|---|
| REQ-001 | `fast_training.py:main`, `build_parser` | CLI subprocess emits JSON without Pygame import |
| REQ-002 | `ColonySimulation.run_training` | Continuous-vs-uninterrupted tick equivalence and cumulative learning/event state |
| REQ-003 | `run_training` window loop | Tick intervals, zero-window behavior, executed tick sum |
| REQ-004 | `run_training` and CLI | Static import check, fast subprocess run, no runtime field |
| REQ-005 | `run_training` record builder | Birth/death event deltas, population, invariants, boundary hashes |
| REQ-006 | `fast_training.py:main` | JSON parse, canonical byte shape, required report keys |
| REQ-007 | `build_parser` and `main` | Invalid numeric/config inputs: non-zero, stderr, empty stdout |
| REQ-008 | `run_training` terminal mode | Forced terminal fixture in stop and continuation modes; post-terminal tick accounting |
| REQ-009 | Seeded API/CLI path | Repeat identical API and subprocess runs and compare canonical output |
| REQ-010 | `pygame_app.py` default config/header | Dummy-display UI smoke and UI regression test for `ai_enabled`/`learning_updated` |

## CLI contract

Required/common options:

- `--generations N`: non-negative integer training-window count;
- `--ticks-per-generation T`: positive integer, default `20`;
- `--seed S`: integer, default `7`.
- `--stop-on-game-over`: optional diagnostic mode; training continues by default.

Useful allowlisted world overrides are `--width`, `--height`, `--population`,
`--settlements`, and `--max-age`; defaults come from `ColonyConfig`. They are
validated before constructing the simulation. Training always forces
`ai_enabled=True`; no non-AI mode is exposed by this command. Output is stdout
only. Game over is a successful result with terminal metadata.

## Persistence, migration, concurrency, and performance

- No snapshot or save schema change; the report is output-only schema version 1.
- No new shared collections or threads; one caller owns the simulation and RNG.
- No sleeps, Pygame imports, frame loop, or wall-clock fields.
- Canonical report construction must not call timing APIs.
- A benchmark is run externally with a documented workload; measured duration is
  evidence only and is not part of deterministic JSON.
- Rollback is additive: remove the new API method, CLI, dedicated tests, README
  section, and verification artifact without touching existing saves or UI.

## Ordered implementation tasks

1. Add private event-count helpers and `ColonySimulation.run_training()` near
   `run()`. Keep report values JSON-compatible, validate terminal mode, track
   first-terminal/post-terminal metrics, and copy invariant payloads only through
   existing value-returning methods.
2. Add `fast_training.py` with strict argparse parsing, allowlisted config
   overrides, continuation as the default training mode, `--stop-on-game-over`
   diagnostics, controlled stderr errors, and one canonical stdout document.
3. Add tests for window ticks, progressive state, event deltas, both terminal
   modes, zero windows, API determinism, CLI output, no Pygame import, and
   validation.
4. Make `ai_enabled=True` explicit in default UI configurations and expose the
   read-only `AI learning: ON/OFF` header state; cover it in the UI regression test.
5. Update README quick start and limitations/roadmap wording with the exact
   command and the training-window semantics.
6. Run full tests, compileall, CLI repeatability, invalid CLI cases, a 100-window
   performance observation, and the independent evaluator/quality gate.

## Explicitly deferred

True biological cohort generations, selection/replacement across populations,
cross-run policy inheritance, episode reset/respawn after extinction, report
files/checkpoint resumption, and production-scale performance thresholds remain
roadmap work. Resident neural-network training and parent-to-child policy
inheritance are specified separately in `docs/specs/neural-policy-learning.md`.
Continued ticking after terminal state is not
population evolution; it exists to complete a requested online-learning workload.
