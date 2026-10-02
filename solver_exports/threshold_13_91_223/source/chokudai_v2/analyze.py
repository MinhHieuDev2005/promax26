"""Summarize measured experiments and physical end states (no score invention)."""
import json
from pathlib import Path

root = Path(__file__).resolve().parents[2]
rows = []
for path in sorted((root / "solver_learning/runs").glob("*.json")):
    if path.name.endswith(".partial.json"):
        continue
    r = json.loads(path.read_text(encoding="utf-8"))
    rows.append(r)
    print(r["experiment_id"], r["score"], "coverage", r["valid"],
          "wall_s", round(r["wall_ms"] / 1000, 2), "deadline", r["deadline_pass"])
    if r["solver"] in ("v1", "v2", "alns", "lns"):
        for d in r["days"]:
            print(" day", d["day"]+1, "udon", d["servings"],
                  "end(pos,fuel)", [(a["cell"], a["fuel"]) for a in d["ending_agents"]],
                  "wait_steps", [sum(-x for x in actions if x < 0) for actions in d["plan"]])
print("Completed", len(rows), "feasible", sum(r["valid"] for r in rows))
