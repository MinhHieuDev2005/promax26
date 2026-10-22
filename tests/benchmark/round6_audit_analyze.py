"""Strict record validation and paired results for the Round 6 follow-up."""
from collections import Counter, defaultdict
import json
from pathlib import Path
import re

import round6_audit as audit
from round6_analyze import quantiles


def analyze():
    report = {}
    for directory in sorted(audit.OUTPUT.iterdir()):
        if not directory.is_dir():
            continue
        records = defaultdict(dict)
        for path in sorted(directory.glob("*.json")):
            record = json.loads(path.read_text())
            if not isinstance(record, dict) or "command" not in record:
                continue
            assert record["valid"] and record["returncode"] == 0, path
            assert len(record["days"]) == record["expected_days"], path
            assert all(day["valid"] for day in record["days"]), path
            command = record["command"]
            assert record["binary_sha256"] == audit.round5.digest(Path(command[0])), path
            assert record["fixture_sha256"] == audit.round5.digest(Path(command[1])), path
            assert record["log_sink"] == "pipe" and record["threads"] == 8, path
            case, variant = path.stem.rsplit("-", 1)
            records[variant][case] = record
        if not records:
            continue
        manifest = directory / "manifest.json"
        if manifest.exists():
            protocol = json.loads(manifest.read_text())
            expected = {f"{family}-{seed}" for family, seed, search in protocol["cases"]}
            assert set(records) == set(protocol["variants"]), directory
            for variant, trials in records.items():
                assert set(trials) == expected, (directory, variant, set(trials), expected)
                for trial in trials.values():
                    assert trial["budget_ms"] == protocol["day_ms"]
                    assert trial["selection_budget_ms"] == protocol["selection_ms"]
        summary = {}
        for variant, cases in records.items():
            trials = list(cases.values())
            summary[variant] = stats = dict(
                n=len(trials), invalid=0,
                day_ms=quantiles([day["elapsed_ms"] for trial in trials for day in trial["days"]]),
                wall_ms=quantiles([trial["wall_ms"] for trial in trials]),
                selection_ms=quantiles([trial["selection_ms"] for trial in trials]),
                rss_kib=quantiles([trial["peak_rss_kib"] for trial in trials]),
                daily_misses=sum(day["elapsed_ms"] > trial["budget_ms"] for trial in trials for day in trial["days"]),
                selection_misses=sum(trial["selection_ms"] > trial["selection_budget_ms"] for trial in trials),
                scores={case: trial["score"] for case, trial in cases.items()})
            for reference in ("B", "BC", "J1"):
                common = sorted(cases.keys() & records.get(reference, {}).keys())
                if not common:
                    continue
                paired = stats["vs_" + reference] = dict(n=len(common), wins=0, ties=0, losses=0, primary_losses=[], changes={})
                for case in common:
                    current, baseline = cases[case], records[reference][case]
                    assert current["seed"] == baseline["seed"]
                    assert current["fixture_sha256"] == baseline["fixture_sha256"]
                    assert current["budget_ms"] == baseline["budget_ms"]
                    comparison = (tuple(current["score"]) > tuple(baseline["score"])) - (tuple(current["score"]) < tuple(baseline["score"]))
                    paired[("losses", "ties", "wins")[comparison + 1]] += 1
                    if comparison:
                        paired["changes"][case] = dict(baseline=baseline["score"], candidate=current["score"],
                                                       kinds= [baseline["kinds"], current["kinds"]])
                    if current["score"][0] < baseline["score"][0]:
                        paired["primary_losses"].append(case)
            diagnostics = []
            for case in cases:
                text = (directory / f"{case}-{variant}.log").read_text()
                boundary = text.rfind("[selection-score]")
                for match in re.finditer(r"\[multiday\] horizon=(\d+) completed=(\d+) generated=(\d+) valid=(\d+) elapsed_ms=([\d.e+\-]+)", text):
                    horizon, completed, generated, valid = map(int, match.groups()[:4])
                    diagnostics.append(dict(case=case, horizon=horizon, completed=completed, generated=generated,
                                            valid=valid, elapsed_ms=float(match.group(5)), selection=match.start() < boundary))
            if diagnostics:
                stats["search"] = diagnostics
                final = [row for row in diagnostics if not row["selection"]]
                stats["final_search"] = dict(calls=len(final), complete=sum(row["completed"] == row["horizon"] for row in final),
                    cap_exhausted=sum(row["generated"] >= 24000 for row in final),
                    incomplete_other=sum(row["completed"] < row["horizon"] and row["generated"] < 24000 for row in final),
                    elapsed_ms=quantiles([row["elapsed_ms"] for row in final]),
                    depth_histogram=dict(Counter(str((row["completed"], row["horizon"])) for row in final)))
        report[directory.name] = summary
    (audit.OUTPUT / "summary.json").write_text(json.dumps(report, indent=2))
    for suite, variants in report.items():
        for variant, stats in variants.items():
            print(suite, variant, "n", stats["n"], "vs_B", stats.get("vs_B"), "search", stats.get("final_search"))


if __name__ == "__main__":
    analyze()
