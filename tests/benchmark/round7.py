"""Round 7 isolated builds and sequential reproducible experiments; WSL only."""
import argparse
import difflib
import json
import os
from pathlib import Path
import random
import shutil
import subprocess

import round5
import round6_audit

ROOT = round5.ROOT
OUTPUT = ROOT / "results/solver-round7"
WORK = Path("/home/hexa/solver-experiments/round7")
replace = round5.replace_once


def instrument(kernel):
    kernel = kernel.replace("#pragma once", "")
    kernel = replace(kernel, "    int completed = 0;", "    int completed = 0;\n    nlohmann::json levels = nlohmann::json::array();")
    kernel = replace(kernel, "        map<vector<long long>, Node> pool;", """        map<vector<long long>, Node> pool;
        set<vector<long long>> observed;
        long long repeats = 0, poolRepeats = 0, dominated = 0, pruned = 0, trims = 0, terminals = 0;
        const auto started = generated;""")
    kernel = replace(kernel, "            if (ordered.size() > 64) ordered.resize(64);", "            ++trims;\n            if (ordered.size() > 64) { pruned += ordered.size() - 64; ordered.resize(64); }")
    kernel = replace(kernel, "                auto found = pool.find(key);", """                repeats += !observed.insert(key).second;
                terminals += depth + 1 == horizon;
                auto found = pool.find(key);
                poolRepeats += found != pool.end();
                dominated += found != pool.end() && child.rank <= found->second.rank;""")
    kernel = replace(kernel, "        if (pool.empty() || exhausted) break;\n        trim();", """        if (!pool.empty() && !exhausted) trim();
        levels.push_back({{"depth", depth + 1}, {"attempts", generated - started},
            {"distinct", observed.size()}, {"repeat_states", repeats}, {"pool_repeats", poolRepeats},
            {"dominated", dominated}, {"pruned", pruned}, {"trims", trims}, {"terminals", terminals},
            {"retained", pool.size()}, {"exhausted", exhausted}});
        if (pool.empty() || exhausted) break;""")
    kernel = replace(kernel, '    cerr << "[multiday] horizon="', '    cerr << "[r7-states] " << levels.dump() << "\\n";\n    cerr << "[multiday] horizon="')
    return kernel


def binary(variant):
    if variant in ("A", "B", "J4"):
        return round6_audit.binary(variant)
    return WORK / variant / "build/solver_bench"


