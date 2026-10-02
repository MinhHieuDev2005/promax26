"""Print paired raw results, retaining coverage ahead of servings."""
import argparse
from collections import defaultdict
import json
from pathlib import Path
import statistics


def wall_ms(record):
    return record.get("wall_ms", sum(d["wall_ms"] for d in record.get("days", [])))


def serving_gain(record):
    if "days" in record:
        return sum(serving_gain(day) for day in record["days"])
    return record["score"][2] - record["baseline_score"][2]


p = argparse.ArgumentParser()
p.add_argument("path", nargs="?", default="build/chokudai/budget-study/runs.jsonl")
a = p.parse_args()
rows = [json.loads(line) for line in Path(a.path).read_text(encoding="utf-8").splitlines()]
groups = defaultdict(list)
for r in rows:
    groups[(r["case"], r["threads"])].append(r)
for (case, threads), records in sorted(groups.items()):
    print(case, "threads=", threads)
    for r in sorted(records, key=lambda r: (r["budget_ms"], r["seed"])):
        print(f"  {r['budget_ms']/1000:>3g}s seed={r['seed']} score={r['score']} "
              f"base={r.get('baseline_score', 'per-day')} wall={wall_ms(r):.2f} "
              f"exp={r.get('expansions', sum(d['expansions'] for d in r.get('days', [])))}")
print("COMPLETE PAIRS BY THREAD COUNT")
for threads in sorted({r["threads"] for r in rows}):
    rr = [r for r in rows if r["threads"] == threads]
    budgets = sorted({r["budget_ms"] for r in rr})
    keys = [{(r["case"], r["seed"]) for r in rr if r["budget_ms"] == b} for b in budgets]
    paired = set.intersection(*keys)
    print("threads", threads, "paired case/seed count", len(paired))
    for b in budgets:
        group = [r for r in rr if r["budget_ms"] == b and (r["case"], r["seed"]) in paired]
        if not group:
            continue
        totals = [sum(r["score"][i] for r in group) for i in range(3)]
        seed_gains = sum(serving_gain(r) for r in group)
        print(b, "totals=", totals, "servings_gain_over_seed=", seed_gains,
              "mean_wall_ms=", round(statistics.mean(wall_ms(r) for r in group), 1))
