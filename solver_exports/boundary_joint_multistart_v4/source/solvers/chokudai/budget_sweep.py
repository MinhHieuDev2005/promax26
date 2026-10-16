"""Measure existing v1 EXE at fixed states and budgets; never changes solver.

Uses the existing core trace for independent validation and snapshot generation.
Raw records are append-only JSONL, permitting incremental/resumable experiments.
"""
import argparse
import concurrent.futures
import copy
import hashlib
import json
import os
from pathlib import Path
import random
import subprocess
import time

ROOT = Path(__file__).resolve().parents[2]
RUNNER = ROOT / "build/chokudai/chokudai_runner.exe"
CORE = ROOT / "bin/hexudon.exe"
CASES = ROOT / "cases/mlns-profile/online"


def call(executable, payload, env, args=(), timeout=65):
    began = time.perf_counter()
    proc = subprocess.run([str(executable), *args], input=json.dumps(payload),
                          capture_output=True, text=True, encoding="utf-8",
                          env=env, timeout=timeout, cwd=ROOT)
    if proc.returncode:
        raise RuntimeError(proc.stderr + proc.stdout)
    result = json.loads(proc.stdout)
    if result.get("ok") is False or result.get("valid") is False:
        raise RuntimeError(str(result))
    return result, round(1000 * (time.perf_counter() - began), 2)


def trace(payload, plan, env):
    data = copy.deepcopy(payload)
    data["actions"] = plan
    return call(CORE, data, env, ("trace", "greedy"), timeout=15)[0]


def advance(payload, plan, replay, traffic_history):
    config = payload["config"]
    day = payload["day_info"]["day"]
    frames = replay["frames"]
    roads = {r * config["map"]["width"] + c
             for r, row in enumerate(config["map"]["cells"])
             for c, terrain in enumerate(row) if terrain == 1}
    dwell = {pos: 0 for pos in roads}
    for frame in frames[1:]:
        for agent in frame["agents"]:
            if agent["cell"] in dwell:
                dwell[agent["cell"]] += 1
    traffic_history.append(dwell)
    history = payload["history"]
    brands = {s["pos"]: s["brand"] for s in config["spots"]}
    collected = {brands[pos] for frame in frames for pos in frame["collected"]}
    history["distinct_brands"] = sorted(set(history["distinct_brands"]) | collected)
    history["submitted_actions"].append(plan)
    history["cumulative_daily_types"] += len(collected)
    history["total_servings"] += frames[-1]["servings"]
    # Same sum of the last TWO days / players as road_status_for_day.
    # One own team: do not divide by the number of days.
    used = traffic_history[-2:]
    traffics = []
    for pos in sorted(roads):
        volume = sum(d.get(pos, 0) for d in used)
        status = 2 if volume >= config["jammedThreshold"] else (
            1 if volume >= config["busyThreshold"] else 0)
        traffics.append({"pos": pos, "status": status})
    payload["day_info"] = {
        "day": day + 1,
        "agents": [{"kind": a["type"], "pos": a["cell"], "fuel": a["fuel"]}
                   for a in frames[-1]["agents"]],
        "others": [], "traffics": traffics,
    }


def snapshots(directory, names, env):
    directory.mkdir(parents=True, exist_ok=True)
    for name in names:
        path = directory / f"{name}-d0.json"
        if path.exists():
            continue
        source = next(CASES.glob(name + "-*.json"))
        config = json.loads(source.read_text(encoding="utf-8"))["config"]
        roles, _ = call(RUNNER, {"op": "roles", "config": config,
                                "search": {"timeLimitMs": 1200}}, env)
        types = roles["roles"]
        config["startsAt"] = 0
        data = {"op": "plan", "config": config, "types": types,
                "history": {"distinct_brands": [], "submitted_actions": [],
                            "cumulative_daily_types": 0, "total_servings": 0},
                "day_info": {"day": 0, "agents": [
                    {"kind": kind, "pos": pos, "fuel": config["fuelLimits"]}
                    for kind, pos in zip(types, config["agents"])],
                    "others": [], "traffics": []}}
        data["day_info"]["traffics"] = [
            {"pos": r * config["map"]["width"] + c, "status": 0}
            for r, row in enumerate(config["map"]["cells"])
            for c, t in enumerate(row) if t == 1]
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        traffic_history = []
        for day in range(min(2, len(config["daySteps"]) - 1)):
            data["search"] = {"timeLimitMs": 3000, "randomSeed": 1}
            result, _ = call(RUNNER, data, env)
            replay = trace(data, result["plan"], env)
            advance(data, result["plan"], replay, traffic_history)
        if data["day_info"]["day"] > 0:
            data.pop("search", None)
            (directory / f"{name}-d{data['day_info']['day']}.json").write_text(
                json.dumps(data, indent=2), encoding="utf-8")
        print(f"snapshots ready {name} roles={types}", flush=True)


