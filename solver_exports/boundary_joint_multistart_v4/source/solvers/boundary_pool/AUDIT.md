# Phase 1: architecture and bottleneck audit

The new attachment calls for staged implementation and measured promotion.
This continues the approved hybrid direction, rather than rewriting production.

## Reused architecture

- `src/main.cpp`: CLI entry (`plan`, `solve`, `trace`, `check`, `eval`).
- `include/hexudon/core.hpp`: config, day state, history, limits, score and plans.
- `src/core.cpp`: JSON parsers, hex adjacency, movement costs, simulation, scoring.
- `include/hexudon/internal.hpp`: candidate evaluation and reusable route engines.
- `src/lns.cpp`, `aco.cpp`, `local_search.cpp`, `simple_lns.cpp`, `lns_dp.cpp`,
  `bp.cpp`: existing independent generator/repair families.
- `solvers/chokudai*`: standalone search wrappers and route DP experiments.
- `gui.py`: process/HTTP orchestration, NOT the action evaluator.
- `qa.md`: reflection/action ordering, per-source movement cost, one bowl per
  patrol/spot/day, published daily horizons, fuel carried between days.

Coverage is a hard promotion gate on the target case; tuple comparison remains
lexicographic. Other supplied cases may have unreachable full coverage: valid
fallback actions are still returned and benchmark coverage failures are reported.

## Evidence, not assumptions

ALNS 8 s, roles [1,0,0,0], idle opponents, seed 1:
`51,51,54,32,47,34,54 = 323`, full replay verified.
First free-endpoint DP+pool prototype: same 323. Day 5 proposes 48 rather than
47, but a next-day rollout is 32 rather than 34, so the change is rejected.
This is not a demonstrated improvement, and the prototype is not promoted.

The DP scans 3,145,725 mask rows for three patrols, enumerates 531,441 route
combinations, yet consumes only about 0.2--1.5 s extra on most target days.
ALNS generation and repeated continuation calls dominate measured wall time.
These rows are NOT the number of expanded reachable search states.

Search weakness: ALNS tends to end long days with all patrols at the supplier.
The first pool experiment only accepted current-day score/fuel improvements,
so it could not test an equal-score, different-endpoint boundary solution.
Do not tune a larger beam until this restriction is removed and ablated.

## Phase-1 implementation

`benchmark.py` accepts raw/wrapped configs, multiple seeds, fixed-state ablations
and complete matches. It reuses the existing traffic adapter and unchanged
`bin/hexudon.exe trace`; it never duplicates movement/scoring rules. Every run
is replayed twice. It logs EXE/input hashes, plans, CPU, wall time, process peak
memory, available counters and per-map mean/median/min/max/stddev. Missing
instrumentation is null. Runs are serial to avoid CPU-budget interference.

## Next bounded experiment

At a long-to-short boundary only, retain full-coverage equal-bowl alternatives
with diverse endpoints, even if fuel is lower. Compare against an incumbent
rollout. This is heuristic continuation ranking, not safe dominance. Keep all
old engines, GUI role selection and official simulator unchanged.

## Correctness gate added before release

A new-prototype edge case was found during review: a bowl bound initialized
from an incomplete-coverage incumbent could reject a lower-bowl solution with
better primary/secondary score. The fixed pool now uses that bowl floor only
when the incumbent already satisfies coverage. Two-day selection also compares
global types and summed daily types before bowl sums. Regression fixture:
`1/1/8` must lose to `2/2/6`. This does not alter the legacy evaluator or solvers.

The eight C++ test groups cover source-cell movement cost, congestion, fuel,
one acquisition per patrol/spot/day, shared stock, tuple ordering, exhaustive
small-route checks, boundary macro feasibility, 24 randomized stock/undo cases,
and the coverage-before-bowls regression. Eleven Python checks cover benchmark
metadata/statistics and the GUI/JSON protocol, malformed input, invalid days,
stale planner hints and short-deadline fallback on a tiny fixture.
