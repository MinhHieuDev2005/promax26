"""Serial, replay-verified benchmarks; no network or server mutations.

Use --checkpoint/--day for a paired fixed-state ablation, or --cases for
independent full matches. Uninstrumented search counters are null, not zero.
"""
import argparse
import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import statistics
import subprocess
import threading
import time

import psutil

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("traffic_benchmark", ROOT / "solvers/horizon_portfolio/benchmark.py")
traffic_bench = importlib.util.module_from_spec(spec)
spec.loader.exec_module(traffic_bench)
sim = traffic_bench.legacy.sim


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def measure(command, payload, env, timeout):
    start = time.perf_counter()
    process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                               stderr=subprocess.PIPE, text=True, encoding="utf-8", env=env, cwd=ROOT)
    watched = psutil.Process(process.pid)
    stop = threading.Event()
    samples = {"peak_rss_bytes": 0, "cpu_seconds_sampled": 0.0}

    def monitor():
        while not stop.is_set():
            try:
                mem = watched.memory_info()
                samples["peak_rss_bytes"] = max(samples["peak_rss_bytes"], mem.rss, getattr(mem, "peak_wset", 0))
                cpu = watched.cpu_times()
                samples["cpu_seconds_sampled"] = max(samples["cpu_seconds_sampled"], cpu.user + cpu.system)
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                break
            stop.wait(0.025)

    thread = threading.Thread(target=monitor, daemon=True)
    thread.start()
    try:
        out, err = process.communicate(json.dumps(payload), timeout=timeout)
    except subprocess.TimeoutExpired:
        process.kill()
        process.communicate()
        raise
    finally:
        stop.set()
        thread.join()
    samples["wall_ms"] = (time.perf_counter() - start) * 1000
    if process.returncode:
        raise RuntimeError(f"exit={process.returncode}: {err[:2000]} {out[:2000]}")
    value = json.loads(out)
    if isinstance(value, list):
        value = {"plan": value}
    if value.get("ok") is False:
        raise RuntimeError(str(value))
    return value, samples


def initial_state(path, role_spec):
    raw = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    c = copy.deepcopy(raw.get("config", raw))
    c["startsAt"] = 0
    if role_spec == "first":
        roles = [1] + [0] * (len(c["agents"]) - 1)
    else:
        roles = [int(x) for x in role_spec.split(",")]
    if len(roles) != len(c["agents"]) or any(x not in (0, 1) for x in roles) or not any(x == 0 for x in roles):
        raise ValueError("roles must specify one 0/1 per agent and at least one patrol")
    return {"op": "plan", "config": c, "types": roles,
            "history": {"distinct_brands": [], "submitted_actions": [],
                        "cumulative_daily_types": 0, "total_servings": 0},
            "day_info": {"day": 0, "agents": [
                {"kind": kind, "pos": pos, "fuel": c["fuelLimits"]} for kind, pos in zip(roles, c["agents"])],
                "others": [], "traffics": [
                    {"pos": r*c["map"]["width"]+col, "status": 0}
                    for r, row in enumerate(c["map"]["cells"]) for col, terrain in enumerate(row) if terrain == 1]}}


def score(data):
    h = data["history"]
    return [len(h["distinct_brands"]), h["cumulative_daily_types"], h["total_servings"]]


def metrics(diag):
    diag = diag or {}
    names = ["expanded", "candidate_count", "duplicates", "tt_hits", "tt_lookups",
             "dominance_prunes", "bound_prunes", "local_search_moves", "route_count",
             "combinations", "validated", "improvements", "labels", "transitions"]
    result = {name: diag.get(name) for name in names}
    for rate, count, total in [("duplicate_rate", "duplicates", "candidate_count"),
                               ("tt_hit_rate", "tt_hits", "tt_lookups"),
                               ("expansions_per_ms", "expanded", "elapsed_ms")]:
        result[rate] = diag[count]/diag[total] if diag.get(count) is not None and diag.get(total) else None
    return result


