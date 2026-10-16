"""Extract an exact revealed-day input by replaying a saved checkpoint prefix."""
import argparse
import copy
import importlib.util
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("budget_v1", ROOT / "solvers/chokudai/budget_sweep.py")
sim = importlib.util.module_from_spec(spec); spec.loader.exec_module(sim)
p = argparse.ArgumentParser()
p.add_argument("checkpoint")
p.add_argument("day", type=int)
p.add_argument("output")
a = p.parse_args()
r = json.loads(Path(a.checkpoint).read_text(encoding="utf-8"))
if a.day < 0 or a.day >= len(r["days"]):
    raise SystemExit("day must identify a day inside the checkpoint")
data = copy.deepcopy(r["initial"]); traffic=[]
env = dict(os.environ, HEXUDON_THREADS=str(r.get("threads", 4)))
for row in r["days"][:a.day]:
    trace = sim.trace(data, row["plan"], env)
    sim.advance(data, row["plan"], trace, traffic)
data.pop("search", None); data.pop("planner_state", None)
Path(a.output).parent.mkdir(parents=True, exist_ok=True)
Path(a.output).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps({"day": data["day_info"]["day"], "score": [len(data["history"]["distinct_brands"]),
      data["history"]["cumulative_daily_types"], data["history"]["total_servings"]]}))
