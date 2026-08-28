# Colony Life Simulation

An experimental artificial-life simulation in which autonomous people and their settlements compete for resources, learn through selection, and gradually develop more complex collective behavior.

> **Project status:** legacy research prototype / pre-alpha. The repository contains a playable visual simulation, but it is not yet the complete settlement-to-civilization system described in the roadmap below.

## Vision

The long-term goal is to start with small groups of people in an unknown procedural world and let both individuals and settlements develop over time. People should perceive, remember, learn, work, reproduce, and make decisions. Settlements should accumulate shared knowledge, build economies and cities, discover technologies, negotiate, trade, and eventually compete or fight over territory and scarce resources.

The interesting behavior should emerge from the simulation rules, agent cognition, learning, and selection rather than from scripts that force a predetermined story.

## What exists today

Version 1.0 implements the first prototype loop:

- A procedurally populated `73 x 33` tile world rendered with Pygame.
- Trees and berry bushes placed randomly at the beginning of each run.
- Four color-coded colonies, each starting with five men and five women.
- Individual state for health, hunger, age in ticks, fitness, inventory, skills, known tiles, and a chromosome.
- Eight-direction movement, local perception, random exploration, and colony-level sharing of discovered map objects.
- Four available actions: cut trees, gather berries, build a house, and eat.
- Shared colony inventories and a simple colony level that increases when buildings are completed.
- A small neural policy per person: five inputs, one four-unit hidden layer, and four action outputs.
- An experimental genetic loop that selects, crosses over, and mutates neural-network chromosomes using runtime fitness.
- Loading and saving chromosome populations between runs through pickle files.
- Parallel colony and person updates using Python thread pools.
- A visual status panel showing each colony's color and shared resources.
- A separate display-free deterministic core probe in `simulation_core.py` with explicit ticks, seeded randomness, structured events, and versioned JSON snapshots; `headless_demo.py` demonstrates deterministic checkpoint/resume.
- A separate display-free multi-phase engine in `colony_simulation.py` with tick-driven needs, aging, death, directed affinity, consent, pair bonding, pregnancy, birth, childcare hooks, and isolated genome inheritance.
- Phase 3 cognition in the same headless engine: bounded perception, private episodic memory with deterministic TTL, semantic facts, explicit settlement knowledge sharing, and learned policy state isolated from genomes.
- Phase 4 economy in the same headless engine: recipes, material reservation, labor ticks, incentive-based job allocation, wallets, settlement treasuries, demand pressure, material/time cost floors, and atomic purchases.

The deterministic core and Phases 2–4 engine are implemented infrastructure/domain slices, not yet a replacement for the legacy Pygame simulation. Technology, diplomacy, conflict, and scale remain later roadmap phases.

Several additional resource and building classes already exist in the code (`Stone`, `Iron`, `Copper`, `Gold`, `Barn`, `Tavern`, and `Farm`), but they are not connected to the active simulation loop.

## How the prototype works

1. `InitialGame` creates the world and four colonies.
2. `FieldProcessing` creates the grid and places trees and berries.
3. Each colony creates ten people and assigns neural-network chromosomes.
4. On every update, the network chooses one of the four actions for each person.
5. People move toward remembered resources, gather them, return them to the shared inventory, eat, or build.
6. Fitness is recalculated and chromosomes are crossed over and mutated.
7. A colony is removed when it has no people left. The run ends when no more than one colony remains.

The outer loop starts another run automatically after a simulated game-over. Closing the Pygame window saves the surviving chromosome populations and exits.

## Project structure

| Path | Responsibility |
| --- | --- |
| `main.py` | Application entry point and repeated-run loop |
| `InitialGame.py` | World and colony initialization |
| `PygameModule.py` | Event loop, concurrent updates, and rendering |
| `Field.py` | A single world tile and its occupants |
| `FieldProcessing.py` | Grid generation, resource placement, and movement |
| `Human.py` | Person state, memory, actions, skills, and fitness |
| `Colony.py` | Shared knowledge, inventories, population updates, and genetic operations |
| `Resources.py` | Harvestable resource types |
| `Obj.py` | Building types |
| `neuralnetwork.py` | Lightweight NumPy neural network |
| `Animals.py` | Placeholder for a future animal system |
| `image/` | Pygame sprites |

## Quick start

