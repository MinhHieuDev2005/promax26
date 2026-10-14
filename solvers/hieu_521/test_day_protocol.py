"""Check all schedule indices in both supported wire formats."""
import json
from pathlib import Path
import subprocess
import os
import importlib.util

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("budget", ROOT / "solvers/chokudai/budget_sweep.py")
SIM = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(SIM)


def test_day_protocol():
    data = json.loads((ROOT / "cases/master/user-32x32-target500.snapshot.json").read_text(encoding="utf-8"))
    executable = ROOT / "build-pro26-hieu/hexa_udon_hieu_runner_v2.exe"
    for index, steps in enumerate(data["config"]["daySteps"]):
        for field, wire_day in (("day_info", index), ("state", index + 1)):
            state = dict(data["day_info"], day=wire_day)
            if field == "state":
                state["stepsCount"] = steps
            request = {"op": "plan", "config": data["config"], field: state,
                       "search": {"timeLimitMs": 100, "threads": 1}}
            process = subprocess.run([str(executable)], input=json.dumps(request),
                                     capture_output=True, text=True, encoding="utf-8",
                                     timeout=10, check=True)
            result = json.loads(process.stdout)
            assert result["ok"], result
            assert result["diagnostics"]["day_index"] == index
            assert result["diagnostics"]["steps"] == steps
            validation = dict(data, day_info=dict(data["day_info"], day=index))
            SIM.trace(validation, result["plan"], dict(os.environ))


if __name__ == "__main__":
    test_day_protocol()
    print("PASS: 6 days x 2 wire formats")
