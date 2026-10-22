"""Isolated Round 5 builds and paired selector/planner experiments (Linux/WSL)."""
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import random
import re
import shutil
import statistics
import subprocess
import time

import round4

ROOT = Path(__file__).resolve().parents[2]
OUTPUT = ROOT / "results/solver-round5"
WORK = Path("/home/hexa/solver-experiments/round5")
SINK = "file"


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def execute(binary, fixture, seed, day_ms, workers, lineup, selection_ms, prefix):
    command = [str(binary), str(fixture), str(seed), str(day_ms), str(workers), lineup, str(selection_ms)]
    started = time.monotonic()
    with prefix.with_suffix(".log").open("w") as log:
        try:
            result = subprocess.run(command, stdout=subprocess.PIPE, stderr=log if SINK == "file" else subprocess.PIPE, text=True,
                                    timeout=15 + (selection_ms + day_ms * 64) / 1000)
            if SINK == "pipe":
                log.write(result.stderr)
            record = json.loads(result.stdout) if result.stdout.strip() else {"valid": False}
            record["returncode"] = result.returncode
        except (subprocess.TimeoutExpired, json.JSONDecodeError, OSError) as error:
            record = {"valid": False, "error": str(error), "timeout": isinstance(error, subprocess.TimeoutExpired)}
    if record.get("returncode", 1) != 0:
        record["valid"] = False
    record.update(wall_ms=(time.monotonic() - started) * 1000, command=command,
                  fixture_sha256=digest(fixture), binary_sha256=digest(binary),
                  expected_days=len(json.loads(fixture.read_text())["daySteps"]), log_sink=SINK)
    prefix.with_suffix(".json").write_text(json.dumps(record, indent=2))
    print(prefix.name, record.get("kinds"), record.get("score"), flush=True)
    return record


def initial():
    target = OUTPUT / "initial"
    target.mkdir(parents=True, exist_ok=True)
    fixture = ROOT / "results/solver-round4/B-auto/bridge-919.json"
    for variant, build in (("B", "round3-build-relocation"), ("C", "round4-C")):
        for lineup in ("000", "001"):
            execute(WORK.parent / build / "solver_bench", fixture, 23, 1000, 8, lineup, 2500,
                    target / f"{variant}-{lineup}")


def replace_once(text, old, new):
    assert text.count(old) == 1, (old, text.count(old))
    return text.replace(old, new)