def hybrid(kernel, variant="H1"):
    kernel = replace(kernel, "    struct Node {", "    struct RestoreRng { Rng saved; ~RestoreRng() { rng = saved; } } restore{rng};\n    struct Node {")
    anchor = "    auto moves = [&](const Node& node, int agent, int length, Router& router, const vector<int>& incumbent) {"
    selective_check = ""
    if variant in ("H2", "H3"):
        selective_check = """    // ponytail: skips overnight search if all brands collected or patrols are disjoint; upgrade to multi-pair graph if needed
    if (count(before.begin(), before.end(), 1) == B) return plan;
    int bestA = 0, bestB = 1, minDist = INT_MAX;
    for (size_t i = 0; i < patrols.size(); ++i) {
        for (size_t j = i + 1; j < patrols.size(); ++j) {
            int d = abs(initial[patrols[i]].pos % W - initial[patrols[j]].pos % W) + abs(initial[patrols[i]].pos / W - initial[patrols[j]].pos / W);
            if (d < minDist) { minDist = d; bestA = i; bestB = j; }
        }
    }
    if (patrols.size() > 2 && minDist > 12) return plan;
"""
    comparator = """    auto greedy = [&](const Node& node, int length, int depth) {
        Router router(node.traffic);
        Day next(node.agents, length, today + depth, router, patrols, supplies, brandSpots, node.collected);
        vector<vector<pair<int, int>>> schedule;
        for (int agent : supplies) schedule.push_back({{node.agents[agent].pos, INT_MAX}});
        next.setSchedule(schedule);
        int missing = 0;
        return next.toPlan(next.fill(next.assignBrands(missing), 0));
    };
    Node baseline = root;
    int baselineTransitions = 0;
    for (int depth = 0; depth < horizon; ++depth) {
        if (budget.ms() >= timeMs) {
            cerr << "[r7-hybrid] " << nlohmann::json({{"day", today}, {"accepted", false},
                {"reason", "baseline_timeout"}, {"baseline_plan", plan}}).dump() << '\\n';
            return plan;
        }
        const int length = depth == 0 ? steps : daySteps[today + depth];
        const auto actions = depth == 0 ? plan : greedy(baseline, length, depth);
        const auto result = simulateDay(baseline.agents, actions, baseline.traffic, length);
        ++baselineTransitions;
        if (!result.valid) throw runtime_error("Invalid baseline rollout");
        baseline.agents = result.end;
        baseline.daily += result.brands;
        baseline.bowls += result.balls;
        for (int brand = 0; brand < B; ++brand) baseline.collected[brand] |= result.brandHit[brand];
        auto totalStay = result.stay;
        for (int cell = 0; cell < NC; ++cell) totalStay[cell] += baseline.stay[cell];
        baseline.stay = result.stay;
        baseline.traffic = statusFromStay(totalStay, PLAYERS);
        for (int cell = 0; cell < NC; ++cell) baseline.traffic[cell] = max(baseline.traffic[cell], forecast[cell]);
    }
    const auto baselineKey = reward(baseline);
    auto incumbentPlan = plan;
    bool accepted = false;
    vector<long long> candidateKey;
"""
    kernel = replace(kernel, anchor, selective_check + comparator + anchor)

    if variant in ("H2", "H3"):
        kernel = replace(kernel, "            if (spots[spot].stock <= 0) continue;",
                         "            if (spots[spot].stock <= 0 || node.collected[spots[spot].brand]) continue;")
        max_opts = 12 if variant == "H3" else 16
        kernel = replace(kernel, "if (options.size() < 24 &&", f"if (options.size() < {max_opts} &&")
        kernel = replace(kernel, "options.size() >= 24", f"options.size() >= {max_opts}")
        pair_loop = """            for (size_t first = 0; first < patrols.size() && !exhausted; ++first)
                for (size_t second = first + 1; second < patrols.size() && !exhausted; ++second)"""
        single_pair_loop = """            for (size_t first : {bestA})
                for (size_t second : {bestB})"""
        kernel = replace(kernel, pair_loop, single_pair_loop)

    if variant == "H3":
        adaptive_cap = """    map<vector<long long>, Node> pool;
    int lastDepth = 0;
    const long long dynamicCap = min(30000LL, max(2000LL, static_cast<long long>((timeMs - budget.ms()) * 40)));
    for (int depth = 0; depth < horizon && budget.ms() < timeMs; ++depth) {
        lastDepth = depth;"""
        kernel = replace(kernel, "    for (int depth = 0; depth < horizon && budget.ms() < timeMs; ++depth) {", adaptive_cap)
        kernel = replace(kernel, "        map<vector<long long>, Node> pool;", "        pool.clear();")
        kernel = kernel.replace("generated >= 24000", "generated >= dynamicCap")
        acceptance = """    Node* best = nullptr;
    if (completed == horizon && !beam.empty()) {
        best = const_cast<Node*>(&*max_element(beam.begin(), beam.end(), [](const Node& left, const Node& right) { return left.rank < right.rank; }));
    } else if (!pool.empty() && lastDepth + 1 == horizon) {
        auto it = max_element(pool.begin(), pool.end(), [](const auto& left, const auto& right) { return left.second.rank < right.second.rank; });
        best = const_cast<Node*>(&it->second);
    }
    if (best) {
        candidateKey = reward(*best);
        if (candidateKey > baselineKey && simulateDay(initial, best->first, status, steps).valid) {
            plan = best->first;
            accepted = plan != incumbentPlan;
        }
    }"""
        kernel = replace(kernel, """    if (completed == horizon) {
        const auto best = max_element(beam.begin(), beam.end(), [](const Node& left, const Node& right) { return left.rank < right.rank; });
        plan = best->first;
    }""", acceptance)
    else:
        kernel = replace(kernel, "        plan = best->first;", """        candidateKey = reward(*best);
        if (candidateKey > baselineKey && simulateDay(initial, best->first, status, steps).valid) {
            plan = best->first;
            accepted = plan != incumbentPlan;
        }""")

    kernel = replace(kernel, '    cerr << "[r7-states] "', """    cerr << "[r7-hybrid] " << nlohmann::json({{"day", today}, {"accepted", accepted},
        {"reason", completed == horizon ? "evaluated" : "incomplete"}, {"horizon", horizon},
        {"baseline_key", baselineKey}, {"candidate_key", candidateKey}, {"baseline_plan", incumbentPlan},
        {"returned_plan", plan}, {"baseline_transitions", baselineTransitions}}).dump() << '\\n';
""" + '    cerr << "[r7-states] "')
    return kernel


