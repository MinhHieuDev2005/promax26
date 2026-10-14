"""Explicit traffic scenarios; scoring stays in unchanged hexudon.exe trace.

mirror: all players generate own-team traffic (legacy benchmark assumption).
idle: other players generate zero traffic, averaged over config.players.
Neither scenario asserts knowledge of real opponents.
"""
import argparse
import copy
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import time

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("legacy_experiment", ROOT / "solvers/chokudai_v2/experiment.py")
legacy = importlib.util.module_from_spec(spec)
spec.loader.exec_module(legacy)


def advance(data, plan, trace, traffic_history, mode):
    legacy.sim.advance(data, plan, trace, traffic_history)
    if mode == "idle":
        config = data["config"]
        for road in data["day_info"]["traffics"]:
            volume = sum(t.get(road["pos"], 0) for t in traffic_history[-2:])
            road["status"] = (2 if volume >= config["jammedThreshold"] * config["players"]
                              else 1 if volume >= config["busyThreshold"] * config["players"] else 0)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--policy", default="alns")
    parser.add_argument("--exe")
    parser.add_argument("--budget", type=int, default=8000)
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--traffic", choices=["mirror", "idle"], required=True)
    parser.add_argument("--roles", default="0,1,0,0")
    parser.add_argument("--label", required=True)
    args = parser.parse_args()
    data = json.loads((ROOT / "solver_learning/snapshots/user-25x25-d0.json").read_text(encoding="utf-8"))
    data["types"] = [int(x) for x in args.roles.split(",")]
    for agent, role in zip(data["day_info"]["agents"], data["types"]):
        agent["kind"] = role
    initial = copy.deepcopy(data)
    env = dict(os.environ, HEXUDON_THREADS="1")
    traffic, records = [], []
    output = ROOT / "solver_learning/runs" / (args.label + ".json")
    if output.exists():
        raise FileExistsError(output)
    partial = output.with_suffix(".partial.json")
    if partial.exists():
        previous = json.loads(partial.read_text(encoding="utf-8"))
        if (previous["initial"] != initial or previous["traffic_model"] != args.traffic
                or previous["budget_ms"] != args.budget or previous["seed"] != args.seed
                or previous.get("executable") != args.exe or previous["policy"] != args.policy):
            raise ValueError("checkpoint does not match requested scenario")
        records = previous["days"]
        for row in records:
            tr = legacy.sim.trace(data, row["plan"], env)
            advance(data, row["plan"], tr, traffic, args.traffic)
        if previous.get("planner_state") is not None:
            data["planner_state"] = previous["planner_state"]
        print("RESUME", len(records), "completed days", flush=True)
    for day in range(len(records), len(data["config"]["daySteps"])):
        data["search"] = {"timeLimitMs": args.budget, "randomSeed": args.seed,
                          "minIterations": 0, "maxIterations": 1000000,
                          "stagnationIterations": 0}
        data["include_planner_state"] = True
        if args.exe:
            started = time.perf_counter()
            result = subprocess.run([args.exe], input=json.dumps(data), text=True,
                                    capture_output=True, env=env, timeout=args.budget / 1000 + 15)
            if result.returncode:
                raise RuntimeError(result.stderr + result.stdout)
            result = json.loads(result.stdout)
            wall = (time.perf_counter() - started) * 1000
        else:
            result, wall = legacy.invoke(args.policy, data, env, args.budget)
        plan = result.get("plan", result.get("actions"))
        trace = legacy.sim.trace(data, plan, env)
        state = copy.deepcopy(data["day_info"])
        advance(data, plan, trace, traffic, args.traffic)
        if result.get("planner_state") is not None:
            data["planner_state"] = result["planner_state"]
        else:
            data.pop("planner_state", None)
        before = records[-1]["daily_total"] if records else 0
        records.append({"day": day, "plan": plan, "input_state": state,
                        "servings": trace["frames"][-1]["servings"],
                        "daily_types": data["history"]["cumulative_daily_types"] - before,
                        "daily_total": data["history"]["cumulative_daily_types"],
                        "wall_ms": wall, "diagnostics": result.get("diagnostics")})
        checkpoint = {"initial": initial, "days": records, "traffic_model": args.traffic,
                      "policy": args.policy, "executable": args.exe,
                      "planner_state": data.get("planner_state"),
                      "budget_ms": args.budget, "seed": args.seed,
                      "opponent_assumption": "identical own-team traffic" if args.traffic == "mirror" else "all other teams idle",
                      "score": [len(data["history"]["distinct_brands"]),
                                data["history"]["cumulative_daily_types"], data["history"]["total_servings"]]}
        output.with_suffix(".partial.json").write_text(json.dumps(checkpoint, indent=2), encoding="utf-8")
        print(args.label, "day", day + 1, "bowls", records[-1]["servings"], "score", checkpoint["score"], "ms", round(wall), flush=True)
    replay = copy.deepcopy(initial)
    traffic = []
    for row in records:
        trace = legacy.sim.trace(replay, row["plan"], env)
        advance(replay, row["plan"], trace, traffic, args.traffic)
    assert replay["history"] == data["history"]
    checkpoint["verified"] = True
    checkpoint["deadline_pass"] = all(r["wall_ms"] <= args.budget for r in records)
    output.write_text(json.dumps(checkpoint, indent=2), encoding="utf-8")
    print("VERIFIED", checkpoint["score"], flush=True)


if __name__ == "__main__":
    main()