The prototype has no pinned dependency manifest yet. It requires Python 3, [Pygame](https://www.pygame.org/), and [NumPy](https://numpy.org/).

```bash
python -m venv .venv
```

Activate the environment, then install the runtime packages:

```bash
python -m pip install pygame numpy
mkdir save
python main.py
```

To exercise the new display-free core without opening a window:

```bash
python headless_demo.py
python -m unittest discover -s tests -v
```

The renderer currently opens a fixed `1920 x 1080` window. There are no gameplay controls; close the window to save chromosomes and stop the program. The `save/` directory must exist before the first save.

## Current limitations

- The legacy simulation is tightly coupled to Pygame and wall-clock time; the new deterministic core probe is not yet wired into that loop.
- Legacy random seeds, simulation speed, world size, and population size are not externally configurable; the core probe has explicit configuration.
- Shared mutable state is updated from nested thread pools without an explicit synchronization model.
- The deterministic core has a dependency-light test suite, but the legacy simulation still lacks complete integration coverage, dependency locking, packaging metadata, CI, and a benchmark harness.
- Population evolution changes chromosomes of existing people; biological reproduction and inheritance are not modeled yet.
- The headless Phase 2 engine models biological reproduction and inheritance separately from the legacy chromosome evolution path.
- Skills are counters only and do not yet change productivity or unlock behavior.
- Legacy persistence uses unversioned pickle files and assumes the `save/` directory already exists; the new core uses versioned JSON snapshots but does not migrate chromosome saves.
- Advanced resources and buildings are defined but disabled or unused.
- Love/affinity, courtship, consent, reproduction, children, pregnancy, inheritance, and childcare are implemented in the headless Phase 2 engine but are not wired into the legacy Pygame loop.
- Bounded perception, episodic/semantic memory, learning, and explicit settlement knowledge sharing are implemented in the headless Phase 3 engine but are not wired into the legacy Pygame loop.
- Money, material/time-based production costs, supply/demand pricing, wallets/treasury, and atomic trade are implemented in the headless Phase 4 engine but are not wired into the legacy Pygame loop.
- Technologies, settlement memory, governance, professions, production chains, diplomacy, warfare, and city-scale growth are roadmap items, not current features.

The phased specifications and the active implementation plan are in [`docs/specs/roadmap.md`](docs/specs/roadmap.md) and [`docs/plans/roadmap.md`](docs/plans/roadmap.md).

## Development roadmap

The roadmap is intentionally capability-driven. Each milestone should be delivered as a small, measurable vertical slice with deterministic tests and observable simulation outcomes.

1. **Stabilize the simulation core**
   - Separate world updates from rendering.
   - Add a deterministic clock, seeded randomness, configuration, logging, and a headless runner.
   - Introduce tests, benchmarks, versioned saves, and dependency management.
2. **Complete individual life cycles**
   - Add needs, injury, aging, death, pair bonding, love/affinity, courtship, consent, reproduction, pregnancy, children, inheritance, childcare, and meaningful skill progression.
   - Replace global action throttles with per-agent scheduling and explicit ownership of mutable state.
3. **Build cognition and memory**
   - Define perception limits, episodic and semantic memory, learned world models, and lifetime learning. The first headless cognition slice is implemented; legacy integration remains deferred.
   - Keep individual memory separate from knowledge shared by a settlement.
4. **Grow settlements and economies**
   - The first headless economy slice is implemented: jobs, storage, production chains, wallets/treasury, money, and atomic trade.
   - Price created goods from explicit material and labor-time cost foundations, then adjust quotes from observable supply and demand. Legacy integration remains deferred.
   - Make settlement-level decisions depend on shared observations and measurable needs.
5. **Research technologies**
   - Add discoverable knowledge, prerequisites, experimentation, diffusion, and technologies that alter possible actions.
6. **Add diplomacy and conflict**
   - Model claims, trade, alliances, migration, resource pressure, combat, and persistent inter-settlement memory.
7. **Scale from villages to cities**
   - Profile and optimize the engine, add observability and replay tools, and validate long-running emergent behavior across many seeds.

## Agent-assisted development

This repository includes a Codex development pipeline for turning a product idea into a reviewable, verified increment:

```text
request -> specification -> technical plan -> implementation -> tests/evaluation -> quality gate
```

Use `$colony-development-pipeline` for non-trivial features, simulation changes, or architectural work. The repository-local skill defines artifact contracts and quality gates; specialized agents live in `.codex/agents/`. Read-only investigation and evaluation can run in parallel. Code-writing work runs in parallel only when file ownership is disjoint; otherwise it is intentionally sequential.

See [`AGENTS.md`](AGENTS.md) for repository rules and `.agents/skills/colony-development-pipeline/` for the complete workflow.

## Contributing

The canonical legacy branch is `master`. Develop changes on focused branches (the Codex convention is `codex/<task-name>`), keep the working tree reviewable, and do not mix broad cleanup with behavior changes. A change is complete only when its acceptance criteria are traced to tests or other reproducible evidence.

## License

This project is licensed under the GNU General Public License v3.0. See [`LICENSE`](LICENSE).
