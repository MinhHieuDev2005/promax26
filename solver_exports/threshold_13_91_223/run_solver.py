import argparse
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parent
SOLVERS = {
    "alns": (ROOT / "bin/hexudon.exe", ["plan", "alns"]),
    "lns": (ROOT / "bin/hexudon.exe", ["plan", "lns"]),
    "v2": (ROOT / "bin/chokudai_v2_runner.exe", []),
    "h04": (ROOT / "bin/chokudai_v2_h04_runner.exe", []),
    "h08": (ROOT / "bin/chokudai_v2_h08_runner.exe", []),
    "h17": (ROOT / "bin/chokudai_v2_h17_runner.exe", []),
    "h20": (ROOT / "bin/chokudai_v2_h20_runner.exe", []),
    "h22": (ROOT / "bin/chokudai_v2_h22_runner.exe", []),
}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--solver", choices=SOLVERS, required=True)
    parser.add_argument("--input", required=True)
    parser.add_argument("--output")
    parser.add_argument("--threads", type=int, default=4)
    args = parser.parse_args()
    payload = json.loads(Path(args.input).read_text(encoding="utf-8"))
    exe, extra = SOLVERS[args.solver]
    import os
    env = dict(os.environ, HEXUDON_THREADS=str(args.threads))
    proc = subprocess.run([str(exe), *extra], input=json.dumps(payload),
                          text=True, encoding="utf-8", capture_output=True,
                          env=env, cwd=ROOT)
    if proc.returncode:
        raise SystemExit(proc.stderr or proc.stdout)
    result = json.loads(proc.stdout)
    rendered = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output:
        Path(args.output).write_text(rendered + "\n", encoding="utf-8")
    else:
        print(rendered)


if __name__ == "__main__":
    main()
