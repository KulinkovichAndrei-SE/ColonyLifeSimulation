# Colony Life Simulation

An experimental artificial-life simulation written in Python. Autonomous people belong to competing colonies, explore a procedurally populated world, gather resources, build houses, and choose actions through neural networks whose weights evolve with a genetic algorithm.

> **Status:** Version 1.0 is a playable research prototype.

## Implemented features

- A `73 x 33` tile world rendered with Pygame.
- Random placement of 600 trees and 400 berry bushes at the start of every run.
- Four color-coded colonies.
- Ten people per colony: five men and five women.
- Individual health, hunger, lifetime in ticks, fitness, inventory, skills, map knowledge, and neural-network chromosome.
- Local perception and shared colony knowledge about discovered resources and empty tiles.
- Movement in eight directions and movement toward remembered targets.
- Four active actions:
  - cut down trees;
  - gather berries;
  - build houses;
  - eat berries from the colony inventory.
- Shared resource inventories for each colony.
- House construction using 50 units of wood.
- Colony level growth when a building is completed.
- A neural policy with five inputs, one four-unit hidden layer, and four action outputs.
- Genetic selection, chromosome crossover, and mutation based on runtime fitness.
- Loading and saving chromosome populations with pickle files.
- Parallel colony and person updates using Python thread pools.
- A visual status panel showing colony colors and shared resources.

The codebase also defines stone, iron, copper, gold, barns, taverns, farms, and an animal placeholder. These classes are not connected to the active Version 1.0 simulation loop.

## Simulation loop

1. The game creates the tile grid and randomly places trees and berries.
2. Four colonies spawn at random positions.
3. Each colony creates ten people and assigns neural-network chromosomes.
4. On every update, each person's neural network selects an action from their current state and colony resources.
5. People explore, remember nearby tiles, move toward resources, gather them, eat, or build.
6. Each person's fitness is recalculated, then chromosomes are crossed over and mutated.
7. A colony is removed after all of its people die.
8. The run ends when no more than one colony remains, and a new run starts automatically.

## Requirements

- Python 3
- Pygame
- NumPy
- A display capable of opening a `1920 x 1080` window

Dependency versions are not pinned in Version 1.0.

## Installation and launch

Clone the repository and enter its directory:

```bash
git clone https://github.com/KulinkovichAndrei-SE/The-project-of-simulation-of-life-of-colonies-of-inhabitants.git
cd The-project-of-simulation-of-life-of-colonies-of-inhabitants
```

Create and activate a virtual environment:

```bash
python -m venv .venv
```

Windows PowerShell:

```powershell
.\.venv\Scripts\Activate.ps1
```

Linux or macOS:

```bash
source .venv/bin/activate
```

Install the runtime dependencies:

```bash
python -m pip install pygame numpy
```

Create the directory used for chromosome saves:

```bash
mkdir save
```

Start the simulation from the repository root:

```bash
python main.py
```

## Controls and saves

The simulation runs automatically and has no gameplay controls. Close the Pygame window to save the current chromosome populations and exit.

Save files are written to:

```text
save/chromosome_list_colony1.pkl
save/chromosome_list_colony2.pkl
save/chromosome_list_colony3.pkl
save/chromosome_list_colony4.pkl
```

When these files exist, their chromosomes are loaded into the next simulation run. Pickle files must only be loaded from a trusted source.

## Project structure

| Path | Responsibility |
| --- | --- |
| `main.py` | Application entry point and repeated-run loop |
| `InitialGame.py` | World and colony initialization |
| `PygameModule.py` | Event loop, concurrent updates, and rendering |
| `Field.py` | A single world tile and its occupants |
| `FieldProcessing.py` | Grid generation, resource placement, and movement |
| `Human.py` | Person state, memory, actions, skills, and fitness |
| `Colony.py` | Shared knowledge, resources, population updates, and genetic operations |
| `Resources.py` | Harvestable resource types |
| `Obj.py` | Building types |
| `neuralnetwork.py` | NumPy neural network implementation |
| `Animals.py` | Placeholder animal class |
| `image/` | Pygame sprites |

## License

This project is licensed under the GNU General Public License v3.0. See [`LICENSE`](LICENSE).
