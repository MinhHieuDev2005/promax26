"""Optimistic one-day serving bound from independent patrol routes.

Ignores fuel, congestion, refueling and contention. It is an upper bound, not a
constructive plan: every real acquisition order has at least the shortest-path
travel time used here.
"""

from __future__ import annotations

import argparse
import heapq
import json
from pathlib import Path


def neighbors(pos: int, width: int, height: int):
    row, col = divmod(pos, width)
    offsets = ((-1, 0), (-1, 1), (0, 1), (1, 1), (1, 0), (0, -1)) if row % 2 == 0 else (
        (-1, -1), (-1, 0), (0, 1), (1, 0), (1, -1), (0, -1))
    for dr, dc in offsets:
        nr, nc = row + dr, col + dc
        if 0 <= nr < height and 0 <= nc < width:
            yield nr * width + nc


def distances(config: dict, source: int) -> list[int]:
    width, height = config["map"]["width"], config["map"]["height"]
    cells = [cell for row in config["map"]["cells"] for cell in row]
    infinity = 10**9
    best = [infinity] * len(cells)
    best[source] = 0
    queue = [(0, source)]
    while queue:
        cost, pos = heapq.heappop(queue)
        if cost != best[pos]:
            continue
        for target in neighbors(pos, width, height):
            if cells[target] == 3:
                continue
            next_cost = cost + (1 if cells[pos] == 1 else 3 if cells[pos] == 2 else 2)
            if next_cost < best[target]:
                best[target] = next_cost
                heapq.heappush(queue, (next_cost, target))
    return best


def fuel_distances(config: dict, source: int) -> list[int]:
    width, height = config["map"]["width"], config["map"]["height"]
    cells = [cell for row in config["map"]["cells"] for cell in row]
    infinity = 10**9
    best = [infinity] * len(cells)
    best[source] = 0
    queue = [(0, source)]
    while queue:
        cost, pos = heapq.heappop(queue)
        if cost != best[pos]:
            continue
        for target in neighbors(pos, width, height):
            if cells[target] == 3:
                continue
            next_cost = cost + (1 if cells[pos] == 0 else 2)
            if next_cost < best[target]:
                best[target] = next_cost
                heapq.heappush(queue, (next_cost, target))
    return best


def coverage_fuel_lower_bound(config: dict, patrol_count: int) -> int:
    """Minimum spanning forest over brands, with one component per patrol."""
    brands = sorted({spot["brand"] for spot in config["spots"]})
    spots_by_brand = {brand: [spot["pos"] for spot in config["spots"]
                              if spot["brand"] == brand] for brand in brands}
    all_distances = {spot["pos"]: fuel_distances(config, spot["pos"])
                     for spot in config["spots"]}
    edges = []
    for left in range(len(brands)):
        for right in range(left + 1, len(brands)):
            cost = min(min(all_distances[source][target], all_distances[target][source])
                       for source in spots_by_brand[brands[left]]
                       for target in spots_by_brand[brands[right]])
            edges.append((cost, left, right))
    parent = list(range(len(brands)))

    def root(index):
        while parent[index] != index:
            index = parent[index]
        return index

    components = len(brands)
    total = 0
    for cost, left, right in sorted(edges):
        a, b = root(left), root(right)
        if a == b:
            continue
        parent[a] = b
        total += cost
        components -= 1
        if components <= patrol_count:
            break
    return total


def attainable(config: dict, start: int, horizon: int) -> tuple[int, int]:
    spots = config["spots"]
    count = len(spots)
    targets = [spot["pos"] for spot in spots]
    route_cost = [distances(config, point) for point in [start, *targets]]
    infinity = 10**9
    best = [[infinity] * count for _ in range(1 << count)]
    for index, pos in enumerate(targets):
        best[1 << index][index] = route_cost[0][pos]
    max_spots = 0
    feasible_masks = 0
    for mask, ends in enumerate(best):
        if mask and min(ends) <= horizon:
            max_spots = max(max_spots, mask.bit_count())
            feasible_masks += 1
        for last, cost in enumerate(ends):
            if cost > horizon:
                continue
            for target, pos in enumerate(targets):
                bit = 1 << target
                if mask & bit:
                    continue
                next_cost = cost + route_cost[last + 1][pos]
                if next_cost < best[mask | bit][target]:
                    best[mask | bit][target] = next_cost
    return max_spots, feasible_masks


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("case", type=Path)
    parser.add_argument("--roles", help="comma-separated 0/1 vehicle roles")
    parser.add_argument("--all-roles", action="store_true", help="bound every role mask")
    args = parser.parse_args()
    raw = json.loads(args.case.read_text(encoding="utf-8-sig"))
    config = raw.get("config", raw)
    if not args.all_roles and not args.roles:
        parser.error("provide --roles or --all-roles")
    horizon = config["daySteps"][0]
    all_patrol = [attainable(config, start, horizon) for start in config["agents"]]
    if args.all_roles:
        groups = {}
        for mask in range(1 << len(all_patrol)):
            patrol = [all_patrol[index][0] for index in range(len(all_patrol))
                      if not (mask & (1 << index))]
            per_spot_cap = sum(min(spot["stocks"], len(patrol)) for spot in config["spots"])
            day_one_bound = min(per_spot_cap, sum(patrol))
            match_bound = day_one_bound + (len(config["daySteps"]) - 1) * per_spot_cap
            refuel_count = mask.bit_count()
            entry = groups.get(refuel_count)
            if entry is None or match_bound > entry["match_upper_bound"]:
                groups[refuel_count] = {
                    "roles": [int(bool(mask & (1 << index))) for index in range(len(all_patrol))],
                    "day_one_upper_bound": day_one_bound,
                    "later_day_upper_bound": per_spot_cap,
                    "match_upper_bound": match_bound,
                }
        print(json.dumps({"horizon": horizon, "per_start_route_maxima": all_patrol,
                          "all_patrol_initial_fuel": len(all_patrol) * config["fuelLimits"],
                          "all_patrol_coverage_fuel_lower_bound":
                              len(config["daySteps"]) * coverage_fuel_lower_bound(config, len(all_patrol)),
                          "best_upper_bound_by_refuel_count": groups}, indent=2))
        return
    roles = [int(value) for value in args.roles.split(",")]
    if len(roles) != len(config["agents"]):
        parser.error("role count mismatch")
    patrol = [values for values, role in zip(all_patrol, roles) if role == 0]
    daily_stock = sum(spot["stocks"] for spot in config["spots"])
    per_spot_cap = sum(min(spot["stocks"], len(patrol)) for spot in config["spots"])
    day_one_bound = min(per_spot_cap, sum(value for value, _ in patrol))
    match_bound = day_one_bound + (len(config["daySteps"]) - 1) * per_spot_cap
    print(json.dumps({"horizon": horizon, "patrol_route_maxima": patrol,
                      "day_one_upper_bound": day_one_bound,
                      "later_day_upper_bound": per_spot_cap,
                      "match_upper_bound": match_bound,
                      "daily_stock": daily_stock}, indent=2))


if __name__ == "__main__":
    main()
