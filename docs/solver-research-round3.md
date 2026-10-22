# Algorithm research, round 3 (2026-10-14)

## Baseline and scope

Baseline: `219b5441a11e97b4a402cd2a27206fdac423df0c`, including collected-brand
history. This is NOT a comparison against the older, history-blind solver.
Production source and `/home/hexa/build-release/hexa_udon` are left unchanged.
No commit or push is authorized by this experiment.

All experiments use GCC 13.3 Release in WSL HexaUdon, CPU affinity 0-7.
Batches and builds run sequentially, without simultaneous solver benchmarks.
Fixed patrol/supply lineups isolate route search from vehicle selection.
Discovery uses nine existing fixture families, map seed 307, search seeds 7/8;
held-out uses map seed 409, search seeds 9/10. The day allowance is 1,000 ms,
one worker, with the existing 85% planner allocation. No variant gets extra
iterations, threads or wall-clock budget.

These are synthetic, single-team matches, not live-server evidence. Score means
the lexicographic tuple (match brands, cumulative daily brands, bowls), not a
weighted scalar. All validity checks use the repository simulator, not an
independent implementation of the competition server. Full 60-second days,
opponents, HTTP deadlines and submission-time tie-breaking are not covered.

## What previous changes actually did

- Strict vehicle selection changed which complete lineup won; it was not a
  search-speed optimization.
- Brand history changed demand priority and the objective. It fixed actual
  information loss between match progress and daily planning.
- Fuel relaxation changed future resource allocation but lost primary brands
  in earlier held-out trials. Temperature scaling changed acceptance, without
  consistently improving final matches. Neither is reapplied here.
- This solver uses regret insertion plus LNS/SA, NOT beam search. Increasing
  beam width is not an applicable diagnosis.

## Score versus time, not iterations versus time

Same 18 match keys: nine families, map 307, search seed 7, two fixed lineups.
Each time budget has only one run; tiny differences are not significance claims.

| Day allowance | Mean tuple | Logged iterations | P95 day ms | On-time days |
|---|---|---:|---:|---:|
| 100 ms | (13.222, 52.667, 106.167) | 1,669,582 | 149.382 | 40/80 |
| 400 ms | (13.222, 53.000, 107.167) | 6,949,299 | 384.370 | 79/80 |
| 1,200 ms | (13.222, 53.167, 106.889) | 20,178,768 | 1,066.314 | 80/80 |

These are aggregate curve points, not interchangeable paired-budget scores.
The 100/400 ms runs expose initialization/budget overshoot and are NOT eligible
deployment results. Increasing allowance twelvefold leaves primary coverage
unchanged; the same tight16 all-patrol match remains at 10/12 brands.

Importantly, 17/18 matches already collect every brand in their fixture. Their
primary score cannot improve at all. The mean primary upper bound for this
suite is 13.333. This limits what an aggregate percentage can demonstrate; it
does NOT prove the remaining two brands are jointly attainable.

Existing operator logs count raw heuristic improvements, including moves that
never beat the incumbent. Logged iterations include no-ops; neither number
measures distinct states. No exact duplicate-state rate, CPU hotspot profile,
or statistical convergence certificate was obtained. The evidence supports
representation/neighborhood blind spots, not a claim that speed never matters.

## Model and structural constraints

The daily subproblem is a resource-constrained team orienteering problem with
brand prizes, shared store stocks and mobile refueling rendezvous. It is not
mandatory delivery: omitting a previously served brand can be correct. Across
days, positions, remaining fuel, accumulated brands and traffic history form a
sequential state. Days cannot be independently optimized without opportunity
costs. Supply schedules and patrol routing are coupled through time and fuel.

Exact facts used here:

- Match coverage is bounded by the number of distinct brands in the input.
- Holding the same route set after repair holds its represented brand set.
- Complete-route nodes are stores or refueling events. There is no general
  intermediate overnight waypoint in the baseline representation.
- More fuel and a superset of brands do not alone establish global dominance:
  positions, daily score, remaining steps and traffic must also be comparable.
  No unsafe dominance pruning is introduced.