def build(variants):
    OUTPUT.mkdir(parents=True, exist_ok=True)
    for variant in variants:
        source = WORK / variant / "source"
        source.mkdir(parents=True, exist_ok=False)
        for folder in ("src", "include", "cmake", "tests"):
            shutil.copytree(ROOT / folder, source / folder, ignore=shutil.ignore_patterns("__pycache__"))
        shutil.copy2(ROOT / "CMakeLists.txt", source)
        selector, planner = {"A": ("A", "A"), "B": ("B", "B"), "C": ("C", "C"),
                             "BC": ("B", "C"), "CB": ("C", "B"),
                             "N": ("C", "C"), "H": ("C", "C")}[variant]
        for patch, enabled in (("relocation.patch", "B" in (selector, planner)),
                               ("round4-c.patch", "C" in (selector, planner))):
            if enabled:
                subprocess.run(["git", "apply", str(ROOT / "tests/benchmark/variants" / patch)],
                               cwd=source, check=True)
        day_path = source / "src/planner/day_planner.cpp"
        optimizer_path = source / "src/optimizer/optimizer.cpp"
        day = day_path.read_text()
        optimizer = optimizer_path.read_text()
        if variant == "N":
            optimizer = replace_once(optimizer, "int T = max(1, threads);", "int T = choosingKinds ? 1 : max(1, threads);")
            optimizer = replace_once(optimizer, "    if (T == 1) {", "    if (T == 1) {\n        const Rng savedRng = rng;")
            optimizer = replace_once(optimizer, "        auto plan = p.plan(timeMs);", "        auto plan = p.plan(timeMs);\n        if (choosingKinds) rng = savedRng;")
        if variant == "H":
            optimizer = replace_once(optimizer, "        candidate.key.insert(candidate.key.end(), candidate.profile.begin(), candidate.profile.end());\n        long long fuel = 0;\n        for (int agent : patrols) fuel += candidate.result.end[agent].fuel;",
                "        if (!choosingKinds) candidate.key.insert(candidate.key.begin(), candidate.profile.back());\n        candidate.key.insert(candidate.key.end(), candidate.profile.begin(), candidate.profile.end());\n        long long fuel = 0;\n        for (int agent : patrols) fuel += candidate.result.end[agent].fuel;")
        if selector != planner:
            gate = "choosingKinds" if selector == "B" else "!choosingKinds"
            day = replace_once(day, "if (!lastDay) {\n        auto assigned", f"if (!lastDay && {gate}) {{\n        auto assigned")
            gate = "choosingKinds" if selector == "C" else "!choosingKinds"
            optimizer = replace_once(optimizer, "lastDay ? timeMs : timeMs * 0.8",
                                     f"lastDay || !({gate}) ? timeMs : timeMs * 0.8")
            optimizer = replace_once(optimizer, "if (!lastDay && budget.ms() < timeMs)",
                                     f"if (!lastDay && {gate} && budget.ms() < timeMs)")
        day_path.write_text(day)
        optimizer_path.write_text(optimizer)
        patch_text = ""
        for relative in ("src/planner/day_planner.cpp", "src/optimizer/optimizer.cpp"):
            import difflib
            patch_text += "".join(difflib.unified_diff((ROOT / relative).read_text().splitlines(True),
                                  (source / relative).read_text().splitlines(True),
                                  fromfile="a/" + relative, tofile="b/" + relative))
        (OUTPUT / f"{variant}.patch").write_text(patch_text)
        selector_path = source / "src/planner/prematch_type_selector.cpp"
        text = selector_path.read_text()
        text = text.replace('#include "hexa_udon/solver.hpp"', '#include "hexa_udon/solver.hpp"\n#include <nlohmann/json.hpp>')
        text = replace_once(text, "        auto plan = planDay", "        Timer traceTimer;\n        auto plan = planDay")
        text = replace_once(text, "        if (!r.valid) r =", "        bool fallback = !r.valid;\n        if (!r.valid) r =")
        text = replace_once(text, "        stays.push_back(r.stay);", '''        vector<int> positions, fuel;
        for (const auto& agent : r.end) { positions.push_back(agent.pos); fuel.push_back(agent.fuel); }
        cerr << "[selection-day] " << nlohmann::json({{"kinds", kinds}, {"busy", busy}, {"day", d},
            {"budget_ms", timeMs / D}, {"elapsed_ms", traceTimer.ms()}, {"fallback", fallback},
            {"brands", r.brands}, {"bowls", r.balls}, {"hits", r.brandHit}, {"plan", plan},
            {"positions", positions}, {"fuel", fuel}}).dump() << '\\n';
        stays.push_back(r.stay);''')
        text = replace_once(text, "        scored.push_back({ms, cands[c]});", '''        cerr << "[selection-score] " << nlohmann::json({{"kinds", cands[c]}, {"each_ms", each},
            {"smooth", {smooth.matchBrands, smooth.dayBrands, smooth.balls}},
            {"heavy", {heavy.matchBrands, heavy.dayBrands, heavy.balls}},
            {"estimate", {ms.matchBrands, ms.dayBrands, ms.balls}}}).dump() << '\\n';
        scored.push_back({ms, cands[c]});''')
        selector_path.write_text(text)
        if "C" in (selector, planner):
            optimizer = replace_once(optimizer, "    if (!choosingKinds) { yesterdayStatus = status;", '''    if (choosingKinds) cerr << "[overnight-budget] day=" << today << " allowance=" << timeMs
        << " elapsed=" << budget.ms() << '\\n';
    if (!choosingKinds) { yesterdayStatus = status;''')
            optimizer_path.write_text(optimizer)
        harness = source / "tests/benchmark/match.cpp"
        text = harness.read_text()
        text = replace_once(text, "    solver::choosingKinds = false;", "    solver::rng.x = static_cast<uint64_t>(seed);\n    solver::choosingKinds = false;")
        text = replace_once(text, "        std::vector<int> fuel, positions;", '''        std::vector<int> fuel, positions, consumed(agents.size()), replenished(agents.size());
        for (size_t index = 0; index < agents.size(); ++index) {
            int cell = agents[index].pos;
            for (int action : plan[index]) if (action >= 0) {
                if (agents[index].kind == 0) consumed[index] += solver::fuelCost(cell);
                cell = solver::neighbor(cell, action);
            }
            replenished[index] = result.end[index].fuel - agents[index].fuel + consumed[index];
        }''')
        text = replace_once(text, '{"positions", positions}, {"hits", result.brandHit}',
                             '{"consumed", consumed}, {"replenished", replenished}, {"positions", positions}, {"hits", result.brandHit}')
        harness.write_text(text)
        binary_dir = WORK / variant / "build"
        with (OUTPUT / f"build-{variant}.log").open("w") as log:
            subprocess.run(["cmake", "-S", str(source / "tests/benchmark"), "-B", str(binary_dir),
                            "-DCMAKE_BUILD_TYPE=Release"], stdout=log, stderr=log, check=True)
            subprocess.run(["cmake", "--build", str(binary_dir), "--target", "solver_bench", "--parallel", "4"],
                           stdout=log, stderr=log, check=True)
        print("built", variant, flush=True)