def check_score(data, result, replay):
    frames = replay["frames"]
    brand_at = {s["pos"]: s["brand"] for s in data["config"]["spots"]}
    daily = {brand_at[p] for f in frames for p in f["collected"]}
    official = [len(set(data["history"]["distinct_brands"]) | daily),
                len(daily), frames[-1]["servings"]]
    if official != result["diagnostics"]["score"]:
        raise AssertionError((official, result["diagnostics"]))
    baseline = result["diagnostics"]["baseline_score"]
    if any(official[i] < baseline[i] for i in (0, 1)):
        raise AssertionError(("coverage regression", baseline, official))


def run_one(path, budget, seed, threads):
    data = json.loads(path.read_text(encoding="utf-8"))
    data["search"] = {"timeLimitMs": budget, "randomSeed": seed}
    env = dict(os.environ, HEXUDON_THREADS=str(threads))
    result, wall = call(RUNNER, data, env, timeout=budget / 1000 + 15)
    replay = trace(data, result["plan"], env)
    check_score(data, result, replay)
    return {"case": path.stem, "budget_ms": budget, "seed": seed,
            "threads": threads, "wall_ms": wall,
            "snapshot_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            **result["diagnostics"]}


def run_match(path, budget, seed, threads):
    data = json.loads(path.read_text(encoding="utf-8"))
    if data["day_info"]["day"] != 0:
        raise ValueError("full-match benchmark requires day zero")
    env = dict(os.environ, HEXUDON_THREADS=str(threads))
    traffic_history = []
    records = []
    for day in range(len(data["config"]["daySteps"])):
        data["search"] = {"timeLimitMs": budget, "randomSeed": seed}
        result, wall = call(RUNNER, data, env, timeout=budget / 1000 + 15)
        replay = trace(data, result["plan"], env)
        check_score(data, result, replay)
        records.append({"day": day, "wall_ms": wall, **result["diagnostics"]})
        advance(data, result["plan"], replay, traffic_history)
        print(f"MATCH {path.stem} {budget/1000:g}s day={day} score="
              f"{result['diagnostics']['score']}", flush=True)
    h = data["history"]
    return {"case": path.stem, "budget_ms": budget, "seed": seed, "threads": threads,
            "days": records, "score": [len(h["distinct_brands"]),
            h["cumulative_daily_types"], h["total_servings"]]}


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--output", default="build/chokudai/budget-study")
    p.add_argument("--prepare", action="store_true")
    p.add_argument("--maps", nargs="+", default=["q01", "q03", "q04", "q06"])
    p.add_argument("--states", nargs="+", default=["q01-d0", "q03-d0", "q04-d0", "q06-d0"])
    p.add_argument("--budgets", nargs="+", type=int, default=[3000, 5000, 10000, 20000, 30000, 40000, 50000])
    p.add_argument("--seeds", nargs="+", type=int, default=[1])
    p.add_argument("--jobs", type=int, default=2)
    p.add_argument("--threads", type=int, default=4)
    p.add_argument("--matches", action="store_true")
    a = p.parse_args()
    output = ROOT / a.output
    output.mkdir(parents=True, exist_ok=True)
    if a.prepare:
        snapshots(output / "snapshots", a.maps, dict(os.environ, HEXUDON_THREADS=str(a.threads)))
    file = output / ("matches.jsonl" if a.matches else "runs.jsonl")
    done = set()
    if file.exists():
        for line in file.read_text(encoding="utf-8").splitlines():
            r = json.loads(line)
            done.add((r["case"], r["budget_ms"], r["seed"], r["threads"]))
    tasks = [(output / "snapshots" / (name + ".json"), budget, seed, a.threads)
             for name in a.states for budget in a.budgets for seed in a.seeds
             if (name, budget, seed, a.threads) not in done]
    random.Random(9029).shuffle(tasks)
    print(f"START {len(tasks)} runs, jobs={a.jobs}, threads/solver={a.threads}", flush=True)
    with concurrent.futures.ThreadPoolExecutor(max_workers=a.jobs) as pool:
        worker = run_match if a.matches else run_one
        futures = {pool.submit(worker, *task): task for task in tasks}
        for future in concurrent.futures.as_completed(futures):
            result = future.result()
            with file.open("a", encoding="utf-8") as stream:
                stream.write(json.dumps(result) + "\n")
            print(f"{result['case']} {result['budget_ms']/1000:g}s seed={result['seed']} "
                  f"score={result['score']} baseline={result.get('baseline_score')} "
                  f"wall={result.get('wall_ms')}ms", flush=True)


if __name__ == "__main__":
    main()
