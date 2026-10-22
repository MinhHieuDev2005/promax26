# Round 5: vehicle selection and waypoint planning

Date: 2026-10-14. Base: `219b5441a11e97b4a402cd2a27206fdac423df0c`.
Production A, GUI files, and `/home/hexa/build-release/hexa_udon` are not modified.
Experiments use independent source trees and executables under
`/home/hexa/solver-experiments/round5`. Raw evidence is in `results/solver-round5`.

## Diagnosis: two different failures, not just a bad lineup

The original `bridge-919-auto-23` result is reproducible at the level of its
principal failure, but **the original explanation in Round 4 is not accurate**:

1. C's selector can omit the entire waypoint phase at short per-day allowances.
   All-patrol routes then remain WAIT, because the underlying LNS has no
   intermediate-waypoint route representation. B's relocation runs *inside*
   `Day::toPlan`, so it is already present during construction and evaluation.
2. With sufficient daily time, C still loses on B's all-patrol lineup. Its
   optimistic union of individually reachable brands makes a third patrol seem
   redundant; the remaining-fuel tiebreak then prefers WAIT. Two other patrols
   cannot necessarily collect that optimistic union in a joint feasible match.

Thus selector calibration is genuinely broken in this case, but reusing B's
selector alone does not repair the route planner. This is not a map-specific fix.

### Historical candidate trace

These are the *original* saved Round 4 logs, not reconstructed estimates. Zero
means patrol, one means supply. Candidate order is identical in B and C.

| Lineup | Patrol / supply | B estimate | C estimate |
|---|---:|---|---|
| 010 | 2 / 1 | (8,16,33) | (5,8,18) |
| 100 | 2 / 1 | (8,15,33) | (5,7,19) |
| 001 | 2 / 1 | (9,16,32) | (7,8,20) |
| 000 | 3 / 0 | (10,18,41) | (0,0,0) |

B selects 000 and realizes (10,23,23); C selects 001 and realizes (9,16,16).
The third estimate component sums two scenarios' bowls, so it is **not** a
prediction of one realized match's bowl count.

Initial fixed-lineup replay, original binary hashes, seed 23, eight workers,
1,000 ms/day and 2,500 ms selection allowance:

| Frozen lineup | Planner B | Planner C |
|---|---|---|
| 000, selected by historical B | (10,23,23) | (9,14,15) |
| 001, selected by historical C | (9,16,16) | (9,16,16) |

This is already a controlled counterexample to "B selector + C planner fixes
the bridge regression." C on 000 also loses to C on 001 on secondary score.
These four replays do not establish which selector is best on other maps.

### Earliest decisions and missing brands

In the instrumented C selection, all-patrol's day allowance is 53.414 ms.
Day-zero `planDay` takes 58.240 ms before trace serialization; the completed
simulation takes 58.900 ms. The postprocessing guard has no time left, the
plan is `[[-12],[-12],[-12]]`, and all cars remain at [80,145,160]. The same
failure repeats across both traffic scenarios, producing estimate (0,0,0).
This is a missing search phase, not merely a changed final tie between lineups.

Under final C planning with 000, day zero moves the first two cars to 86 and
151 but leaves the third at 160. B moves that third car to 166 immediately.
C's logged WAIT and chosen keys for the third patrol are identical:
`5:5:5:5:10:10:83`. A later horizon predicts all ten brands even without moving
the third patrol. It also waits on day one, finally moving to 166 on day two.
C ends without brand 6 at cell 11; B collects it on day three. The first
observed route divergence is therefore day-zero WAIT, two days before the
late relocation. This is an observed counterfactual under the tested planners,
not a proof that every continuation after that WAIT must lose brand 6.

In historical auto-C's 001 lineup, both patrols and the supply car move to cell
117 on day zero, and both patrols refill to 32. **The supply car is not idle**,
contrary to the Round 4 prose. The match omits brand 1 at cell 251. B's 000
day-zero endpoints are [86,151,166], fuel [26,25,26]; no supply is needed for
that observed ten-brand continuation. Converging for refueling trades spatial
coverage for fuel. It is not evidence that supply vehicles are generally bad.

`bridge-trace.json` preserves original candidate scores, original match plans,
new candidate/day traces, all four feasible three-agent lineups, and replays.

The new instrumented fixed-lineup trials (seed 23) quantify the mismatch for
every candidate, rather than only the winners:

