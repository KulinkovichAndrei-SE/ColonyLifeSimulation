# Fast headless training

Status: approved for implementation
Owner: Codex
Base commit: `cf89481`
Last updated: 2026-08-29

## Current behavior

The active path is a deterministic `ColonySimulation` driven by explicit ticks,
seeded randomness, autonomous resident and settlement AI, ordered domain events,
snapshots, state/event hashes, and invariant metrics. `run(steps)` advances ticks
but there is no command that runs a requested training workload or reports progress
at intervals. `pygame_app.py` is an observation UI and is not suitable for fast
batch training. The engine has no cohort-generation field; births are observable
as `child_born` events.

## Problem and value

The user needs to train and evaluate the autonomous colonies without watching the
UI. A display-free command should run quickly for a requested number of training
windows and produce machine-readable evidence of learning, population change,
economy, and terminal outcomes.

## Scope

### In scope

- A `ColonySimulation` API for running sequential training windows.
- A `fast_training.py` CLI that runs the active AI simulation without importing or
  initializing Pygame.
- A fixed number of explicit ticks per training window, with no sleep or frame
  timing.
- One continuous simulation and random stream across all windows so learned
  policies, memories, jobs, settlement knowledge, and resources accumulate.
- Canonical JSON output containing configuration, per-window metrics, final metrics,
  hashes, invariant metrics, and terminal status.
- A training mode that completes the requested workload after a terminal colony
  outcome, plus a diagnostic mode that stops at the terminal tick.
- Explicit AI-learning enablement in the default Pygame UI and a visible status
  indicator, so the interactive run uses the same learning-enabled engine.
- Input validation and deterministic tests.

### Out of scope

- A new biological cohort or generation model.
- Neural-network training or cross-process population evolution.
- Resetting or selecting a new population at window boundaries.
- UI controls, UI redesign, persistence of a training report, or remote execution.
- Changing existing AI, reproduction, economy, research, diplomacy, or conflict
  rules beyond what the runner observes.

## Domain terms and state ownership

- **Tick:** one explicit domain transition owned by `ColonySimulation`.
- **Training window:** a configured interval of ticks in the same simulation.
- **Biological birth:** a child creation observed through `child_born`; it is not a
  training-window boundary.
- **Biological generation:** a lineage concept not currently stored by the engine;
  this increment must not imply that window index is a biological generation.
- **Continuous run:** one simulation instance and one seeded random source spanning
  every requested window.
- **Terminal state:** `game_over` is true because one settlement remains populated
  or no agents remain alive.

Simulation state remains owned by `ColonySimulation`; the CLI only constructs,
advances, and serializes it. Individual memory, learned policy, skills, genome,
and relationships remain agent-owned. Settlement knowledge, policy, treasury,
storage, and relations remain settlement-owned.

## Requirements

### REQ-001 — Headless command

Provide `python fast_training.py --generations N` as a display-free entry point.
The command must not import or initialize Pygame, wait for frames, or require user
interaction. `--ticks-per-generation T` is supported and defaults to a documented
positive value so the common command needs only the requested count.

### REQ-002 — Continuous seeded AI run

One invocation constructs one `ColonySimulation` with `ai_enabled=True` and
advances it in order across all windows. It must not reset state or the random
stream at a boundary. Learning events from earlier windows must remain available
to later windows. The training CLI defaults to continuing the same simulation
after `game_over` so a requested workload is completed; the API retains an
explicit diagnostic-stop default for compatibility.

### REQ-003 — Explicit window semantics

For `N` windows and `T` ticks per window, continuation mode executes exactly
`N * T` ticks, including ticks after terminal state. Diagnostic-stop mode may
execute fewer. Window `i` (1-based) covers the half-open tick interval
`[(i-1)*T, i*T)` in a non-terminal run. Each record reports requested and actual
ticks. The report calls these training windows; it does not claim they are
biological generations.

`N=0` is a valid deterministic no-op report at the current tick. `T` must be
positive even when `N=0`.

### REQ-004 — Fast execution

Progress is driven only by explicit calls to `step()`. No domain behavior may
depend on wall-clock time, `sleep`, frame rate, or rendering. Runtime may be
measured externally but is excluded from deterministic report fields.

### REQ-005 — Per-window observability

Each window record contains, at minimum:

- window index and start/end tick;
- requested and actual tick counts;
- alive and dead population;
- births and deaths observed in that window;
- interval and cumulative event counts;
- game-over status and winner at the boundary;
- invariant metrics, state hash, and event hash.

Births and deaths are calculated from `child_born` and `agent_died` event deltas;
they do not create a biological generation counter.

### REQ-006 — Final canonical JSON report