def competition(variants):
    target = OUTPUT / "competition"
    target.mkdir(parents=True, exist_ok=True)
    fixture = target / "bridge-2207.fixture.json"
    fixture.write_text(json.dumps(make_fixture("bridge", 2207)))
    records = []
    for variant in variants:
        prefix = target / f"bridge-2207-47-auto-{variant}"
        if prefix.with_suffix(".json").exists():
            record = json.loads(prefix.with_suffix(".json").read_text())
        else:
            record = execute(WORK / variant / "build/solver_bench", fixture, 47, 57000, 8,
                             "auto", 28500, prefix)
        record.update(key="bridge-2207-47-auto", variant=variant, mode="auto")
        records.append(record)
        (target / "results.jsonl").write_text("".join(json.dumps(item) + "\n" for item in records))
    analyze("competition")


def certified_wait():
    target = OUTPUT / "certified-wait"
    target.mkdir(parents=True, exist_ok=True)
    fixture = target / "wait.fixture.json"
    setting = round4.fixture("exact", 2309)
    setting.update(agents=[0], spots=[dict(brand=0, pos=0, stocks=1)], fuelLimits=1, daySteps=[1] * 4)
    fixture.write_text(json.dumps(setting))
    for variant in ("A", "B", "C", "BC", "N", "H"):
        record = execute(WORK / variant / "build/solver_bench", fixture, 53, 100, 1, "0", 2500, target / variant)
        assert record["valid"] and record["score"] == [1, 4, 4]
        assert all(day["plan"] == [[-1]] for day in record["days"])


def trace():
    result = {"historical": {}, "replayed": {}, "selection": {}}
    for variant in ("B", "C"):
        directory = ROOT / f"results/solver-round4/{variant}-auto"
        record = next(json.loads(line) for line in (directory / "results.jsonl").read_text().splitlines()
                      if json.loads(line)["key"] == "bridge-919-auto-23")
        candidates = []
        for line in (directory / "bridge-919-auto-23.log").read_text().splitlines():
            match = re.search(r"\[kind\] cand=(\d+) \(([01]+)\) brands=(\d+) dayBrands=(\d+) balls=(\d+)", line)
            if match:
                index, lineup, *score = match.groups()
                candidates.append(dict(index=int(index), lineup=lineup, patrols=lineup.count("0"),
                                       supplies=lineup.count("1"), estimate=list(map(int, score))))
        result["historical"][variant] = dict(candidates=candidates, match=record)
    for path in (OUTPUT / "causal").glob("bridge-*.json"):
        if not path.name.endswith(".fixture.json"):
            result["replayed"][path.stem] = json.loads(path.read_text())
    for path in (OUTPUT / "causal").glob("bridge-*auto-*.log"):
        events = []
        for line in path.read_text().splitlines():
            for prefix in ("[selection-day] ", "[selection-score] "):
                if line.startswith(prefix):
                    events.append(dict(event=prefix.strip(), **json.loads(line[len(prefix):])))
        result["selection"][path.stem] = events
    (OUTPUT / "bridge-trace.json").write_text(json.dumps(result, indent=2))


