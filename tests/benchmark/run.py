import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import random
import re
import statistics
import subprocess
import sys
import time


CASES = {
    "open8": (8, 3, 6, 40, 24, 4),
    "mixed16": (16, 7, 16, 80, 32, 6),
    "sparse16": (16, 3, 4, 100, 32, 4),
    "tight16": (16, 5, 12, 24, 40, 6),
    "dense16": (16, 7, 24, 70, 40, 4),
    "large32": (32, 8, 24, 100, 64, 4),
    "tight8": (8, 3, 6, 12, 24, 4),
    "tight32": (32, 8, 24, 40, 64, 4),
    "coverage16": (16, 3, 16, 48, 14, 4),
}


def digest(data):
    return hashlib.sha256(data).hexdigest()


def fixture(name, seed):
    size, agents, spots, fuel, steps, days = CASES[name]
    randomizer = random.Random(seed)
    cells = [0 if name == "open8" else randomizer.choices([0, 1, 2], [5, 3, 2])[0]
             for _ in range(size * size)]
    positions = randomizer.sample(range(size * size), spots + agents)
    stores = []
    for index, position in enumerate(positions[:spots]):
        cells[position] = 0
        stores.append(dict(brand=index if name != "dense16" else index // 2,
                           pos=position, stocks=randomizer.randint(1, agents)))
    for position in positions[spots:]:
        cells[position] = 0
    return dict(startsAt=0, daySeconds=[60] * days,
                daySteps=[steps + 2 * day for day in range(days)],
                map=dict(height=size, width=size,
                         cells=[cells[start:start + size] for start in range(0, size * size, size)]),
                spots=stores, agents=positions[spots:], fuelLimits=fuel,
                players=1, busyThreshold=2, jammedThreshold=4)


def percentile(values, fraction):
    return sorted(values)[max(0, math.ceil(len(values) * fraction) - 1)] if values else None


