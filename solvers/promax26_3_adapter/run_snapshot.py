"""Benchmark the read-only promax26-3 adapter on the supplied idle snapshot."""
import argparse
import copy
from collections import Counter
import importlib.util
import json
import os
import hashlib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "budget_sweep", ROOT / "solvers/chokudai/budget_sweep.py")
BENCH = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(BENCH)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--snapshot", type=Path, required=True)
    parser.add_argument("--exe", type=Path, required=True)
    parser.add_argument("--budget", type=int, default=45_000)
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--threads", type=int, default=8)
    parser.add_argument("--future-weight", type=float, default=0.0)
    parser.add_argument("--terminal-access-weight", type=float, default=0.0)
    parser.add_argument("--cross-moves", type=int, default=7)
    parser.add_argument("--tail-repair", action="store_true")
    parser.add_argument("--terminal-rollout", action="store_true")
    parser.add_argument("--stock-repair", action="store_true")
    parser.add_argument("--marginal-stock", action="store_true")
    parser.add_argument("--path-stock", action="store_true")
    parser.add_argument("--mobile-forecast", action="store_true")
    parser.add_argument("--idle-forecast", action="store_true")
    parser.add_argument("--actual-ruin", action="store_true")
    parser.add_argument("--boundary-select", action="store_true")
    parser.add_argument("--cluster-ruin", action="store_true")
    parser.add_argument("--direct-stock-insert", action="store_true")
    parser.add_argument("--two-day-select", action="store_true")
    parser.add_argument("--hard-full-max", action="store_true")
    parser.add_argument("--dual-hub-seeds", action="store_true")
    parser.add_argument("--stock-build-seeds", action="store_true")
    parser.add_argument("--loop-repair", action="store_true")
    parser.add_argument("--objective", choices=["OFFICIAL_LEXICOGRAPHIC", "MAX_TOTAL_UDON"], default="OFFICIAL_LEXICOGRAPHIC")
    parser.add_argument(
        "--end-spot-weight", type=float, default=-1.0,
        help="-1 selects adaptive flat-tail behavior; nonnegative overrides it",
    )
    parser.add_argument(
        "--roles",
        help="Comma-separated vehicle kinds, for example 0,0,0,0,1,0,0",
    )
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    runner = args.exe.resolve()
    data = json.loads(args.snapshot.read_text(encoding="utf-8"))
    if args.roles:
        roles = [int(value.strip()) for value in args.roles.split(",")]
        agents = data["day_info"]["agents"]
        if len(roles) != len(agents):
            parser.error(f"--roles requires exactly {len(agents)} values")
        if any(role not in (0, 1) for role in roles):
            parser.error("--roles values must be 0 (patrol) or 1 (supply)")
        data["types"] = roles
        for agent, role in zip(agents, roles):
            agent["kind"] = role
    env = dict(os.environ, HEXUDON_THREADS=str(args.threads))
    traffic_history = []
    days = []
    for day in range(len(data["config"]["daySteps"])):
        data["search"] = {
            "timeLimitMs": args.budget,
            "randomSeed": args.seed,
            "threads": args.threads,
            "futureWeight": args.future_weight,
            "terminalAccessWeight": args.terminal_access_weight,
            "crossMoves": args.cross_moves,
            "endSpotWeight": args.end_spot_weight,
            "tailRepair": args.tail_repair,
            "terminalRollout": args.terminal_rollout,
            "stockRepair": args.stock_repair,
            "marginalStock": args.marginal_stock,
            "pathStock": args.path_stock,
            "mobileForecast": args.mobile_forecast,
            "idleForecast": args.idle_forecast,
            "actualRuin": args.actual_ruin,
            "boundarySelect": args.boundary_select,
            "clusterRuin": args.cluster_ruin,
            "directStockInsert": args.direct_stock_insert,
            "twoDaySelect": args.two_day_select,
            "hardFullMax": args.hard_full_max,
            "dualHubSeeds": args.dual_hub_seeds,
            "stockBuildSeeds": args.stock_build_seeds,
            "loopRepair": args.loop_repair,
            "objectiveMode": args.objective,
        }
        start_agents = copy.deepcopy(data["day_info"]["agents"])
        response, wall_ms = BENCH.call(
            runner, data, env, timeout=args.budget / 1000 + 15)
        replay = BENCH.trace(data, response["plan"], env)
        frames = replay["frames"]
        brand_at = {spot["pos"]: spot["brand"] for spot in data["config"]["spots"]}
        spot_positions = set(brand_at)
        patrol_visits = {pos: {} for pos in spot_positions}
        previous_cells = [None] * len(start_agents)
        for tick, frame in enumerate(frames):
            for agent_index, agent in enumerate(frame["agents"]):
                cell = agent["cell"]
                if (start_agents[agent_index]["kind"] == 0 and cell in spot_positions
                        and previous_cells[agent_index] != cell):
                    patrol_visits[cell].setdefault(str(agent_index), []).append(tick)
                previous_cells[agent_index] = cell
        daily_brands = {
            brand_at[pos] for frame in frames for pos in frame["collected"]
        }
        day_score = [
            len(set(data["history"]["distinct_brands"]) | daily_brands),
            len(daily_brands),
            frames[-1]["servings"],
        ]
        days.append({
            "day": day,
            "wall_ms": wall_ms,
            "score": day_score,
            "start_agents": start_agents,
            "end_agents": copy.deepcopy(frames[-1]["agents"]),
            "plan": response["plan"],
            "collected_spots": sorted({
                pos for frame in frames for pos in frame["collected"]
            }),
            "collection_counts": dict(sorted(Counter(
                pos for frame in frames for pos in frame["collected"]
            ).items())),
            "spot_visits": {
                str(pos): visitors for pos, visitors in sorted(patrol_visits.items())
                if visitors
            },
            "diagnostics": copy.deepcopy(response.get("diagnostics", {})),
        })
        print(f"MATCH day={day} score={day_score}", flush=True)
        BENCH.advance(data, response["plan"], replay, traffic_history)
        for traffic in data["day_info"]["traffics"]:
            traffic["status"] = 0

    history = data["history"]
    result = {
        "case": args.snapshot.stem,
        "budget_ms": args.budget,
        "seed": args.seed,
        "threads": args.threads,
        "future_weight": args.future_weight,
        "terminal_access_weight": args.terminal_access_weight,
        "cross_moves": args.cross_moves,
        "end_spot_weight": args.end_spot_weight,
        "traffic": "idle",
        "tail_repair": args.tail_repair,
        "terminal_rollout": args.terminal_rollout,
        "stock_repair": args.stock_repair,
        "marginal_stock": args.marginal_stock,
        "path_stock": args.path_stock,
        "mobile_forecast": args.mobile_forecast,
        "idle_forecast": args.idle_forecast,
        "actual_ruin": args.actual_ruin,
        "boundary_select": args.boundary_select,
        "cluster_ruin": args.cluster_ruin,
        "direct_stock_insert": args.direct_stock_insert,
        "two_day_select": args.two_day_select,
        "hard_full_max": args.hard_full_max,
        "dual_hub_seeds": args.dual_hub_seeds,
        "stock_build_seeds": args.stock_build_seeds,
        "loop_repair": args.loop_repair,
        "objective": args.objective,
        "exe": str(runner),
        "exe_sha256": hashlib.sha256(runner.read_bytes()).hexdigest(),
        "days": days,
        "score": [
            len(history["distinct_brands"]),
            history["cumulative_daily_types"],
            history["total_servings"],
        ],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result["score"]))


if __name__ == "__main__":
    main()
