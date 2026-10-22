"""Isolated Round 6 audit, bounded multiday search and sequential trials (WSL)."""
import argparse
import difflib
import json
import os
from pathlib import Path
import random
import shutil
import subprocess

import round6
import round5

ROOT = round6.ROOT
OUTPUT = ROOT / "results/solver-round6-audit"
WORK = round6.WORK


def binary(variant):
    return WORK / variant / "build/solver_bench" if variant in ("J3", "J4", "J4H2") else round6.binary(variant)


def build(variant):
    if variant not in ("J4", "J4H2"):
        raise ValueError(variant)
    source = WORK / variant / "source"
    shutil.copytree(round6.PREVIOUS / "C/source", source)
    optimizer = source / "src/optimizer/optimizer.cpp"
    before = optimizer.read_text()
    start = before.index("vector<vector<int>> chooseOvernight(")
    end = before.index("vector<vector<int>> planDay(", start)
    horizon = 2 if variant == "J4H2" else 3
    kernel = (ROOT / "tests/benchmark/round6_multiday.hpp").read_text().replace("#pragma once", "")
    text = before[:start] + f"#define HEXA_JOINT_HORIZON {horizon}\n" + kernel + "\n" + before[end:]
    optimizer.write_text(text)
    OUTPUT.mkdir(parents=True, exist_ok=True)
    (OUTPUT / f"{variant}-optimizer.patch").write_text("".join(difflib.unified_diff(
        before.splitlines(True), text.splitlines(True), fromfile="a/src/optimizer/optimizer.cpp", tofile="b/src/optimizer/optimizer.cpp")))
    shutil.copy2(ROOT / "tests/benchmark/round6_exact.cpp", source / "tests/benchmark/round6_exact.cpp")
    cmake = source / "tests/benchmark/CMakeLists.txt"
    cmake.write_text(cmake.read_text() + "\nadd_executable(round6_exact round6_exact.cpp)\ntarget_link_libraries(round6_exact PRIVATE hexa_udon_json hexa_udon_simulator)\n")
    with (OUTPUT / f"build-{variant}.log").open("w") as log:
        subprocess.run(["cmake", "-S", str(source / "tests/benchmark"), "-B", str(WORK / variant / "build"), "-DCMAKE_BUILD_TYPE=Release"], stdout=log, stderr=log, check=True)
        subprocess.run(["cmake", "--build", str(WORK / variant / "build"), "--target", "solver_bench", "round6_exact", "--parallel", "4"], stdout=log, stderr=log, check=True)
    print("built", variant, flush=True)


def execute(fixture, variant, seed, day_ms, lineup, selection_ms, target):
    prefix = target / f"{fixture.name.removesuffix('.fixture.json')}-{variant}"
    record_path = prefix.with_suffix(".json")
    if record_path.exists():
        record = json.loads(record_path.read_text())
        assert record["binary_sha256"] == round5.digest(binary(variant))
        assert record["fixture_sha256"] == round5.digest(fixture)
        assert record["command"] == [str(binary(variant)), str(fixture), str(seed), str(day_ms), "8", lineup, str(selection_ms)]
    else:
        record = round5.execute(binary(variant), fixture, seed, day_ms, 8, lineup, selection_ms, prefix)
    assert record["returncode"] == 0 and record["valid"] and len(record["days"]) == record["expected_days"], prefix
    return record


def exact(variants):
    target = OUTPUT / "exact"
    target.mkdir(parents=True, exist_ok=True)
    fixtures = {path.name: path for folder in ("exact", "exact-followup")
                for path in (round6.OUTPUT / folder).glob("*.fixture.json")}
    for name, original in sorted(fixtures.items()):
        fixture = target / name
        shutil.copy2(original, fixture)
        oracle = json.loads(subprocess.check_output([str(WORK / "J4/build/round6_exact"), str(fixture)], text=True))
        (target / name.replace(".fixture", "-oracle")).write_text(json.dumps(oracle, indent=2))
        for variant in variants:
            record = execute(fixture, variant, 101, 1000, "00", 2500, target)
            assert tuple(record["score"]) <= tuple(oracle["score"])
            if variant == "J4":
                assert record["score"] == oracle["score"], (name, record["score"], oracle["score"])


def suite(name, variants, lineup, day_ms, selection_ms):
    target = OUTPUT / name
    target.mkdir(parents=True, exist_ok=True)
    families = ("bridge", "fork", "fuel", "rendezvous", "traffic", "wait", "multi", "patrol")
    cases = [(family, base + index, 131 + index) for base in (9100, 10100) for index, family in enumerate(families)]
    if name.startswith("competition"):
        cases = [("fork", 11101, 151)] if lineup == "fixed" else [("multi", 11106, 156)]
    manifest = dict(cases=cases, variants=variants, lineup=lineup, day_ms=day_ms, selection_ms=selection_ms,
                    workers=8, affinity=list(range(8)), log_sink="pipe", runner_sha256=round5.digest(Path(__file__)),
                    binaries={variant: round5.digest(binary(variant)) for variant in variants})
    manifest_path = target / "manifest.json"
    if manifest_path.exists():
        assert json.loads(manifest_path.read_text()) == manifest
    else:
        manifest_path.write_text(json.dumps(manifest, indent=2))
    for family, map_seed, seed in cases:
        fixture = target / f"{family}-{map_seed}.fixture.json"
        fixture.write_text(json.dumps(round5.make_fixture(family, map_seed)))
        order = list(variants)
        random.Random(map_seed).shuffle(order)
        for variant in order:
            mode = "0" * len(json.loads(fixture.read_text())["agents"]) if lineup == "fixed" else lineup
            execute(fixture, variant, seed, day_ms, mode, selection_ms, target)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("build", "exact", "suite"))
    parser.add_argument("--variants", nargs="+", default=["B", "BC", "J1", "J4"])
    parser.add_argument("--name", default="fixed")
    parser.add_argument("--lineup", default="fixed")
    parser.add_argument("--day-ms", type=int, default=1000)
    parser.add_argument("--selection-ms", type=int, default=2500)
    args = parser.parse_args()
    os.sched_setaffinity(0, range(8))
    round5.SINK = "pipe"
    if args.action == "build":
        for variant in args.variants:
            build(variant)
    elif args.action == "exact":
        exact(args.variants)
    else:
        suite(args.name, args.variants, args.lineup, args.day_ms, args.selection_ms)
