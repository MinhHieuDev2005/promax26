import hashlib
import json
from pathlib import Path
import random
import sys

import run

NAMES = ("bridge", "fork", "fuel", "rendezvous", "traffic", "wait", "exact")


def fixture(name, seed):
    randomizer = random.Random(seed)
    size = 8 if name == "exact" else 16
    cells = [randomizer.choices([0, 1, 2], [7, 2, 1])[0] for _ in range(size * size)]
    agents, count, fuel, steps, days = 3, 10, 32, 12, 4
    if name == "exact":
        cells = [0] * 64
        positions = randomizer.sample(range(64), 4)
        return dict(startsAt=0, daySeconds=[60]*4, daySteps=[4]*4,
                    map=dict(height=8, width=8, cells=[cells[start:start+8] for start in range(0, 64, 8)]),
                    spots=[dict(brand=index, pos=position, stocks=1) for index, position in enumerate(positions[:3])],
                    agents=positions[3:], fuelLimits=12, players=1, busyThreshold=2, jammedThreshold=4)
    if name in ("bridge", "rendezvous"):
        starts = randomizer.sample([row*size+column for row in range(4, 12) for column in range(3)], agents)
        pool = [row*size+column for row in range(size) for column in range(8, size)]
        if name == "rendezvous": fuel, steps, days = 14, 16, 5
    elif name == "fork":
        starts = randomizer.sample([row*size+column for row in range(6, 10) for column in range(6, 10)], agents)
        pool = [row*size+column for row in range(size) for column in range(size)
                if (row < 4 or row > 11) and (column < 4 or column > 11)]
        steps, days = 10, 5
    else:
        starts = randomizer.sample(range(size*size), agents)
        pool = [position for position in range(size*size) if position not in starts]
    if name == "fuel": fuel, steps, days = 16, 12, 5
    if name == "traffic":
        cells = [1 if position % size in (6, 7, 8) or position // size in (6, 7, 8)
                 else cells[position] for position in range(size*size)]
        steps, days = 16, 5
    positions = randomizer.sample(pool, count)
    if name == "wait":
        positions[:agents] = starts
        positions = list(dict.fromkeys(positions))
        fuel, steps, days = 16, 10, 5
    for position in starts + positions: cells[position] = 0
    return dict(startsAt=0, daySeconds=[60]*days, daySteps=[steps]*days,
                map=dict(height=size, width=size, cells=[cells[start:start+size] for start in range(0, size*size, size)]),
                spots=[dict(brand=index, pos=position, stocks=randomizer.randint(1, agents))
                       for index, position in enumerate(positions)], agents=starts, fuelLimits=fuel,
                players=1, busyThreshold=1 if name == "traffic" else 2,
                jammedThreshold=2 if name == "traffic" else 4)


if __name__ == "__main__":
    if sys.argv[1:] == ["--self-test"]:
        for name in NAMES:
            for seed in (101, 202):
                setting = fixture(name, seed)
                assert setting == fixture(name, seed)
                assert len({spot["pos"] for spot in setting["spots"]}) == len(setting["spots"])
                assert all(setting["map"]["cells"][pos//setting["map"]["width"]][pos%setting["map"]["width"]] == 0
                           for pos in setting["agents"])
        print("Round 4 generator checks passed")
    else:
        run.CASES = dict.fromkeys(NAMES)
        run.fixture = fixture
        run.main()
        if "--output" in sys.argv:
            metadata = Path(sys.argv[sys.argv.index("--output") + 1]) / "metadata.json"
            record = json.loads(metadata.read_text())
            record["generator_sha256"] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
            metadata.write_text(json.dumps(record, indent=2))
