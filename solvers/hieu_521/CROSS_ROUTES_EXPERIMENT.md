# Cross-route experiment — 2026-10-14

Acceptance target: 26 distinct types, 156 cumulative types, at least 530
servings on cases/master/user-32x32-target500.snapshot.json with idle traffic.
Budget: 45000 ms/day, 8 workers, roles 0,0,0,0,1,0,0.

Separate binary: build-pro26-hieu/udon530_cross_runner.exe.
The previous baseline and seeded executables are not rebuilt or overwritten.

## Decision

Test two explicit cross-route neighborhoods rather than add another planner:
suffix exchange between two patrol routes, transfer of 2–3 consecutive
collection targets, and exchange of one target between patrol routes. These are inspired by the reviewed
procon37kyogi improve.py; this is a separate C++ implementation.

Input search.crossMoves controls ablation: 0 = control (default), 1 = suffix
exchange, 2 = segment transfer; bits may be combined. The control is the SAME binary;
historical 522 is only a reference because other local optimizer changes
precede this experiment. Keep futureWeight=0 and tailRepair=false.

Duplicate collection targets are rejected. Segment transfer does not move
refueling nodes. Suffix exchange preserves refueling nodes, then existing
joint repair and simulator evaluation determine feasibility. A mutation alone
is not evidence of a valid plan. The benchmark independently validates every
day and replays the full match.

## Checks

- C++20 Release build succeeded.
- cross_routes_test.exe passed: successful exchange/transfer, duplicate rejection,
  unchanged inputs on rejection, refueling node handling and invalid bounds.
- Full-match scores must come from benchmark JSON, never from this design.

## Validated results

All rows use the supplied 32x32 snapshot, idle traffic and roles
`0,0,0,0,1,0,0`. Every row passed six daily validations and full replay.

| Variant | Budget/day | Threads | Score |
|---|---:|---:|---:|
| Same binary, crossMoves=0 control | 45 s | 8 | 26/156/518 |
| Suffix exchange only | 45 s | 8 | 26/156/519 |
| Segment transfer only | 45 s | 8 | 26/156/521 |
| Suffix + segment, seed 1 | 45 s | 8 | **26/156/525** |
| Suffix + segment, seed 2 | 45 s | 8 | 26/156/524 |
| Suffix + segment, seed 3 | 45 s | 8 | 26/156/521 |
| Suffix + segment | 55 s | 8 | 26/156/523 |
| Suffix + segment | 45 s | 16 | 26/156/519 |
| Plus target exchange (rejected) | 45 s | 8 | 26/156/521 |
| Plus stock-aware replacement (rejected) | 45 s | 8 | 26/156/517 |

Best verified result is 525, not the acceptance target 530. More deadline and
more logical workers both regressed in their first controlled runs. Recommended
runtime remains 45 s/day and 8 workers.

## Reproduction

From promax26-duc, run:

```powershell
cmake --build build-pro26-hieu/adapter --target udon530_cross_runner cross_routes_test -j 4
build-pro26-hieu/adapter/cross_routes_test.exe
python solvers/hybrid_master/benchmark/run.py --snapshot cases/master/user-32x32-target500.snapshot.json --exe build-pro26-hieu/udon530_cross_runner.exe --budget 45000 --roles 0,0,0,0,1,0,0 --traffic idle --seed 1 --threads 8 --output solvers/hybrid_master/benchmark/results/target530_cross_default_45s_s1.json
```

Timer-based optimization is not bit-reproducible even with a fixed seed.
One run cannot establish statistical improvement. Do not promote this binary
to the GUI default unless validation and comparison support it.

After ablation, the standalone cross runner defaults to `crossMoves=3`.
Explicit `crossMoves=0` remains the control. Target exchange scored
26/156/521 and stock-aware replacement scored 26/156/517; both were removed
instead of leaving inactive experimental code in the production solver.

## Chokudai evaluation

The existing `solvers/chokudai` implementation passed its native test suite
(18 replayed days). On this exact 32x32 snapshot:

- 3 s/day full match: 26/156/417, independently validated.
- 45 s day 1: seed 26/26/81, final 26/26/82 after 4,609 expansions and
  166,106 decoded candidates. The cross-route solver scored 84 on day 1.

Chokudai therefore demonstrates a real +1 repair over its own seed, but its
seed/search representation is currently weaker than the 525 solver. Do not
replace the current optimizer or reserve most of the deadline for this search.
A later targeted layered search is justified only around stock multiplicity
assignments, while reusing the stronger joint refueling decoder.
