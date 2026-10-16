"""Optimistic daily bound with optional acquisitions on each route.

Each patrol selects one maximal time-feasible route from a free-start
relaxation, then may collect any subset of spots on that route. This avoids
the old bound's unsafe assumption that every selected route must collect every
spot in its mask. Fuel, traffic, rendezvous and route-order interactions stay
relaxed, so the result is an upper bound.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
from scipy.optimize import Bounds, LinearConstraint, milp
from scipy.sparse import coo_matrix

from day_one_stock_bound import maximal_time_feasible_masks


def bound(config: dict, roles: list[int], day: int) -> dict:
    spots = config["spots"]
    brands = sorted({spot["brand"] for spot in spots})
    patrol = [i for i, role in enumerate(roles) if role == 0]
    route_sets = [maximal_time_feasible_masks(config, None,
                                               config["daySteps"][day])
                  for _ in patrol]
    route_offsets = []
    route_count = 0
    for routes in route_sets:
        route_offsets.append(route_count)
        route_count += len(routes)
    pair_count = route_count * len(spots)
    route_vars = route_count
    variables = route_vars + pair_count
    route_group_rows = len(patrol)
    stock_rows = len(spots)
    brand_rows = len(brands)
    rows = route_group_rows + stock_rows + brand_rows
    ri: list[int] = []
    ci: list[int] = []
    values: list[float] = []
    lower = np.full(rows, -np.inf)
    upper = np.full(rows, np.inf)
    for group, routes in enumerate(route_sets):
        lower[group] = upper[group] = 1
        for local, _mask in enumerate(routes):
            ri.append(group)
            ci.append(route_offsets[group] + local)
            values.append(1)
    def pair_col(route_index: int, spot_index: int) -> int:
        return route_vars + route_index * len(spots) + spot_index
    for spot_index, spot in enumerate(spots):
        row = route_group_rows + spot_index
        upper[row] = spot["stocks"]
        for route_index, routes in enumerate(route_sets):
            for local, mask in enumerate(routes):
                if mask & (1 << spot_index):
                    ri.append(row)
                    ci.append(pair_col(route_offsets[route_index] + local,
                                      spot_index))
                    values.append(1)
    for brand_index, brand in enumerate(brands):
        row = route_group_rows + stock_rows + brand_index
        lower[row] = 1
        for route_index, routes in enumerate(route_sets):
            for local, mask in enumerate(routes):
                route_id = route_offsets[route_index] + local
                for spot_index, spot in enumerate(spots):
                    if spot["brand"] == brand and mask & (1 << spot_index):
                        ri.append(row)
                        ci.append(pair_col(route_id, spot_index))
                        values.append(1)
    pair_rows = route_count * len(spots)
    for route_index, routes in enumerate(route_sets):
        for local, mask in enumerate(routes):
            route_id = route_offsets[route_index] + local
            for spot_index in range(len(spots)):
                if not mask & (1 << spot_index):
                    continue
                # serve(route, spot) <= selected(route)
                pair_row = rows + route_id * len(spots) + spot_index
                ri.extend([pair_row, pair_row])
                ci.extend([pair_col(route_id, spot_index), route_id])
                values.extend([1, -1])
    # The pair rows above are upper-bound rows appended after core rows.
    matrix = coo_matrix((values, (ri, ci)), shape=(rows + pair_rows, variables)).tocsr()
    pair_lower = np.full(pair_rows, -np.inf)
    pair_upper = np.zeros(pair_rows)
    all_lower = np.concatenate([lower, pair_lower])
    all_upper = np.concatenate([upper, pair_upper])
    objective = np.zeros(variables)
    for route_id in range(route_count):
        objective[route_vars + route_id * len(spots):
                   route_vars + (route_id + 1) * len(spots)] = -1
    integral = np.ones(variables, dtype=int)
    result = milp(objective, integrality=integral,
                   bounds=Bounds(np.zeros(variables),
                                 np.ones(variables)),
                   constraints=LinearConstraint(matrix, all_lower, all_upper),
                   options={"time_limit": 120, "mip_rel_gap": 0})
    if result.status != 0:
        raise RuntimeError(result.message)
    return {"roles": roles, "day": day + 1, "patrols": len(patrol),
            "route_counts": [len(x) for x in route_sets],
            "optional_acquisition_upper_bound": round(-result.fun)}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("case", type=Path)
    parser.add_argument("--roles", required=True)
    parser.add_argument("--day", type=int, default=4)
    args = parser.parse_args()
    raw = json.loads(args.case.read_text(encoding="utf-8-sig"))
    config = raw.get("config", raw)
    roles = [int(x) for x in args.roles.split(",")]
    print(json.dumps(bound(config, roles, args.day - 1), indent=2))


if __name__ == "__main__":
    main()