| Lineup | B actual | C actual | B/C fuel consumed | B/C fuel replenished | B/C missing brands |
|---|---|---|---|---|---|
| 010 | (10,16,16) | (9,16,16) | 60 / 73 | 6 / 16 | none / 1 |
| 100 | (10,17,17) | (9,16,16) | 69 / 70 | 45 / 13 | none / 1 |
| 001 | (9,16,16) | (9,16,16) | 61 / 72 | 0 / 15 | 3 / 1 |
| 000 | (10,23,23) | (9,14,15) | 85 / 69 | 0 / 0 | none / 6 |

These actual scores are independent replays, not outcomes inside the short
selector simulation. C never reaches ten brands on these tested lineups;
reranking those four C continuations cannot produce B's ten-brand result.

## Systematic answers to Phase 1 questions

1. **Lineup generation**: `kindCandidates` evaluates 1-supply masks ordered by
   sum of distances from supply start to spots, then 2..min(3, NA/2) supplies,
   and finally all-patrol. Tight fuel retains all combos, else 1 per count.
2. **Lineup score**: Min over two scenarios (smooth and forced-busy) for match
   brands, min for daily brands, sum of both scenarios for bowls.
3. **Match scope**: It simulates full multi-day matches with day-by-day states
   (positions, fuel, hits, 2-day traffic), not single days.
4. **Objective match**: The ranking tuple `(min_match, min_daily, sum_bowls)`
   serves as a robust surrogate; bowl sum does not equal official bowls.
5. **C's influence**: C alters `planDay` by reserving 20% budget for overnight
   waypoint search, changing daily routes during selection simulation.
6. **Stability**: Highly unstable at low allowances due to candidate starvation
   and logging delays; stable at 28.5s selection budget.
7. **Assumption consistency**: Inconsistent. Selection caps schedule cands at 8,
   uses static endpoints for tomorrow's lookahead, and does not carry yesterdayStatus.
8. **Lineup budget**: Adaptive wall-time slice `(remain / candsLeft) / 2` per
   scenario, split across D days.
9. **Bias on C**: C does not systematically favor supply or patrol in theory,
   but starvation at low allowances artificially zeroes out late candidates (patrol).
10. **Value vs realized score**: Severe mismatch on bridge fixtures. C's optimistic
   waypoint heuristic overestimates joint reachable coverage while planner C
   fails to achieve it.

## Systematic answers to Phase 2 factorial questions

- **Is C intrinsically worse on the problematic lineup?** Yes. On bridge-919
  with lineup `[0,0,0]`, B gets `(10,23,23)` while C gets `(9,14,15)`.
- **Is the selector choosing a worse lineup because of score changes?** At
  2.5s budget, C's selector suffered from phase starvation. But even when
  choosing `[0,0,0]` at 28.5s budget, planner C still regresses.
- **Would C perform better given B's lineup?** No. On bridge-919, C on B's
  lineup achieves `(9,14,15)` vs `(9,16,16)` on C's lineup.
- **Does vehicle selection explain most of auto regression?** No. The route
  planner itself has an intrinsic deficiency on bridge topologies.
- **Could B's selector be reused safely with C's planner?** No. BC still loses
  to B on bridge maps because planner C cannot convert the all-patrol lineup.

## Factorial results

Twelve development pairs: six map families, map 919, search seeds 23 and 29.
Lineups in this table are frozen from one B and one C selection per fixture
and seed, so the E1/E2 and E3/E4 interventions do not rerun selection.

| Experiment | Mean (match brands, daily brands, bowls) | W/T/L versus E1 | Primary losses versus E1 |
|---|---|---|---:|
| E1, B selector / B planner | (8.833,25.667,26.167) | - | - |
| E2, B selector / C planner | (8.667,24.167,24.833) | 0/10/2 | 2/12 |
| E3, C selector / B planner | (8.917,24.500,25.000) | 1/8/3 | 1/12 |
| E4, C selector / C planner | (8.750,24.417,24.917) | 1/8/3 | 3/12 |

At seed 23 the bridge lineups are B=000 and C=010, with E1/E2/E3/E4 scores
`(10,23,23) / (9,14,15) / (10,16,16) / (9,16,16)`.
At seed 29 C instead selects 100; E3 becomes (10,17,17), while the other three
scores are unchanged. The historical C=001 choice is not stable across runs.
The frozen replay deliberately honors each observed lineup rather than
pretending that a seed determines it uniquely.

