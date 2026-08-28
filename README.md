# Colony Life Simulation

An experimental artificial-life simulation in which autonomous people and their settlements compete for resources, learn through selection, and gradually develop more complex collective behavior.

> **Project status:** research prototype / pre-alpha. The active `main.py` path is a playable Pygame view over the deterministic multi-phase engine; the older simulation remains available as a comparison path.

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
- Phase 4 economy in the same headless engine: recipes, material reservation, labor ticks, bounded storage capacity, incentive-based job allocation, wallets, settlement treasuries, demand pressure, material/time cost floors, atomic purchases, and specialization metrics.
- Phase 5 technology in the same headless engine: prerequisite-gated research, deterministic success/failure, tick/resource costs, recipe effects, and treaty-gated diffusion.
- Phase 6 diplomacy/conflict in the same headless engine: territory claims, treaties, migration, cross-settlement trade gates, persistent relation memory, deterministic combat, injury/death, and territory transfer.
- A Pygame presentation layer in `pygame_app.py`; `main.py` now advances and renders the deterministic engine. The UI is observational: click residents to inspect them, while all movement, work, learning, love, reproduction, trade, research, diplomacy, and conflict are selected by the simulation AI.
- Phase 7 replay/evaluation support: immutable checkpoint hashes, deterministic replay comparison, explicit 32-seed event/winner/specialization reports, and benchmark reports with warm-up, repetitions, runtime, and memory fields.

The deterministic core and Phases 2–7 engine are implemented infrastructure/domain slices, and the new Pygame UI consumes that state without owning domain rules. Resident and settlement decisions use deterministic learned policies and explicit rewards; this is an explainable policy-learning layer, not a claim of a neural-network trainer. The legacy Pygame simulation remains a separate comparison path.

Several additional resource and building classes already exist in the code (`Stone`, `Iron`, `Copper`, `Gold`, `Barn`, `Tavern`, and `Farm`), but they are not connected to the active simulation loop.

## How the prototype works

1. `main.py` creates a configured `ColonySimulation` and `PygameSimulationApp`.
2. The UI calls one explicit simulation tick per unpaused frame and renders the resulting state.
3. Click an agent to inspect its age, needs, wallet, job, bond, children, memory, and learning state.
4. The simulation AI calls domain transitions for production, demand, research, courtship, reproduction, diplomacy, trade, and conflict; events appear in the right-hand panel.
5. The legacy `InitialGame -> Colony -> Human` path remains available in its original modules for comparison, but is no longer the `main.py` entry path.

Keyboard input is limited to Space (pause/continue or restart after game over), Up (faster), and Down (slower). Closing the Pygame window exits the active run.

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
| `colony_simulation.py` | Deterministic multi-phase domain engine |
| `pygame_app.py` | Pygame renderer and input adapter |
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

The renderer opens a `1440 x 900` window by default. The map and ledger are read-only views; Space, Up, and Down control only the simulation loop. The `save/` directory is still required only by the legacy comparison path.

## Current limitations

- The legacy simulation remains tightly coupled to wall-clock time, while the new Pygame UI uses the deterministic engine through `pygame_app.py`.
- Legacy random seeds, simulation speed, world size, and population size are not externally configurable; the core probe has explicit configuration.
- Shared mutable state is updated from nested thread pools without an explicit synchronization model.
- The deterministic core has a dependency-light test suite, but the legacy simulation still lacks complete integration coverage, dependency locking, packaging metadata, CI, and a benchmark harness.
- The legacy simulation still evolves chromosomes separately; the active engine models biological reproduction and inherited genomes explicitly.
- Skills and learned policies are intentionally lightweight and explainable; a richer neural or population-training system remains roadmap work.
- Legacy persistence uses unversioned pickle files and assumes the `save/` directory already exists; the new core uses versioned JSON snapshots but does not migrate chromosome saves.
- Advanced resources and buildings are defined but disabled or unused.
- Love/affinity, courtship, consent, reproduction, children, pregnancy, inheritance, childcare, bounded memory, and learning are implemented in the active engine and selected autonomously.
- Money, material/time-based production costs, supply/demand pricing, wallets/treasury, and atomic trade are implemented in the active engine; treaty-connected AI settlements can trade food when inventories diverge.
- Technology prerequisites, research, recipe effects, and treaty-gated diffusion are implemented in the active engine; settlement AI can share technology after contact.
- Territory claims, treaties, migration, relation memory, and deterministic conflict consequences are implemented in the active engine and selected autonomously.
- The Pygame UI is intentionally an observation surface, not a command console; direct domain APIs remain available for deterministic tests and tooling.
- The benchmark harness reports workload evidence, but it does not yet claim a target hardware threshold or production-scale performance result.

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
   - The first deterministic technology slice is implemented: prerequisites, funded research ticks, rule effects, and treaty/contact-gated diffusion. The current UI exposes research status; deeper visualization remains deferred.
6. **Add diplomacy and conflict**
   - The first deterministic diplomacy/conflict slice is implemented: claims, trade gates, treaties, migration, resource-pressure decisions, combat, and persistent inter-settlement memory. The current UI exposes the resulting state and events while settlement AI chooses the actions.
7. **Scale from villages to cities**
   - The first deterministic scale/replay slice is implemented: checkpoints, replay hashes, multi-seed reports, and benchmark metadata. Larger optimization and approved production-scale thresholds remain follow-up work.

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
