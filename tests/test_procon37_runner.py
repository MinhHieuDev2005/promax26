import json
import subprocess
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RUNNER = ROOT / "solvers" / "procon37kyogi_runner.py"
SAMPLE = ROOT / "solvers" / "procon37kyogi_upstream" / "problems" / "sample_16.json"


class Procon37RunnerTests(unittest.TestCase):
    def run_runner(self, payload):
        result = subprocess.run(
            [sys.executable, str(RUNNER)], input=json.dumps(payload),
            text=True, capture_output=True, timeout=30,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads(result.stdout)

    def test_roles_and_plan_protocol(self):
        config = json.loads(SAMPLE.read_text(encoding="utf-8"))
        roles = self.run_runner({"op": "roles", "config": config})
        self.assertTrue(roles["ok"])
        self.assertEqual(len(roles["roles"]), len(config["agents"]))

        agents = [
            {"pos": position, "fuel": config["fuelLimits"] if kind == 0 else 0, "kind": kind}
            for position, kind in zip(config["agents"], roles["roles"])
        ]
        response = self.run_runner({
            "op": "plan", "config": config,
            "state": {"day": 1, "stepsCount": config["daySteps"][0],
                      "agents": agents, "traffics": []},
            "stock": [spot["stocks"] for spot in config["spots"]],
        })
        self.assertTrue(response["ok"], response)
        self.assertEqual(len(response["plan"]), len(agents))
        self.assertGreater(response["diagnostics"]["candidates"], 1)


if __name__ == "__main__":
    unittest.main()
