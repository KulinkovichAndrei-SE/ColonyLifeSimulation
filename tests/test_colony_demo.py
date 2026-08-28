import json
import subprocess
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class ColonyDemoTests(unittest.TestCase):
    def test_all_phase_demo_reports_replay_and_seed_evidence(self):
        result = subprocess.run(
            [sys.executable, "colony_demo.py"],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        evidence = json.loads(result.stdout)
        self.assertTrue(evidence["children"])
        self.assertTrue(evidence["technologies"]["settlement-000"])
        self.assertTrue(evidence["replay_matches"])
        self.assertEqual(evidence["multi_seed_sample_size"], 32)
        self.assertIn("event_totals", evidence["emergence_metrics"])
        self.assertEqual(evidence["benchmark"]["repetitions"], 2)


if __name__ == "__main__":
    unittest.main()
