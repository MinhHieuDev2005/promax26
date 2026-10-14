# Solver optimization results - round 2

Date: October 14, 2026. Baseline: `2fcec16`.
No commit, push, live-server submission or GUI binary replacement was performed.

## Decision

Keep the collected-brand history implementation **uncommitted for review**. Restore
baseline fuel reservation and annealing temperature. The history candidate improved
paired held-out results and repeated coverage tests, but this is not proof of optimality
or of improvement on every map or at a live 60-second competition deadline.

## Frozen experiments and conditions

- Adaptive fuel: multiply reserved fuel by 0.8 only when day steps exceed tank capacity.
- History: propagate acquired raw brand IDs through both local and LAN callers; prefer
  unseen brands during assignment/repair and add a bounded new-brand score coefficient.
- Temperature: scale initial SA temperature by sqrt(max(1, spots/8)), leaving final
  temperature, objective and budget unchanged.
- Nine fixture families: open8, mixed16, sparse16, tight16, dense16, large32, tight8,
  tight32 and coverage16. Fixtures are synthetic and have no ponds or opponent teams.
- Discovery: map seed 29, search seeds 1/2, two fixed lineups, 400 ms/day, one thread.
- Held-out: map seed 71, search seeds 3/4, same budgets and lineups.
- Auto: unseen map seed 113, search seed 5, automatic types, 1,000 ms/day,
  2,500 ms selection budget, eight threads. Nine matches per variant.
- Confirmation: tight32/coverage16 on seeds 71 and 197, search seed 6,
  both fixed lineups, 1,000 ms/day, eight threads. Eight matches per binary.
- Search receives 85% of the day allowance. CPU affinity is 0-7 in WSL; binaries
  use GCC 13.3.0 Release builds. Experiments run sequentially, not concurrently.

## Paired results

Each cell is wins / ties / losses against the baseline, comparing
(match brands, cumulative daily brands, bowls) lexicographically.

| Experiment | Discovery (36) | Held-out (36) | Auto (9) |
|---|---:|---:|---:|
| Adaptive fuel | 10 / 19 / 7 | 7 / 15 / 14 | 3 / 4 / 2 |
| Collected-brand history | 6 / 20 / 10 | 14 / 17 / 5 | 5 / 3 / 1 |
| Scaled SA temperature | 3 / 28 / 5 | 6 / 23 / 7 | 2 / 6 / 1 |

History confirmation: **7 / 1 / 0**. This was a targeted confirmation
on difficult coverage/fuel cases, not an unbiased extra random sample.
All recorded round-2 match plans were valid under the repository simulator.
The simulator is shared with the search; it is not an independent server oracle.

### Why fuel and temperature are not retained

Adaptive fuel loses primary brands on held-out tight32 (23 -> 21 for both search
seeds), despite some Daily improvements elsewhere. Its fixed-supply controls also
vary between runs, so small bowl differences cannot be attributed to this rule alone.
Scaled temperature does not show a consistent paired advantage on discovery/held-out.
Neither experiment is combined with history.

### What improved with brand history

- Held-out coverage16 with one supply: (13, 34, 34) -> (14, 29, 29), and
  (13, 33, 33) -> (16, 27, 27). More total brands wins even with fewer bowls.
- Held-out tight32 all-patrol: (23, 74, 76) -> (24, 74, 76) for both seeds.
- Auto coverage16 on map seed 113: (15, 42, 42) -> (16, 45, 45).
- Confirmation coverage16 on additional map seed 197, one supply:
  (12, 28, 28) -> (16, 27, 27).

History still loses some individual comparisons: discovery 10, held-out 5,
auto 1. Do not describe it as universally superior.

## Held-out metrics: baseline versus history

| Metric | Baseline | History |
|---|---:|---:|
| Component means (not a scalar score) | (13.056, 53.861, 113.056) | (13.278, 53.333, 113.222) |
| Median tuple | (12, 54, 70) | (12, 54, 70) |
| Best tuple | (24, 96, 219) | (24, 96, 223) |
| Worst tuple | (4, 16, 28) | (4, 16, 28) |
| P95 planning time (ms) | 374.954 | 410.858 |
| Peak RSS (KiB) | 19328 | 19456 |
| Valid matches | 36 | 36 |
| Local day deadline rate | 0.988 | 0.925 |
| Live HTTP deadline success | N/A | N/A |

Tuple statistics span different fixture sizes; they are descriptive and are not a
replacement for paired comparisons. Component averages are not an official scalar score.
Local deadline rates measure planner return time only, including missing days as failures.

All 40 day-planning calls in each auto batch returned within 1,000 ms. Selection exceeded
its separate 2,500 ms allowance in all nine baseline and all nine history runs: baseline
maximum 2,774 ms, history maximum 2,810 ms (rounded). Existing initialization/time-budget
overshoot is therefore still present; this experiment does not establish hard deadlines.
In the confirmation batch, all 32 daily calls per binary returned within 1,000 ms.

## Noise control

An unchanged baseline repeated on eight fixed-supply cases scored 3 / 1 / 4
against its earlier run. Search is wall-clock bounded; even identical seeds are not
bit-reproducible. Small bowl differences and timing changes are not enough to prove a
causal improvement. No statistical-significance claim is made. The stronger evidence
for history is recurring primary-brand gains across different maps and budgets.

## Retained code and checks

- `include/hexa_udon/solver.hpp`: history conversion declaration and per-day history.
- `src/core/problem.cpp`: map raw acquired brand IDs into solver-indexed history.
- `src/app/auto_client.cpp`, `src/app/lan_worker.cpp`: stop replacing actual progress with zeros.
- `src/optimizer/optimizer.cpp`: carry immutable history through workers and validate it
  before spawning threads; initialize day-zero history explicitly.
- `src/planner/day_planner.cpp`: prefer unseen brands in assignment/repair and evaluation.
  Fuel reservation is unchanged from baseline.
- `tests/unit/app_test.cpp`: noncontiguous IDs, complete/invalid history, score ordering,
  and a deterministic two-choice route that must select the unseen brand.

Full Release build and all five CTest executables passed in
`/home/hexa/solver-experiments/history-validation`; GUI and benchmark self-checks passed.
The GUI still uses `/home/hexa/build-release/hexa_udon`, which was not overwritten.

## Reproduction and remaining risks

See `tests/benchmark/README.md`. Local raw records, fixtures, stderr logs, paired reports,
three trial patches and `round2-manifest.json` are in `results/solver-optimization/`.
These artifacts are ignored by Git and remain on this machine. The manifest contains
baseline and patch hashes; each batch records binary/harness hashes and machine metadata.
The history patch includes regression tests added after the benchmark binary was built;
its algorithm did not change between discovery, held-out, auto and confirmation runs.

The remaining work before deployment is replay/live-server parity checks and a longer
realistic-budget benchmark. No HTTP latency, opponent traffic, submission-time tiebreak,
or GUI day-zero preplanning is modeled. No CPU hotspot profile or independent full-rule
simulator was added. A new commit still requires explicit user permission.