The CLI emits exactly one valid canonical JSON document to stdout on success. It
contains a report schema version, run configuration, requested windows, executed
windows, completed windows, total actual ticks, ordered window records, final
metrics, terminal reason, winner or `null`, and deterministic state/event hashes.
Object key ordering and separators are canonical. Runtime duration is not included.

### REQ-007 — Validation and failure behavior

Invalid CLI arguments fail before simulation starts, return a non-zero status, and
write a human-readable diagnostic to stderr without a successful JSON report.
Reject negative or non-integer window counts, non-positive or non-integer tick
counts, and invalid `ColonyConfig` overrides. Internal invariant or serialization
errors also fail rather than producing a partial success report.

### REQ-008 — Terminal behavior and training continuation

The runner supports two explicit modes. `diagnostic_stop` checks `game_over`
before each tick, records a partial terminal window, and stops without advancing
further. `continue_after_game_over` executes every requested tick even after
terminal state, preserves the terminal status, and reports all requested windows.
The CLI uses continuation by default and accepts `--stop-on-game-over` for
diagnostic-stop behavior. Reaching game over is a successful run condition, not a
CLI error.

Both modes report the first terminal tick, first terminal reason (`winner` or
`all_agents_dead`), whether the run was already terminal at start, and the number
of ticks executed after that observation. They also retain the first winning
settlement as `terminal_winner`, even if later continued ticks remove that
settlement's last living resident. Continued ticking is not a reset,
respawn, selection cycle, or biological generation.

### REQ-009 — Determinism

Identical seed, configuration, window count, and tick count produce byte-identical
JSON, including window metrics, final metrics, state hash, and event hash. Changing
the seed may change stochastic outcomes and hashes.

### REQ-010 — Visible UI learning enablement

The default Pygame application configuration must explicitly construct
`ColonyConfig(ai_enabled=True)`. Its observation header must show whether AI
learning is on or off based on the active simulation configuration. The UI must
remain observation-only and must not add action controls or mutate domain state
through the indicator.

## Invariants

- One seeded random source and one mutable simulation span all windows.
- Final executed ticks equal final tick minus the tick at runner start.
- Continue mode executes exactly `N * T`; diagnostic-stop mode never exceeds it.
- Tick and event sequence order remain monotonic.
- Agent positions remain inside world bounds.
- Asset quantities and money balances remain non-negative.
- Existing settlement/job ownership and memory boundaries remain valid at every
  window boundary.
- No display initialization is needed for the command.
- Window index is not reported as a biological generation.

## Acceptance criteria

1. `python fast_training.py --seed 7 --generations 3 --ticks-per-generation 5`
   returns valid JSON with three ordered windows and final tick 15; continuation
   mode does not shorten the workload if a terminal state is reached.
2. Running the same command twice produces byte-identical stdout.
3. Non-terminal records have tick ranges `0-5`, `5-10`, and `10-15`; actual tick
   totals equal the final executed tick count.
4. `--generations 0` returns a deterministic zero-window report at tick 0.
5. Negative generation counts, zero/negative tick counts, malformed numeric values,
   and invalid configuration values return non-zero status and no success JSON.
6. A deterministic terminal fixture in diagnostic-stop mode records a partial
   terminal window, actual tick count, winner/reason, and unexecuted windows, then
   stops.
7. The same fixture in continuation mode executes exactly `N*T` ticks, records all
   windows, preserves terminal metadata, and reports post-terminal ticks.
8. Per-window birth/death deltas equal the corresponding domain-event counts.
9. Repeated API runs with identical seed/configuration and terminal mode have equal report JSON,
   state hashes, event hashes, window metrics, and final metrics.
10. The headless command runs without importing or initializing Pygame and introduces no real-time delay.
11. The default Pygame UI explicitly enables AI learning, displays `AI learning: ON`, and emits `learning_updated` after a tick; action keys remain non-mutating.
12. Existing simulation, snapshot/replay, UI contract, and demo tests remain green.

## Configuration and migration

The runner reuses `ColonyConfig`; its training-only values are not persisted into
colony snapshots. The report has its own schema version (`1`) and is output-only,
so no migration of existing save files is required.

## Risks and decisions

- Non-blocking assumption: “generation” in the user command means a training
  window because the current engine has no biological generation field.
- Non-blocking assumption: default `T=20` gives useful progress while allowing a
  short command; users can override it for larger or smaller workloads.
- Non-blocking risk: after all agents are dead, continuation can execute ticks but
  cannot produce further resident learning events; the report exposes this through
  terminal and learning event metrics.
- Deferred: biological cohort replacement across independent runs, recurrent
  memory, and cross-run population selection. Resident/settlement neural
  updates and within-settlement generation selection are covered by the neural
  policy phase.
