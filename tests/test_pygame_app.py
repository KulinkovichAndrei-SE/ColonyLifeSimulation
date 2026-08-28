import os
import subprocess
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class PygameAppTests(unittest.TestCase):
    def test_pygame_ui_runs_a_bounded_dummy_display_session(self):
        environment = os.environ.copy()
        environment["SDL_VIDEODRIVER"] = "dummy"
        result = subprocess.run(
            [sys.executable, "main.py", "--frames", "4"],
            cwd=ROOT,
            env=environment,
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("pygame", result.stdout.lower())

    def test_action_keys_do_not_mutate_the_observation_ui(self):
        os.environ["SDL_VIDEODRIVER"] = "dummy"
        from pygame_app import PygameSimulationApp

        app = PygameSimulationApp(frames_per_second=12)
        try:
            before_tick = app.simulation.tick
            before_speed = app.frames_per_second
            before_paused = app.paused
            app._handle_key(app.pygame.K_a)
            self.assertEqual(app.simulation.tick, before_tick)
            self.assertEqual(app.frames_per_second, before_speed)
            self.assertEqual(app.paused, before_paused)
        finally:
            app.close()


if __name__ == "__main__":
    unittest.main()