### Blind spot 1: mandatory-brand repair

`Planner::improve` passes the current route-brand mask as `need`.
`Day::repair` rejects the whole candidate if any of those brands cannot be
reinserted, BEFORE `evaluate` runs. Consequently, changing SA temperature or
the match-brand coefficient cannot rescue such a rejected candidate.

Runnable counterexample: `tests/benchmark/brand_lock_check.cpp`. One patrol
can visit either the previously collected brand or the new brand, not both.
The simulator-backed heuristic scores are 1000.67 and 6004.67 respectively;
baseline repair rejects the superior replacement. Changing the required mask
to the replacement's brand allows it. This proves a missing transition, NOT
that the baseline's initial greedy constructor fails on that particular input.

### Blind spot 2: inability to travel across day boundaries

Runnable counterexample: `tests/benchmark/overnight_check.cpp`. On a plain 8x8
map, one patrol starts at cell 0 and the only store is at cell 7. Four days of
four steps allow seven plain-cell moves in total; plain moves cost two steps.
Fuel is sufficient. No single day can traverse the complete initial route.

Baseline stays at cell 0 for all four days and collects zero brands. The
relocation prototype ends successive days at cells 2, 4, 6, 7, collecting one
brand on the final day with 13 fuel remaining. Every plan is simulated and
checked. The baseline logs hundreds of thousands of iterations on this tiny
case without discovering the missing kind of action. Additional iterations
cannot introduce an intermediate waypoint that the representation omits.

The first test fixture mistakenly allowed only two steps/day, insufficient
even for the proposed four-day journey; that assertion failed. It was corrected
to four steps/day for BOTH binaries before the recorded passing checks. This
was a fixture error, not a successful run hidden by the benchmark.

## Ranked hypotheses and implementation

Ranks reflect structural impact/cost/confidence, not a measured universal order.

| Rank | Hypothesis and code area | Expected cost | Risk / falsification |
|---|---|---|---|
| 1 | Explicit overnight progression in `Day::toPlan` opens multi-day paths | Cached path query per idle patrol/store | Wrong target wastes future fuel; compare held-out full matches and exact stranded case |
| 2 | Atomic prize exchange in `Planner::perturb` crosses the mandatory-brand barrier | Repeated insertion while ejecting visits from one route | Less search elsewhere; compare fixed-budget full matches |
| 3 | Two-day prize-aware rollout replaces count-only `tomorrowMisses` | Several extra simulated days per shortlisted endpoint | Prediction error and deadline cost; ablate against endpoint-only policy; not implemented |
| 4 | Joint supply/patrol rendezvous optimization avoids repairing one side against a fixed other side | Small event scheduling DP/beam | Expensive synchronized feasibility; test fuel-tight supply cases; not implemented |
| 5 | Small-instance multi-day DP over day/position/fuel/brand mask supplies exact bounds and routes | Exponential brand mask, bounded small instances only | Does not scale to full fleet/traffic; compare tiny instances with brute force; not implemented |

Soft repair is a cheap ablation of hypothesis 2, not a separate breakthrough.

Implemented variants are independent patches against the frozen baseline:

- `soft-repair.patch`: failing to restore an old brand no longer rejects a
  candidate. Original insertion order and missing-brand cadence remain.
- `exchange.patch`: a tenth operator chooses an absent brand, prioritizing
  match-new brands. It ejects visits from one patrol, preferring already-known
  brands, until insertion succeeds. The resulting brand mask becomes the
  repair requirement for that move. Ordinary moves retain baseline behavior.
- `relocation.patch`: an empty-route patrol not already at a store can move
  toward an uncollected/unassigned brand and stop midway overnight. It keeps
  the original per-day fuel reservation, checks the complete target path fits
  current fuel, and never applies on the last day. Existing nonempty routes
  and all production protocol code are unchanged.

Relocation's nearest-target choice and one-target-per-brand assignment are
heuristics, not an exact assignment or a guaranteed improvement. In particular,
it does not yet reposition a patrol after a nonempty route or from a store.
Exchange changes the random stream; its win/loss count alone cannot separate
operator quality from wall-clock/randomness effects. No constants were tuned
against held-out seed 409.

