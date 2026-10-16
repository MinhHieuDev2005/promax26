"""Replayable offline experiments. No online calls and no legacy modifications."""
import argparse
import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import time

ROOT = Path(__file__).resolve().parents[2]
MEMORY = ROOT / "solver_learning"
spec = importlib.util.spec_from_file_location("budget_v1", ROOT / "solvers/chokudai/budget_sweep.py")
sim = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sim)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def log(value):
    with (MEMORY / "experiment_log.jsonl").open("a", encoding="utf-8") as f:
        f.write(json.dumps(value, ensure_ascii=False) + "\n")


def invoke(policy, payload, env, budget):
    if policy == "v1":
        exe, args = sim.RUNNER, []
    elif policy == "v2":
        exe, args = ROOT / "build/chokudai_v2/chokudai_v2_runner.exe", []
    elif policy == "v2h04":
        exe, args = ROOT / "build/chokudai_v2/chokudai_v2_h04_runner.exe", []
    elif policy == "v2h05":
        exe, args = ROOT / "build/chokudai_v2/chokudai_v2_h05_runner.exe", []
    elif policy == "v2h08":
        exe, args = ROOT / "build/chokudai_v2/chokudai_v2_h08_runner.exe", []
    elif policy == "v2h12":
        exe, args = ROOT / "build/chokudai_v2/chokudai_v2_h12_runner.exe", []
    elif policy == "v2h17":
        exe, args = ROOT / "build/chokudai_v2/chokudai_v2_h17_runner.exe", []
    elif policy == "v2h20":
        exe, args = ROOT / "build/chokudai_v2/chokudai_v2_h20_runner.exe", []
    elif policy == "v2h22":
        exe, args = ROOT / "build/chokudai_v2/chokudai_v2_h22_runner.exe", []
    elif policy == "h24":
        exe, args = ROOT / "build/chokudai_h24/chokudai_h24_runner.exe", []
    elif policy == "pareto_route_pool":
        exe, args = ROOT / "build/pareto_route_pool/pareto_route_pool_runner.exe", []
    elif policy == "pareto_route_pool_v2":
        exe, args = ROOT / "build/pareto_route_pool_v2/pareto_route_pool_v2_runner.exe", []
    else:
        exe, args = sim.CORE, ["plan", policy]
    started = time.perf_counter()
    proc = subprocess.run([str(exe), *args], input=json.dumps(payload), capture_output=True,
                          text=True, encoding="utf-8", env=env, cwd=ROOT,
                          timeout=budget / 1000 + 15)
    if proc.returncode:
        raise RuntimeError(proc.stderr + proc.stdout)
    result = json.loads(proc.stdout)
    if isinstance(result, list):
        result = {"actions": result}
    if result.get("ok") is False:
        raise RuntimeError(str(result))
    return result, round((time.perf_counter() - started) * 1000, 3)


def replay(checkpoint, env):
    data = copy.deepcopy(checkpoint["initial"])
    traffic = []
    scores = []
    for row in checkpoint["days"]:
        trace = sim.trace(data, row["plan"], env)
        sim.advance(data, row["plan"], trace, traffic)
        scores.append(len({s["brand"] for s in data["config"]["spots"]
                           if any(s["pos"] in f["collected"] for f in trace["frames"])}))
    h = data["history"]
    score = [len(h["distinct_brands"]), h["cumulative_daily_types"], h["total_servings"]]
    if score != checkpoint["score"]:
        raise AssertionError(("replay mismatch", score, checkpoint["score"]))
    return {"score": score, "daily_types": scores, "validator": "unchanged bin/hexudon.exe trace"}