def suite(name, variants, day_ms, selection_ms, workers):
    target = OUTPUT / name
    target.mkdir(parents=True, exist_ok=True)
    if name.startswith("causal"):
        cases = [(family, 919, seed) for family in ("bridge", "fork", "fuel", "rendezvous", "traffic", "wait")
                 for seed in (23, 29)]
    else:
        cases = [(family, map_seed, seed) for family in ("bridge", "fork", "fuel", "rendezvous", "traffic", "wait", "multi", "patrol")
                 for map_seed, seed in ((1607, 41), (1907, 43))]
    metadata = dict(cases=cases, variants=variants, day_ms=day_ms, selection_ms=selection_ms, workers=workers,
                    affinity=sorted(os.sched_getaffinity(0)), runner_sha256=digest(Path(__file__)), log_sink=SINK,
                    note="Sequential randomized variant order; wall-clock search is not bit deterministic.")
    manifest = target / "metadata.json"
    if manifest.exists():
        previous = json.loads(manifest.read_text())
        for field in ("variants", "day_ms", "selection_ms", "workers"):
            assert previous[field] == metadata[field], "Incompatible resume"
        assert previous.get("log_sink", "file") == SINK, "Incompatible log transport"
        metadata["prior_runner_sha256"] = previous["runner_sha256"]
    manifest.write_text(json.dumps(metadata, indent=2))
    order = random.Random(505)
    records_file = target / "results.jsonl"
    records = [json.loads(line) for line in records_file.read_text().splitlines()] if records_file.exists() else []
    completed = {(record["key"], record["variant"]): record for record in records}
    for family, map_seed, seed in cases:
        fixture = target / f"{family}-{map_seed}.fixture.json"
        fixture.write_text(json.dumps(make_fixture(family, map_seed)))
        lineup_modes = ["auto"]
        if name.startswith("causal") and family == "bridge":
            lineup_modes += ["000", "001", "010", "100"]
        for lineup in lineup_modes:
            shuffled = list(variants if lineup == "auto" else [item for item in variants if item in ("B", "C")])
            order.shuffle(shuffled)
            for variant in shuffled:
                key = f"{family}-{map_seed}-{seed}-{lineup}"
                if (key, variant) in completed:
                    assert completed[key, variant]["binary_sha256"] == digest(WORK / variant / "build/solver_bench")
                    assert completed[key, variant]["fixture_sha256"] == digest(fixture)
                    continue
                record = execute(WORK / variant / "build/solver_bench", fixture, seed, day_ms, workers,
                                 lineup, selection_ms, target / f"{key}-{variant}")
                record.update(key=key, variant=variant, mode=lineup)
                records.append(record)
                with (target / "results.jsonl").open("a") as stream:
                    stream.write(json.dumps(record) + "\n")
    return records


def make_fixture(family, seed):
    setting = round4.fixture("rendezvous" if family == "multi" else "fork" if family == "patrol" else family, seed)
    if family == "multi":
        randomizer = random.Random(seed + 50000)
        setting["agents"] = randomizer.sample([row * 16 + column for row in range(4, 12) for column in range(3)], 6)
        setting["fuelLimits"] = 10
        setting["daySteps"] = [18] * 5
        for spot in setting["spots"]:
            spot["stocks"] = 3
        for position in setting["agents"]:
            setting["map"]["cells"][position // 16][position % 16] = 0
    if family == "patrol":
        setting["fuelLimits"] = 64
    return setting


def quantile(values, fraction):
    if not values:
        return None
    ordered = sorted(values)
    position = (len(ordered) - 1) * fraction
    lower, upper = math.floor(position), math.ceil(position)
    if isinstance(ordered[lower], tuple):
        return ordered[lower]
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)


