"""Summarize complete Round 6 records and retain every primary-loss trace."""
from collections import Counter, defaultdict
import json
from pathlib import Path
import random
import re
import statistics

import round6


def quantiles(values):
    ordered = sorted(values)
    return {label: ordered[min(len(ordered)-1, int((len(ordered)-1)*fraction))]
            for label, fraction in (("p50", .5), ("p95", .95), ("max", 1))} if ordered else {}


def operator_stats(rows):
    stats = dict(zip(("attempts", "generated", "valid", "surrogate_best_improvements", "total_ms"),
        (sum(row[index] for row in rows) for index in range(5))))
    stats["zero_improvement_calls_ms"] = sum(row[4] for row in rows if row[3] == 0)
    stats["mean_ms_per_attempt"] = stats["total_ms"] / max(1, stats["attempts"])
    return stats


def analyze():
    summaries, regressions = {}, []
    for directory in sorted(round6.OUTPUT.iterdir()):
        if not directory.is_dir() or directory.name.startswith("exact") or directory.name == "bridge-919":
            continue
        records = defaultdict(dict)
        for path in sorted(directory.glob("*.json")):
            if path.name.endswith(".fixture.json"):
                continue
            record = json.loads(path.read_text())
            if "command" not in record:
                continue
            key, variant = path.stem.rsplit("-", 1)
            if not (record.get("valid") and record.get("returncode") == 0
                    and len(record["days"]) == record["expected_days"]):
                raise RuntimeError(f"Incomplete/invalid trial: {path}")
            records[variant][key] = record
        summary = {}
        for variant, cases in records.items():
            trials = list(cases.values())
            times = [day["elapsed_ms"] for trial in trials for day in trial["days"]]
            primary = [trial["score"][0] for trial in trials]
            stats = dict(n=len(trials), primary_mean=statistics.mean(primary), primary_histogram=dict(Counter(primary)),
                daily_mean=statistics.mean(trial["score"][1] for trial in trials),
                bowls_mean=statistics.mean(trial["score"][2] for trial in trials),
                day_ms=quantiles(times), wall_ms=quantiles([trial["wall_ms"] for trial in trials]),
                selection_ms=quantiles([trial["selection_ms"] for trial in trials]),
                rss_kib=quantiles([trial["peak_rss_kib"] for trial in trials]), invalid=0,
                day_deadline_misses=sum(day["elapsed_ms"] > trial["budget_ms"] for trial in trials for day in trial["days"]),
                planner_allowance_overruns=sum(day["elapsed_ms"] > .85*trial["budget_ms"] for trial in trials for day in trial["days"]),
                selection_deadline_misses=sum(trial["selection_ms"] > trial["selection_budget_ms"] for trial in trials))
            references = ["B"]
            if variant in ("M", "J1", "J2") and "BC" in records:
                references.append("BC")
            if variant in ("MS", "J2") and "M" in records:
                references.append("M")
            for reference in references:
                common = sorted(cases.keys() & records[reference].keys())
                differences = [cases[key]["score"][0] - records[reference][key]["score"][0] for key in common]
                comparison_stats = dict(paired_n=len(common), wins=0, ties=0, losses=0, primary_losses=sum(value < 0 for value in differences))
                stats["vs_" + reference] = comparison_stats
                for key in common:
                    baseline, current = records[reference][key], cases[key]
                    comparison = (tuple(current["score"]) > tuple(baseline["score"])) - (tuple(current["score"]) < tuple(baseline["score"]))
                    comparison_stats[("losses", "ties", "wins")[comparison+1]] += 1
                    if current["score"][0] >= baseline["score"][0] or variant == "A":
                        continue
                    fixture = json.loads((directory / f"{key}.fixture.json").read_text())
                    first = next((index for index, (left, right) in enumerate(zip(baseline["days"], current["days"])) if left["plan"] != right["plan"]), None)
                    lost = [brand for brand, (left, right) in enumerate(zip(baseline["days"][-1]["collected"], current["days"][-1]["collected"])) if left and not right]
                    def trace(trial):
                        return dict(kinds=trial["kinds"], score=trial["score"], selection_ms=trial["selection_ms"],
                            fuel_consumed=[sum(day["consumed"][agent] for day in trial["days"]) for agent in range(len(trial["kinds"]))],
                            fuel_replenished=[sum(day["replenished"][agent] for day in trial["days"]) for agent in range(len(trial["kinds"]))],
                            days=[{field: day[field] for field in ("day", "plan", "positions", "fuel", "hits", "elapsed_ms")} for day in trial["days"]])
                    regressions.append(dict(suite=directory.name, case=key, variant=variant, reference=reference, first_plan_difference=first,
                        first_decision="selection" if baseline["kinds"] != current["kinds"] else f"day {first}", lost_brands=lost,
                        initial_positions=fixture["agents"], steps=fixture["daySteps"], baseline=trace(baseline), candidate=trace(current)))
                if differences:
                    comparison_stats["primary_mean_difference"] = statistics.mean(differences)
                    if len(differences) > 1 and directory.name != "confirmation":
                        generator = random.Random(6006)
                        bootstrap = sorted(statistics.mean(generator.choices(differences, k=len(differences))) for repeat in range(3000))
                        comparison_stats["primary_bootstrap_95"] = [bootstrap[75], bootstrap[2924]]
            operators, final_operators = [], []
            for key in cases:
                log = (directory / f"{key}-{variant}.log").read_text(errors="replace")
                selection_end = log.rfind("[selection-score]")
                for match in re.finditer(r"\[joint-lns\] attempts=(\d+) generated=(\d+) valid=(\d+) best=(\d+) ms=([\d.e+\-]+)", log):
                    row = tuple(map(float, match.groups()))
                    operators.append(row)
                    if match.start() > selection_end:
                        final_operators.append(row)
            if operators:
                stats["joint_lns_visible_worker"] = operator_stats(operators)
                stats["joint_lns_final_planning_visible_worker"] = operator_stats(final_operators)
            summary[variant] = stats
        summaries[directory.name] = summary
    (round6.OUTPUT / "summary.json").write_text(json.dumps(summaries, indent=2))
    (round6.OUTPUT / "primary-regressions.json").write_text(json.dumps(regressions, indent=2))
    print(json.dumps(summaries, indent=2))


if __name__ == "__main__":
    analyze()
