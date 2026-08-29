import json
import subprocess
import sys
import unittest
from pathlib import Path

from colony_simulation import ColonyConfig, ColonySimulation
from simulation_core import canonical_json


ROOT = Path(__file__).resolve().parents[1]


class FastTrainingTests(unittest.TestCase):
    def fixture(self, **overrides):
        values = {
            "seed": 7,
            "width": 20,
            "height": 12,
            "population": 4,
            "settlement_count": 2,
            "adult_age": 2,
            "fertility_start": 2,
            "fertility_end": 25,
            "max_age": 200,
            "gestation_ticks": 2,
            "perception_radius": 5,
        }
        values.update(overrides)
        return ColonyConfig(**values)

    def test_training_windows_are_continuous_and_observable(self):
        simulation = ColonySimulation(self.fixture())

        report = simulation.run_training(3, ticks_per_generation=5)

        self.assertEqual(report["requested_generations"], 3)
        self.assertEqual(report["executed_generations"], 3)
        self.assertEqual(report["completed_generations"], 3)
        self.assertEqual(report["unexecuted_generations"], 0)
        self.assertEqual(report["executed_ticks"], 15)
        self.assertEqual(
            [(window["start_tick"], window["end_tick"]) for window in report["windows"]],
            [(0, 5), (5, 10), (10, 15)],
        )
        self.assertGreater(report["final_metrics"]["event_counts"].get("learning_updated", 0), 0)
        for window in report["windows"]:
            self.assertEqual(window["births"], window["interval_event_counts"].get("child_born", 0))
            self.assertEqual(window["deaths"], window["interval_event_counts"].get("agent_died", 0))
            self.assertEqual(window["end_tick"] - window["start_tick"], window["actual_ticks"])
            self.assertIn("specialization", window["invariants"])
            self.assertEqual(len(window["state_hash"]), 64)
            self.assertEqual(len(window["event_hash"]), 64)

    def test_training_is_deterministic_and_preserves_continuous_state(self):
        first = ColonySimulation(self.fixture()).run_training(3, ticks_per_generation=5)
        second = ColonySimulation(self.fixture()).run_training(3, ticks_per_generation=5)

        self.assertEqual(canonical_json(first), canonical_json(second))
        uninterrupted = ColonySimulation(self.fixture()).run(15)
        self.assertEqual(first["final_metrics"]["state_hash"], uninterrupted.state_hash())
        self.assertEqual(first["final_metrics"]["event_hash"], uninterrupted.event_hash())

    def test_terminal_state_records_partial_window_and_stops(self):
        simulation = ColonySimulation(self.fixture(population=2))
        for agent in simulation.alive_agents:
            agent.health = 1
            agent.hunger = 0

        report = simulation.run_training(4, ticks_per_generation=5)

        self.assertEqual(report["executed_generations"], 1)
        self.assertEqual(report["completed_generations"], 0)
        self.assertEqual(report["unexecuted_generations"], 3)
        self.assertEqual(report["executed_ticks"], 1)
        self.assertTrue(report["game_over"])
        self.assertEqual(report["terminal_reason"], "all_agents_dead")
        self.assertEqual(report["windows"][0]["actual_ticks"], 1)
        self.assertEqual(report["windows"][0]["deaths"], 2)
        self.assertEqual(simulation.tick, 1)

    def test_continue_mode_runs_the_requested_workload_after_terminal_state(self):
        simulation = ColonySimulation(self.fixture(population=2))
        for agent in simulation.alive_agents:
            agent.health = 1
            agent.hunger = 0

        report = simulation.run_training(
            4,
            ticks_per_generation=5,
            terminal_mode="continue_after_game_over",
        )

        self.assertEqual(report["terminal_mode"], "continue_after_game_over")
        self.assertEqual(report["executed_generations"], 4)
        self.assertEqual(report["completed_generations"], 4)
        self.assertEqual(report["unexecuted_generations"], 0)
        self.assertEqual(report["executed_ticks"], 20)
        self.assertTrue(report["terminal_reached"])
        self.assertEqual(report["terminal_tick"], 1)
        self.assertEqual(report["post_terminal_ticks"], 19)
        self.assertTrue(all(window["actual_ticks"] == 5 for window in report["windows"]))
        self.assertEqual(simulation.tick, 20)

    def test_training_rejects_an_unknown_terminal_mode(self):
        with self.assertRaises(ValueError):
            ColonySimulation(self.fixture()).run_training(1, terminal_mode="reset")

    def test_zero_windows_is_a_deterministic_no_op(self):
        report = ColonySimulation(self.fixture()).run_training(0, ticks_per_generation=5)

        self.assertEqual(report["windows"], [])
        self.assertEqual(report["executed_generations"], 0)
        self.assertEqual(report["completed_generations"], 0)
        self.assertEqual(report["unexecuted_generations"], 0)
        self.assertEqual(report["executed_ticks"], 0)
        self.assertEqual(report["final_metrics"]["tick"], 0)

    def test_training_arguments_use_strict_integer_validation(self):
        simulation = ColonySimulation(self.fixture())

        with self.assertRaises(ValueError):
            simulation.run_training(True, ticks_per_generation=5)
        with self.assertRaises(ValueError):
            simulation.run_training(1, ticks_per_generation=False)
        with self.assertRaises(ValueError):
            simulation.run_training(-1, ticks_per_generation=5)
        with self.assertRaises(ValueError):
            simulation.run_training(1, ticks_per_generation=0)

    def test_cli_emits_one_canonical_json_report_without_pygame(self):
        command = [
            sys.executable,
            "fast_training.py",
            "--seed",
            "7",
            "--generations",
            "3",
            "--ticks-per-generation",
            "5",
            "--population",
            "4",
            "--max-age",
            "200",
        ]
        first = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, check=False)
        second = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, check=False)

        self.assertEqual(first.returncode, 0, first.stderr)
        self.assertEqual(second.returncode, 0, second.stderr)
        self.assertEqual(first.stdout, second.stdout)
        report = json.loads(first.stdout)
        self.assertEqual(first.stdout, canonical_json(report) + "\n")
        self.assertEqual(report["executed_ticks"], 15)
        self.assertEqual(len(report["windows"]), 3)

        import_check = subprocess.run(
            [sys.executable, "-c", "import sys; import fast_training; print('pygame' in sys.modules)"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(import_check.returncode, 0, import_check.stderr)
        self.assertEqual(import_check.stdout.strip(), "False")

    def test_cli_continues_after_game_over_by_default(self):
        command = [
            sys.executable,
            "fast_training.py",
            "--generations",
            "3",
            "--ticks-per-generation",
            "2",
            "--settlements",
            "1",
            "--population",
            "2",
            "--max-age",
            "200",
        ]
        continued = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, check=False)
        stopped = subprocess.run(
            [*command, "--stop-on-game-over"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )

        self.assertEqual(continued.returncode, 0, continued.stderr)
        continued_report = json.loads(continued.stdout)
        self.assertEqual(continued_report["terminal_mode"], "continue_after_game_over")
        self.assertEqual(continued_report["executed_generations"], 3)
        self.assertEqual(continued_report["executed_ticks"], 6)
        self.assertEqual(continued_report["terminal_at_start"], True)
        self.assertEqual(continued_report["post_terminal_ticks"], 6)

        self.assertEqual(stopped.returncode, 0, stopped.stderr)
        stopped_report = json.loads(stopped.stdout)
        self.assertEqual(stopped_report["terminal_mode"], "diagnostic_stop")
        self.assertEqual(stopped_report["executed_ticks"], 0)
        self.assertEqual(stopped_report["unexecuted_generations"], 2)

    def test_cli_rejects_invalid_input_without_success_json(self):
        invalid_commands = [
            ["--generations", "-1"],
            ["--generations", "1", "--ticks-per-generation", "0"],
            ["--generations", "not-an-int"],
            ["--generations", "1", "--width", "0"],
            ["--generations", "1", "--population", "-1"],
        ]
        for arguments in invalid_commands:
            result = subprocess.run(
                [sys.executable, "fast_training.py", *arguments],
                cwd=ROOT,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertNotEqual(result.returncode, 0, arguments)
            self.assertEqual(result.stdout, "", arguments)
            self.assertTrue(result.stderr.strip(), arguments)

    def test_cli_accepts_zero_windows(self):
        result = subprocess.run(
            [sys.executable, "fast_training.py", "--generations", "0"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads(result.stdout)
        self.assertEqual(report["requested_generations"], 0)
        self.assertEqual(report["executed_ticks"], 0)
        self.assertEqual(report["windows"], [])


if __name__ == "__main__":
    unittest.main()
