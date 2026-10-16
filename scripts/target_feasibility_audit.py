"""Prove an optimistic upper bound on Hexudon servings for one input case.

This is a diagnostic tool, not a solver. It never modifies the input or the
official evaluator. A result below the requested target rules that target out
for every fixed vehicle-role assignment, even without C1/C2 constraints.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from fuel_relaxation_bound import (
    count_relaxation,
    min_route_fuel_by_visits,
    open_path_costs,
)
from spot_route_bound import attainable


def audit(config: dict, target: int) -> dict:
    agents = config["agents"]
    spots = config["spots"]
    days = len(config["daySteps"])
    first_day_max = [attainable(config, start, config["daySteps"][0])[0]
                     for start in agents]

    # With r patrols, a spot can be collected at most once by each patrol
    # and at most stocks times in a day. Refuel vehicles never collect.
    upper_by_refuel_count: dict[int, int] = {}
    for role_mask in range(1 << len(agents)):
        patrol_indices = [index for index in range(len(agents))
                          if not role_mask & (1 << index)]
        day_stock_cap = sum(min(spot["stocks"], len(patrol_indices))
                            for spot in spots)
        day_one_cap = min(day_stock_cap,
                          sum(first_day_max[index] for index in patrol_indices))
        whole_match_cap = day_one_cap + (days - 1) * day_stock_cap
        refuel_count = role_mask.bit_count()
        upper_by_refuel_count[refuel_count] = max(
            upper_by_refuel_count.get(refuel_count, 0), whole_match_cap)

    path_costs = open_path_costs(config)
    route_costs = min_route_fuel_by_visits(path_costs, len(spots))
    patrol_fuel = count_relaxation(config, route_costs, target)
    refuel_upper = max((bound for count, bound in upper_by_refuel_count.items()
                        if count > 0), default=0)
    stock_upper = days * sum(spot["stocks"] for spot in spots)
    global_upper = min(stock_upper, max(
        refuel_upper,
        patrol_fuel["optimistic_all_patrol_score_upper_bound"],
    ))
    brands = len({spot["brand"] for spot in spots})
    return {
        "requested_minimum_servings": target,
        "criterion_1_max_distinct_brands": brands,
        "criterion_2_max_cumulative_daily_brands": brands * days,
        "stock_only_upper_bound": stock_upper,
        "first_day_max_spot_visits_per_agent": first_day_max,
        "serving_upper_bound_by_refuel_vehicle_count": upper_by_refuel_count,
        "all_patrol_fuel_relaxation": patrol_fuel,
        "global_serving_upper_bound": global_upper,
        "requested_target_is_proven_impossible": global_upper < target,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("case", type=Path)
    parser.add_argument("--target", required=True, type=int,
                        help="minimum C3 to test, e.g. 111 for >110")
    args = parser.parse_args()
    content = args.case.read_bytes()
    raw = json.loads(content.decode("utf-8-sig"))
    config = raw.get("config", raw)
    result = audit(config, args.target)
    result["case"] = str(args.case)
    result["case_sha256"] = hashlib.sha256(content).hexdigest()
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