Primary-mean decomposition on these observations:

```
E4 - E1 = (E2 - E1) + (E4 - E2)
 -0.083 =    -0.167  +    +0.083
           route effect  selector effect under C
```

C loses to B on both selectors' frozen bridge lineups. Replacing C's selector
with B's does not explain away most of the regression in this sample; the
selector contribution actually offsets part of the average route loss.
E2 versus E4 is 1/8/3 with one primary regression, not a safe dominance result.
Cluster bootstrap by fixture gives E2-E1 primary delta 95% interval [-0.5,0]
and E4-E1 [-0.583,0.417]. There are only six fixture families sharing a map
seed, not six independent random map draws. These descriptive intervals do
not account for all cross-family terrain correlation or execution noise and
cannot support a general superiority or safety claim.

Separate integrated pipeline runs give C versus B 2/7/3, BC versus B 1/9/2,
and BC versus C 1/7/4. They differ from the frozen experiment because selection
is timed and repeated; this difference is itself relevant deployment evidence,
not a reason to pool the experiments or cherry-pick a preferred comparison.

## Actual architecture and objective

- `kindCandidates`: enumerate one-supply masks, ordered by sum of patrol-mode
  distances from that supply's start to all stores. Enumerate 2 through
  `min(3, NA/2)` supplies as well. If maximum day steps are at least
  `1.5 * fuelLimit`, retain all multi-supply placements; otherwise retain one
  central placement per multi-supply count. All-patrol is last. With three cars
  there are exactly four candidates, with no two-supply candidate.
- `solveKind`: run **two full matches per candidate**, smooth and forced-busy.
  The latter raises every road to at least busy after day zero. For each
  candidate, allocate `max(1, remaining / candidatesLeft) / 2` to each scenario,
  then divide that allowance equally among days. This is adaptive wall time,
  not equal iterations, equal per-candidate time, or an exact rollout.
- Rank `(min(smooth brands, heavy brands), min(smooth daily, heavy daily),
  smooth bowls + heavy bowls)` lexicographically. Exact ties retain the first
  candidate. Supply count never overrides a better score. This robust scenario
  surrogate is not the official score of any one necessarily realizable match.
- `simulateMatch` carries positions, fuel, collected brands, and two-day stay
  history. Invalid plans fall back to all-WAIT. The new trace records that flag;
  final-match validity is still checked without silently replacing bad routes.
- C directly changes these simulations through `planDay`: it reserves 20% of
  each nonfinal day's allowance for a separate `chooseOvernight` call, which is
  skipped if the preceding solve has already exhausted the allowance.
- Construction, thread creation/joining, router setup, simulation, and logging
  are not hard-preempted. Candidate generation happens before `solveKind`'s
  internal timer. Overruns reduce later candidates' budget and can omit them.
  This creates an order-dependent disadvantage for all-patrol and, on six-car
  fuel-tight maps, potentially many late candidates.
- Selection truncates initial supply schedule candidates to eight. Final
  planning does not. Selection also does not update `yesterdayStatus`, whereas
  final planning does. Tomorrow's penalty uses a greedy assignment with static
  supply endpoints, not the actual next day's optimized rendezvous. These
  assumptions differ even before wall-clock noise is considered.
- Eight-worker `solveDay` copies the main RNG into worker-local RNGs with worker
  offsets; it does not advance the caller's RNG. A one-worker solve normally
  advances it. Equal seeds do not make timed annealing deterministic: iteration
  counts, temperature trajectories, and the available waypoint phase vary.
- `AutoClient` allocates half the type-selection window to `solveKind`, then
  uses remaining time for day-zero preplanning. The offline harness has no
  preplanned warm start, no HTTP traffic, and no interim submission arbitration.

### The C key in the request is not the implemented key

The actual analytic key is:

```
(potential union through tomorrow,
 brands today + independently reachable brands tomorrow,
 bowls today + independently reachable brands tomorrow,
 potential unions for each remaining horizon,
 total remaining patrol fuel)
```

Before ranking, C rejects candidates that decrease today's exact
`(collected union, daily brands, bowls)` relative to the incumbent. Only idle
patrols whose initial cell is not a store are considered; already-moving
routes are not rewritten. WAIT is explicitly retained. The returned daily
plan is simulator-validated, but the potential-union key is **not a feasibility
certificate**: each brand may be individually reachable while the set is not
jointly serviceable, and congestion, shared time, stocks and future supply
meetings are not jointly scheduled by that estimate.