def summarize(records):
    valid = [record for record in records if record.get("valid")]
    scores = sorted(tuple(record["score"]) for record in valid)
    days = [day for record in records for day in record.get("days", [])]
    runtimes = [day["elapsed_ms"] for day in days]
    expected_days = sum(record.get("expected_days", len(record.get("days", []))) for record in records)
    return dict(matches=len(records), valid_matches=len(valid),
                valid_rate=len(valid) / len(records) if records else None,
                component_means=[statistics.mean(score[index] for score in scores) for index in range(3)] if scores else None,
                median_tuple=scores[(len(scores) - 1) // 2] if scores else None,
                best_tuple=scores[-1] if scores else None,
                worst_tuple=scores[0] if scores else None,
                day_runtime_p50_ms=percentile(runtimes, 0.5),
                day_runtime_p95_ms=percentile(runtimes, 0.95),
                day_runtime_max_ms=max(runtimes, default=None),
                peak_rss_kib=max((record["peak_rss_kib"] for record in records if "peak_rss_kib" in record), default=None),
                expected_days=expected_days, completed_days=len(days),
                local_day_deadline_rate=sum(day["elapsed_ms"] <= record["budget_ms"]
                    for record in records for day in record.get("days", [])) / expected_days if expected_days else None)


def compare(before, after):
    baseline = {record["key"]: record for record in before}
    candidate = {record["key"]: record for record in after}
    if len(baseline) != len(before) or len(candidate) != len(after) or baseline.keys() != candidate.keys():
        raise ValueError("Missing or duplicate benchmark pairs")
    counts = dict(wins=0, ties=0, losses=0, invalid_pairs=0)
    changes = []
    for key, old in baseline.items():
        new = candidate[key]
        for field in ("fixture_sha256", "budget_ms", "threads", "selection_budget_ms", "harness_sha256"):
            if old[field] != new[field]:
                raise ValueError(f"Incompatible pair {key}: {field}")
        if not old.get("valid") or not new.get("valid"):
            counts["invalid_pairs"] += 1
            continue
        old_score, new_score = tuple(old["score"]), tuple(new["score"])
        category = "wins" if new_score > old_score else "losses" if new_score < old_score else "ties"
        counts[category] += 1
        if category != "ties":
            changes.append(dict(key=key, baseline=old_score, candidate=new_score))
    return dict(paired=counts, changes=changes, baseline=summarize(before), candidate=summarize(after))


def self_test():
    assert fixture("mixed16", 17) == fixture("mixed16", 17)
    for name in CASES:
        setting = fixture(name, 17)
        assert len({spot["pos"] for spot in setting["spots"]}) == len(setting["spots"])
        assert len(setting["daySteps"]) == len(setting["daySeconds"])
        assert all(value in (0, 1, 2) for row in setting["map"]["cells"] for value in row)
    record = dict(key="test", valid=True, score=[3, 12, 20], fixture_sha256="same", budget_ms=10,
                  threads=1, selection_budget_ms=10, harness_sha256="same", days=[])
    assert compare([record], [dict(record, score=[3, 11, 100])])["paired"]["losses"] == 1
    assert compare([record], [dict(record, score=[4, 1, 1])])["paired"]["wins"] == 1
    assert compare([record], [dict(record, valid=False)])["paired"]["invalid_pairs"] == 1
    assert summarize([dict(record, valid=False, expected_days=4)])["local_day_deadline_rate"] == 0
    assert summarize([dict(record, valid=False)])["peak_rss_kib"] is None
    for candidate in ([], [dict(record, budget_ms=11)], [record, record]):
        try:
            compare([record], candidate)
        except ValueError:
            pass
        else:
            raise AssertionError("Incompatible benchmark accepted")
    print("Benchmark checks passed")


def read_records(path):
    return [json.loads(line) for line in Path(path).read_text().splitlines() if line]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--compare", nargs=2, metavar=("BASELINE", "CANDIDATE"))
    parser.add_argument("--binary", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--cases", nargs="+", choices=CASES, default=list(CASES))
    parser.add_argument("--map-seeds", nargs="+", type=int, default=[17])
    parser.add_argument("--seeds", nargs="+", type=int, default=[1, 2])
    parser.add_argument("--modes", nargs="+", choices=["patrol", "supply", "auto"], default=["patrol", "supply"])
    parser.add_argument("--day-ms", type=int, default=300)
    parser.add_argument("--selection-ms", type=int, default=1200)
    parser.add_argument("--threads", type=int, default=1)
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return
    if args.compare:
        print(json.dumps(compare(*map(read_records, args.compare)), indent=2))
        return
    if not args.binary or not args.output:
        parser.error("--binary and --output are required")
    if not 1 <= args.day_ms <= 60000 or not 1 <= args.selection_ms <= 60000 or not 1 <= args.threads <= 8:
        parser.error("Invalid budget or thread count")
    if any(not 1 <= seed <= 1000000000 for seed in args.seeds + args.map_seeds):
        parser.error("Seeds must be in 1..1000000000")
    for values in (args.cases, args.map_seeds, args.seeds, args.modes):
        if len(set(values)) != len(values):
            parser.error("Duplicate cases/seeds/modes")
    binary = args.binary.resolve(strict=True)
    args.output.mkdir(parents=True, exist_ok=False)
    harness = digest(Path(__file__).read_bytes() + Path(__file__).with_name("match.cpp").read_bytes())
    cpuinfo = Path("/proc/cpuinfo")
    metadata = dict(binary=str(binary), binary_sha256=digest(binary.read_bytes()),
                    harness_sha256=harness, command=sys.argv, python=platform.python_version(),
                    platform=platform.platform(), affinity=sorted(os.sched_getaffinity(0)),
                    cpuinfo=cpuinfo.read_text() if cpuinfo.exists() else None)
    (args.output / "metadata.json").write_text(json.dumps(metadata, indent=2))
    records = []
    with (args.output / "results.jsonl").open("x") as results:
        for name in args.cases:
            for map_seed in args.map_seeds:
                setting = fixture(name, map_seed)
                encoded = json.dumps(setting, sort_keys=True).encode()
                path = args.output / f"{name}-{map_seed}.json"
                path.write_bytes(encoded)
                for mode in args.modes:
                    count = len(setting["agents"])
                    lineup = "auto" if mode == "auto" else "0" * (count - 1) + ("1" if mode == "supply" else "0")
                    for seed in args.seeds:
                        key = f"{name}-{map_seed}-{mode}-{seed}"
                        command = [str(binary), str(path), str(seed), str(args.day_ms), str(args.threads), lineup, str(args.selection_ms)]
                        record = dict(key=key, fixture_sha256=digest(encoded), harness_sha256=harness,
                                      budget_ms=args.day_ms, threads=args.threads, selection_budget_ms=args.selection_ms,
                                      expected_days=len(setting["daySteps"]),
                                      valid=False, mode=mode, seed=seed, binary_sha256=metadata["binary_sha256"])
                        started = time.monotonic()
                        with (args.output / f"{key}.log").open("w") as log:
                            try:
                                completed = subprocess.run(command, stdout=subprocess.PIPE, stderr=log, text=True,
                                    timeout=10 + 6 * (args.selection_ms + len(setting["daySteps"]) * args.day_ms) / 1000)
                                if completed.stdout.strip():
                                    record.update(json.loads(completed.stdout))
                                if completed.returncode:
                                    record.update(valid=False, error=f"exit {completed.returncode}")
                            except (subprocess.TimeoutExpired, json.JSONDecodeError, OSError) as error:
                                record.update(valid=False, error=str(error))
                        record["wall_ms"] = (time.monotonic() - started) * 1000
                        logs = (args.output / f"{key}.log").read_text()
                        record["logged_iterations"] = sum(map(int, re.findall(r"\[solver\] iter=(\d+)", logs)))
                        records.append(record)
                        results.write(json.dumps(record) + "\n")
                        results.flush()
                        print(key, record.get("score", record.get("error")), flush=True)
    summary = summarize(records)
    (args.output / "summary.json").write_text(json.dumps(summary, indent=2))
    print(json.dumps(summary, indent=2))
    if any(not record["valid"] for record in records):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
