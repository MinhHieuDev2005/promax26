"""Optimistic patrol-fuel bounds for a target Hexudon serving count.

Each agent may start for free at any spot every day. Travel uses shortest fuel
paths. The relaxed problem is therefore easier than a real match; exceeding
initial fuel proves a target impossible without a refuel vehicle. ``count``
also ignores stock and brand coverage; ``stock`` retains both but is practical
only for small maps.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
from scipy.optimize import Bounds, LinearConstraint, milp
from scipy.sparse import lil_matrix

from spot_route_bound import fuel_distances


def open_path_costs(config: dict) -> list[int]:
    spots = config["spots"]
    count = len(spots)
    costs = [fuel_distances(config, spot["pos"]) for spot in spots]
    infinity = 10**8
    best = [[infinity] * count for _ in range(1 << count)]
    for index in range(count):
        best[1 << index][index] = 0
    result = [0] + [infinity] * ((1 << count) - 1)
    for mask, ends in enumerate(best):
        for last, cost in enumerate(ends):
            if cost >= infinity:
                continue
            result[mask] = min(result[mask], cost)
            for target in range(count):
                bit = 1 << target
                if mask & bit:
                    continue
                candidate = cost + costs[last][spots[target]["pos"]]
                if candidate < best[mask | bit][target]:
                    best[mask | bit][target] = candidate
    return result


def min_route_fuel_by_visits(path_costs: list[int], spots: int) -> list[int]:
    """Cheapest open route visiting exactly k distinct spots, for each k."""
    infinity = 10**8
    result = [infinity] * (spots + 1)
    for mask, cost in enumerate(path_costs):
        count = mask.bit_count()
        if cost < result[count]:
            result[count] = cost
    return result


def count_relaxation(config: dict, route_costs: list[int], target: int) -> dict:
    """Optimistic whole-match bound, ignoring every constraint except fuel.

    There is one free-start route for every patrol vehicle on every day. Any
    actual serving needs one distinct spot visit on that vehicle's route.
    """
    agent_days = len(config["agents"]) * len(config["daySteps"])
    initial_fuel = len(config["agents"]) * config["fuelLimits"]
    options = [(visits, cost) for visits, cost in enumerate(route_costs)
               if cost < 10**8]

    # Minimum fuel required for at least the requested number of visits.
    infinity = 10**9
    fuel_for_visits = [infinity] * (target + 1)
    fuel_for_visits[0] = 0
    for _ in range(agent_days):
        following = [infinity] * (target + 1)
        for visits_so_far, spent in enumerate(fuel_for_visits):
            if spent == infinity:
                continue
            for additional, cost in options:
                next_visits = min(target, visits_so_far + additional)
                following[next_visits] = min(following[next_visits], spent + cost)
        fuel_for_visits = following

    # Maximum possible visits on the actual initial-fuel budget. Stock,
    # starting positions and day horizons can only reduce this figure.
    visits_for_fuel = [-1] * (initial_fuel + 1)
    visits_for_fuel[0] = 0
    for _ in range(agent_days):
        following = [-1] * (initial_fuel + 1)
        for spent, visits_so_far in enumerate(visits_for_fuel):
            if visits_so_far < 0:
                continue
            for additional, cost in options:
                if spent + cost <= initial_fuel:
                    following[spent + cost] = max(
                        following[spent + cost], visits_so_far + additional)
        visits_for_fuel = following

    return {
        "target": target,
        "agent_days": agent_days,
        "initial_patrol_fuel": initial_fuel,
        "optimistic_fuel_needed_for_target": fuel_for_visits[target],
        "optimistic_all_patrol_score_upper_bound": max(visits_for_fuel),
        "target_impossible_if_all_patrol": fuel_for_visits[target] > initial_fuel,
        "minimum_route_fuel_by_distinct_spot_visits": route_costs,
    }


def min_fuel_for_score(config: dict, path_costs: list[int], score: int) -> float:
    spots = config["spots"]
    masks = len(path_costs)
    total_variables = masks + len(spots)
    brands = sorted({spot["brand"] for spot in spots})
    total_rows = 1 + len(spots) + len(brands) + 1
    matrix = lil_matrix((total_rows, total_variables), dtype=float)
    lower = np.full(total_rows, -np.inf)
    upper = np.full(total_rows, np.inf)
    matrix[0, :masks] = 1
    lower[0] = upper[0] = len(config["agents"])
    for index, spot in enumerate(spots):
        for mask in range(masks):
            if mask & (1 << index):
                matrix[1 + index, mask] = -1
        matrix[1 + index, masks + index] = 1
        upper[1 + index] = 0
    brand_offset = 1 + len(spots)
    for index, brand in enumerate(brands):
        for spot_index, spot in enumerate(spots):
            if spot["brand"] == brand:
                matrix[brand_offset + index, masks + spot_index] = 1
        lower[brand_offset + index] = 1
    matrix[-1, masks:] = 1
    lower[-1] = score
    costs = np.array([*path_costs, *([0] * len(spots))], dtype=float)
    variable_upper = np.array([*([len(config["agents"])] * masks),
                               *[spot["stocks"] for spot in spots]], dtype=float)
    result = milp(costs, integrality=np.ones(total_variables),
                  bounds=Bounds(np.zeros(total_variables), variable_upper),
                  constraints=LinearConstraint(matrix.tocsr(), lower, upper),
                  options={"time_limit": 60})
    if result.status != 0:
        raise RuntimeError(f"MILP did not prove optimum for score {score}: {result.message}")
    return result.fun


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("case", type=Path)
    parser.add_argument("--target", type=int, required=True)
    parser.add_argument("--mode", choices=("count", "stock"), default="count")
    args = parser.parse_args()
    raw = json.loads(args.case.read_text(encoding="utf-8-sig"))
    config = raw.get("config", raw)
    if args.mode == "stock" and len(config["spots"]) > 12:
        parser.error("stock relaxation supports at most 12 spots")
    path_costs = open_path_costs(config)
    if args.mode == "count":
        route_costs = min_route_fuel_by_visits(path_costs, len(config["spots"]))
        print(json.dumps(count_relaxation(config, route_costs, args.target), indent=2))
        return
    days = len(config["daySteps"])
    min_daily = len({spot["brand"] for spot in config["spots"]})
    max_daily = sum(spot["stocks"] for spot in config["spots"])
    costs = {}
    for score in range(min_daily, max_daily + 1):
        costs[score] = min_fuel_for_score(config, path_costs, score)
        print(f"daily score {score}: optimistic fuel >= {costs[score]:g}", flush=True)
    dp = {0: 0.0}
    for _ in range(days):
        next_dp = {}
        for total, used in dp.items():
            for score, cost in costs.items():
                key = total + score
                next_dp[key] = min(next_dp.get(key, float("inf")), used + cost)
        dp = next_dp
    min_fuel = min((fuel for score, fuel in dp.items() if score >= args.target),
                   default=float("inf"))
    initial_fuel = len(config["agents"]) * config["fuelLimits"]
    print(json.dumps({"target": args.target, "optimistic_fuel_lower_bound": min_fuel,
                      "initial_fuel": initial_fuel,
                      "impossible_if_all_patrol": min_fuel > initial_fuel,
                      "daily_costs": costs}, indent=2))


if __name__ == "__main__":
    main()
