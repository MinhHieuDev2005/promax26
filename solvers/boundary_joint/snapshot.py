"""Freeze a unique source/EXE snapshot; never overwrite an existing version."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import zipfile

ROOT = Path(__file__).resolve().parents[2]


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--name", required=True)
    p.add_argument("--export", action="store_true", help="Only for replay-verified full-match improvements")
    p.add_argument("--record", nargs="*", default=[])
    a = p.parse_args()
    if Path(a.name).name!=a.name or a.name in (".",".."):
        p.error("plain directory name required")
    exe = ROOT / "build/boundary_joint/boundary_joint_runner.exe"
    records = [ROOT / path for path in a.record]
    if a.export:
        if not records:
            p.error("exports need a verified full-match record")
        for path in records:
            r = json.loads(path.read_text(encoding="utf-8"))
            if not (r.get("verified") and r.get("full_coverage") and r.get("deadline_pass")
                    and r["initial"]["day_info"]["day"]==0
                    and len(r["days"])==len(r["initial"]["config"]["daySteps"])
                    and r["executable_sha256"]==sha(exe)):
                p.error("record must match current EXE and pass full-match gates")
    target = ROOT / ("solver_exports" if a.export else "solver_learning/snapshots") / a.name
    if target.exists():
        raise FileExistsError(target)
    files = [ROOT / "CMakeLists.txt"]
    for directory in ("src", "include", "tests", "solvers/boundary_joint", "solvers/boundary_pool"):
        files += [f for f in (ROOT / directory).rglob("*")
                  if f.is_file() and f.suffix in (".cpp", ".hpp", ".py", ".md", ".txt", ".json")
                  and "__pycache__" not in f.parts]
    files += [ROOT / x for x in ("solvers/horizon_portfolio/benchmark.py", "solvers/chokudai_v2/experiment.py", "solvers/chokudai/budget_sweep.py")]
    target.mkdir(parents=True)
    shutil.copy2(exe,target/exe.name)
    with zipfile.ZipFile(target/"source.zip","w",zipfile.ZIP_DEFLATED) as z:
        for f in files:
            z.write(f,f.relative_to(ROOT))
    for record in records:
        shutil.copy2(record,target/record.name)
    manifest = {"executable_sha256": sha(exe), "source_zip_sha256": sha(target/"source.zip"),
                "source_files": {str(f.relative_to(ROOT)):sha(f) for f in files},
                "records": {f.name:sha(f) for f in records},
                "status": "verified_full_match" if a.export else "experimental_snapshot"}
    with (target/"manifest.json").open("x",encoding="utf-8") as stream:
        json.dump(manifest,stream,indent=2)
    print(target)


if __name__ == "__main__":
    main()
