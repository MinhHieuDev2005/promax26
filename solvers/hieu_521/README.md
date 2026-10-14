# Hieu adapter and 530-target experiments

All writable source and build artifacts are in `promax26-duc`. CMake reads
`../pro26-hieu/promax26` as a dependency and places its object files in the Duc
build tree. The Hieu checkout is not modified.

Build from `promax26-duc` in PowerShell:

```powershell
cmake -S solvers/hieu_521 -B build-pro26-hieu/adapter -G Ninja -DCMAKE_BUILD_TYPE=Release -DCMAKE_PREFIX_PATH=C:/msys64/ucrt64
cmake --build build-pro26-hieu/adapter --target udon530_tail_runner
python solvers/hieu_521/test_day_protocol.py
```

`hexa_udon_hieu_runner_v2.exe` is the GUI baseline.
`udon530_runner.exe` is the first seed-aware experiment.
`udon530_tail_runner.exe` adds optional traffic persistence and suffix repair.
Experimental names describe the target; they do not certify a 530 score.

Benchmark:

```powershell
python solvers/hybrid_master/benchmark/run.py --snapshot cases/master/user-32x32-target500.snapshot.json --exe build-pro26-hieu/udon530_tail_runner.exe --budget 45000 --seed 1 --roles 0,0,0,0,1,0,0 --traffic idle --output solvers/hybrid_master/benchmark/results/target530_tail.json
```

Pass `--search-json` with a JSON object containing `tailRepair: true` or
`preserveTraffic: true` to enable each ablation. Both are off by default.
PowerShell must preserve the quotation marks in that JSON argument.
Do not change or replace an EXE while a multi-day benchmark is using it.

Input `day_info.day` uses zero-based days; GUI `state.day` uses one-based days.
`state.stepsCount`, when supplied, is the live horizon. Moves consume terrain
time; the length of the JSON array is not the number of simulation steps.

The current verified corrected baseline is 26/156/520. See
`OPTIMIZATION_REPORT.md` and the saved benchmark replay for evidence.
