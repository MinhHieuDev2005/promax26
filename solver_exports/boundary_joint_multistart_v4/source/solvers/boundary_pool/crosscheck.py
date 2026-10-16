"""Paired first-day regression checks, explicitly NOT a full-match gate."""
import argparse
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

spec = importlib.util.spec_from_file_location("bench", Path(__file__).with_name("benchmark.py"))
bench = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bench)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--exe", required=True)
    p.add_argument("--label", required=True)
    p.add_argument("--seeds", nargs="+", type=int, default=[1, 2])
    a = p.parse_args()
    cases = ["cases/user-input-16x16.json", "cases/user-input-24x24.json", "cases/user-input-32x32.json"]
    results = {}
    for variant in ("baseline", "preview"):
        args = SimpleNamespace(exe=a.exe, policy="alns", checkpoint=None, day=1, max_days=1,
                               roles="first", budget=45000, traffic="idle", label=a.label+"-"+variant,
                               search=json.dumps({"enablePool": int(variant != "baseline"),
                                                  "boundaryTrade": int(variant != "baseline"),
                                                  "fastFuture": int(variant != "baseline"),
                                                  "enableBoundarySearch": 0}))
        results[variant] = [bench.run(args, case, seed) for case in cases for seed in a.seeds]
    pairs = []
    for baseline, challenger in zip(results["baseline"], results["preview"]):
        assert baseline["case_path"] == challenger["case_path"] and baseline["seed"] == challenger["seed"]
        pairs.append({"case": baseline["case_path"], "seed": baseline["seed"],
                      "baseline": baseline["score"], "preview": challenger["score"],
                      "non_regression": challenger["score"] >= baseline["score"]})
    summary = {"scope": "first day only; cannot establish whole-match superiority",
               "baseline": bench.summarize(results["baseline"]), "preview": bench.summarize(results["preview"]),
               "pairs": pairs}
    path = bench.ROOT / "solver_learning/runs" / (a.label+"-crosscheck.json")
    if path.exists():
        raise FileExistsError(path)
    path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2), flush=True)


if __name__ == "__main__":
    main()