def run(args, case, seed):
    env = dict(os.environ, HEXUDON_THREADS="1")
    if args.checkpoint:
        parent = json.loads(Path(args.checkpoint).read_text(encoding="utf-8"))
        data, traffic = copy.deepcopy(parent["initial"]), []
        if parent["traffic_model"] != args.traffic:
            raise ValueError("fixed-state traffic scenario mismatch")
        for row in parent["days"][:args.day-1]:
            tr = sim.trace(data, row["plan"], env)
            traffic_bench.advance(data, row["plan"], tr, traffic, args.traffic)
        if data["day_info"]["day"] != args.day-1:
            raise ValueError("checkpoint does not contain requested prefix")
    else:
        data, traffic = initial_state(case, args.roles), []
    initial, initial_traffic = copy.deepcopy(data), copy.deepcopy(traffic)
    exe = Path(args.exe).resolve() if args.exe else sim.CORE
    command = [str(exe)] + (["plan", args.policy]
                            if not args.exe or args.native_cli else [])
    identity = Path(args.checkpoint or case).stem
    mode = f"day{args.day}" if args.checkpoint else (f"prefix{args.max_days}" if args.max_days else "match")
    name = f"{args.label}-{identity}-{mode}-s{seed}"
    output = ROOT / "solver_learning/runs" / (name + ".json")
    if output.exists():
        raise FileExistsError(output)
    rows = []
    end = args.day if args.checkpoint else len(data["config"]["daySteps"])
    if args.max_days and not args.checkpoint:
        end = min(end, args.max_days)
    metadata = {"experiment_id": name, "initial": initial, "traffic_model": args.traffic,
                "case_path": str(case) if case else None, "checkpoint": args.checkpoint,
                "source_sha256": digest(args.checkpoint or case), "executable": str(exe),
                "executable_sha256": digest(exe), "seed": seed, "budget_ms": args.budget,
                "search": json.loads(args.search), "mode": mode, "policy": args.policy,
                "roles": data["types"], "profiling": "psutil 25ms; Windows peak_wset; sampled CPU is a lower bound"}
    for day in range(data["day_info"]["day"], end):
        data["search"] = {**metadata["search"], "timeLimitMs": args.budget, "randomSeed": seed,
                          "minIterations": 0, "maxIterations": 1000000, "stagnationIterations": 0}
        state_before = copy.deepcopy(data["day_info"])
        value, performance = measure(command, data, env, args.budget/1000 + 3)
        actions = value.get("plan", value.get("actions"))
        if actions is None:
            raise ValueError("missing actions")
        replay = sim.trace(data, actions, env)
        before = score(data)
        traffic_bench.advance(data, actions, replay, traffic, args.traffic)
        if value.get("planner_state") is not None:
            data["planner_state"] = value["planner_state"]
        else:
            data.pop("planner_state", None)
        diag = value.get("diagnostics", {})
        row = {"day": day, "input_state": state_before, "plan": actions, **performance,
               "daily_types": score(data)[1]-before[1], "servings": score(data)[2]-before[2],
               "diagnostics": diag, "metrics": metrics(diag)}
        rows.append(row)
        metadata.update(days=rows, score=score(data))
        output.with_suffix(".partial.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
        print(name, "day", day+1, "score", score(data), "ms", round(performance["wall_ms"]),
              "MiB", round(performance["peak_rss_bytes"]/2**20, 1), flush=True)
    # Independent second replay from the original state, ignoring planner hints.
    check, check_traffic = copy.deepcopy(initial), initial_traffic
    for row in rows:
        tr = sim.trace(check, row["plan"], env)
        traffic_bench.advance(check, row["plan"], tr, check_traffic, args.traffic)
    assert check["history"] == data["history"]
    required = len({s["brand"] for s in data["config"]["spots"]})
    metadata.update(verified=True, full_coverage=all(r["daily_types"] == required for r in rows),
                    deadline_pass=all(r["wall_ms"] <= args.budget for r in rows),
                    peak_rss_bytes=max(r["peak_rss_bytes"] for r in rows),
                    max_day_ms=max(r["wall_ms"] for r in rows))
    output.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    return metadata


def summarize(records):
    # Group different maps separately: raw bowl totals have different scales.
    result = {}
    for row in records:
        key = row.get("case_path") or row["checkpoint"]
        result.setdefault(key, []).append(row)
    for key, group in list(result.items()):
        bowls = [sum(d["servings"] for d in r["days"]) for r in group]
        result[key] = {"n": len(bowls), "mean": statistics.mean(bowls), "median": statistics.median(bowls),
                       "min": min(bowls), "max": max(bowls), "stddev": statistics.pstdev(bowls),
                       "invalid": sum(not r["verified"] for r in group),
                       "coverage_failures": sum(not r["full_coverage"] for r in group),
                       "deadline_failures": sum(not r["deadline_pass"] for r in group)}
    return result


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--cases", nargs="+")
    p.add_argument("--checkpoint")
    p.add_argument("--day", type=int, default=4, help="1-based fixed day")
    p.add_argument("--max-days", type=int, help="prefix smoke only; not a complete-match result")
    p.add_argument("--exe")
    p.add_argument("--native-cli", action="store_true",
                   help="invoke --exe through the core '<command> <policy>' protocol")
    p.add_argument("--policy", default="alns")
    p.add_argument("--budget", type=int, default=45000)
    p.add_argument("--roles", default="first")
    p.add_argument("--seeds", nargs="+", type=int, default=[1, 2, 3])
    p.add_argument("--traffic", choices=["idle", "mirror"], required=True)
    p.add_argument("--search", default="{}")
    p.add_argument("--variant", choices=["baseline", "pool", "boundary", "wide", "chokudai", "preview"], default="boundary")
    p.add_argument("--label", required=True)
    args = p.parse_args()
    if args.budget<=0 or args.day<=0 or (args.max_days is not None and args.max_days<=0):
        p.error("budget/day/max-days must be positive")
    presets = {
        "baseline": {"enablePool": 0, "boundaryTrade": 0, "enableBoundarySearch": 0},
        "pool": {"enablePool": 1, "boundaryTrade": 0, "enableBoundarySearch": 0},
        "boundary": {"enablePool": 1, "boundaryTrade": 1, "enableBoundarySearch": 0},
        "wide": {"enablePool": 1, "boundaryTrade": 1, "enableBoundarySearch": 0, "rolloutCandidates": 8},
        "chokudai": {"enablePool": 1, "boundaryTrade": 1, "enableBoundarySearch": 1, "rolloutCandidates": 8},
        "preview": {"enablePool": 1, "boundaryTrade": 1, "enableBoundarySearch": 0, "fastFuture": 1},
    }
    requested_search = json.loads(args.search)
    # Windows command shells can preserve one extra JSON string layer.
    if isinstance(requested_search, str):
        requested_search = json.loads(requested_search)
    if not isinstance(requested_search, dict):
        p.error("--search must decode to a JSON object")
    args.search = json.dumps({**presets[args.variant], **requested_search})
    if bool(args.cases) == bool(args.checkpoint):
        p.error("specify exactly one of --cases or --checkpoint")
    records = [run(args, case, seed) for case in args.cases or [None] for seed in args.seeds]
    summary = summarize(records)
    path = ROOT / "solver_learning/runs" / (args.label + "-summary.json")
    if path.exists():
        raise FileExistsError(path)
    path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2), flush=True)


if __name__ == "__main__":
    main()
