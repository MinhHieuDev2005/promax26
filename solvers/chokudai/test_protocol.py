"""Integration tests for the standalone runner; no old solver files are edited."""
import json
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
RUNNER = ROOT / "build/chokudai/chokudai_runner.exe"


def payload():
    return {
        "op": "plan",
        "config": {
            "startsAt": 0, "daySeconds": [60, 60], "daySteps": [14, 14],
            "map": {"height": 4, "width": 4, "cells": [[0] * 4 for _ in range(4)]},
            "spots": [{"brand": 0, "pos": 3, "stocks": 2},
                      {"brand": 1, "pos": 11, "stocks": 2}],
            "agents": [0, 12], "fuelLimits": 8, "players": 1,
            "busyThreshold": 2, "jammedThreshold": 4,
        },
        "day_info": {"day": 0, "agents": [
            {"kind": 0, "pos": 0, "fuel": 8}, {"kind": 1, "pos": 12, "fuel": 0}],
            "others": [], "traffics": []},
        "search": {"timeLimitMs": 100, "seedPercent": 0, "maxExpansions": 8},
    }


def run(data):
    result = subprocess.run([str(RUNNER)], input=json.dumps(data), text=True,
                            capture_output=True, timeout=8, cwd=ROOT)
    response = json.loads(result.stdout)
    assert (result.returncode == 0) == response["ok"], result.stderr
    return response


def test_native_and_history():
    data = payload()
    data["history"] = {"distinct_brands": [9], "cumulative_daily_types": 0, "total_servings": 0}
    result = run(data)
    assert result["ok"] and result["history_supplied"]
    assert len(result["plan"]) == 2
    assert result["diagnostics"]["score"] == [3, 2, 2]
    assert result["diagnostics"]["score"] >= result["diagnostics"]["baseline_score"]


def test_gui_one_based_state():
    data = payload()
    data["state"] = data.pop("day_info")
    data["state"]["day"] = 1
    result = run(data)
    assert result["ok"] and not result["history_supplied"]


@pytest.mark.parametrize("patch", [
    {"timeLimitMs": 50001}, {"timeLimitMs": 0}, {"layerCapacity": 0},
    {"depth": 0}, {"branching": 129}, {"maxExpansions": -1},
])
def test_reject_bad_search(patch):
    data = payload()
    data["search"].update(patch)
    assert not run(data)["ok"]


def test_reject_bad_day_and_types():
    data = payload()
    data["day_info"]["day"] = 99
    assert not run(data)["ok"]
    data = payload()
    data["types"] = [0, 0]
    assert not run(data)["ok"]


def test_reject_elapsed_deadline():
    data = payload()
    data["day_info"]["endsAt"] = 1
    assert not run(data)["ok"]


def test_roles_protocol():
    data = payload()
    data["op"] = "roles"
    result = run(data)
    assert result["ok"] and len(result["roles"]) == 2
    assert all(role in (0, 1) for role in result["roles"])


def test_iteration_limited_search_is_reproducible():
    data = payload()
    data["search"].update(timeLimitMs=2000, randomSeed=73)
    first, second = run(data), run(data)
    assert first["plan"] == second["plan"]
    assert first["diagnostics"]["score"] == second["diagnostics"]["score"]
    assert first["diagnostics"]["expansions"] == second["diagnostics"]["expansions"] == 8


def test_one_millisecond_still_returns_valid_shaped_incumbent():
    data = payload()
    data["search"]["timeLimitMs"] = 1
    result = run(data)
    assert result["ok"] and len(result["plan"]) == 2
    assert all(route and all(type(action) is int for action in route) for route in result["plan"])


def test_empty_spots():
    data = payload()
    data["config"]["spots"] = []
    result = run(data)
    assert result["ok"] and result["diagnostics"]["score"] == [0, 0, 0]
