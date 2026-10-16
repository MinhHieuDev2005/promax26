# 530 target: measured work log

The target is full coverage and at least 530 collected udon on the provided
32x32 case. It is not yet achieved. Hieu remains a read-only source dependency.

## Machine

Windows 11 Home, version 10.0.26200; AMD Ryzen 7 8745H, 8 physical cores and
16 logical processors. GCC 15.2.0, CMake and Ninja. Available RAM fluctuates;
one measurement during the work was 4,256,653,312 bytes.

## Correctness before optimization

The former adapter mixed zero-based benchmark days with one-based GUI days.
The correction selects the indexing convention from the input field:
`day_info` is zero-based and `state` is one-based. This is essential when
consecutive days have identical step counts, where guessing from steps fails.
`test_day_protocol.py` checks all six days in both formats and replays all
twelve plans through `bin/hexudon.exe trace greedy`.

## Baseline

File: `../hybrid_master/benchmark/results/hieu_v2_corrected_baseline_45s.json`.
Requested budget 45,000 ms/day; eight solver workers (default half of the 16
logical processors); fixed roles `[0,0,0,0,1,0,0]`; traffic model `idle`.

| Metric | Corrected baseline |
|---|---:|
| Distinct types | 26 |
| Cumulative types | 156 |
| Total udon | 520 |
| Wall time (ms) | 249155.018 |
| Valid days | 6 |
| Illegal plans | 0 |

Daily collections: 84, 78, 81, 86, 93, 98. All plans were replayed again.
The prior measured 521 remains a historical result, not a guaranteed outcome.

## Experiments under evaluation

- Explicit RNG seed: old adapter ignored `randomSeed`; new experimental target
  mixes it into the solver RNG. A same-budget full-match experiment is running.
- Allow requests up to 55 seconds, retaining 8% headroom. This is a budget
  correction, not a demonstrated algorithmic speedup.
- Optional `preserveTraffic` restores yesterday's traffic from planner state.
  It is disabled by default pending A/B measurement.
- Optional `tailRepair` tests replacement patrol suffixes with unchanged supply
  routes. It accepts only simulator-valid strict score improvements. Its local
  score improvement does not prove a full-match improvement.

The benchmark now records snapshot/executable SHA-256, explicit roles and
search overrides. New runs also sample CPU time and peak process memory.
Logged iterations cover only workers that emit iteration logs, not the entire
parallel search. CPU sampling can miss the last 25 ms; report it as sampled.

## Seed-aware run, completed

`target530_seeded_45s_s1.json` recorded 26/156/522 with six valid days and zero
illegal plans. Total wall time: 249323.798 ms. Daily collections: 83, 78, 82,
88, 95, 96. This is one successful run, not proof of a statistically reliable
two-udon improvement. Source compilation and short protocol tests occurred
during this experiment, so strict performance comparison needs an isolated rerun.

The 530 goal and comparative MAX_TOTAL_UDON experiments remain unfinished.

## Suffix repair, rejected as a default

`target530_tail_45s_s1.json`: 26/156/518, six valid days, zero illegal plans,
249801.165 ms. Peak process RAM 117.15625 MiB; sampled CPU total 1867.953125 s;
973281 iterations logged by the reporting workers only. The experimental flag
remains off. Full-match score regressed despite strictly improving any suffix
replacement locally. Timing-dependent search variation also affects this single
run, so this is insufficient to establish the isolated causal effect.

## Next-day collection projection

`src/optimizer.cpp` is a local copy of the inspected Hieu optimizer with a Duc
extension. Hieu's checkout is unchanged. The extension constructs and simulates
a greedy next-day route, then adds a configurable fraction (`futureWeight`,
default 0.15) of projected next-day bowls to the search evaluation. The cache
holds at most 2048 endpoint/fuel keys per planner. The bound-based shortcut for
updating the incumbent was adjusted because adding a positive future reward
invalidates the original assumption that total fitness is at most raw fitness.
Full-match benchmark is in progress; this candidate is not promoted to GUI.
