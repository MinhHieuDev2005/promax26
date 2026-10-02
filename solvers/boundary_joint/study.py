"""Serial H61 studies using the frozen Boundary Pool replay harness."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace
import time

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("bench", ROOT / "solvers/boundary_pool/benchmark.py")
bench = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bench)
# User-authorized 24-hour window. Restarting the script does not extend it.
DEADLINE = 1790968920  # 2026-10-02 19:22 UTC / Oct03 02:22 Asia/Bangkok


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--label", required=True)
    p.add_argument("--checkpoint")
    p.add_argument("--day", type=int, default=3)
    p.add_argument("--case", default="cases/user-input-25x25.json")
    p.add_argument("--roles", default="1,0,0,0")
    p.add_argument("--seeds", nargs="+", type=int, default=[1])
    p.add_argument("--quota", type=int, default=3)
    p.add_argument("--slack", type=int, default=1)
    p.add_argument("--tails", type=int, default=0)
    p.add_argument("--budget", type=int, default=45000)
    p.add_argument("--preview", type=int, default=1)
    p.add_argument("--baseline-ms", type=int, default=8000)
    p.add_argument("--pool", type=int, default=1)
    p.add_argument("--exe", default="build/boundary_joint/boundary_joint_runner.exe")
    a = p.parse_args()
    if not 1 <= a.budget <= 45000:
        p.error("budget must be 1..45000")
    expected_requests = 1 if a.checkpoint else len(bench.initial_state(a.case, a.roles)["config"]["daySteps"])
    args = SimpleNamespace(exe=a.exe, policy="alns", checkpoint=a.checkpoint, day=a.day,
                           max_days=None, roles=a.roles, budget=a.budget, traffic="idle", label=a.label,
                           search=json.dumps({"endpointQuota": a.quota, "bowlSlack": a.slack,
                                              "enableBoundarySearch": a.tails, "fastFuture": a.preview,
                                              "baselineMs": a.baseline_ms, "enablePool": a.pool}))
    records = []
    for seed in a.seeds:
        if time.time()+(expected_requests*(a.budget/1000+5)) > DEADLINE:
            raise RuntimeError("Research deadline would be exceeded; no new trial launched")
        # A benchmark must never silently change EXE between days.
        digest = hashlib.sha256(Path(a.exe).read_bytes()).hexdigest()
        row = bench.run(args, None if a.checkpoint else a.case, seed)
        if hashlib.sha256(Path(a.exe).read_bytes()).hexdigest()!=digest:
            raise RuntimeError("EXE changed while benchmark was running")
        records.append(row)
    summary = bench.summarize(records)
    output = ROOT / "solver_learning/runs" / (a.label+"-summary.json")
    with output.open("x", encoding="utf-8") as f:
        json.dump(summary,f,indent=2)
    print(json.dumps(summary,indent=2),flush=True)


if __name__ == "__main__":
    main()