## Measured results

W/T/L compares full-match lexicographic scores, not per-day heuristic scores.

| Algorithm | Implemented | Result | Decision |
|---|---|---|---|
| Soft repair | Yes, independent one-line ablation | Discovery 6/22/8; no primary gains | Reject |
| Atomic prize exchange | Yes, tenth neighborhood operator | Discovery 6/21/9; no primary gains | Reject for deployment |
| Idle-route overnight relocation | Yes, partial path across days | Discovery 8/21/7; held-out 10/21/5 | Retain experimental candidate, not universal dominance |
| Relocation after nonempty routes too | Yes, independent extension | Targeted pilot 2/1/5 versus history, 0/2/6 versus idle-only | Reject; preserve idle-only restriction |
| Tomorrow-infeasibility gate | Yes, fifth independent prototype | Nine-match pilot 3/5/1 versus history, 0/8/1 versus idle-only | Reject added complexity; no measured advantage over idle-only |

Why soft repair fails to establish an improvement: it removes the rejection but
keeps the same greedy restoration order; it does not deliberately create room
for a high-value absent brand. Exchange does create that transition, but on
this discovery suite primary coverage is already saturated in most cases.
Its extra search work does not solve the remaining overnight-positioning case.
These are explanations consistent with the code and data, not causal operator
ablations proving which individual overhead caused each loss.

The broader tail-relocation extension loses primary coverage on tight32:
(24, 75, 78) -> (21, 70, 76), in both search seeds. It also changes coverage16
from (16, 45, 45) to (16, 40, 42). Spending idle tail time/fuel from an already
productive endpoint is not automatically beneficial. Do not generalize the
stranded-vehicle counterexample into a rule that every vehicle should move.

The fifth prototype moves an idle patrol only toward a brand it could NOT
finish tomorrow from its current position under tomorrow's proportional fuel
allowance and current traffic. This tries to distinguish necessary bridging
from needless movement. It retains the tight16 improvements but also retains
the tight32 map-503 daily-brand regression. The nine paired patrol cases use
tight16/tight32/coverage16, maps 307/409/503, fresh search seed 13, one worker
and 1,000 ms/day; all three binaries are rerun. It does not justify a new
default or another layer of thresholds. This is not fresh-map held-out evidence
for the gate: the three maps informed its hypothesis.

### The consequential early decision

Discovery tight16, map 307, all patrols, both search seeds:

| Version | Final match tuple |
|---|---|
| History baseline | (10, 39, 53) |
| Idle relocation | (12, 41, 51) |

On day zero both versions get two daily brands and three bowls. In the baseline,
patrols 3/4 retain fuel 24/24; relocation spends three fuel each, ending at 21/21.
This positioning does NOT improve day-zero reward. By the final day, coverage
is 12 rather than 10; the lexicographic gain outweighs losing two total bowls.
The two added brands also close this fixture's primary upper-bound gap.

The same result repeats with **eight workers and 5,000 ms/day**, search seed 12:
map 307 is (10,39,53) -> (12,41,51); map 409 is (12,26,33) -> (12,31,33).
Both paired matches win, with 12/12 on-time days per binary. This is stronger
evidence than a tiny stochastic bowl gain: substantially more baseline search
still cannot produce the missing overnight action.

However, the additional eight-worker test on fresh map 503 is only **1/3/2**
over six matches. Tight32 all-patrol loses cumulative daily brands 78 -> 76.
All 28 days per binary meet their 1,000 ms limit. The prototype is therefore
not presented as universally better, nor silently substituted into the GUI.

### Held-out metrics (36 matches per binary)

