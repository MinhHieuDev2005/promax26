# Validated improved solver export — 2026-09-30

This folder freezes the H24 C++ source, its two Windows executables, and the
unchanged-evaluator checkpoints that demonstrate an improvement. No older
solver, GUI, evaluator or input JSON was edited to create this export.

## Included version

`h24_profile/bin/chokudai_h24_runner.exe` is the JSON stdin/stdout day-plan
runner. The plan engine is production ALNS; the new `op=roles` heuristic keeps
at most one Refuel vehicle. `h24_profile/bin/chokudai_h24_role_optimizer.exe`
is a **separate, pre-match** complete-match role profiler for 16×16, 24×24 and
32×32. Its profile can select more than one Refuel vehicle. The profiler is
not an HTTP bot and is not suitable for the GUI's short role callback.

| Exact input | Frozen roles | Verified C1/C2/C3 | Earlier comparison |
|---|---|---:|---|
| 16×16 | `[0,1,0,0]` | 8/48/94 | other one-Refuel masks: 91, 88, 92 |
| 24×24-A | `[0,0,1,0,0]` | 10/70/213 | old two-Refuel selector: 183 |
| 24×24-B | `[0,0,0,0,1,0,0]` | 14/70/260 | new profiled case; no comparable old full-coverage score claimed |
| 32×32 | `[1,1,0,0,0,0,0]` | 14/70/265 | new profiled case; no comparable old full-coverage score claimed |

The four exact input JSONs are copied to `h24_profile/cases/`. All four
checkpoint JSONs in `h24_profile/evidence/` have `valid=true`, exact
scores above, full daily brand coverage, and verification using the unchanged
`bin/hexudon.exe trace`. The H24 runner EXE was built after its source and
before these checkpoints. As ALNS is time-limited, running again may obtain a
different score; the evidence is a frozen valid action trajectory, not a
guarantee for every run or every new map.

**Important:** `op=roles` in the day runner does **not** automatically return
the 32×32 two-Refuel mask. To test that measured 265 trajectory family, first
run the separate role optimizer (or set `[1,1,0,0,0,0,0]` manually before the
match), then pass the server-confirmed roles to the day runner. Do not change
roles after a match starts. The same applies to reproducing the exact measured
mask on any case; the runner's fast selector is only a heuristic.

Frozen EXE SHA-256 values:

| EXE | SHA-256 |
|---|---|
| `chokudai_h24_runner.exe` | `251c9edc2f400bcac253d73c6319afecf4b2f1941dcf4a1c8dd04ea2be091d7f` |
| `chokudai_h24_role_optimizer.exe` | `ad9ca752ae76fe8524639780a63e6ab2ad6f6f61a37ffdf9cc31d4ff52bd6b72` |
| historical `chokudai_v2_h08_runner.exe` | `b7a6c84a238688210ab7a6a67bf5d0701fcbf7e33a41a0408e8d9c87e8464bd8` |

The roles profiler accepts:

```powershell
rtk proxy .\h24_profile\bin\chokudai_h24_role_optimizer.exe `
  .\h24_profile\cases\user-input-32x32.json 1000 role-result.json 1 profile
```

Arguments are `input.json budget_ms output.json seed profile`. Run the example
from this export directory, or use absolute paths. This command writes only
the requested `role-result.json`; it does not submit to a server.

## C++ source and rebuild

`h24_profile/source/` is a complete copy of the C++ project components needed
for H24: the root core, headers, v2 search library and H24 runner/profiler.
It uses the system Boost JSON development package, as the original build did.
From the repository root on the same Windows toolchain:

```powershell
cmake -S solver_exports/validated_improvements_2026-09-30/h24_profile/source/solvers/chokudai_h24 `
  -B build/exported-h24 -G Ninja `
  -DCMAKE_CXX_COMPILER=C:/msys64/ucrt64/bin/g++.exe
cmake --build build/exported-h24 --target chokudai_h24_runner chokudai_h24_role_optimizer
```

The EXEs consume/return JSON, not HTTP. To use a day runner in the GUI, add
`chokudai_h24_runner.exe` as a custom EXE solver. Keep the roles exactly as
confirmed by the server.

## Historical 225 version

The earlier H08 Chokudai update reached a replayable 13/91/225 on its 13-brand
test. Its historical EXE and checkpoint are retained separately under
`historical_h08_225/`. The H08 binary predates later changes to the shared
`solvers/chokudai_v2/search.cpp`, and no exact H08-time C++ snapshot survives
in this workspace. Consequently, **no C++ source is falsely labeled as the
exact H08 version**; the H08 folder is explicitly binary-and-evidence only.
