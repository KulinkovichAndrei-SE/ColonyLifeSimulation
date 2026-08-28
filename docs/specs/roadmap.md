# Colony Life Simulation roadmap, core, and relationships

- **Status:** End-to-end execution underway; Phases 1 through 5 are implemented in the headless path, and Phases 6 through 7 remain sequenced work.
- **Owner:** Maintainer / primary agent
- **Base commit:** `028a209` on `codex/agent-development-foundation` (PR #6, base `master`)
- **Last updated:** 2026-08-28
- **Context:** [PR #6](https://github.com/KulinkovichAndrei-SE/ColonyLifeSimulation/pull/6)

## 1. Evidence-based baseline

### Implemented in the current checkout

The legacy application starts from `main.py`, creates a Pygame world in `InitialGame`, populates a fixed `73 x 33` `FieldProcessing` grid, and updates `Colony` and `Human` objects from `PygameModule`. The code confirms:

- Four colonies are created with five men and five women each.
- People have health, hunger, age-like `day`, fitness, skill counters, inventories, known fields, and neural-network chromosomes.
- The active actions are cutting trees, gathering berries, building a house, and eating.
- `Human.build()` immediately spends 50 shared `Tree` units and creates a `House`; it has no money, seller, buyer, demand, or production duration.
- Resource extraction and movement use wall-clock time and class-level mutable state; colony/person work uses nested thread pools.
- `Stone`, `Iron`, `Copper`, `Gold`, `Barn`, `Tavern`, and `Farm` exist but are not connected to the active loop.
- Chromosome persistence is unversioned pickle storage. There is no headless runner or automated test suite.

The baseline compile/test command was attempted during specification work but could not run because this host has no `python` executable on PATH. This is `NOT RUN`, not a passing result.

### Specified by this document

The roadmap is divided into seven capability phases. Phase 2 explicitly includes reproduction, children, pair bonding, love/affinity, consent, pregnancy, birth, and inheritance. Phase 4 explicitly includes the requested money system. Phases 1 and 2 are now in scope for the current implementation pass; later phases remain specified until their own gates pass.

### Roadmap, not current behavior

The deterministic headless engine now includes the Phase 1 seam, Phase 2 lifecycle/relationship rules, Phase 3 bounded cognition/memory rules, Phase 4 production/economy rules, and Phase 5 research/technology rules. Diplomacy, conflict, and city-scale behavior are not claimed to exist until their phase gates pass.

## 2. Product goal and user value

Turn the prototype into a deterministic, observable artificial-life simulation where material constraints, time, needs, relationships, learning, and selection create behavior that is not scripted as a story. The first product slice establishes a display-free core so later lifecycle, love/reproduction, and market rules can be tested and replayed before they are connected to Pygame.

## 3. Phased implementation specification

### Phase 1 — Stabilize the simulation core

**Purpose:** make simulation state executable without Pygame and reproducible from explicit configuration.

**Specified capabilities:** fixed-step clock, seeded random source, immutable run configuration, headless runner, structured event stream, canonical snapshots, versioned validated JSON snapshots, dependency-light tests, and benchmark seams. Rendering consumes state and events but does not own domain transitions.

**Phase gate:** two headless runs with the same seed/configuration produce byte-identical canonical state/event output; a different seed can change stochastic output; save/load preserves state and deterministic resume; no domain module requires display initialization.

**Phase requirements:** REQ-P1-001 explicit integer ticks; REQ-P1-002 seed-owned randomness; REQ-P1-003 display-free execution; REQ-P1-004 ordered events and snapshots; REQ-P1-005 versioned validated non-executable snapshots.

### Phase 2 — Complete individual life cycles and relationships

**Purpose:** make survival, love, reproduction, and inheritance meaningful selection pressures.

**Specified capabilities:** explicit needs, injury/recovery, aging, death removal, fertility, children, pair bonding, love/affinity, courtship, consent/rejection, pregnancy, gestation, birth, childcare, inherited genome, meaningful skill progression, and per-agent scheduling with explicit ownership.

**Relationship and reproduction rules:** love is an emergent relationship state, not a scripted label. Compatible adults accumulate or lose affinity from explicit interactions, shared experiences, proximity, trust, and rejection events. Courtship requires time and consent; either participant may decline. A reproduction attempt requires configured fertility/age conditions, a mutually accepted bond, and enough settlement capacity/resources. Pregnancy and gestation advance in simulation ticks. Birth creates a distinct child with its own needs, memory, learned behavior, and inherited genome produced from the parents under configured crossover/mutation rules. Parents may incur childcare obligations and relationship changes after birth.

**Phase gate:** deterministic tests cover need/injury/aging/death, affinity changes, consent/rejection, gestation, birth, child/parent separation, and inheritance. Parent genomes are not mutated by child learning. Population and resource totals remain conserved except for documented sources/sinks.

**Phase requirements:** REQ-P2-001 explicit tick-driven needs, injury, aging, and death; REQ-P2-002 directed or symmetric affinity changes from explicit interaction events; REQ-P2-003 courtship and reproduction require adult/fertility conditions and mutual consent; REQ-P2-004 pregnancy, gestation, birth, and child state are explicit and capacity/resource constrained; REQ-P2-005 child genome inheritance is isolated from parent/child memory and learned behavior; REQ-P2-006 death and birth update ownership, jobs, inventories, and scheduler references atomically.

### Phase 3 — Build cognition and memory

**Purpose:** let people act on bounded perception and experience rather than omniscient shared state.

**Specified capabilities:** perception limits, episodic observations, semantic facts, learned world models, memory decay/reinforcement, lifetime learning, and a separate settlement knowledge projection.

**Phase gate:** an agent cannot act on an out-of-range undiscovered resource without a memory path; two agents can hold different memories of one world; settlement knowledge changes only through explicit sharing/observation events.

**Phase requirements:** REQ-P3-001 bounded perception; REQ-P3-002 separate episodic and semantic memory; REQ-P3-003 deterministic memory retention/decay; REQ-P3-004 settlement knowledge sharing through explicit events; REQ-P3-005 learned policy state remains distinct from inherited genome and relationship/economic state.

### Phase 4 — Grow settlements and economies

**Purpose:** make collective production and exchange respond to needs and constraints.

**Specified capabilities:** jobs, task allocation, material storage, buildings, production recipes, labor/logistics, territory, population growth, and the requested money/market layer. A recipe declares material inputs and labor ticks. Production reserves inputs, progresses only on simulation ticks, and creates output on completion. A market owns actor or treasury balances and good ownership; a purchase transfers money and goods atomically. A quote has a cost floor based on material prices plus labor/time and a demand-pressure component based on outstanding demand relative to available stock. Someone creating a good therefore incurs explicit material and time cost; someone needing it creates demand that can raise the transaction price.

**Phase gate:** deterministic integration tests show that production cannot complete without inputs or enough labor ticks, successful purchases conserve money and goods, invalid transactions have no partial side effects, demand increases the price under fixed supply, and replenishing supply reduces pressure. Full Phase 4 requires multi-seed evaluation before claiming emergent specialization or stable market behavior.

**Phase requirements:** REQ-P4-001 explicit jobs, recipes, materials, goods, storage, supply, demand, price, and wallet/treasury state; REQ-P4-002 production consumes exactly declared materials and explicit labor time; REQ-P4-003 a cost floor incorporates material and labor/time foundations; REQ-P4-004 greater accepted demand raises or preserves price under fixed supply and configured bounds; REQ-P4-005 trades transfer money and goods atomically and conserve totals; REQ-P4-006 logistics, capacity, and incentives can produce specialization without scripted roles; REQ-P4-007 economic outcomes are explainable from recorded state transitions and remain separate from memory, genome, and learned behavior.

### Phase 5 — Research technologies

**Purpose:** let settlements discover and diffuse capabilities instead of receiving hard-coded unlocks.

**Specified capabilities:** discoverable knowledge, prerequisites, experimentation cost/risk, research work, diffusion through contact/trade, and technologies that alter actions, recipes, or efficiency.

**Phase gate:** prerequisites and discovery are enforced, experimentation is deterministic under replay, and technology ownership remains distinct from individual memory, genome, and learned behavior.

**Phase requirements:** REQ-P5-001 explicit technology prerequisites and ownership; REQ-P5-002 experimentation consumes tick/resources and records success or failure; REQ-P5-003 technology effects alter actions, recipes, productivity, or constraints through rules; REQ-P5-004 knowledge diffuses only through explicit observation/contact/trade events.

### Phase 6 — Add diplomacy and conflict

**Purpose:** make inter-settlement relationships respond to claims, trade opportunities, alliances, migration, resource pressure, and conflict.

**Specified capabilities:** territory claims, inter-settlement trade, migration, treaties/alliances, persistent inter-settlement memory, resource-pressure decisions, and combat with injury/death consequences.

**Phase gate:** claims, transfers, treaty changes, migration, and combat are deterministic transitions; conflict cannot create resources or money; multi-seed evaluation reports distributions rather than relying on one visual run.

**Phase requirements:** REQ-P6-001 explicit territory, trade, alliance, migration, and conflict transitions; REQ-P6-002 resource pressure and settlement incentives affect decisions through observable state; REQ-P6-003 inter-settlement memory is persistent and separately owned; REQ-P6-004 combat has deterministic consequences for people, goods, territory, and settlement state.

### Phase 7 — Scale from villages to cities

**Purpose:** make long runs measurable and affordable at larger populations.

**Specified capabilities:** profiling, bounded parallelism with explicit ownership, compact observability, replay tooling, deterministic checkpoints, and multi-seed long-run evaluation.

**Phase gate:** benchmark scale, warm-up, repetitions, and target performance are recorded; replay from a checkpoint reproduces subsequent canonical output; no unsynchronized shared mutation is introduced; emergent claims use quantitative multi-seed evidence.

**Phase requirements:** REQ-P7-001 configurable workload and benchmark scale; REQ-P7-002 checkpoints, event streams, invariant counters, and replay inspection; REQ-P7-003 performance reports include population, world, ticks, warm-up, repetitions, and distributions; REQ-P7-004 emergent claims use approved multi-seed metrics and thresholds.

## 4. Current increment: deterministic simulation core

The first five vertical slices implement a pure-Python deterministic clock, seed-owned random source, display-free probe runner, structured events, canonical snapshots, a versioned JSON snapshot/resume seam, a headless lifecycle/relationship engine, bounded cognition/memory, a production/economy engine, and a technology engine. The new engine supports tick-driven needs, aging, injury/death, directed affinity, courtship/consent, pair bonds, pregnancy, birth, childcare, isolated inherited genomes, bounded observations, memory TTL, explicit knowledge sharing, learned policy, material/labor production, incentive-based jobs, wallets/treasuries, demand pricing, atomic trade, prerequisite-gated research, recipe effects, and treaty-gated diffusion. It does not replace the Pygame loop; diplomacy, conflict, and scale remain later tasks with separate gates.

### In scope

- Immutable configuration with explicit integer seed, world dimensions, population count, and tick semantics.
- A fixed-step clock advanced only by explicit calls.
- A controlled seeded random source owned by the headless runner.
- A small display-free probe world with stable agent identifiers and bounded deterministic movement; this is infrastructure evidence, not complete `Human` behavior.
- Ordered structured events and canonical JSON-compatible snapshots.
- Versioned JSON snapshots with schema validation and deterministic resume state.
- Dependency-light deterministic tests.

### Out of scope for this increment

- Cognition beyond the current bounded observations, memory TTL, learning, and explicit sharing hooks.
- Buildings beyond the current recipe/storage economy, plus diplomacy, conflict, and scale integration.
- Automatic integration of legacy neural-network decisions with the new core.
- Migration of legacy chromosome pickle files; no new compatibility commitment is made for those files.

## 5. Domain terms and state ownership

- **Simulation tick:** the only domain time unit; wall-clock time must not affect transitions.
- **Seeded random source:** an explicit deterministic source owned by one runner, never process-global randomness.
- **Core state:** tick, configuration, stable probe-agent positions, and random-source state, owned by the headless core.
- **Event:** an ordered serializable state-transition record, owned by the core event log.
- **Snapshot:** a canonical JSON-compatible observation of state and schema version; it must not execute data when loaded.
- **Love/affinity:** relationship state derived from explicit interactions and consent, owned by the relationship system rather than copied into genomes or settlement knowledge.
- **Wallet/market/demand/supply/price:** Phase 4 economic state owned by actor wallets and settlement treasuries, with explicit recipes, reservations, quotes, and atomic exchange.
- **Individual state, memory, inherited genome, learned behavior, settlement knowledge:** separate categories that future phases must not alias or silently merge.

## 6. Numbered requirements for the current increment

### REQ-001 — Explicit fixed-step clock

The headless core MUST advance through an explicit integer tick. `step()` advances exactly one tick and `run(n)` advances exactly n ticks; zero is a no-op. Domain transitions MUST NOT read wall-clock time or frame rate.

### REQ-002 — Controlled seeded randomness

All stochastic behavior in the new headless core MUST use a configured seed-owned random source. The same initial configuration and seed MUST produce the same state transitions; changing the seed MUST be allowed to change probe behavior.

### REQ-003 — Display-free headless runner

The new core MUST run and be importable without initializing Pygame, opening a display, importing NumPy, or depending on legacy mutable globals.

### REQ-004 — Canonical events and snapshots

Each transition MUST be represented by an ordered structured event. A canonical snapshot MUST expose tick, configuration, probe-agent state, and random-source state. Equivalent runs MUST compare equal without relying on object identity or incidental dictionary insertion order.

### REQ-005 — Versioned validated JSON snapshots

The core MUST save a versioned non-executable JSON envelope and MUST validate schema version, dimensions, tick, agent identifiers, positions, seed, and random-source state before loading. Malformed or incompatible data MUST be rejected without executing arbitrary code or partially replacing current state.

### REQ-006 — Explicit configuration boundaries

Configuration MUST validate positive world dimensions, non-negative population, and a valid integer seed; booleans MUST NOT be accepted as numeric configuration values. It MUST be inspectable in snapshots and must not be hidden in class-level mutable state.

### REQ-007 — Regression tests and documentation

The repository MUST include dependency-light deterministic tests for clock boundaries, seed repeatability, changed-seed behavior, bounded movement, snapshot round-trip/resume, schema rejection, and no-display import. The README MUST label the core probe as implemented and Phase 2 love/reproduction and Phase 4 money as specified/deferred.

## 7. Invariants and explicit failure behavior

- Tick is a non-negative integer and never moves backwards.
- Probe-agent identifiers are stable and unique; positions remain within configured bounds.
- The seeded random source is owned by one core instance; no global source or wall-clock reseeding is used.
- Negative or non-integral step counts fail before state changes.
- Loading malformed JSON, unsupported schema versions, invalid dimensions, invalid seed/state, duplicate/missing agents, or out-of-bounds positions raises a documented validation error without partially replacing the current core.
- Snapshot save/load does not deserialize pickle or execute data.
- Event sequence numbers are strictly increasing and event ticks are non-decreasing.
- The core probe must not be described as completed lifecycle, love, reproduction, economy, or civilization behavior.

## 8. Observability, configuration, and persistence

The implementation exposes seed, world dimensions, population, current tick, stable probe-agent positions, random-source state, ordered events, and schema version. JSON snapshots support deterministic resume/replay and inspection. Existing chromosome pickle files remain untouched and are not treated as compatible core snapshots. No money, production, love, or reproduction state is persisted by this increment.

## 9. Risks, assumptions, and open decisions

- **Non-blocking assumption:** the first headless probe uses bounded deterministic movement solely to prove the core seam; it does not replace `Human` behavior.
- **Non-blocking risk:** the legacy Pygame loop still has wall-clock and concurrency defects. This foundation isolates new logic but does not claim to repair those paths.
- **Blocking Phase 2 decision:** choose symmetric pair affinity, two directed preferences, or both; recommended first model is directed affinity plus a mutual-consent threshold.
- **Blocking Phase 2 decision:** define adult age, fertility, gestation duration, childcare/resource costs, settlement capacity, and failure behavior if a partner disappears.
- **Blocking Phase 4 decision:** choose colony treasury, individual wallets, or both; choose whether labor is paid or represented only as cost basis.
- **Non-blocking decision:** currency display name and price formatting.

## 10. Acceptance criteria

| ID | Given / When / Then | Evidence |
| --- | --- | --- |
| AC-001 / REQ-001 | Given a new core, when `step()` and `run(n)` are called, then tick advances exactly by 1 and n; zero is a no-op. | Deterministic unit tests. |
| AC-002 / REQ-002 | Given identical config/seed and run length, when two cores run, then snapshots/events are equal; a different seed can produce a different probe trace. | Repeatability and changed-seed tests. |
| AC-003 / REQ-003 | Given a host with no display, when the core is imported and run, then no Pygame display initialization is required. | Import test and dependency inspection. |
| AC-004 / REQ-004 | Given a tick transition, when events and snapshot are inspected, then stable sequence/order and canonical JSON-compatible state are present. | Event/snapshot tests. |
| AC-005 / REQ-005 | Given a saved versioned JSON snapshot, when it is loaded into a new core and resumed, then subsequent output matches an uninterrupted run; malformed/unsupported data is rejected. | Round-trip/resume and validation tests. |
| AC-006 / REQ-006 | Given invalid dimensions, population, seed, boolean-as-integer values, or step count, when construction/advance is attempted, then it fails before state mutation. | Boundary validation tests. |
| AC-007 / REQ-007 | Given the docs and tests, when the new core is used, then current core behavior is labeled implemented and Phase 2 love/reproduction plus Phase 4 money are labeled specified/deferred. | README review and test command evidence. |

## 11. Deferred roadmap work

The next task after this increment is the Phase 6 diplomacy/conflict slice. Cognition, economy, and technology are implemented in the headless path; diplomacy, conflict, and scale remain deferred.