It is therefore incorrect to diagnose this implementation as simply sorting
by "today's brands first." A conservative today-score guard does exist, but
the bridge failure happens with equal zero brands today. Reordering today's
reward cannot resolve the observed overoptimistic redundancy test.

## Experimental design and changes

`tests/benchmark/round5.py` builds copies, applies existing B/C patches, runs
fixtures sequentially on CPU affinity 0-7, and retains raw stdout/stderr,
fixture and binary hashes, budgets, plans, fuel flows, validity and peak RSS.
It resets the final-planning RNG independently of selector consumption.
Consumption is summed over patrol movement edges; replenishment is derived
from conservation, so refueling cannot masquerade as zero fuel consumption.

Two complementary experiments distinguish timing noise from interventions:

1. Integrated B/B, B/C, C/B, C/C binaries independently run selection and final
   planning. These test the actual complete pipelines, including selector
   nondeterminism. Repeated C selectors need not choose identical lineups.
2. Frozen factorial: select once with B and once with C, then replay both
   selected lineups with both planners using a common final seed. Identical
   lineup/planner pairs reuse the same replay. This controls lineup exactly;
   selection overhead is attached from the source selection run, not claimed
   to be a second integrated measurement.

Independent experimental variants:

| Name | Selector | Final planner | Isolated change |
|---|---|---|---|
| A | A | A | Frozen production/history baseline |
| B / E1 | B | B | Round 3 idle relocation |
| C / E4 | C | C | Round 4 waypoint phase |
| BC / E2 | B | C | Relocation gated to selection, C phase to final planning |
| CB / E3 | C | B | Reverse gates, diagnostic only |
| N | C, one worker | C, eight workers | Avoid eight-worker overhead in tiny selector calls |
| H | C | C, horizon-first | Prepend final-horizon potential only in final waypoint ranking |

N changes only `solveDay`'s selection worker policy, restoring the caller RNG
after each single-worker selection solve. This preserves common main seeds
across candidates/days as in the original eight-worker path. No route scoring,
scenario weights, lineup enumeration, or final route budget is changed.
The same wall-clock ceiling is used; N deliberately uses fewer selector CPU
workers, so it is not an equal CPU-consumption experiment. It is a minimal
evaluation-policy test motivated by measured phase-skipping, not Top-K or a
new lineup feature model.

The bridge pilot **rejects worker count as a sufficient explanation**: N also
estimates 000 as (0,0,0). Its all-patrol per-day allowance is 52.622 ms, while
day-zero planning takes 61.728 ms. It selects 001 and realizes (9,16,16).
Consequently N is an experimental, failed bridge repair, not an established
performance improvement. In particular, these measurements do not attribute
all overhead to thread startup; diagnostic output itself occurs inside the
timed phases and requires a separate transport control.

H changes only final waypoint priority. It tests a full-match-horizon-first
potential ordering without arbitrary weights. N and H are never combined.
Top-K and joint search are not justified merely by the bridge example: C
already loses when given B's lineup, and more selection work cannot make that
fixed-lineup route failure disappear.

## Reproduction

Run inside WSL HexaUdon, from the repository, with no other solver benchmark:

```sh
python3 tests/benchmark/round5.py check
python3 tests/benchmark/round5.py build --variants A B C BC CB
python3 tests/benchmark/round5.py campaign
```

Build directories must be new; suite execution can resume completed records
after interruption and verifies their fixture/binary hashes. The campaign
runs causal development, frozen factorial, N/H pilots, independent held-out
tests, an exactly bounded WAIT check, and full-window offline smoke tests.
Source-level patches are exported beside results. Build logs retain failures.
The small tracked `round5-bc.patch`, `round5-n.patch`, and `round5-h.patch` apply
**independently on top of Round 4 C**, not cumulatively. Their application was
checked against the saved uninstrumented C source. The builder separately adds
common tracing to all experimental source copies; production is never patched.

Development map 919 and seeds 23/29 are not held-out. New maps 1607/1907 with
independent search seeds 41/43 are held-out. They cover bridge, fork, fuel,
rendezvous, traffic, wait, six-car multi-supply interaction and high-fuel
patrol maps. The extra bridge map 2207/search seed 47 is a full-window smoke
test, not a statistically adequate deployment set. Named prior seeds
701/811/919/1201 are never relabeled unseen.

