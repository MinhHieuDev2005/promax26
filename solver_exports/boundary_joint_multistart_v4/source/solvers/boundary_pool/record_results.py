"""Register measured artifacts without overwriting or comparing unlike scenarios."""
import argparse
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MEMORY = ROOT / "solver_learning"


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--files", nargs="+", required=True)
    a = p.parse_args()
    log_path = MEMORY / "experiment_log.jsonl"
    recorded = set()
    for line in log_path.read_text(encoding="utf-8").splitlines():
        row = json.loads(line)
        if row.get("status") == "complete":
            recorded.add(row["experiment_id"])
    elite_path = MEMORY / "elite_solutions.json"
    elites = json.loads(elite_path.read_text(encoding="utf-8"))
    elite_ids = {r["experiment_id"] for r in elites}
    for pattern in a.files:
        for file in ROOT.glob(pattern):
            if "partial" in file.name or "summary" in file.name:
                continue
            record = json.loads(file.read_text(encoding="utf-8"))
            if "days" not in record or not record.get("verified"):
                continue
            run_id = record.get("experiment_id", file.stem)
            roles = record.get("roles", record["initial"].get("types"))
            group = {"config_sha256": hashlib.sha256(json.dumps(record["initial"]["config"], sort_keys=True).encode()).hexdigest(),
                     "roles": roles, "traffic_model": record["traffic_model"],
                     "mode": record.get("mode", "match")}
            complete = record["initial"]["day_info"]["day"] == 0 and len(record["days"]) == len(record["initial"]["config"]["daySteps"])
            required = len({s["brand"] for s in record["initial"]["config"]["spots"]})
            coverage = all(r["daily_types"] == required for r in record["days"])
            if run_id not in recorded:
                entry = {"experiment_id": run_id, "status": "complete", "family": "boundary_pool_study",
                         "checkpoint": str(file.relative_to(ROOT)), "score": record["score"],
                         "valid": True, "full_match": complete, "full_coverage": coverage,
                         "comparison_group": group, "budget_ms": record["budget_ms"], "seed": record["seed"],
                         "executable_sha256": record.get("executable_sha256"),
                         "deadline_pass": record["deadline_pass"],
                         "max_day_ms": max(r["wall_ms"] for r in record["days"]),
                         "verification": "unchanged bin/hexudon.exe trace, full second replay"}
                with log_path.open("a", encoding="utf-8") as stream:
                    stream.write(json.dumps(entry, ensure_ascii=False) + "\n")
                recorded.add(run_id)
            # Preserve measured complete feasible trajectories in their own
            # comparison groups. They are offline artifacts, never embedded.
            if complete and coverage and run_id not in elite_ids:
                elites.append({"experiment_id": run_id, "score": record["score"],
                               "signature": hashlib.sha256(file.read_bytes()).hexdigest(),
                               "checkpoint": str(file.relative_to(ROOT)), "family": "boundary_pool_study",
                               "comparison_group": group, "offline_only": True})
                elite_ids.add(run_id)
            print(run_id, record["score"], "full_match", complete)
    elite_path.write_text(json.dumps(elites, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
