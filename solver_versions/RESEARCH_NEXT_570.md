# Research toward 24/240/570 — 2026-10-14

This audit inspects the current local source and saved benchmark reports. It does not claim a new benchmark result or change the production binary.

## Evidence and feasibility

Validated run: `reports/32japan-isolated-target-55s-s1.json`, seed 1, eight threads, idle traffic, roles `0,0,0,0,1,0,0`, requested budget 55,000 ms/day, `crossMoves=7`, `endSpotWeight=0`.

Daily bowls: `41,49,55,59,57,58,57,59,57,58`, final `24/240/550`.

The map contains 61 bowls/day. The first three days collected 145. Keeping that prefix, the stock-only ceiling is 572, and reaching 570 requires 425 of 427 available bowls in the remaining seven days. This is a conditional stock bound, not proof that those routes are feasible. Improving the first three days is therefore valuable, alongside optimizing the repeated tail.

The observed runtime is 506,385.97 ms across ten solver calls, approximately 50.6 seconds/day. `offline_runner.cpp` passes `time_ms * 0.92` to `planDay`. Additional search budget must preserve time for validation, serialization and submission.

## Confirmed configuration discrepancy

The 550 benchmark explicitly sets `endSpotWeight=0`. The GUI payload does not set this field; the EXE defaults to -1 (adaptive). In `Day::evaluate`, adaptive scoring gives end-spot bonuses before the flat tail. Consequently the GUI-default binary is not proven to reproduce the benchmark configuration. Changing `crossMoves` alone did not align the complete configuration.

## Search weaknesses observed in source

1. Targeted restart ranks all patrols by distance, including patrols that already visit the target or start on it. Replacing those routes with `{target}` need not add a distinct collecting patrol. Measure new target visitors after repair before attributing improvement to this mutation.
2. The target is chosen using route reservation counts, not actual replay collections. Reservations are useful for construction but can differ from the actual collection footprint. Instrument both quantities before changing the heuristic.
3. `repair()` may prune the forced target, then greedily fill the remaining space. Thus a nominal target-directed restart does not guarantee that its target survives.
4. Restarts retain the global annealing temperature schedule. Late large changes face a cold acceptance threshold. Reheating only restart windows is a testable hypothesis, not a demonstrated improvement.
5. Eight workers explore separately and only share emitted output; there is no explicit exchange of route incumbents. More workers may reduce per-worker search depth. The existing three-seed short runs do not establish a universal 8-versus-16-thread optimum at 55 seconds.
6. Full-match multi-day search is expensive under an online per-day deadline. A cheap terminal-state estimate must first predict next-day outcomes better than existing heuristics before adding a beam across days.

## Existing feature worth testing first

`tail_repair.hpp` already implements suffix replacement with full-plan simulation and lexicographic daily acceptance. It is disabled by default through `search.tailRepair=false`. It receives 3% of the requested budget when enabled. Test it before introducing another mutation. A daily improvement may still hurt future days through the changed terminal position, so full-match comparison remains necessary.

## Prioritized experiments

1. Align and record the exact EXE/GUI/benchmark settings; retain binary hashes and source snapshots for every promoted candidate.
2. Enable existing tail repair in an explicit experiment, compare equal total deadlines, and record both daily gains and final match score.
3. Improve targeted restart selection to favor additional target visitors; log target survival after repair and actual bowl gain.
4. Test restart reheating only if instrumentation shows valid large mutations are consistently rejected.
5. Evaluate next-day terminal-state alternatives on fixed starting states before investing in multi-day beam search.

Use paired seeds and sequential runs to avoid CPU contention. A single +2 full run is a best observed result, not a demonstrated increase in expected score. Promote only with full criteria 1–2, valid replay, recorded settings and reproducible artifacts. Keep the existing 550 EXE throughout experiments.
