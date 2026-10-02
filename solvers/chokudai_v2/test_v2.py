import copy
import json
import os
from pathlib import Path
import subprocess

import pytest
import experiment

ROOT = Path(__file__).resolve().parents[2]
RUNNER = ROOT / "build/chokudai_v2/chokudai_v2_runner.exe"


def payload():
    return {"op": "plan", "config": {
        "startsAt": 0, "daySeconds": [60, 60], "daySteps": [14, 14],
        "map": {"height": 4, "width": 4, "cells": [[0]*4 for _ in range(4)]},
        "spots": [{"brand": 0, "pos": 3, "stocks": 2}, {"brand": 1, "pos": 11, "stocks": 2}],
        "agents": [0, 12], "fuelLimits": 8, "players": 1,
        "busyThreshold": 2, "jammedThreshold": 4},
        "types": [0, 1], "history": {"distinct_brands": [], "submitted_actions": [],
                                    "cumulative_daily_types": 0, "total_servings": 0},
        "day_info": {"day": 0, "agents": [{"kind": 0, "pos": 0, "fuel": 8},
                                              {"kind": 1, "pos": 12, "fuel": 0}],
                     "others": [], "traffics": []},
        "search": {"timeLimitMs": 1000, "sliceMs": 10, "maxExpansions": 12}}


def call(data):
    proc = subprocess.run([str(RUNNER)], input=json.dumps(data), capture_output=True,
                          text=True, timeout=6, env=dict(os.environ, HEXUDON_THREADS="1"))
    result = json.loads(proc.stdout)
    assert (proc.returncode == 0) == result["ok"]
    return result


def test_full_suffix_and_warm_replay():
    data = payload()
    r = call(data)
    assert r["ok"], r
    assert r["diagnostics"]["projected_final"] == [2, 4, 4]
    env = dict(os.environ, HEXUDON_THREADS="1")
    traffic = []
    tr = experiment.sim.trace(data, r["plan"], env)
    experiment.sim.advance(data, r["plan"], tr, traffic)
    data["planner_state"] = r["planner_state"]
    second = call(data)
    assert second["ok"] and second["diagnostics"]["warm_valid"]
    assert second["diagnostics"]["projected_final"] == [2, 4, 4]


@pytest.mark.parametrize("patch", [
    {"timeLimitMs": 60001}, {"timeLimitMs": 0}, {"sliceMs": 0},
    {"layerCapacity": 0}, {"attempts": 0}, {"maxExpansions": -1}, {"randomSeed": -1}])
def test_invalid_search(patch):
    data = payload(); data["search"].update(patch)
    assert not call(data)["ok"]


def test_no_false_success_when_coverage_impossible():
    data = payload()
    data["config"]["daySteps"] = [1, 1]
    result = call(data)
    assert not result["ok"]


def test_missing_history_rejected():
    data = payload(); data["day_info"]["day"] = 1
    assert not call(data)["ok"]


def test_expired_deadline_rejected():
    data = payload(); data["day_info"]["endsAt"] = 1
    assert not call(data)["ok"]


def test_gui_day_numbering():
    data = payload(); data["state"] = data.pop("day_info"); data["state"]["day"] = 1
    assert call(data)["ok"]


def test_bad_roles_rejected():
    data = payload(); data["types"] = [0, 0]
    assert not call(data)["ok"]