def paired(old, new):
    assert old.keys() == new.keys(), "Incomplete pairs"
    result = dict(wins=0, ties=0, losses=0, invalid=0, primary_regressions=0, changes=[])
    clusters = {}
    for key in sorted(old):
        before, after = old[key], new[key]
        assert before["fixture_sha256"] == after["fixture_sha256"]
        if not before.get("valid") or not after.get("valid"):
            result["invalid"] += 1
            continue
        prior, current = tuple(before["score"]), tuple(after["score"])
        result["wins" if current > prior else "losses" if current < prior else "ties"] += 1
        result["primary_regressions"] += current[0] < prior[0]
        clusters.setdefault(before["fixture_sha256"], []).append(current[0] - prior[0])
        if current != prior:
            result["changes"].append(dict(key=key, before=prior, after=current))
    if clusters:
        values = list(clusters.values())
        randomizer = random.Random(505)
        samples = []
        for _ in range(2000):
            sampled = [delta for group in randomizer.choices(values, k=len(values)) for delta in group]
            samples.append(statistics.mean(sampled))
        result["primary_mean_delta"] = statistics.mean(delta for group in values for delta in group)
        result["primary_regression_rate"] = result["primary_regressions"] / sum(map(len, values))
        result["primary_delta_cluster_bootstrap_95"] = [quantile(samples, 0.025), quantile(samples, 0.975)]
    return result


def analyze(name):
    target = OUTPUT / name
    records = [json.loads(line) for line in (target / "results.jsonl").read_text().splitlines()]
    groups = {}
    for record in records:
        if record["mode"] == "auto":
            groups.setdefault(record["variant"], {})[record["key"]] = record
    summary = {"variants": {}, "comparisons": {}}
    for variant, group in groups.items():
        valid = [record for record in group.values() if record.get("valid")]
        days = [day for record in valid for day in record["days"]]
        scores = [tuple(record["score"]) for record in valid]
        selection = [record["selection_ms"] for record in valid]
        elapsed = [day["elapsed_ms"] for day in days]
        summary["variants"][variant] = dict(matches=len(group), valid=len(valid),
            mean_score=[statistics.mean(score[index] for score in scores) for index in range(3)],
            median_score=quantile(scores, 0.5), worst_score=min(scores),
            primary_median=statistics.median(score[0] for score in scores),
            primary_p05=quantile([score[0] for score in scores], 0.05),
            day_p95_ms=quantile(elapsed, 0.95), day_max_ms=max(elapsed),
            wall_p95_ms=quantile([record["wall_ms"] for record in valid], 0.95),
            wall_max_ms=max(record["wall_ms"] for record in valid),
            peak_rss_kib=max(record["peak_rss_kib"] for record in valid),
            selection_mean_ms=statistics.mean(selection), selection_max_ms=max(selection),
            selection_misses=sum(record["selection_ms"] > record["selection_budget_ms"] for record in valid),
            day_misses=sum(record.get("expected_days", len(record.get("days", []))) -
                sum(day.get("valid", False) and day["elapsed_ms"] <= record["budget_ms"] for day in record.get("days", []))
                for record in group.values()),
            total_days=len(days), fuel_mean=statistics.mean(sum(sum(day["consumed"]) for day in record["days"]) for record in valid),
            supply_mean=statistics.mean(sum(record["kinds"]) for record in valid))
    for baseline in groups:
        for candidate in groups:
            if baseline != candidate:
                summary["comparisons"][f"{candidate}_vs_{baseline}"] = paired(groups[baseline], groups[candidate])
    (target / "summary.json").write_text(json.dumps(summary, indent=2))
    for variant, metrics in summary["variants"].items():
        print(variant, json.dumps(metrics))
    for comparison in ("B_vs_A", "C_vs_B", "BC_vs_B", "BC_vs_C", "CB_vs_B", "CB_vs_C", "N_vs_C", "N_vs_B"):
        if comparison in summary["comparisons"]:
            print(comparison, {key: value for key, value in summary["comparisons"][comparison].items() if key != "changes"})


