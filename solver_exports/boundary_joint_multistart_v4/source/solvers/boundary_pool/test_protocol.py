"""Offline JSON protocol + unchanged-core validation (no GUI/server writes)."""
import copy
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import time
import unittest

spec = importlib.util.spec_from_file_location("bench", Path(__file__).with_name("benchmark.py"))
bench = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bench)
EXE = bench.ROOT / "build/boundary_pool/boundary_pool_runner.exe"


def payload():
    config = {"startsAt": 0, "daySeconds": [45, 45], "daySteps": [10, 8],
              "map": {"width": 4, "height": 4, "cells": [[0]*4 for _ in range(4)]},
              "spots": [{"pos": 2, "brand": 0, "stocks": 2}, {"pos": 7, "brand": 1, "stocks": 2}],
              "agents": [0, 15], "fuelLimits": 30, "players": 2,
              "busyThreshold": 3, "jammedThreshold": 5}
    return {"op": "plan", "config": config, "types": [0, 1],
            "day_info": {"day": 0, "agents": [{"kind": 0, "pos": 0, "fuel": 30},
                                                 {"kind": 1, "pos": 15, "fuel": 30}],
                         "others": [], "traffics": []},
            "history": {"submitted_actions": [], "distinct_brands": [], "cumulative_daily_types": 0, "total_servings": 0},
            "search": {"timeLimitMs": 300, "randomSeed": 1}}


class ProtocolTests(unittest.TestCase):
    def invoke(self, value):
        p = subprocess.run([str(EXE)], input=json.dumps(value), capture_output=True, text=True, timeout=5)
        self.assertEqual(p.returncode, 0, p.stdout+p.stderr)
        result = json.loads(p.stdout)
        self.assertTrue(result["ok"])
        return result

    def check(self, value, canonical=None):
        answer = self.invoke(value)
        replay = bench.sim.trace(canonical or value, answer["plan"], dict(os.environ, HEXUDON_THREADS="1"))
        self.assertTrue(replay["valid"])
        self.assertEqual(len(answer["plan"]), len(value["config"]["agents"]))
        return answer

    def test_zero_based_day_info(self):
        self.check(payload())

    def test_one_based_gui_state(self):
        value = payload()
        canonical = copy.deepcopy(value)
        value["state"] = value.pop("day_info")
        value["state"]["day"] = 1
        self.check(value, canonical)

    def test_invalid_warm_hint_is_ignored(self):
        value = payload()
        value["planner_state"] = {"fingerprint": "wrong map", "source_day": -1, "next_plan": [[99]]}
        self.check(value)

    def test_expired_deadline_still_returns_valid_actions_on_tiny_map(self):
        value = payload()
        value["day_info"]["endsAt"] = time.time()-1
        self.check(value)

    def test_roles_protocol(self):
        value = payload()
        value["op"] = "roles"
        result = self.invoke(value)
        self.assertEqual(len(result["roles"]), 2)
        self.assertTrue(all(x in (0, 1) for x in result["roles"]))
        self.assertIn(0, result["roles"])

    def test_bad_json_returns_json_error(self):
        p = subprocess.run([str(EXE)], input="{", capture_output=True, text=True, timeout=5)
        self.assertNotEqual(p.returncode, 0)
        self.assertFalse(json.loads(p.stdout)["ok"])

    def test_invalid_day_returns_json_error(self):
        value = payload();value["day_info"]["day"] = 2
        p = subprocess.run([str(EXE)], input=json.dumps(value), capture_output=True, text=True, timeout=5)
        self.assertNotEqual(p.returncode, 0)
        self.assertFalse(json.loads(p.stdout)["ok"])


if __name__ == "__main__":
    unittest.main()
