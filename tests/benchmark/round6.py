"""Round 6 isolated joint-search experiments; run under WSL HexaUdon."""
import argparse
import difflib
import json
import os
import random
from pathlib import Path
import shutil
import subprocess

import round5

ROOT = round5.ROOT
OUTPUT = ROOT / "results/solver-round6"
WORK = Path("/home/hexa/solver-experiments/round6")
PREVIOUS = WORK.parent / "round5"
round5.OUTPUT = OUTPUT
round5.SINK = "pipe"


def build(variant):
    source = WORK / variant / "source"
    if variant not in ("CT", "M", "MS", "J1", "J2"):
        raise ValueError(variant)
    parent = "C" if variant in ("CT", "M", "MS", "J2") else "B"
    shutil.copytree(PREVIOUS / parent / "source", source)
    path = source / "src/optimizer/optimizer.cpp"
    before = path.read_text()
    text = before
    if variant == "CT":
        text = round5.replace_once(text, '#include "hexa_udon/solver.hpp"', '#include "hexa_udon/solver.hpp"\n#include <nlohmann/json.hpp>')
        text = round5.replace_once(text, "        candidate.key.push_back(fuel);\n    };\n    auto rollout", """        candidate.key.push_back(fuel);
        vector<int> positions, remainingFuel;
        for (const auto& state : candidate.result.end) {
            positions.push_back(state.pos);
            remainingFuel.push_back(state.fuel);
        }
        cerr << "[waypoint-candidate] " << nlohmann::json({{"day", today}, {"steps", steps},
            {"positions", positions}, {"fuel", remainingFuel}, {"hits", candidate.result.brandHit},
            {"plan", candidate.plan}, {"key", candidate.key}, {"profile", candidate.profile}}).dump() + "\\n";
    };
    auto rollout""")
    if variant in ("M", "MS", "J2"):
        shutil.copy2(ROOT / "tests/benchmark/round6_joint.hpp", source / "include/hexa_udon/round6_joint.hpp")
        text = text.replace('#include "hexa_udon/solver.hpp"', '#include "hexa_udon/solver.hpp"\n#include "hexa_udon/round6_joint.hpp"')
        anchor = "        candidate.key.push_back(fuel);\n    };\n    auto rollout"
        text = round5.replace_once(text, anchor, "        candidate.key.push_back(fuel);\n        const auto team = jointKey(candidate.result.end, collected, router, daySteps[today + 1]);\n        candidate.key.insert(candidate.key.begin(), team.begin(), team.end());\n    };\n    auto rollout")
    if variant == "MS":
        text = round5.replace_once(text, "budget.ms() >= timeMs || spotAt[st[agent].pos] >= 0", "budget.ms() >= timeMs")
    if variant in ("J1", "J2"):
        text = round5.replace_once(text, "static const int OPS = 9;", "static const int OPS = 10;")
        text = round5.replace_once(text, '"station", "split"};', '"station", "split", "jointTail"};')
        text = round5.replace_once(text, "        if (P == 0) return false;", """        if (op == 9) {
            if (P < 2 || routes[pi].empty()) return false;
            const int other = (pi + 1 + rng.nextInt(P - 1)) % P;
            if (routes[other].empty()) return false;
            const int firstCut = rng.nextInt(routes[pi].size());
            const int secondCut = rng.nextInt(routes[other].size());
            vector<int> firstTail(routes[pi].begin() + firstCut, routes[pi].end());
            vector<int> secondTail(routes[other].begin() + secondCut, routes[other].end());
            if (firstTail == secondTail) return false;
            routes[pi].erase(routes[pi].begin() + firstCut, routes[pi].end());
            routes[other].erase(routes[other].begin() + secondCut, routes[other].end());
            routes[pi].insert(routes[pi].end(), secondTail.begin(), secondTail.end());
            routes[other].insert(routes[other].end(), firstTail.begin(), firstTail.end());
            return true;
        }
        if (P == 0) return false;""")
        text = round5.replace_once(text, "        double lastEmit = 0, lastBest = 0;", "        double lastEmit = 0, lastBest = 0, jointMs = 0;\n        long long jointAttempts = 0, jointGenerated = 0, jointValid = 0, jointBest = 0;")
        text = round5.replace_once(text, "            int op = rng.nextInt(OPS);", "            int op = rng.nextInt(OPS);\n            Timer operatorTimer;\n            const double priorBest = best.score;\n            if (op == 9) ++jointAttempts;")
        text = round5.replace_once(text, "} else if (!perturb(day, next, sch, op)) continue;", "} else if (!perturb(day, next, sch, op)) {\n                if (op == 9) jointMs += operatorTimer.ms();\n                continue;\n            }\n            if (op == 9) ++jointGenerated;")
        text = round5.replace_once(text, "            } else if (schChanged) day.setSchedule(cur.schedule);", "            } else if (schChanged) day.setSchedule(cur.schedule);\n            if (op == 9) {\n                jointValid += v > -1e17;\n                jointBest += best.score > priorBest;\n                jointMs += operatorTimer.ms();\n            }")
        text = round5.replace_once(text, '            cerr << "[solver] iter="', '            cerr << "[joint-lns] attempts=" << jointAttempts << " generated=" << jointGenerated << " valid=" << jointValid << " best=" << jointBest << " ms=" << jointMs << "\\n";\n            cerr << "[solver] iter="')
    path.write_text(text)
    OUTPUT.mkdir(parents=True, exist_ok=True)
    (OUTPUT / f"{variant}-optimizer.patch").write_text("".join(difflib.unified_diff(before.splitlines(True), text.splitlines(True),
        fromfile="a/src/optimizer/optimizer.cpp", tofile="b/src/optimizer/optimizer.cpp")))
    with (OUTPUT / f"build-{variant}.log").open("w") as log:
        subprocess.run(["cmake", "-S", str(source / "tests/benchmark"), "-B", str(WORK / variant / "build"),
                        "-DCMAKE_BUILD_TYPE=Release"], stdout=log, stderr=log, check=True)
        subprocess.run(["cmake", "--build", str(WORK / variant / "build"), "--target", "solver_bench", "--parallel", "4"],
                       stdout=log, stderr=log, check=True)
    print("built", variant, flush=True)