def run(a, policy):
    # Explicitly load durable learning before each experiment.
    for name in ("knowledge_base.md", "elite_solutions.json", "failed_patterns.json"):
        (MEMORY / name).read_text(encoding="utf-8")
    initial = json.loads(Path(a.snapshot).read_text(encoding="utf-8"))
    if a.roles:
        roles = [int(x) for x in a.roles.split(",")]
        if len(roles) != len(initial["day_info"]["agents"]) or any(x not in (0, 1) for x in roles):
            raise ValueError("--roles must contain one 0/1 value per agent")
        initial["types"] = roles
        for agent, role in zip(initial["day_info"]["agents"], roles):
            agent["kind"] = role
    data = copy.deepcopy(initial)
    env = dict(os.environ, HEXUDON_THREADS=str(a.threads))
    run_id = f"{a.label}-{policy}-{a.budget}-{a.seed}"
    output = MEMORY / "runs" / (run_id + ".json")
    if output.exists():
        print("SKIP", output, flush=True)
        return
    overrides = json.loads(a.search)
    if a.slice_ms is not None:
        overrides["sliceMs"] = a.slice_ms
    if a.layer_capacity is not None:
        overrides["layerCapacity"] = a.layer_capacity
    if a.attempts is not None:
        overrides["attempts"] = a.attempts
    meta = {"experiment_id": run_id, "parent": a.parent, "hypothesis": a.hypothesis,
            "solver": policy, "budget_ms": a.budget, "random_seed": a.seed,
            "threads": a.threads, "snapshot_sha256": digest(Path(a.snapshot)),
            "roles": initial.get("types"),
            "search_overrides": overrides, "status": "started"}
    log(meta)
    traffic, records = [], []
    total_brands = len({s["brand"] for s in data["config"]["spots"]})
    try:
        for day in range(data["day_info"]["day"], len(data["config"]["daySteps"])):
            data["search"] = {"timeLimitMs": a.budget, "randomSeed": a.seed,
                              "minIterations": 0, "maxIterations": 1000000,
                              "stagnationIterations": 0, **overrides}
            data["include_planner_state"] = True
            result, wall = invoke(policy, data, env, a.budget)
            plan = result.get("plan", result.get("actions"))
            tr = sim.trace(data, plan, env)
            before = copy.deepcopy(data["day_info"])
            sim.advance(data, plan, tr, traffic)
            if result.get("planner_state") is not None:
                data["planner_state"] = result["planner_state"]
            else:
                data.pop("planner_state", None)
            acquired = {p for f in tr["frames"] for p in f["collected"]}
            daily_types = len({s["brand"] for s in data["config"]["spots"] if s["pos"] in acquired})
            record = {"day": day, "wall_ms": wall, "daily_types": daily_types,
                      "servings": tr["frames"][-1]["servings"], "plan": plan,
                      "input_state": before, "ending_agents": tr["frames"][-1]["agents"],
                      "diagnostics": result.get("diagnostics", {}),
                      "acquisitions": [{"step": i, "spots": f["collected"]}
                                       for i, f in enumerate(tr["frames"]) if f["collected"]]}
            records.append(record)
            write_json(MEMORY / "runs" / (run_id + ".partial.json"),
                       {**meta, "initial": initial, "days": records})
            print(run_id, "day", day + 1, "score", daily_types, record["servings"], "ms", wall, flush=True)
        h = data["history"]
        score = [len(h["distinct_brands"]), h["cumulative_daily_types"], h["total_servings"]]
        valid = score[:2] == [total_brands, total_brands * len(data["config"]["daySteps"])]
        checkpoint = {**meta, "status": "complete", "initial": initial, "days": records,
                      "score": score, "valid": valid, "wall_ms": sum(d["wall_ms"] for d in records),
                      "deadline_pass": all(d["wall_ms"] <= a.budget + 100 for d in records)}
        checkpoint["verification"] = replay(checkpoint, env)
        write_json(output, checkpoint)
        log({k: v for k, v in checkpoint.items() if k not in ("initial", "days")})
        if valid:
            archive_path = MEMORY / "elite_solutions.json"
            archive = json.loads(archive_path.read_text(encoding="utf-8"))
            signature = hashlib.sha256(json.dumps([d["plan"] for d in records]).encode()).hexdigest()
            if not any(e["signature"] == signature for e in archive):
                archive.append({"experiment_id": run_id, "score": score, "signature": signature,
                                "checkpoint": str(output.relative_to(ROOT)), "family": policy})
                write_json(archive_path, sorted(archive, key=lambda r: r["score"], reverse=True))
        print("COMPLETE", run_id, score, "coverage", valid, flush=True)
    except Exception as exc:
        log({**meta, "status": "failed", "error": str(exc)})
        raise


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--policies", nargs="+", default=["v1"])
    p.add_argument("--snapshot", default="build/chokudai/budget-study/snapshots/q06-d0.json")
    p.add_argument("--budget", type=int, default=50000)
    p.add_argument("--seed", type=int, default=1)
    p.add_argument("--threads", type=int, default=4)
    p.add_argument("--label", required=True)
    p.add_argument("--parent", default=None)
    p.add_argument("--hypothesis", required=True)
    p.add_argument("--search", default="{}")
    p.add_argument("--slice-ms", type=int)
    p.add_argument("--layer-capacity", type=int)
    p.add_argument("--attempts", type=int)
    p.add_argument("--roles", help="comma-separated role override for role experiments")
    p.add_argument("--replay")
    a = p.parse_args()
    if a.replay:
        print(replay(json.loads(Path(a.replay).read_text(encoding="utf-8")),
                     dict(os.environ, HEXUDON_THREADS=str(a.threads))))
    else:
        for policy in a.policies:
            run(a, policy)


if __name__ == "__main__":
    main()
