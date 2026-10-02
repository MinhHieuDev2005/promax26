"""Optimistic day-one servings bound with routes and per-spot stock.

Only travel time, starting positions, one acquisition per spot per patrol,
stocks and optional full brand coverage are respected. Fuel, traffic, refuel
movement and route contention are ignored, so the result is an upper bound.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
from scipy.optimize import Bounds, LinearConstraint, milp
from scipy.sparse import coo_matrix

from spot_route_bound import distances


def maximal_time_feasible_masks(config: dict, start: int | None, horizon: int) -> list[int]:
    spots = config["spots"]
    count = len(spots)
    positions = [spot["pos"] for spot in spots]
    origins = [distances(config, point) for point in positions]
    start_distances = distances(config, start) if start is not None else None
    infinity = 10**8
    best = [[infinity] * count for _ in range(1 << count)]
    for index, pos in enumerate(positions):
        best[1 << index][index] = start_distances[pos] if start_distances is not None else 0
    feasible = [False] * (1 << count)
    feasible[0] = True
    for mask, ends in enumerate(best):
        if mask and min(ends) <= horizon:
            feasible[mask] = True
        for last, cost in enumerate(ends):
            if cost > horizon:
                continue
            for target, pos in enumerate(positions):
                bit = 1 << target
                if mask & bit:
                    continue
                next_cost = cost + origins[last][pos]
                if next_cost < best[mask | bit][target]:
                    best[mask | bit][target] = next_cost
    return [mask for mask, valid in enumerate(feasible) if valid and
            not any(not mask & (1 << target) and feasible[mask | (1 << target)]
                    for target in range(count))]


def bound(config: dict, roles: list[int], *, require_daily_brands: bool = True,
          time_limit: int = 120, day_index: int = 0,
          free_start: bool = False) -> dict:
    if len(roles) != len(config["agents"]):
        raise ValueError("one role required per agent")
    spots = config["spots"]
    brands = sorted({spot["brand"] for spot in spots})
    patrol = [index for index, role in enumerate(roles) if role == 0]
    route_sets = [maximal_time_feasible_masks(
        config, None if free_start else config["agents"][index],
        config["daySteps"][day_index]) for index in patrol]
    route_counts = [len(routes) for routes in route_sets]
    spot_offset = sum(route_counts)
    variables = spot_offset + len(spots)
    group_rows = len(patrol)
    stock_rows = len(spots)
    brand_rows = len(brands) if require_daily_brands else 0
    rows = group_rows + stock_rows + brand_rows
    row_indices: list[int] = []
    column_indices: list[int] = []
    values: list[float] = []
    lower = np.full(rows, -np.inf)
    upper = np.full(rows, np.inf)
    column = 0
    for group, routes in enumerate(route_sets):
        lower[group] = upper[group] = 1
        for mask in routes:
            row_indices.append(group)
            column_indices.append(column)
            values.append(1)
            for spot in range(len(spots)):
                if mask & (1 << spot):
                    row_indices.append(group_rows + spot)
                    column_indices.append(column)
                    values.append(-1)
            column += 1
    for spot, entry in enumerate(spots):
        row_indices.append(group_rows + spot)
        column_indices.append(spot_offset + spot)
        values.append(1)
        upper[group_rows + spot] = 0
        if require_daily_brands:
            brand_row = group_rows + stock_rows + brands.index(entry["brand"])
            row_indices.append(brand_row)
            column_indices.append(spot_offset + spot)
            values.append(1)
    if require_daily_brands:
        lower[group_rows + stock_rows:] = 1
    matrix = coo_matrix((values, (row_indices, column_indices)),
                        shape=(rows, variables)).tocsr()
    objective = np.array([0] * spot_offset + [-1] * len(spots), dtype=float)
    integral = np.array([1] * spot_offset + [0] * len(spots), dtype=int)
    result = milp(
        objective,
        integrality=integral,
        bounds=Bounds(np.zeros(variables), np.array(
            [1] * spot_offset + [spot["stocks"] for spot in spots], dtype=float)),
        constraints=LinearConstraint(matrix, lower, upper),
        options={"time_limit": time_limit, "mip_rel_gap": 0},
    )
    if result.status != 0:
        raise RuntimeError(f"MILP optimum unproven: {result.message}")
    selected_routes = []
    offset = 0
    for agent, routes in zip(patrol, route_sets):
        chosen = next(mask for index, mask in enumerate(routes)
                      if result.x[offset + index] > 0.5)
        selected_routes.append({"agent": agent,
                                "spots": [spots[index]["pos"]
                                          for index in range(len(spots))
                                          if chosen & (1 << index)]})
        offset += len(routes)
    return {"roles": roles, "patrols": len(patrol),
            "day_index": day_index, "free_start": free_start,
            "maximal_route_counts": route_counts,
            "day_one_serving_upper_bound": round(-result.fun),
            "full_daily_brands_required": require_daily_brands,
            "optimistic_route_spots": selected_routes,
            "optimistic_servings_by_spot": [round(x) for x in result.x[spot_offset:]]}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("case", type=Path)
    parser.add_argument("--roles", required=True, help="comma-separated 0/1 roles")
    parser.add_argument("--without-coverage", action="store_true")
    parser.add_argument("--day", type=int, default=1, help="1-based day index")
    parser.add_argument("--free-start", action="store_true",
                        help="free teleport to any first spot (safe future-day relaxation)")
    args = parser.parse_args()
    raw = json.loads(args.case.read_text(encoding="utf-8-sig"))
    config = raw.get("config", raw)
    if not 1 <= args.day <= len(config["daySteps"]):
        parser.error("day outside schedule")
    roles = [int(x) for x in args.roles.split(",")]
    print(json.dumps(bound(config, roles,
                           require_daily_brands=not args.without_coverage,
                           day_index=args.day - 1,
                           free_start=args.free_start), indent=2))


if __name__ == "__main__":
    main()
