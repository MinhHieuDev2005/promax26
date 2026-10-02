"""Wrap an authoritative raw Hexudon config as a reproducible local case."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--name", default="user-input")
    parser.add_argument("--snapshot-output", type=Path)
    parser.add_argument("--roles", help="comma-separated 0/1 roles for a day-zero snapshot")
    args = parser.parse_args()

    config = json.loads(args.input.read_text(encoding="utf-8-sig"))
    case = {
        "schema_version": 1,
        "source": "user-provided-authoritative-config",
        "question": {"question_id": args.name, "name": args.name},
        "config": config,
        "opponents": [],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(case, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    if args.snapshot_output:
        if not args.roles:
            parser.error("--snapshot-output requires --roles")
        roles = [int(value) for value in args.roles.split(",")]
        if len(roles) != len(config["agents"]) or any(role not in (0, 1) for role in roles):
            parser.error("--roles must contain one 0/1 value per agent")
        width = config["map"]["width"]
        snapshot = {
            "op": "plan",
            "config": {**config, "startsAt": 0},
            "types": roles,
            "history": {
                "distinct_brands": [], "submitted_actions": [],
                "cumulative_daily_types": 0, "total_servings": 0,
            },
            "day_info": {
                "day": 0,
                "agents": [
                    {"kind": role, "pos": pos, "fuel": config["fuelLimits"]}
                    for role, pos in zip(roles, config["agents"])
                ],
                "others": [],
                "traffics": [
                    {"pos": row * width + col, "status": 0}
                    for row, cells in enumerate(config["map"]["cells"])
                    for col, terrain in enumerate(cells) if terrain == 1
                ],
            },
        }
        args.snapshot_output.parent.mkdir(parents=True, exist_ok=True)
        args.snapshot_output.write_text(
            json.dumps(snapshot, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )


if __name__ == "__main__":
    main()
