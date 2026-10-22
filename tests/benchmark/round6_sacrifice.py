"""Find and verify a two-day exact witness that must sacrifice today's brands."""
import json
import random
import subprocess

import round6_audit as audit


def reference(fixture, minimum=None):
    command = [str(audit.WORK / "J4/build/round6_exact"), str(fixture)]
    if minimum is not None:
        command.append(str(minimum))
    return json.loads(subprocess.check_output(command, text=True))


def check():
    target = audit.OUTPUT / "sacrifice"
    target.mkdir(parents=True, exist_ok=True)
    template = json.loads((audit.round6.OUTPUT / "exact/competing-7303.fixture.json").read_text())
    tested = []
    for seed in range(9400, 10400):
        generator = random.Random(seed)
        fixture = target / "search.fixture.json"
        positions = generator.sample([0, 1, 2, 3, 8, 9, 10, 11, 16, 17, 18, 24, 25, 26], 6)
        template["agents"] = positions[:2]
        template["spots"] = [dict(brand=index, pos=position, stocks=1) for index, position in enumerate(positions[2:])]
        template["daySteps"] = [2, 4]
        template["daySeconds"] = [60, 60]
        fixture.write_text(json.dumps(template))
        optimum = reference(fixture)
        today = optimum["witness"][0]["brands"]
        restricted = reference(fixture, today + 1) if today < 4 else {"feasible": False}
        tested.append(dict(seed=seed, score=optimum["score"], today=today, restricted=restricted.get("score")))
        if not restricted["feasible"] or restricted["score"][0] >= optimum["score"][0]:
            continue
        fixture = target / f"sacrifice-{seed}.fixture.json"
        fixture.write_text(json.dumps(template))
        (target / f"sacrifice-{seed}-oracle.json").write_text(json.dumps(optimum, indent=2))
        (target / f"sacrifice-{seed}-restricted.json").write_text(json.dumps(restricted, indent=2))
        (target / "search.json").write_text(json.dumps(tested, indent=2))
        for variant in ("B", "C", "M", "MS", "J1", "J2", "J4H2", "J4"):
            record = audit.execute(fixture, variant, 101, 1000, "00", 2500, target)
            assert tuple(record["score"]) <= tuple(optimum["score"])
            if variant in ("J4H2", "J4"):
                assert record["score"] == optimum["score"], (variant, record["score"], optimum["score"])
                assert record["days"][0]["brands"] < today + 1
        print("Verified necessary first-day sacrifice", seed, optimum["score"], restricted["score"], flush=True)
        return
    (target / "search.json").write_text(json.dumps(tested, indent=2))
    raise AssertionError("No strict primary-sacrifice witness in the fixed search range")


def two_day_checks():
    target = audit.OUTPUT / "two-day"
    target.mkdir(parents=True, exist_ok=True)
    template = json.loads((audit.round6.OUTPUT / "exact/competing-7303.fixture.json").read_text())
    template.update(daySteps=[2, 2], daySeconds=[60, 60], fuelLimits=2)
    for name, starts, positions, expected in (
        ("shared", [0, 0], [0], [1, 2, 2]),
        ("waypoints", [0, 8], [2, 24], [2, 2, 2]),
        ("wait-move", [0, 1], [0, 3], [2, 3, 3]),
    ):
        template["agents"] = starts
        template["spots"] = [dict(brand=index, pos=position, stocks=1) for index, position in enumerate(positions)]
        fixture = target / f"{name}.fixture.json"
        fixture.write_text(json.dumps(template))
        oracle = reference(fixture)
        assert oracle["score"] == expected, (name, oracle["score"])
        (target / f"{name}-oracle.json").write_text(json.dumps(oracle, indent=2))
        for variant in ("B", "C", "M", "MS", "J1", "J2", "J4H2", "J4"):
            record = audit.execute(fixture, variant, 101, 1000, "00", 2500, target)
            assert tuple(record["score"]) <= tuple(expected)
            if variant in ("J4H2", "J4"):
                assert record["score"] == expected, (name, variant, record["score"])
                if name == "wait-move":
                    assert all(action < 0 for action in record["days"][0]["plan"][0])
                    assert any(action >= 0 for action in record["days"][0]["plan"][1])
                if name == "waypoints":
                    assert all(position not in positions for position in record["days"][0]["positions"])
    for invalid in ("-1", "5", "1x"):
        result = subprocess.run([str(audit.WORK / "J4/build/round6_exact"), str(fixture), invalid], capture_output=True)
        assert result.returncode != 0
    assert reference(fixture, 4)["feasible"] is False


def missing_comparators():
    target = audit.OUTPUT / "exact"
    for seed in range(8301, 8305):
        fixture = target / f"competing-{seed}.fixture.json"
        oracle = reference(fixture)
        for variant in ("C", "J1", "J2"):
            record = audit.execute(fixture, variant, 101, 1000, "00", 2500, target)
            assert tuple(record["score"]) <= tuple(oracle["score"])


if __name__ == "__main__":
    audit.os.sched_setaffinity(0, range(8))
    audit.round5.SINK = "pipe"
    check()
    two_day_checks()
    missing_comparators()