| Metric | History baseline | Idle relocation | Delta |
|---|---:|---:|---:|
| Mean match brands | 13.1667 | 13.1667 | 0 |
| Mean cumulative daily brands | 52.3611 | 52.5556 | +0.1944 |
| Mean bowls | 112.5000 | 113.1389 | +0.6389 |
| Paired wins against the other version | 5/36 (13.9%) | 10/36 (27.8%) | +5 wins |
| Paired ties | 21/36 | 21/36 | 0 |
| P95 daily runtime, ms | 891.820 | 887.940 | -3.880 |
| Maximum RSS, KiB | 19,456 | 19,328 | -128 |
| Simulator-valid matches | 36/36 | 36/36 | 0 |
| Local daily deadline success | 160/160 | 160/160 | 0 |

Component means are descriptive, not an official aggregate score. Timing/RSS
differences this small are not a speed/memory improvement claim. No live HTTP
deadline success rate was measured. An unchanged baseline repeated on eight
discovery supply matches scores 2/4/2, confirming wall-clock noise remains.

The idle-relocation application builds in Release in its separate validation
directory and passes all five existing CTest executables. The benchmark harness
self-test and both counterexample checks also pass. None of this establishes
live-server parity or the full competition deadline.

### Final decision and remaining work

There are **329 complete simulator-valid matches across 18 batches**, including
the short-budget diagnostic curve. Do not confuse simulator validity with
deadline success: the curve has 41 late days. The other batches have no late
days. All source variants and failures remain reproducible; none is committed.

The strongest retained research candidate is **idle-only overnight relocation**.
It demonstrates a real representational advantage, confirmed at five seconds
and eight workers, but is NOT a proven across-the-board replacement for history.
The history baseline remains the production/GUI version. Reject soft repair,
exchange, broad tail relocation and the extra gate as new defaults. The rejected
variants were isolated from the outset, so rollback means not promoting them;
the known-good working source never needs to be reverted.

Next substantial algorithmic question: make overnight destinations explicit
search choices, retaining WAIT and the incumbent route as alternatives, and
evaluate a small two-day rollout including future daily-brand opportunity cost.
The negative tight32 result shows why nearest-uncollected-brand alone is not
enough. A small-instance multi-day DP could provide reference optima before
extending this to the full fleet. Avoid another arbitrary gate or map-name
classifier. A deployment decision still needs independent traffic/live replay,
vehicle-selection parity and realistic competition-budget tests.

## Reproduction and rollback

See `tests/benchmark/README.md` for the ordinary runner. Build a frozen checkout
of commit `219b544` outside the working tree using `git archive`; never reset
the user's working tree. Build each candidate from a separate copy and apply
only its patch from `tests/benchmark/variants/` using `git apply`.
The fifth patch is `bridge-only.patch`; do not stack the prototype patches.
On a Windows CRLF worktree use `git apply --check --ignore-space-change` first;
the native Windows `git diff --check` passes. WSL's different newline settings
reported existing CRLF files as whitespace changes, so that check was rerun
with native Git without changing any source line endings.

```sh
cmake -S tests/benchmark -B /tmp/round3-baseline \
  -DSOLVER_SOURCE_ROOT=/absolute/path/to/frozen-baseline -DCMAKE_BUILD_TYPE=Release
cmake --build /tmp/round3-baseline --target solver_bench brand_lock_check overnight_check --parallel 4
/tmp/round3-baseline/brand_lock_check
/tmp/round3-baseline/overnight_check 0
# Build the relocation copy similarly, then run its overnight_check with argument 1.
taskset -c 0-7 python3 -B tests/benchmark/run.py \
  --binary /tmp/round3-baseline/solver_bench --output /tmp/round3-baseline-results \
  --map-seeds 307 --seeds 7 8 --day-ms 1000 --threads 1
```

Repeat with each independent binary and a fresh output directory. For held-out,
use map seed 409 and search seeds 9/10, with otherwise identical arguments.
The existing runner rejects mismatched fixture/harness/budget pairings.
Raw fixture hashes, binary hashes, metadata, day records and operator logs live
under ignored `results/solver-optimization/round3-*`. Build trees are under
`/home/hexa/solver-experiments/round3-*`. Prototype patches and the two runnable
counterexamples are retained in the working tree for review.

There is no production rollback to perform: candidates never replace production
sources or the GUI binary. To abandon a prototype, simply continue using the
existing GUI binary; do not apply its patch to production.
