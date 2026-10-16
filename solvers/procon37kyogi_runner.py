"""Runner JSON adapter for yss19411208/procon37kyogi (MIT)."""
from __future__ import annotations

import json
import random
import sys
import time
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
UPSTREAM = HERE / "procon37kyogi_upstream"
sys.path.insert(0, str(UPSTREAM))

from hexa.ai import Policy, load_population  # noqa: E402
from hexa.match import choose_agent_kinds  # noqa: E402
from hexa.pathfind import PathFinder  # noqa: E402
from hexa.planner import DayPlanner  # noqa: E402
from hexa.problem import problem_from_json_dict  # noqa: E402
from hexa.production import GreedyPolicy, _build_candidate, _planned_route_policies  # noqa: E402
from hexa.production import (  # noqa: E402
    PlannedRoutePolicy, _rollout_match, kinds_for_seats, routes_from_result,
    supply_order_from_result, supply_seat_choices,
)
from hexa.improve import improve_routes  # noqa: E402
from hexa.rules import AgentKind, RoadStatus  # noqa: E402

MODELS = UPSTREAM / "models" / "population.json"


def _problem(payload: dict):
    raw = dict(payload["config"])
    stocks = payload.get("stock")
    if isinstance(stocks, list):
        raw["spots"] = [
            {**spot, "stocks": int(stocks[index])}
            for index, spot in enumerate(raw["spots"])
        ]
    return problem_from_json_dict(raw)


