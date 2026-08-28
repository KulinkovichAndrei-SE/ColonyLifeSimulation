"""Small deterministic, display-free demonstration of the simulation core."""

from pathlib import Path
from tempfile import TemporaryDirectory

from simulation_core import DeterministicSimulation, SimulationConfig, canonical_json


def main() -> None:
    config = SimulationConfig(seed=20260828, width=12, height=8, population=3)

    checkpoint_source = DeterministicSimulation(config).run(4)
    checkpoint = checkpoint_source.snapshot()

    uninterrupted = DeterministicSimulation(config).run(7)
    with TemporaryDirectory(prefix="colony-headless-") as temporary_directory:
        snapshot_path = Path(temporary_directory) / "checkpoint.json"
        checkpoint_source.save_json(snapshot_path)
        resumed = DeterministicSimulation.load_json(snapshot_path).run(3)

    resumed_json = resumed.canonical_json()
    uninterrupted_json = uninterrupted.canonical_json()
    evidence = {
        "checkpoint_tick": checkpoint["tick"],
        "final_tick": resumed.tick,
        "resume_matches_uninterrupted": resumed_json == uninterrupted_json,
        "snapshot": resumed.snapshot(),
    }
    print(canonical_json(evidence))


if __name__ == "__main__":
    main()