def build(variant):
    source = WORK / variant / "source"
    is_hybrid = variant.startswith("H")
    parent = "B" if is_hybrid else "C"
    if source.exists():
        shutil.rmtree(source)
    shutil.copytree(round5.WORK / parent / "source", source)
    optimizer = source / "src/optimizer/optimizer.cpp"
    before = optimizer.read_text()
    kernel = instrument((ROOT / "tests/benchmark/round6_multiday.hpp").read_text())
    cap = 24000 if is_hybrid else int(variant.removeprefix("J4I"))
    if not is_hybrid:
        assert cap in (24000, 96000, 384000)
        kernel = kernel.replace("24000", str(cap))
    start = before.index("vector<vector<int>> planDay(") if is_hybrid else before.index("vector<vector<int>> chooseOvernight(")
    end = before.index("vector<vector<int>> planDay(", start)
    if is_hybrid:
        kernel = hybrid(kernel, variant)
    text = before[:start] + "#define HEXA_JOINT_HORIZON 3\n" + kernel + "\n" + before[end:]
    text = replace(text, '#include "hexa_udon/solver.hpp"', '#include "hexa_udon/solver.hpp"\n#include <nlohmann/json.hpp>')
    if is_hybrid:
        text = replace(text, "    auto plan = solveDay(st, status, steps, lastDay, timeMs, warm, before).second;", """    Timer budget;
    auto plan = solveDay(st, status, steps, lastDay, timeMs, warm, before).second;
    if (!choosingKinds && !lastDay) plan = chooseOvernight(move(plan), st, status, before, steps, budget, timeMs / 0.85 * 0.98);""")
    optimizer.write_text(text)
    OUTPUT.mkdir(parents=True, exist_ok=True)
    (OUTPUT / f"{variant}-optimizer.patch").write_text("".join(difflib.unified_diff(before.splitlines(True), text.splitlines(True),
        fromfile="a/src/optimizer/optimizer.cpp", tofile="b/src/optimizer/optimizer.cpp")))
    shutil.copy2(ROOT / "tests/benchmark/round7_probe.cpp", source / "tests/benchmark/round7_probe.cpp")
    cmake = source / "tests/benchmark/CMakeLists.txt"
    cmake.write_text(cmake.read_text() + "\nadd_executable(round7_probe round7_probe.cpp)\ntarget_link_libraries(round7_probe PRIVATE hexa_udon_optimizer hexa_udon_json)\n")
    with (OUTPUT / f"build-{variant}.log").open("w") as log:
        subprocess.run(["cmake", "-S", str(source / "tests/benchmark"), "-B", str(WORK / variant / "build"), "-DCMAKE_BUILD_TYPE=Release"], check=True, stdout=log, stderr=log)
        subprocess.run(["cmake", "--build", str(WORK / variant / "build"), "--target", "solver_bench", "round7_probe", "--parallel", "4"], check=True, stdout=log, stderr=log)
    print("built", variant, flush=True)

def trial(fixture, variant, seed, day_ms, lineup, selection_ms, prefix):
    command = [str(binary(variant)), str(fixture), str(seed), str(day_ms), "8", lineup, str(selection_ms)]
    record_path = prefix.with_suffix(".json")
    if record_path.exists():
        record = json.loads(record_path.read_text())
        assert record["command"] == command
        assert record["binary_sha256"] == round5.digest(binary(variant))
        assert record["fixture_sha256"] == round5.digest(fixture)
    else:
        record = round5.execute(binary(variant), fixture, seed, day_ms, 8, lineup, selection_ms, prefix)
    assert record["valid"] and record["returncode"] == 0 and len(record["days"]) == record["expected_days"], prefix
    return record


def probes(variants):
    target = OUTPUT / "cap-probes"
    target.mkdir(parents=True, exist_ok=True)
    prior = ROOT / "results/solver-round6-audit"
    for name, folder, baseline in (("bridge-10100", "fixed", "J4"), ("fuel-9102", "fixed", "J4"),
                                    ("multi-10106", "fixed", "J4"), ("sacrifice-9401", "sacrifice", "B")):
        for variant in variants:
            for allowance in (130, 1000):
                prefix = target / f"{name}-{variant}-{allowance}"
                executable = WORK / variant / "build/round7_probe"
                command = [str(executable), str(prior / folder / f"{name}.fixture.json"),
                           str(prior / folder / f"{name}-{baseline}.json"), str(allowance)]
                result = subprocess.run(command, capture_output=True, text=True, check=True)
                record = json.loads(result.stdout)
                record.update(command=command, binary_sha256=round5.digest(executable),
                              fixture_sha256=round5.digest(Path(command[1])), baseline_sha256=round5.digest(Path(command[2])))
                prefix.with_suffix(".json").write_text(json.dumps(record, indent=2))
                prefix.with_suffix(".log").write_text(result.stderr)
                assert record["valid"]
                print(prefix.name, record["changed"], round(record["elapsed_ms"], 2), flush=True)


