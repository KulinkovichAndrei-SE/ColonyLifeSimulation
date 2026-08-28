import json
import subprocess
import sys
import tempfile
import unittest
from dataclasses import FrozenInstanceError
from pathlib import Path

from simulation_core import (
    DeterministicSimulation,
    SimulationClock,
    SimulationConfig,
    SnapshotValidationError,
    canonical_json,
)


ROOT = Path(__file__).resolve().parents[1]


class SimulationCoreTests(unittest.TestCase):
    def make_config(self, seed=17, population=3):
        return SimulationConfig(seed=seed, width=12, height=8, population=population)

    def test_clock_step_run_and_zero_are_exact(self):
        clock = SimulationClock()
        self.assertEqual(clock.tick, 0)
        self.assertEqual(clock.step(), 1)
        self.assertEqual(clock.advance(4), 5)
        self.assertEqual(clock.advance(0), 5)

        with self.assertRaises(ValueError):
            clock.advance(-1)
        with self.assertRaises(ValueError):
            clock.advance(1.5)
        self.assertEqual(clock.tick, 5)

    def test_config_is_frozen_and_rejects_invalid_numeric_values(self):
        config = self.make_config()
        with self.assertRaises(FrozenInstanceError):
            config.seed = 18

        invalid_values = [
            {"width": 0},
            {"height": -1},
            {"population": -1},
            {"seed": True},
            {"width": True},
            {"height": False},
            {"population": True},
        ]
        for overrides in invalid_values:
            values = {
                "seed": 17,
                "width": 12,
                "height": 8,
                "population": 3,
            }
            values.update(overrides)
            with self.subTest(overrides=overrides), self.assertRaises(ValueError):
                SimulationConfig(**values)

    def test_same_seed_produces_same_canonical_trace(self):
        first = DeterministicSimulation(self.make_config()).run(5)
        second = DeterministicSimulation(self.make_config()).run(5)

        self.assertEqual(first.canonical_json(), second.canonical_json())
        self.assertEqual(
            [event.as_dict() for event in first.events],
            [event.as_dict() for event in second.events],
        )

    def test_changed_seed_changes_probe_initialization(self):
        first = DeterministicSimulation(self.make_config(seed=1))
        second = DeterministicSimulation(self.make_config(seed=2))

        self.assertNotEqual(first.random_state, second.random_state)
        self.assertNotEqual(
            [agent.as_dict() for agent in first.agents],
            [agent.as_dict() for agent in second.agents],
        )

    def test_probe_ids_and_positions_stay_bounded(self):
        simulation = DeterministicSimulation(self.make_config()).run(50)
        self.assertEqual(
            [agent.agent_id for agent in simulation.agents],
            ["probe-0000", "probe-0001", "probe-0002"],
        )
        for agent in simulation.agents:
            self.assertGreaterEqual(agent.x, 0)
            self.assertLess(agent.x, simulation.config.width)
            self.assertGreaterEqual(agent.y, 0)
            self.assertLess(agent.y, simulation.config.height)

    def test_events_have_stable_fields_and_order(self):
        simulation = DeterministicSimulation(self.make_config(population=2)).run(2)
        self.assertEqual(simulation.events[0].event_type, "tick_advanced")
        self.assertEqual(simulation.events[1].event_type, "probe_moved")
        self.assertEqual(simulation.events[3].event_type, "tick_advanced")
        self.assertEqual(
            [event.sequence for event in simulation.events],
            list(range(1, len(simulation.events) + 1)),
        )
        self.assertEqual(
            [event.tick for event in simulation.events],
            [1, 1, 1, 2, 2, 2],
        )
        self.assertEqual(
            set(simulation.events[1].as_dict()),
            {
                "sequence",
                "tick",
                "event_type",
                "agent_id",
                "previous_position",
                "position",
            },
        )
        self.assertEqual(
            simulation.canonical_json(), canonical_json(simulation.snapshot())
        )

    def test_snapshot_round_trip_and_resume_are_deterministic(self):
        config = self.make_config(seed=91)
        checkpoint = DeterministicSimulation(config).run(3)
        uninterrupted = DeterministicSimulation(config).run(6)

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "checkpoint.json"
            checkpoint.save_json(path)
            loaded = DeterministicSimulation.load_json(path)
            self.assertEqual(loaded.canonical_json(), checkpoint.canonical_json())
            loaded.run(3)

        self.assertEqual(loaded.canonical_json(), uninterrupted.canonical_json())

    def test_invalid_snapshot_is_rejected_without_affecting_existing_state(self):
        simulation = DeterministicSimulation(self.make_config()).run(2)
        before = simulation.canonical_json()
        invalid = simulation.snapshot()
        invalid["schema_version"] = 999

        with self.assertRaises(SnapshotValidationError):
            DeterministicSimulation.from_snapshot(invalid)

        self.assertEqual(simulation.canonical_json(), before)

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "bad.json"
            path.write_text(json.dumps({"schema_version": 1}), encoding="utf-8")
            with self.assertRaises(SnapshotValidationError):
                DeterministicSimulation.load_json(path)

    def test_no_display_or_legacy_dependencies_are_needed(self):
        code = (
            "import sys; "
            "from simulation_core import DeterministicSimulation, SimulationConfig; "
            "DeterministicSimulation(SimulationConfig(seed=3, width=4, height=4, population=1)).run(1); "
            "assert not any(name == 'pygame' or name.startswith('pygame.') for name in sys.modules)"
        )
        result = subprocess.run(
            [sys.executable, "-c", code],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_headless_demo_reports_successful_resume(self):
        result = subprocess.run(
            [sys.executable, "headless_demo.py"],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        evidence = json.loads(result.stdout)
        self.assertTrue(evidence["resume_matches_uninterrupted"])
        self.assertEqual(evidence["checkpoint_tick"], 4)
        self.assertEqual(evidence["final_tick"], 7)


if __name__ == "__main__":
    unittest.main()