def suite(name, variants, lineup, day_ms, selection_ms):
    target = OUTPUT / name
    target.mkdir(parents=True, exist_ok=True)
    families = ("bridge", "fork", "fuel", "rendezvous", "traffic", "wait", "multi", "patrol")
    cases = [(family, base + index, 71 + index) for base in ((4100,) if name.startswith("dev") else (5100, 6100))
             for index, family in enumerate(families)]
    if name.startswith("followup"):
        cases = [(family, 8100 + index, 91 + index) for index, family in enumerate(families)]
    if name == "confirmation":
        cases = [("fork", 5101, seed) for seed in (72, 73, 74, 75)]
    if name.startswith("competition"):
        cases = [("bridge", 2207, 47)] if name.endswith("diagnostic") else [("bridge", 7101, 89)]
    manifest = dict(cases=cases, variants=variants, lineup=lineup, day_ms=day_ms, selection_ms=selection_ms,
        workers=8, affinity=list(range(8)), log_sink="pipe", runner_sha256=round5.digest(Path(__file__)),
        binaries={variant: round5.digest(binary(variant)) for variant in variants})
    (target / "manifest.json").write_text(json.dumps(manifest, indent=2))
    for family, map_seed, seed in cases:
        key = f"{family}-{map_seed}" + (f"-search{seed}" if name == "confirmation" else "")
        fixture = target / f"{key}.fixture.json"
        fixture.write_text(json.dumps(round5.make_fixture(family, map_seed)))
        order = list(variants)
        random.Random(map_seed).shuffle(order)
        for variant in order:
            prefix = target / f"{key}-{variant}"
            count = len(json.loads(fixture.read_text())["agents"])
            mode = "0" * count if lineup == "fixed" else lineup
            if prefix.with_suffix(".json").exists():
                previous = json.loads(prefix.with_suffix(".json").read_text())
                assert previous["binary_sha256"] == round5.digest(binary(variant))
                assert previous["fixture_sha256"] == round5.digest(fixture)
                assert previous["budget_ms"] == day_ms and previous["selection_budget_ms"] == selection_ms
                assert previous["command"][5] == mode and previous["seed"] == seed
                assert previous["threads"] == 8 and previous["log_sink"] == "pipe"
                assert previous["valid"] and len(previous["days"]) == previous["expected_days"]
                continue
            round5.execute(binary(variant), fixture, seed, day_ms, 8, mode, selection_ms, prefix)


def binary(variant):
    return (WORK if variant in ("CT", "M", "MS", "J1", "J2") else PREVIOUS) / variant / "build/solver_bench"

