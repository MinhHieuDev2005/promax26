"""Package independently built runners and their current shared source tree."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import zipfile

ROOT = Path(__file__).resolve().parents[2]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--name", required=True, help="new version directory name only")
    a = p.parse_args()
    if Path(a.name).name != a.name or a.name in (".", ".."):
        p.error("name must be a plain version directory")
    destination = ROOT / "solver_exports" / a.name
    if destination.exists():
        raise FileExistsError(destination)
    binaries = [ROOT / "build/boundary_pool" / name for name in
                ("boundary_pool_runner.exe", "boundary_pool_preview_runner.exe")]
    for binary in binaries:
        if not binary.is_file():
            raise FileNotFoundError(binary)
    files = [ROOT / "CMakeLists.txt"]
    files += list((ROOT / "src").glob("*.cpp"))
    files += list((ROOT / "include").rglob("*.hpp"))
    files += list((ROOT / "tests").glob("*.cpp"))
    files += [f for f in (ROOT / "solvers/boundary_pool").iterdir() if f.is_file() and f.suffix in (".cpp", ".hpp", ".py", ".md", ".txt")]
    for relative in ("solvers/horizon_portfolio/benchmark.py", "solvers/chokudai_v2/experiment.py", "solvers/chokudai/budget_sweep.py"):
        files.append(ROOT / relative)
    for filename in ("README.md", "qa.md", "LICENSE"):
        if (ROOT / filename).is_file():
            files.append(ROOT / filename)
    source_hashes = {str(f.relative_to(ROOT)): sha(f) for f in files}
    destination.mkdir(parents=True)
    for binary in binaries:
        shutil.copy2(binary, destination / binary.name)
        assert sha(binary) == sha(destination / binary.name)
    archive = destination / "source.zip"
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as z:
        for f in files:
            z.write(f, f.relative_to(ROOT))
    manifest = {"binaries": {b.name: sha(destination / b.name) for b in binaries},
                "source_archive_sha256": sha(archive), "source_files": source_hashes,
                "notes": "Windows x64; only Windows system runtime DLL imports. Benchmark requires original cases and bin/hexudon.exe."}
    (destination / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    shutil.copy2(ROOT / "solvers/boundary_pool/README.md", destination / "README.md")
    shutil.copy2(ROOT / "solvers/boundary_pool/RESULTS.md", destination / "RESULTS.md")
    print(destination)
    print(json.dumps(manifest["binaries"], indent=2))


if __name__ == "__main__":
    main()