Main paired runs use eight workers, 1,000 ms/day (850 ms planner allocation),
2,500 ms selection. Full-window smoke uses 57,000 ms/day (48,450 ms planner
allocation after 85%) and 28,500 ms selection, matching the nominal 60-second
window less the client's three-second safety reserve. These remain **offline
simulator** tests, not live server deadline or integration validation.

## Benchmarking summary across all tested variants

Unseen held-out fixtures (16 matches: 8 families x 2 maps, search seeds 41/43):

| Variant | Mean Score | Median Score | P95 Day ms | P95 Wall ms | Deadline Misses | Valid |
|---|---|---|---:|---:|---:|---:|
| **A (Production)** | (7.75, 25.00, 29.88) | (7.0, 30.0, 43.0) | 879.37 | 7241.60 | 0 | 16/16 |
| **B (Round 3 Reloc)** | (8.31, 26.06, 30.50) | (9.5, 25.0, 27.0) | 874.83 | 7118.88 | 0 | 16/16 |
| **C (Round 4 Waypt)** | (7.88, 24.94, 28.56) | (7.5, 30.0, 43.0) | 870.84 | 6453.50 | 0 | 16/16 |
| **BC (B-sel + C-plan)** | (8.63, 26.56, 30.25) | (9.5, 25.0, 27.0) | 869.73 | 6482.85 | 0 | 16/16 |
| **N (1-worker sel)** | (8.19, 25.69, 29.69) | (9.5, 20.0, 20.0) | 868.49 | 6312.95 | 0 | 16/16 |
| **H (Horizon-first)** | (8.31, 26.00, 29.94) | (9.5, 20.0, 20.0) | 870.40 | 6433.06 | 0 | 16/16 |

### Paired Head-to-Head Outcomes on Held-out

- **B vs A**: 5 wins / 9 ties / 2 losses (Primary delta: +0.56, 0 regressions)
- **C vs B**: 2 wins / 8 ties / 6 losses (Primary delta: -0.44, 4 regressions)
- **BC vs B**: 5 wins / 9 ties / 2 losses (Primary delta: +0.31, 0 regressions)
- **BC vs C**: 7 wins / 9 ties / 0 losses (Primary delta: +0.75, 0 regressions)
- **N vs C**: 5 wins / 9 ties / 2 losses (Primary delta: +0.31, 1 regression)
- **H vs C**: 7 wins / 9 ties / 0 losses (Primary delta: +0.44, 0 regressions)

### Competition Budget (57s/day, 28.5s selection) on Bridge-2207

- **A**: Selected `[1, 0, 0]`, Score `(9, 15, 15)`
- **B**: Selected `[0, 0, 0]`, Score `(10, 21, 21)`
- **C**: Selected `[0, 0, 0]`, Score `(9, 14, 14)` (Primary regression!)
- **BC**: Selected `[0, 0, 0]`, Score `(9, 14, 14)` (Planner regression!)
- **N**: Selected `[0, 0, 0]`, Score `(9, 14, 14)`

## Recommendation: KEEP B (or CONTINUE RESEARCH)

- **Do NOT promote C**: C consistently regresses on bridge topologies under both
  tight and realistic competition budgets (10 vs 9 brands).
- **Do NOT deploy BC as a full fix**: While BC avoids regressions on the 16
  short-budget held-out fixtures, on the competition-scale bridge test it still
  scores (9, 14, 14) against B's (10, 21, 21). The underlying C waypoint
  planner remains brittle.
- **Deployment choice**: **KEEP B** as the top candidate if updating from A,
  or **CONTINUE RESEARCH** to fix the waypoint heuristic's joint reachability
  blind spot.

## Experiment log

- Read source and original candidate logs before designing changes.
- Original fixed-lineup bridge replay rejects the simple selector-only fix.
- Instrumented trace reveals selector phase-skipping and the all-patrol WAIT
  redundancy decision; original report's key and idle-supply explanation are
  corrected against actual source and plans.
- The first causal batch was interrupted when its WSL session ended, after 26
  completed records. Completed observations were retained; missing trials were
  resumed in a persistent hidden WSL process, without overlapping benchmarks.
- N tests selector execution policy only; H tests final waypoint priority only.
- No production promotion, commit, push, or server submission is performed.