def exact(variants, fresh=False):
    source = WORK / "M/source"
    for filename in ("round6_exact.cpp", "round6_check.cpp"):
        shutil.copy2(ROOT / "tests/benchmark" / filename, source / "tests/benchmark" / filename)
    cmake = source / "tests/benchmark/CMakeLists.txt"
    text = cmake.read_text()
    if "add_executable(round6_exact" not in text:
        cmake.write_text(text + "\nadd_executable(round6_exact round6_exact.cpp)\ntarget_link_libraries(round6_exact PRIVATE hexa_udon_json hexa_udon_simulator)\nadd_executable(round6_check round6_check.cpp)\ntarget_link_libraries(round6_check PRIVATE hexa_udon_optimizer)\n")
    build_dir = WORK / "M/build"
    subprocess.run(["cmake", "-S", str(source / "tests/benchmark"), "-B", str(build_dir)], check=True, stdout=subprocess.DEVNULL)
    subprocess.run(["cmake", "--build", str(build_dir), "--target", "round6_exact", "round6_check", "--parallel", "4"], check=True, stdout=subprocess.DEVNULL)
    subprocess.run([str(build_dir / "round6_check")], check=True)
    target = OUTPUT / ("exact-followup" if fresh else "exact")
    target.mkdir(parents=True, exist_ok=True)
    cases = [("stock", [0, 0], [0], 1, [2, 2, 2], (1, 3, 3)),
             ("distinct", [0, 0], [1, 8], 1, [2], (2, 2, 2)),
             ("progression", [0, 8], [3, 24], 3, [2, 2, 2], None),
             ("fuel", [0, 0], [3, 24], 1, [2, 2, 2], (0, 0, 0))]
    for seed in (range(8301, 8305) if fresh else range(7301, 7305)):
        positions = random.Random(seed).sample([1, 2, 3, 9, 10, 16, 17, 24, 25], 4)
        cases.append((f"competing-{seed}", [0, 8], positions, 3, [2, 2, 2], None))
    for name, agents, positions, fuel, steps, expected in cases:
        fixture = target / f"{name}.fixture.json"
        setting = dict(startsAt=0, daySeconds=[60]*len(steps), daySteps=steps,
            map=dict(height=8, width=8, cells=[[0]*8 for row in range(8)]),
            spots=[dict(brand=index, pos=position, stocks=1) for index, position in enumerate(positions)],
            agents=agents, fuelLimits=fuel, players=1, busyThreshold=2, jammedThreshold=4)
        fixture.write_text(json.dumps(setting))
        output = subprocess.check_output([str(build_dir / "round6_exact"), str(fixture)], text=True)
        reference = json.loads(output)
        if expected is not None:
            assert tuple(reference["score"]) == expected, (name, reference)
        (target / f"{name}-oracle.json").write_text(json.dumps(reference, indent=2))
        for variant in variants:
            prefix = target / f"{name}-{variant}"
            record = (json.loads(prefix.with_suffix(".json").read_text()) if prefix.with_suffix(".json").exists()
                      else round5.execute(binary(variant), fixture, 101, 1000, 8, "00", 2500, prefix))
            assert record["valid"] and len(record["days"]) == len(steps)
            assert record["binary_sha256"] == round5.digest(binary(variant))
            assert record["fixture_sha256"] == round5.digest(fixture)
            assert tuple(record["score"]) <= tuple(reference["score"]), (name, variant)
        print("exact", name, reference["score"], flush=True)


def reproduce(variants):
    target = OUTPUT / "bridge-919"
    target.mkdir(parents=True, exist_ok=True)
    fixture = ROOT / "results/solver-round4/B-auto/bridge-919.json"
    for variant in variants:
        prefix = target / variant
        if not prefix.with_suffix(".json").exists():
            os.environ["HEXA_JOINT_TRACE"] = "1"
            round5.execute(binary(variant), fixture, 23, 1000, 8, "000", 2500, prefix)
            del os.environ["HEXA_JOINT_TRACE"]
    if "C" in variants:
        for sink in ("pipe", "file"):
            prefix = target / ("starvation-" + sink)
            if not prefix.with_suffix(".json").exists():
                round5.SINK = sink
                round5.execute(binary("C"), fixture, 23, 1000, 8, "auto", 2500, prefix)
        round5.SINK = "pipe"


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["build", "reproduce", "suite", "exact"])
    parser.add_argument("--variants", nargs="+", default=["B", "C"])
    parser.add_argument("--name", default="dev-fixed")
    parser.add_argument("--lineup", default="fixed")
    parser.add_argument("--day-ms", type=int, default=1000)
    parser.add_argument("--selection-ms", type=int, default=2500)
    parser.add_argument("--fresh", action="store_true")
    arguments = parser.parse_args()
    os.sched_setaffinity(0, range(8))
    if arguments.action == "build":
        for variant in arguments.variants:
            build(variant)
    elif arguments.action == "reproduce":
        reproduce(arguments.variants)
    elif arguments.action == "exact":
        exact(arguments.variants, arguments.fresh)
    else:
        suite(arguments.name, arguments.variants, arguments.lineup, arguments.day_ms, arguments.selection_ms)
