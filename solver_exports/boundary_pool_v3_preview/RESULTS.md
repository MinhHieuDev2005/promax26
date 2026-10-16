# Boundary Pool: measured results and release gate

Date: 2026-10-02. This is an intermediate solver improvement, **not achievement
of 16/112/390 and not a universal replacement for ALNS**. Existing solvers,
movement/scoring code, and GUI role-selection code were not changed by this work.

## Reproducible scenario

- Input: `cases/user-input-25x25.json`, raw-file SHA256
  `b2848254d440fbd277f7e26982fffdb4957f187eb844bb7141bfe7e35540e544`.
- Four agents; roles `[1,0,0,0]`, first agent supplies and three patrol.
- Daily steps: `[126,110,130,63,97,66,131]`; fuel 233; 20 spots; 16 brands.
- Explicit idle-opponent traffic, with `players=39`. This is a benchmark
  scenario, not a claim about actual opponents. The local and server score
  rules are the same. Mirror-traffic results must not be mixed into this table.
- Serial runs, `HEXUDON_THREADS=1`; all saved plans independently replayed with
  the unchanged `bin/hexudon.exe trace`. Request budget 45000 ms unless noted.
- Full-match rows below all pass 16 global types and 112 daily types. Validity,
  per-day actions, input states, seeds, EXE hashes and timings are saved in JSON.

## Full seven-day experiments

Numbers are bowls. Standard deviation is population standard deviation.
Version rows have different builds: do not treat them as bit-identical A/B tests.

| Variant / artifact prefix | Seeds: scores | Mean | Median | Min / max | Stddev | Slowest day | Peak MiB |
|---|---|---:|---:|---|---:|---:|---:|
| Native ALNS, 8 s (`u25-alns8-profile`) | 1/2/3: 323,323,323 | 323.00 | 323 | 323/323 | 0 | 8.146 s | 17.4 |
| Free-endpoint pool, current-day only (`u25-boundary-v1-r0-s1`) | 1: 323 | 323 | 323 | 323/323 | 0 | see JSON | see JSON |
| Equal-bowl boundary alternatives (`u25-boundary-v2-profile`) | 1/2/3: 326,325,324 | 325.00 | 325 | 324/326 | 0.816 | 26.568 s | 143.2 |
| Stock-aware bounds (`u25-boundary-v3-profile`) | 1/2/3: 325,325,325 | 325.00 | 325 | 325/325 | 0 | 26.698 s | 142.7 |
| Modules-off wrapper control (`u25-same-exe-control`) | 1/2/3: 323,321,318 | 320.67 | 321 | 318/323 | 2.055 | 8.492 s | 16.8 |
| Eight rollouts (`u25-boundary-wide-verified-build`) | 1: 324 | 324 | 324 | 324/324 | 0 | 42.287 s | 141.9 |
| DP preview, pre-release (`u25-boundary-preview-final`) | 1/2/3: 326,326,325 | 325.67 | 326 | 325/326 | 0.471 | 31.241 s | 142.4 |
| **Packaged preview release** (`u25-preview-release-*`) | **1/2/3: 324,326,324** | **324.67** | **324** | **324/326** | **0.943** | **30.115 s** | **143.4** |

Native ALNS occasionally exceeded its requested 8 seconds slightly, but not
45 seconds. The new full-match runs in this table all satisfy 45 seconds/day.
The modules-off control uses the same executable as the eight-rollout row,
not the final preview executable. ALNS has wall-time stopping, so a seed does
not guarantee identical iteration counts or routes across machines or reruns.
Saved-plan replay, unlike time-based search, is reproducible.

### Final packaged binary

The release build includes additional coverage-order regression fixes after
the pre-release preview batch. Its EXE SHA256 is
`568e53a63e0c9d393212c8ac1b69e9508304a7b22f174cc567044dbafba844d5`.
Final-build results are tracked separately under `u25-preview-release-smoke`
(seed 1) and `u25-preview-release-confirm` (seeds 2/3). All three release runs
pass 16/112, action validity, replay and the 45 s/day limit. The earlier
326/326/325 batch is not attributed to this binary. Release mean is 324.67,
median 324, best 326: promising on this case, but not a guaranteed 326 result.

Release seed 2's verified action output is in
`solver_learning/runs/u25-preview-release-confirm-user-input-25x25-match-s2.json`
under `days[].plan`. This trace is an offline artifact, not embedded in the EXE.

## What actually improved

The baseline measured trajectory was:

`51 + 51 + 54 + 32 + 47 + 34 + 54 = 323`.

A verified 326 trajectory was:

`51 + 51 + 54 + 34 + 48 + 34 + 54 = 326`.

At the long day-3 / short day-4 boundary, keeping 54 bowls but moving a patrol
endpoint from cell 623/full fuel to 447/about 70 fuel allowed 34 bowls next
day instead of 32. Maximizing ending fuel alone discards this alternative.
This directly supports the user's short-day staging hypothesis. Other gains
also involve time-dependent ALNS choices; not every bowl is isolated causally.

