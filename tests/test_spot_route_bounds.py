"""Checks for optimistic, never-underestimating Hexudon score bounds."""

from __future__ import annotations

import itertools
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from fuel_relaxation_bound import (  # noqa: E402
    count_relaxation,
    min_route_fuel_by_visits,
    open_path_costs,
)
from day_one_stock_bound import bound as day_bound  # noqa: E402
from spot_route_bound import attainable, fuel_distances  # noqa: E402
import json  # noqa: E402


def test_fuel_route_dp_matches_brute_force() -> None:
    config = {
        "map": {"width": 4, "height": 2, "cells": [[0] * 4 for _ in range(2)]},
        "spots": [{"pos": 0}, {"pos": 1}, {"pos": 5}],
        "agents": [0, 7],
        "daySteps": [3, 3],
        "fuelLimits": 1,
    }
    route_costs = open_path_costs(config)
    spot_positions = [spot["pos"] for spot in config["spots"]]
    distances = [fuel_distances(config, pos) for pos in spot_positions]
    for mask, optimized in enumerate(route_costs):
        indices = [index for index in range(3) if mask & (1 << index)]
        brute = min(
            (sum(distances[left][spot_positions[right]]
                 for left, right in zip(order, order[1:]))
             for order in itertools.permutations(indices)),
            default=0,
        )
        assert optimized == brute

    minimum = min_route_fuel_by_visits(route_costs, 3)
    assert minimum == [0, 0, 1, 2]
    relaxed = count_relaxation(config, minimum, target=7)
    assert relaxed["agent_days"] == 4
    assert relaxed["initial_patrol_fuel"] == 2
    assert relaxed["optimistic_fuel_needed_for_target"] == 3
    assert relaxed["optimistic_all_patrol_score_upper_bound"] == 6
    assert relaxed["target_impossible_if_all_patrol"]


def test_day_one_route_respects_initial_horizon() -> None:
    config = {
        "map": {"width": 2, "height": 1, "cells": [[0, 0]]},
        "spots": [{"pos": 0}, {"pos": 1}],
    }
    assert attainable(config, start=0, horizon=1)[0] == 1
    assert attainable(config, start=0, horizon=2)[0] == 2


def test_16x16_optimistic_daily_caps_cover_known_replay() -> None:
    case = Path(__file__).resolve().parents[1] / "cases/user-input-16x16.json"
    config = json.loads(case.read_text(encoding="utf-8-sig"))
    roles = [0, 0, 0, 1]
    assert day_bound(config, roles, day_index=0)["day_one_serving_upper_bound"] == 10
    assert day_bound(config, roles, day_index=1, free_start=True)[
        "day_one_serving_upper_bound"] == 15
    assert day_bound(config, roles, day_index=2, free_start=True)[
        "day_one_serving_upper_bound"] == 17