def diagnostics(variants):
    target = OUTPUT / "diagnostic"
    target.mkdir(parents=True, exist_ok=True)
    for case in ("bridge-10100", "fuel-9102", "multi-10106"):
        fixture = target / f"{case}.fixture.json"
        shutil.copy2(ROOT / f"results/solver-round6-audit/fixed/{case}.fixture.json", fixture)
        lineup = "0" * len(json.loads(fixture.read_text())["agents"])
        for variant in variants:
            trial(fixture, variant, 131, 1000, lineup, 2500, target / f"{case}-{variant}")


def exact(variants):
    target = OUTPUT / "exact"
    target.mkdir(parents=True, exist_ok=True)
    prior = ROOT / "results/solver-round6-audit"
    fixtures = [path for folder in ("exact", "sacrifice", "two-day") for path in (prior / folder).glob("*.fixture.json")
                if path.name != "search.fixture.json"]
    for original in sorted(fixtures):
        fixture = target / original.name
        shutil.copy2(original, fixture)
        oracle = json.loads(subprocess.check_output([str(round6_audit.WORK / "J4/build/round6_exact"), str(fixture)], text=True))
        name = fixture.name.removesuffix(".fixture.json")
        (target / f"{name}-oracle.json").write_text(json.dumps(oracle, indent=2))
        for variant in variants:
            record = trial(fixture, variant, 101, 1000, "00", 2500, target / f"{name}-{variant}")
            assert tuple(record["score"]) <= tuple(oracle["score"])


def suite(name, variants, lineup, day_ms, selection_ms):
    target = OUTPUT / f"{name}-{lineup}"
    target.mkdir(parents=True, exist_ok=True)
    families = ("bridge", "fork", "fuel", "rendezvous", "traffic", "wait", "multi", "patrol")
    base = 12100 if name == "dev" else 13100
    seeds = (201,) if name == "dev" else (301, 302)
    cases = [(family, base + index, seed) for index, family in enumerate(families) for seed in seeds]
    if name == "competition":
        cases = [("fork", 14101, 401)] if lineup == "fixed" else [("multi", 14106, 402)]
    manifest = dict(cases=cases, variants=variants, lineup=lineup, day_ms=day_ms, selection_ms=selection_ms,
                    workers=8, affinity=list(range(8)), log_sink="pipe", runner_sha256=round5.digest(Path(__file__)),
                    binaries={variant:round5.digest(binary(variant)) for variant in variants})
    path = target / "manifest.json"
    if path.exists():
        prior = json.loads(path.read_text())
        prior_variants = list(prior.get("variants", []))
        for v in variants:
            if v not in prior_variants: prior_variants.append(v)
            prior["binaries"][v] = round5.digest(binary(v))
        prior["variants"] = prior_variants
        path.write_text(json.dumps(prior, indent=2))
    else:
        path.write_text(json.dumps(manifest, indent=2))
    for family, map_seed, seed in cases:
        case = f"{family}-{map_seed}-s{seed}"
        fixture = target / f"{case}.fixture.json"
        fixture.write_text(json.dumps(round5.make_fixture(family, map_seed)))
        mode = "0" * len(json.loads(fixture.read_text())["agents"]) if lineup == "fixed" else "auto"
        order = list(variants)
        random.Random(map_seed + seed).shuffle(order)
        for variant in order:
            trial(fixture, variant, seed, day_ms, mode, selection_ms, target / f"{case}-{variant}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("build", "probes", "diagnostic", "exact", "suite"))
    parser.add_argument("--variants", nargs="+", required=True)
    parser.add_argument("--name", choices=("dev", "held", "competition"), default="dev")
    parser.add_argument("--lineup", choices=("fixed", "auto"), default="fixed")
    parser.add_argument("--day-ms", type=int, default=1000)
    parser.add_argument("--selection-ms", type=int, default=2500)
    args = parser.parse_args()
    os.sched_setaffinity(0, range(8))
    round5.SINK = "pipe"
    if args.action == "build":
        for variant in args.variants:
            build(variant)
    elif args.action == "probes":
        probes(args.variants)
    elif args.action == "exact":
        exact(args.variants)
    elif args.action == "suite":
        suite(args.name, args.variants, args.lineup, args.day_ms, args.selection_ms)
    else:
        diagnostics(args.variants)
