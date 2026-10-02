# Boundary Pool — experimental standalone JSON solver

The original ALNS/ACO/MLNS/Chokudai sources and GUI remain unchanged. This
runner links their shared core instead of duplicating movement or score rules.

Pipeline: production ALNS seed → compact subset route DP → coverage-diverse
route pool → stock-aware bounded recombination → optional tail Chokudai →
incumbent-versus-candidate next-day rollouts → exact final simulation.

The current campaign target is `16/112/339`; it has **not** been achieved.
Read `RESULTS.md` for measurements and
the scope of each comparison. Do not replace a competition default based on a
single case. Automatic roles currently reuse the existing ALNS selector;
the new route algorithm does not solve the previously reported role-selection
bias. Explicit benchmark roles are recorded and are not hardcoded in the EXE.

## Build

From the repository root, with CMake, Ninja, C++20 and Boost.JSON available:

```powershell
rtk cmake -S solvers/boundary_pool -B build/boundary_pool -G Ninja -DCMAKE_BUILD_TYPE=Release -DCMAKE_CXX_COMPILER=C:/msys64/ucrt64/bin/g++.exe -DCMAKE_PREFIX_PATH=C:/msys64/ucrt64 -DBUILD_TESTING=OFF
rtk cmake --build build/boundary_pool --target boundary_pool_runner boundary_pool_preview_runner boundary_pool_tests -j 2
rtk build/boundary_pool/boundary_pool_tests.exe
rtk python -m unittest discover -s solvers/boundary_pool -p test_*.py -v
```

In GUI use **Add solver EXE → Runner JSON**, not Bot HTTP. Input/output and
1-based `state.day` / 0-based `day_info.day` follow the existing runner protocol.
The EXE writes a single JSON response. Planner hints are tied to the normalized
config, source day and accepted previous plan, then re-simulated before reuse.

Two independently selectable executables are built:

- `boundary_pool_runner.exe`: ALNS + subset route pool + short-day lookahead.
- `boundary_pool_preview_runner.exe`: additionally screens boundary candidates
  with cheap next-day DP before spending ALNS rollout time. This is the candidate
  to try on the supplied 25x25 case, not a promoted all-map default.

The recorded 25x25 experiments explicitly select `[1,0,0,0]` (first car supplies).
For comparable GUI tests select these roles manually before submitting them;
do not expect Auto to reproduce this choice. Request 45000 ms/day; the GUI may
reduce it further to meet the server deadline. No GUI code is changed here.

## Benchmark

Requires Python `psutil`. Run CPU-heavy experiments serially. Output goes to
`solver_learning/runs`; use a new label rather than overwriting prior results.

```powershell
rtk python solvers/boundary_pool/benchmark.py --exe build/boundary_pool/boundary_pool_runner.exe --cases cases/user-input-25x25.json --roles 1,0,0,0 --budget 45000 --seeds 1 2 3 --traffic idle --variant boundary --label my-boundary-study
```

`--variant baseline` disables new modules with the SAME executable/ALNS floor.
`pool` enables subset DP/recombination but disables equal-bowl boundary trades.
`boundary` enables those trades. `wide` raises rollout candidates to eight.
`chokudai` adds bounded tail search and up to eight rollout candidates. Neither
showed enough benefit to become the default. `preview` adds cheap next-day DP
screening, keeping the incumbent and an exploration slot in the rollout list.
These are cumulative ablations; use `--search` for individual parameter tests.

Use `--checkpoint <completed-match.json> --day 3` instead of `--cases` to
compare the exact same starting state. Day is 1-based. This measures one day,
not whole-match improvement; forecast bowls are never substituted for replay.

Traffic models: `idle` adds only own traffic and divides by players; `mirror`
assumes every other player generates the same traffic. Neither assumes knowledge
of actual opponents. Both use identical action/scoring code. Never pool their
scores as if they were the same benchmark.

## Parameters and practical limits

| Map area | Preset | Route capacity | Maximum subset size |
|---|---|---:|---:|
| ≤256, including 16×16 | small | 96 | 20 |
| ≤625, including 24×24 and supplied 25×25 | medium | 80 | 20 |
| >625, including 32×32 | large | 48 | 18 |

These presets are conservative defaults, not a completed tuning study. Capacity
is reduced for ≥4 patrols; rare-type/endpoint reservations can exceed the soft
cap. Larger target sets fall back to ALNS, not an exponential allocation.
Subset labels are packed time/fuel with a byte parent, about 100 MiB at 20
targets, processed one car at a time. One time-first label is heuristic under
fuel constraints; this is NOT advertised as exact Pareto RCSP.

Recombination uses exact shared-stock counting and safe bounds *within its
fixed independent-route pool*. The pool cap, DP label truncation, deadline and
Chokudai endpoint buckets are heuristic restrictions, not safe global dominance.
Current-day complete candidates always go through the original simulator.

Positive budgets are capped at 45 s, with a 3 s reserve (scaled for small
budgets) and an additional `endsAt` constraint. Early return is permitted when
no useful candidates remain. Future roads are explicitly `hold_observed_roads`.
Past days are never invented by this solver. Online forecast quality can differ
when the next day's observed traffic changes.

Eight C++ test groups and eleven Python tests pass for this module. This is not
a claim that the entire legacy repository test suite passes. Saved actions are
replayed with the unchanged core; rerunning a time-limited ALNS seed can still
produce different actions because iteration counts depend on machine timing.

`record_results.py` registers verified measurements and offline elite traces.
`export.py --name <new-version>` packages both EXEs, source ZIP and SHA256
manifest without replacing an existing export. It never embeds elite traces.

Not yet implemented here: a general ten-neighborhood VND, multi-label path RCSP,
cross-map automatic tuning, custom flat TT, CABS/BULB, path relinking and full
ejection-chain repair. Their names must not be used as claims about this EXE.