The preview module ranks endpoint alternatives with a feasible no-refuel
next-day plan, then spends ALNS rollouts on a smaller shortlist. These are
lower estimates, never upper bounds. The incumbent and an exploratory
unscored slot are retained. Future roads are labelled `hold_observed_roads`;
cached next-day plans are validated against the actual next input before use.

## Failed or unproven alternatives

- Current-day-only pool tied 323. A day-5 gain of 48 versus 47 was rejected when
  the next-day estimate fell from 34 to 32: 80 is worse than 81 across the pair.
- Eight blind rollouts scored 324 and took up to 42.287 s. More width is not
  established as better than cheap preview ranking.
- Optional bounded tail Chokudai generated 1288 macros and expanded 13 states
  in the fixed day-3 test. The selected 54+34 forecast came from the DP route
  pool, not the tail search; its best tail alternatives did not establish a
  gain. It is disabled by default, not advertised as the source of 326.
- An unfinished wide run launched against a stale binary after a failed build
  is excluded. `.partial.json` files are never promoted as completed results.

Fixed-state artifacts start with `u25-boundary-preview-fixed3` and
`u25-boundary-chokudai-fixed3`. A two-day forecast is not a full-match score.

## Other-map regression: first day only

Same final preview EXE, modules off/on, seeds 1 and 2, role preset `first`
(one supplier, remaining cars patrol), 45 s/day. These are **not whole matches**.

| Case | Baseline C1/daily/bowls | Preview C1/daily/bowls | Outcome |
|---|---|---|---|
| 16x16, seeds 1/2 | 8/8/9; 8/8/9 | 8/8/9; 8/8/9 | two ties |
| 24x24, seeds 1/2 | 10/10/22; 10/10/22 | 10/10/21; 10/10/22 | one loss, one tie |
| 32x32, seeds 1/2 | 14/14/44; 14/14/44 | 14/14/44; 14/14/43 | one tie, one loss |

All actions valid, full day coverage, all requests under 45 s. In all six
preview runs, the ALNS incumbent was selected, not a replacement pool route.
The two one-bowl differences therefore occurred in time-dependent seed
generation, but this still **fails the broad non-regression promotion gate**.
Evidence: `solver_learning/runs/boundary-release-cross-crosscheck.json`.
Do not change the competition default based on the 25x25 measurements.

## Performance and correctness

- Target precomputation around 25--44 ms; subset DP around 0.14--1.97 s/day;
  stock-aware recombination around 0.08--10 ms in the profiled v3 batch.
  ALNS generation and next-day rollouts dominate wall time.
- Bounds cut long-day complete combinations from 531441 in the prototype to
  hundreds. They are safe only inside the fixed route pool. DP label truncation,
  endpoint buckets, route caps and wall-clock stopping are heuristic limits.
- Packed DP uses one time-first fuel label per `(mask,last)`, so it is not an
  exact general multi-resource shortest-path solver. About 100 MiB is needed
  at 20 targets; one car is processed at a time. Process peak is about 143 MiB.
- Eight C++ test groups pass, including 24 randomized stock/undo cases and the
  lexicographic regression requiring 2/2/6 to beat 1/1/8. Eleven Python tests
  pass, including JSON indexing, malformed input, stale hints and deadline
  fallback on a tiny fixture. The whole legacy suite is not claimed to pass.
- Diagnostics distinguish reachable DP-label expansions, scanned mask rows,
  transition attempts, and recombination leaves. Unavailable TT/VND counters
  remain null in benchmark metrics, not fabricated zeros.

## Scope and next bottleneck

Implemented: separate C++20 runner, legacy ALNS floor, important-node path
precompute, packed subset DP, coverage-diverse route pool, exact shared-stock
recombination with undo/bounds, optional bounded tail Chokudai, short-day
lookahead/preview, validator, multi-seed harness, persistent offline records,
and source/EXE export. No map-specific answer is embedded in the solver.

Not yet implemented/validated: general ten-neighborhood VND, Pareto RCSP path
labels, custom flat TT, path relinking, full ejection chains, CABS/BULB/LDS
ablations, automatic hyperparameter tuning, and whole-match cross-map promotion.
Automatic roles still use the legacy selector; GUI role selection is untouched.

The best measured result remains far below 390. The existing audit in
`solvers/horizon_portfolio/AUDIT_389.md` reports a relaxed bound of 339 for three
patrols on this exact file/evaluator, and smaller upper bounds for
the other fixed role counts. This is an unresolved contradiction with the
reported opponent 389, not a claim the user is wrong or permission to change
scoring. Resolving the configuration/rule discrepancy is necessary before
claiming a credible route to 390 on this case. Within the present model, the
next meaningful solver experiment is better joint staging/supplier repair at
short-day boundaries, with full-match controls and no coverage trade-off.