def _roles(payload: dict) -> list[int]:
    problem = _problem(payload)
    all_brains = load_population(MODELS)
    stride = max(1, len(all_brains) // 8)
    brains = all_brains[::stride][:8]
    counts = Counter(
        sum(kind == AgentKind.SUPPLY for kind in choose_agent_kinds(brain, problem, random.Random(1), 0.0))
        for brain in brains
    )
    learned_count = min(counts, key=lambda count: (-counts[count], count))

    # Test role count and starting seat on this map. This avoids trusting only
    # population-wide statistics when fuel, starts and topology differ.
    finder = PathFinder(problem)
    planner = DayPlanner(problem, finder)
    policy = GreedyPolicy(problem)
    deadline = time.monotonic() + 3.0
    best_kinds = kinds_for_seats(
        problem.agent_count,
        tuple(range(problem.agent_count - learned_count, problem.agent_count)),
    )
    best_score = _rollout_match(problem, planner, best_kinds, policy)
    for supply_count in range(problem.agent_count):
        for seats in supply_seat_choices(problem.agent_count, supply_count):
            if time.monotonic() >= deadline:
                break
            kinds = kinds_for_seats(problem.agent_count, seats)
            score = _rollout_match(problem, planner, kinds, policy)
            if score is not None and (best_score is None or (score, -supply_count) >
                                      (best_score, -sum(k == AgentKind.SUPPLY for k in best_kinds))):
                best_score, best_kinds = score, kinds
    return [int(kind) for kind in best_kinds]


def _plan(payload: dict) -> tuple[list[list[int]], dict]:
    started = time.monotonic()
    search = payload.get("search", {})
    limit_ms = max(100, min(60_000, int(search.get("timeLimitMs", 3_000))))
    deadline = started + limit_ms * 0.82 / 1000.0
    seed = int(search.get("randomSeed", 1))
    problem = _problem(payload)
    state = payload["state"]
    agents = state["agents"]
    kinds = tuple(AgentKind(int(agent["kind"])) for agent in agents)
    positions = [int(agent.get("pos", agent.get("position"))) for agent in agents]
    fuels = [int(agent.get("fuel", 0)) for agent in agents]
    roads = {
        int(item["pos"]): RoadStatus(int(item.get("status", 0)))
        for item in state.get("traffics", [])
    }
    submitted = payload.get("history", {}).get("submitted_actions")
    day = len(submitted) if isinstance(submitted, list) else max(0, int(state.get("day", 1)) - 1)
    day = min(day, problem.day_count - 1)
    steps = int(state.get("stepsCount", problem.day_steps[day]))
    acquired = {int(value) for value in payload.get("history", {}).get("distinct_brands", [])}
    next_steps = problem.day_steps[day + 1] if day + 1 < problem.day_count else 0

    finder = PathFinder(problem)
    planner = DayPlanner(problem, finder)
    all_brains = load_population(MODELS)
    stride = max(1, len(all_brains) // 8)
    brains = all_brains[::stride][:8]
    policies = [("greedy", GreedyPolicy(problem))]
    policies.extend(_planned_route_policies(
        problem, finder, kinds, positions, fuels, roads, steps, acquired,
        next_steps=next_steps,
    ))
    policies.extend(
        (brain.name, Policy(brain, problem, random.Random(seed + index), 0.0))
        for index, brain in enumerate(brains)
    )
    candidates = []
    base_deadline = started + limit_ms * 0.65 / 1000.0
    for label, policy in policies:
        if candidates and time.monotonic() >= base_deadline:
            break
        candidate = _build_candidate(
            label, problem, planner, kinds, positions, fuels, roads, steps,
            policy, acquired, day_index=day, next_steps=next_steps,
        )
        if candidate is not None:
            candidates.append(candidate)
    if not candidates:
        return [[-steps] for _ in agents], {"candidates": 0, "selected": "wait"}
    best = max(candidates, key=lambda candidate: candidate.key)
    base_key = best.key

    # Multi-start LNS: retain official-score incumbent, then repeatedly destroy,
    # repair and reassign route segments while budget remains. Inspired by the
    # two Japanese solvers' multi-seed SA/LNS design; implementation uses the
    # MIT-licensed Python solver's own route polisher and simulator.
    polished_steps = 0
    seeds = sorted(candidates, key=lambda candidate: candidate.key, reverse=True)[:8]
    turn = 0
    while seeds and time.monotonic() < deadline:
        base = seeds[turn % len(seeds)]
        routes = routes_from_result(base.day_result, kinds)
        supply = supply_order_from_result(base.day_result, kinds)

        def evaluate(trial, order):
            return _build_candidate(
                "hybrid-lns", problem, planner, kinds, positions, fuels, roads,
                steps, PlannedRoutePolicy(problem, trial, order), acquired,
                day_index=day, next_steps=next_steps, verify=False,
            )

        improved_routes, improved_supply, candidate = improve_routes(
            problem, kinds, routes, evaluate, budget=80,
            supply_order=supply,
        )
        polished_steps += 80
        if candidate is not None:
            exact = _build_candidate(
                "hybrid-lns", problem, planner, kinds, positions, fuels, roads,
                steps, PlannedRoutePolicy(problem, improved_routes, improved_supply),
                acquired, day_index=day, next_steps=next_steps, verify=True,
            )
            if exact is not None:
                candidates.append(exact)
                seeds[turn % len(seeds)] = exact
                if exact.key > best.key:
                    best = exact
        turn += 1
    return best.action_plan, {
        "candidates": len(candidates), "selected": best.label,
        "base_score_key": list(base_key), "score_key": list(best.key),
        "improved": best.key > base_key, "polished_steps": polished_steps,
        "elapsed_ms": int((time.monotonic() - started) * 1000),
    }


def main() -> None:
    try:
        payload = json.load(sys.stdin)
        if payload.get("op") == "roles":
            response = {"ok": True, "roles": _roles(payload)}
        elif payload.get("op") == "plan":
            plan, diagnostics = _plan(payload)
            response = {"ok": True, "plan": plan, "diagnostics": diagnostics}
        else:
            raise ValueError("op must be roles or plan")
    except Exception as error:
        response = {"ok": False, "error": f"{type(error).__name__}: {error}"}
    json.dump(response, sys.stdout)


if __name__ == "__main__":
    main()