def checks():
    for family in ("bridge", "fork", "fuel", "rendezvous", "traffic", "wait", "multi", "patrol"):
        fixture = make_fixture(family, 1607)
        assert fixture == make_fixture(family, 1607)
        assert len(set(fixture["agents"])) == len(fixture["agents"])
        assert len(fixture["daySteps"]) == len(fixture["daySeconds"])
        assert all(fixture["map"]["cells"][position // 16][position % 16] == 0 for position in fixture["agents"])
    prior = {"test": dict(valid=True, score=[3, 12, 20], fixture_sha256="same")}
    worse = {"test": dict(valid=True, score=[2, 100, 200], fixture_sha256="same")}
    assert paired(prior, worse)["losses"] == paired(prior, worse)["primary_regressions"] == 1
    assert paired(prior, prior)["ties"] == 1
    assert quantile([0, 100], 0.95) == 95
    assert replace_once("abc", "b", "d") == "adc"
    print("Round 5 checks passed")


def factorial(name):
    source = OUTPUT / name
    records = [json.loads(line) for line in (source / "results.jsonl").read_text().splitlines()]
    autos = {(record["key"], record["variant"]): record for record in records if record["mode"] == "auto"}
    fixed = {(record["key"], record["variant"]): record for record in records if record["mode"] != "auto"}
    target = OUTPUT / (name + "-factorial")
    target.mkdir(parents=True, exist_ok=True)
    results = []
    for key in sorted({key for key, variant in autos}):
        for selector, planner, experiment in (("B", "B", "E1"), ("B", "C", "E2"), ("C", "B", "E3"), ("C", "C", "E4")):
            chosen = autos[key, selector]
            lineup = "".join(map(str, chosen["kinds"]))
            fixed_key = key.removesuffix("auto") + lineup
            cache_key = fixed_key, planner
            if cache_key not in fixed:
                prefix = target / f"{fixed_key}-{planner}"
                if prefix.with_suffix(".json").exists():
                    fixed[cache_key] = json.loads(prefix.with_suffix(".json").read_text())
                else:
                    fixed[cache_key] = execute(WORK / planner / "build/solver_bench", Path(chosen["command"][1]),
                        chosen["seed"], chosen["budget_ms"], chosen["threads"], lineup, chosen["selection_budget_ms"], prefix)
            record = dict(fixed[cache_key], key=key, variant=experiment, mode="auto", selector=selector, planner=planner,
                          selection_ms=chosen["selection_ms"], selection_source=chosen["command"])
            record["wall_ms"] += chosen["selection_ms"]
            results.append(record)
    (target / "results.jsonl").write_text("".join(json.dumps(record) + "\n" for record in results))
    analyze(name + "-factorial")


def campaign():
    suite("causal", ["B", "C", "BC", "CB"], 1000, 2500, 8)
    analyze("causal")
    factorial("causal")
    for variant in ("N", "H"):
        if not (WORK / variant / "build/solver_bench").exists():
            build([variant])
    suite("causal-new", ["N", "H"], 1000, 2500, 8)
    analyze("causal-new")
    suite("heldout", ["A", "B", "C", "BC", "N", "H"], 1000, 2500, 8)
    analyze("heldout")
    certified_wait()
    trace()
    competition(["A", "B", "C", "BC", "N"])


def sink_study():
    target = OUTPUT / ("sink-" + SINK)
    target.mkdir(parents=True, exist_ok=True)
    for map_seed, seed in ((919, 23), (919, 29), (1607, 41)):
        fixture = target / f"bridge-{map_seed}.fixture.json"
        fixture.write_text(json.dumps(make_fixture("bridge", map_seed)))
        for variant in ("B", "C", "N"):
            prefix = target / f"bridge-{map_seed}-{seed}-auto-{variant}"
            if not prefix.with_suffix(".json").exists():
                execute(WORK / variant / "build/solver_bench", fixture, seed, 1000, 8, "auto", 2500, prefix)


def objective():
    source = OUTPUT / "causal-factorial/results.jsonl"
    baseline = [json.loads(line) for line in source.read_text().splitlines() if json.loads(line)["variant"] == "E4"]
    target = OUTPUT / "objective-frozen"
    target.mkdir(parents=True, exist_ok=True)
    records = []
    for prior in baseline:
        lineup = "".join(map(str, prior["kinds"]))
        prefix = target / (prior["key"] + "-H")
        if prefix.with_suffix(".json").exists():
            record = json.loads(prefix.with_suffix(".json").read_text())
        else:
            record = execute(WORK / "H/build/solver_bench", Path(prior["command"][1]), prior["seed"],
                             prior["budget_ms"], prior["threads"], lineup, prior["selection_budget_ms"], prefix)
        record.update(key=prior["key"], variant="H", mode="auto", selection_ms=0)
        records += [dict(prior, variant="C", selection_ms=0), record]
    (target / "results.jsonl").write_text("".join(json.dumps(record) + "\n" for record in records))
    analyze("objective-frozen")


def transport():
    global SINK
    target = OUTPUT / "transport"
    target.mkdir(parents=True, exist_ok=True)
    order = random.Random(506)
    for map_seed, seed in ((919, 23), (919, 29), (1607, 41)):
        fixture = target / f"bridge-{map_seed}.fixture.json"
        fixture.write_text(json.dumps(make_fixture("bridge", map_seed)))
        for variant in ("B", "C", "N"):
            sinks = ["file", "pipe"]
            order.shuffle(sinks)
            for sink in sinks:
                SINK = sink
                prefix = target / f"bridge-{map_seed}-{seed}-{variant}-{sink}"
                if not prefix.with_suffix(".json").exists():
                    execute(WORK / variant / "build/solver_bench", fixture, seed, 1000, 8, "auto", 2500, prefix)


def budget_study():
    global SINK
    target = OUTPUT / "budget"
    target.mkdir(parents=True, exist_ok=True)
    fixture = target / "bridge-919.fixture.json"
    fixture.write_text(json.dumps(make_fixture("bridge", 919)))
    for allowance in (1000, 2500, 10000, 28500):
        for sink in ("pipe", "file"):
            SINK = sink
            prefix = target / f"C-{allowance}-{sink}"
            if not prefix.with_suffix(".json").exists():
                execute(WORK / "C/build/solver_bench", fixture, 23, 1000, 8, "auto", allowance, prefix)


def validate():
    checks()
    source = WORK / "N/source"
    shutil.copy2(ROOT / "tests/benchmark/round5_check.cpp", source / "tests/benchmark/round5_check.cpp")
    config = source / "tests/benchmark/CMakeLists.txt"
    if "add_executable(round5_check" not in config.read_text():
        with config.open("a") as stream:
            stream.write("\nadd_executable(round5_check round5_check.cpp)\ntarget_link_libraries(round5_check PRIVATE hexa_udon_optimizer)\n")
    with (OUTPUT / "validation.log").open("w") as log:
        subprocess.run(["cmake", "-S", str(source / "tests/benchmark"), "-B", str(WORK / "N/build")], stdout=log, stderr=log, check=True)
        for variant, target, arguments in (("N", "round5_check", []), ("A", "solver_bench_checks", []),
                                          ("C", "solver_bench_checks", []), ("N", "solver_bench_checks", []),
                                          ("B", "overnight_check", ["1"])):
            build_dir = WORK / variant / "build"
            subprocess.run(["cmake", "--build", str(build_dir), "--target", target, "--parallel", "4"], stdout=log, stderr=log, check=True)
            subprocess.run([str(build_dir / target), *arguments], stdout=log, stderr=log, check=True)
            print("validated", variant, target, flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["initial", "build", "suite", "analyze", "check", "factorial", "competition", "campaign", "trace", "sink-study", "objective", "transport", "budget", "validate"])
    parser.add_argument("--sink", choices=["file", "pipe"], default="file")
    parser.add_argument("--variants", nargs="+", choices=["A", "B", "C", "BC", "CB", "N", "H"], default=["A", "B", "C", "BC", "CB"])
    parser.add_argument("--name", default="causal")
    parser.add_argument("--day-ms", type=int, default=1000)
    parser.add_argument("--selection-ms", type=int, default=2500)
    parser.add_argument("--workers", type=int, choices=[1, 8], default=8)
    arguments = parser.parse_args()
    SINK = arguments.sink
    os.sched_setaffinity(0, range(8))
    if arguments.action == "initial":
        initial()
    elif arguments.action == "build":
        build(arguments.variants)
    elif arguments.action == "suite":
        suite(arguments.name, arguments.variants, arguments.day_ms, arguments.selection_ms, arguments.workers)
    elif arguments.action == "analyze":
        analyze(arguments.name)
    elif arguments.action == "factorial":
        factorial(arguments.name)
    elif arguments.action == "competition":
        competition(arguments.variants)
    elif arguments.action == "campaign":
        campaign()
    elif arguments.action == "trace":
        trace()
    elif arguments.action == "sink-study":
        sink_study()
    elif arguments.action == "objective":
        objective()
    elif arguments.action == "transport":
        transport()
    elif arguments.action == "budget":
        budget_study()
    elif arguments.action == "validate":
        validate()
    else:
        checks()
