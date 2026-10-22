# Round 6: Joint Assignment and Two-Patrol Search

Date: 2026-10-15. Research artifacts only; no production deployment or commit.

Follow-up: `docs/solver-research-round6-audit.md` audits these frozen results,
corrects the record count to 326, and documents a new bounded joint action
search, exact current-day-sacrifice witness, and independent benchmarks.
The tables below remain the original frozen experiments, not the follow-up.

## A. Verified Cause

### Diagnostic reproduction

`results/solver-round6/bridge-919/` contains new, instrumented fixed-000
matches: seed 23, eight workers, 1,000 ms/day. Scores are actual complete-match
lexicographic `(distinct match brands, sum of daily brands, bowls)` tuples.

| Variant | Score | Day-zero endpoints | Day-zero remaining fuel |
|---|---|---|---|
| B | (10,23,23) | 86,151,166 | 26,25,26 |
| C | (9,14,15) | 86,151,160 | 26,25,32 |
| M: C + joint assignment witness | (10,22,23) | 86,197,166 | 26,24,26 |

Initial positions are 80,145,160, each with 32 fuel and 12 daily steps.
There are no supply vehicles in these fixed-lineup trials. All three plans
collect zero brands on day zero. The first B/C divergence is third-patrol
movement on day zero, not a later refueling decision. C stays at 160 for two
days, then reaches 166 on day two. It never collects brand 6 at cell 11; B and
M do collect it on day three. This is an observed continuation difference,
not a proof that every continuation after C's initial WAIT must fail.

C's real key is optimistic tomorrow union, today-plus-tomorrow daily brands,
today-plus-tomorrow bowls, optimistic horizon unions, then remaining fuel.
It is **not** a today-first objective; today's score is a separate rejection
guard. For the third patrol, C's WAIT and chosen key are both
`5:5:5:5:10:10:83`. Independent union reachability credits opportunities
without assigning the limited patrol routes required to realize them.

M's third-patrol WAIT key starts `(3,3,3)` and its cell-166 candidate starts
`(4,4,4)`: these are simulator-realized conditional next-day union, daily
brands, and bowls. Incidental store visits explain how three target assignments
can collect four brands. M also changes the second patrol's endpoint, so this
is evidence for a team-level decision, not an isolated third-patrol ablation.
All candidate matching assignments, plans, hits, endpoints and fuel are in
`M.log`; `waypoint-choice` records the accepted endpoint and old/new keys.

A separately compiled trace-only C copy, CT, also reproduces (9,14,15).
`CT.log` records **every** evaluated candidate, not just the selected one.
With the first two endpoints fixed at 86,151, these third-patrol alternatives
all have exactly the same first six opportunity components:

| Endpoint | Remaining patrol fuel | Opportunity prefix | Team-fuel tie breaker |
|---|---:|---|---:|
| 160, WAIT | 32 | 5,5,5,5,10,10 | 83 |
| 163, half prefix | 29 | 5,5,5,5,10,10 | 80 |
| 166, full prefix | 26 | 5,5,5,5,10,10 | 77 |
| 228, other prefix | 24 | 5,5,5,5,10,10 | 75 |

Thus cell 166 **is generated**; C rejects it on evaluation/tie breaking,
not because it cannot express that particular idle-patrol move. At endpoint
86,151,160 M's explicit assignments are brands 2,1,none and realize two brands.
At 86,197,160 assignments 4,2,none realize three including incidental brand 8.
At 86,197,166 assignments 4,2,5 realize four. Actual M day-one hits are exactly
2,4,5,8 in this diagnostic. CT is instrumentation only and is excluded from
performance comparisons.

### Selector starvation is also an instrumentation effect

New C auto-selection replays use identical map, seed, budgets and workers:

| stderr transport | All-patrol estimate | Selected lineup | Actual score |
|---|---|---|---|
| Pipe | (9,14,29) | 000 | (9,14,15) |
| Windows-mounted file | (0,0,0) | 010 | (9,16,16) |

The file replay logs an all-patrol simulated-day allowance of 63.38 ms,
planning elapsed 80.80 ms, and all-WAIT plans. Unbuffered chained `cerr`
writes consume the reserve before `chooseOvernight` can run. B relocation
lives inside `Day::toPlan`; C's postprocessing can be skipped entirely.
Main comparisons capture stderr through a pipe, as the GUI does. The file
trial is a diagnostic, **not** evidence that the same starvation frequency
occurs in normal GUI operation. Selector timing and daily planning timing
are reported separately.

Earlier reports' mixed-component "median tuples", broad "no deadline misses",
and N-eliminates-starvation claims are not reused. Selection overshoot must
be counted independently. Round 5's H advantage was selector-confounded:
the saved frozen-lineup experiment tied C in 12/12 cases.

## B. Mathematical Model and Its Boundary

The full problem maximizes `(abs(union of all daily hits), sum of daily hit
counts, sum of bowls)` over joint action sequences and vehicle types.
Persistent state includes each vehicle's position, kind and fuel, collected
brands, remaining day lengths, and traffic history. Each day's joint
transition must obey movement time, fuel expenditure, shared store stocks,
agent-index acquisition order, and supply rendezvous/refueling. Stocks reset
each day in the repository simulator. Future traffic depends on joint stays;
it is not generally fixed.

For the restricted matching graph, binary `x[patrol,brand]` satisfies
`sum_brand x <= 1`, `sum_patrol x <= 1`, and `x = 0` on infeasible edges.
These assignment constraints are necessary but not a substitute for the
joint temporal stock/fuel transition. The objective used to accept a
waypoint is evaluated after that transition, not from `sum x` alone.

M uses a deliberately restricted, conditional next-day witness:

1. For each patrol/brand pair, inspect the native minimum-time and minimum-fuel
   paths to all positive-stock stores. Retain one minimum-time feasible path
   with duration at most the next day's steps and fuel at most current fuel.
2. Find a bipartite matching, at most one target per patrol and one patrol per
   target brand. Augment uncollected brands first, then already collected
   brands; within each group process low-degree brands first.
3. Construct all patrol routes together; unmatched patrols and supplies WAIT.
4. Run the native joint simulator. Use **realized** union, daily brands and
   bowls, including incidental acquisitions, not the matching cardinality.

The graph matching avoids duplicate target ownership. It does not make
independent feasibility equal joint feasibility: shared stock and incidental
visits are checked by joint simulation. Supplies are present in the simulation
but there is no new supply scheduling or optimistic future replenishment.
Possible refueling routes that need more than initial fuel can be missed.

This is not an exact team-orienteering solver. It allows only one explicit
target per patrol, retains one path per edge, uses **current frozen traffic**,
and optimizes matching cardinality rather than realized incidental reward.
The simulator witness is feasible only conditional on those traffic and
supply assumptions. Later-day independent profiles remain as tie breakers.
The leading secondary components measure tomorrow alone, not the full
remaining match; today's exact-score guard prevents a local decrease but
does not turn this ranking into an exact two-day objective.
The witness can use all remaining fuel next day, whereas the actual planner
reserves fuel across later days. Nor is the witness handed to tomorrow's
planner as a committed/warm-started assignment. A feasible witness is not a
promise that the next invocation will execute that continuation.

## C. Algorithms and Ablations

| Name | Frozen parent | Change |
|---|---|---|
| A | Round 5 A snapshot | Unmodified production algorithm, benchmark instrumentation |
| B | Round 5 B snapshot | Round 3 idle relocation |
| C | Round 5 C snapshot | Independent overnight opportunity profile |
| BC | Round 5 BC snapshot | B relocation in selection; C final planning |
| M | C | Prepend simulator-checked joint matching key |
| J1 | B | One cross-patrol route-suffix exchange neighborhood |
| J2 | C | M plus exactly the same J1 neighborhood |
| MS, follow-up | C | M with store-start eligibility restored for stationary patrols |

J2 is an exploratory combination control, **not** a declared successful or
deployment-ready successor. It is not a separate pairwise waypoint optimizer.

M retains C's bounded candidate generation: incumbent/WAIT, half/full feasible
prefixes toward uncollected stores, two native path modes, deduplication, and
a four-candidate shortlist. Sequential coordinate descent evaluates every
candidate using the **whole team**, rather than a sum of independent patrol
scores. It does not enumerate a Cartesian product. The existing total day
budget and 80% non-final-day inner-solver allocation remain unchanged.

After M recovered the bridge diagnostic, J1 was implemented as one coordinated
LNS move. Choose two nonempty patrol routes and one cut in each; exchange both
suffixes atomically. Keep both prefixes and the supply schedule. Existing
whole-team `Day::repair` handles feasibility, pruning and reinsertion of
required brands; `Day::evaluate` evaluates the complete resulting plan.
Neither individual suffix transfer must improve independently. Identical
suffixes and empty-route pairs are rejected. No new weights, map-specific
branches, increased budgets or extra threads are used.

This is a real two-route proposal, but it does **not** repair the absence of
intermediate waypoint nodes inside LNS. Existing code already has multi-route
removal/near operators and a two-route restart; it would be inaccurate to call
the old LNS strictly single-route. J1 changes assignment topology, not the
underlying multi-day state representation. Pair choice is random among
nonempty routes, not a learned or conflict-targeted choice.

Diagnostics log operator selections, generated proposals, valid repaired
evaluations, best-surrogate improvements and elapsed operator time. Only the
verbose worker's counters are visible, not summed CPU work from all workers.
An operator selection immediately overridden by the existing stagnation
restart is counted as an attempt but not a generated joint proposal.
`zero_improvement_calls_ms` measures time in calls with no joint best update;
it is a lower bound on all unsuccessful-proposal time. These are surrogate
updates, **not** official match-score improvements; paired full matches are
the latter test.

## D. Isolation, Patches and Reproduction

Production source, GUI and `/home/hexa/build-release/hexa_udon` are untouched.
Production SHA256:
`d864d3fd2f325773cbcd594dc93063b63882ca07fa5947365944fa0e8ec7b903`.
Base HEAD: `219b5441a11e97b4a402cd2a27206fdac423df0c`.
Pre-existing benchmark edits and Round 3-5 files are preserved.

New source files:

- `tests/benchmark/round6_joint.hpp`: matching and joint simulation witness.
- `tests/benchmark/round6.py`: isolated builds, reproducible fixtures and trials.
- `tests/benchmark/round6_exact.cpp`: bounded exact two-patrol dynamic program.
- `tests/benchmark/round6_check.cpp`: stock, distinct assignment, fuel and
  conservative supply checks, independent of `NDEBUG`.
- `tests/benchmark/round6_analyze.py`: strict complete-trial validation,
  lexicographic pairing, timing/selection accounting and loss traces.

Experimental trees are `/home/hexa/solver-experiments/round6/{M,J1,J2}`.
`results/solver-round6/{M,J1,J2}-optimizer.patch` records each optimizer delta
relative to the parent listed above. M/J2 also require `round6_joint.hpp`.
The exact/check CMake targets are added only to M's isolated tree, not to the
user's modified benchmark CMake file. Build logs and each trial's full command,
binary hash, fixture hash, effective budgets, validity, RSS and plans are saved.

Run under WSL HexaUdon from the repository (the build command intentionally
refuses to overwrite an existing experimental source tree):

```sh
python3 tests/benchmark/round6.py build --variants M J1 J2
python3 tests/benchmark/round6.py reproduce --variants B C M
python3 tests/benchmark/round6.py exact --variants B C M J1 J2
python3 tests/benchmark/round6.py suite --name dev-fixed --variants A B BC M J1 J2
python3 tests/benchmark/round6.py suite --name held-fixed --variants A B BC M J1 J2
python3 tests/benchmark/round6.py suite --name held-auto --lineup auto --variants B BC J1 J2
python3 tests/benchmark/round6.py suite --name competition-diagnostic --lineup auto --day-ms 57000 --selection-ms 28500 --variants B C BC J2
python3 tests/benchmark/round6.py suite --name competition-held --lineup auto --day-ms 57000 --selection-ms 28500 --variants B BC J1 J2
python3 tests/benchmark/round6_analyze.py
```

Prior Round 5 source snapshots must exist for these incremental builds.
All build and solver batches run sequentially, affinity CPUs 0-7, eight
solver workers, Release mode. Never compare trials run concurrently.
Timed stochastic search is not bitwise reproducible from RNG seed alone.
Final-planning RNG is reset independently of selector work by the inherited
benchmark harness. These are single-team simulator tests, not server matches.

## E. Exact Joint Reference

The new oracle enumerates both labeled patrols' full move/WAIT plans together
and calls the native simulator, not two independent single-agent DPs.
Day-boundary state is `(position0,fuel0,position1,fuel1,collectedMask)`.
For identical state retain the lexicographically best accumulated
`(dailyBrands,bowls)`; future transitions are identical, so this dominance
rule is sound. The final objective includes popcount of the collected mask.
Predecessors preserve a simulator-replayable optimal joint witness.

Scope: plain-only maps, two patrols, at most four stores/brands, 64 cells,
three days, four fuel and four steps/day. Tested fixtures use two steps/day
and at most three fuel. Plain movement costs two steps and one fuel; repeated
one-step WAITs cover all longer waits. With no roads there is no missing
persistent traffic state. Stock is shared and reset per day. Supply vehicles,
roads, opponents and larger instances are outside this exactness claim.

| Case | Exact | B / J1 | C / M / J2 |
|---|---|---|---|
| stock | (1,3,3) | (1,3,3) | (1,3,3) |
| distinct | (2,2,2) | (2,2,2) | (2,2,2) |
| progression | (2,3,3) | (2,3,3) | (2,3,3) |
| fuel | (0,0,0) | (0,0,0) | (0,0,0) |
| competing-7301 | (4,8,8) | (3,8,8) | (3,8,8) |
| competing-7302 | (4,8,8) | (3,8,8) | (3,8,8) |
| competing-7303 | (4,6,6) | (3,5,5) | (3,5,5) |
| competing-7304 | (4,8,8) | (4,8,8) | (3,6,6) |

All 40 heuristic trials are valid and no score exceeds the exact optimum.
Known-answer assertions cover stock, distinct targets and unreachable fuel.
Optimal witnesses and state/transition counts are in `results/solver-round6/exact/`.

The gaps identify more than an imperfect matching score:

- **7301:** identical day-zero endpoints 9,16. On day one the optimum moves
  9->1 while the other patrol moves 16->24; the heuristic stays at 9.
  The first patrol still collects its starting-store brand before departing.
  Day two 1->2 recovers brand 3. There is no supply or traffic explanation.
  C/M/J2 refuse overnight candidates for a patrol starting at a store;
  B likewise excludes starting-store relocation. LNS cannot represent the
  intermediate non-store endpoint. Today's score need not be sacrificed.
- **7302:** the same representation gap: optimum moves 9->16 on day one,
  then 16->25 on day two. Every heuristic keeps the second patrol at 9.
- **7303:** day zero agrees at 1,9. On day one the optimum sends patrol 0
  to brand 2 at cell 2, while every heuristic sends it to brand 0 at cell 10.
  The other patrol can collect brand 0 on day two from cell 17. The local
  assignment therefore misses brand 3 at cell 3. This is a continuation/
  assignment evaluation failure, not an impossible brand or selector error.
- **7304:** B/J1 equal the oracle. C/M/J2 first send patrol 0 to cell 9 and
  leave patrol 1 at 8, instead of endpoints 1,9. Subsequent single-coordinate
  idle-only proposals cannot undo the moving first patrol's assignment.
  A jointly feasible better sequence exists; adding matching alone does not
  expose the missing joint action transition.

These are constructive counterexamples to a universal coordination fix.
They do not establish optimality, or its absence, on competition-size maps.


### Follow-up exact oracle results (MS and fresh suite)

Restoring candidate waypoint evaluation for patrols currently starting at a
store (MS) resolves the representation gap on `competing-7301` (4,8,8) and
`competing-7302` (4,8,8), matching the exact optimum. On a fresh set of four
competing cases (`competing-8301` through `8304`), MS matches the optimum in
all four cases, notably recovering `competing-8303` (4,6,6) where B and M
both stall at (2,6,6).

However, `competing-7303` remains missed by all heuristics (3,5,5 vs 4,6,6
exact), and `competing-7304` remains missed by M/MS/J2 (3,6,6 vs 4,8,8 exact,
which B and J1 achieve). Thus, waypoint eligibility at stores is a valuable
isolated repair, but does not eliminate all multi-day assignment coordination gaps.

## F. Benchmarks

### Protocol and complete-match results

Eight families: bridge, fork, fuel, rendezvous, traffic, wait, six-agent multi,
and high-fuel patrol. Development uses map seeds 4100..4107; held-out uses
5100..5107 and 6100..6107, with independent map randomness and search seeds
71..78. No algorithm tuning occurs between these fixed and auto held-out runs.
Old bridge seeds 919 and 2207 remain diagnostic, never counted as unseen.
The competition held-out map is bridge-7101, search seed 89. Fixed lineups
are all patrols, including `000000` on the six-agent maps.

Development, eight complete matches per variant, 1,000 ms/day:

| Variant | Mean primary | Mean daily | Mean bowls | W/T/L vs B | Primary losses vs B |
|---|---:|---:|---:|---|---:|
| A | 3.875 | 12.000 | 12.125 | 0/3/5 | 5 |
| B | 7.000 | 21.500 | 22.250 | 0/8/0 | 0 |
| BC | 7.125 | 20.375 | 21.125 | 2/4/2 | 1 |
| M | 7.125 | 20.750 | 22.125 | 2/4/2 | 1 |
| J1 | 7.000 | 21.500 | 22.250 | 0/8/0 | 0 |
| J2 | 7.125 | 20.750 | 22.125 | 2/4/2 | 1 |

Held-out fixed lineups, 16 complete matches per variant:

| Variant | Mean primary | Mean daily | Mean bowls | W/T/L vs B | Primary losses vs B |
|---|---:|---:|---:|---|---:|
| A | 4.0000 | 11.4375 | 12.6875 | 0/4/12 | 9 |
| B | 6.9375 | 19.7500 | 22.0000 | 0/16/0 | 0 |
| BC | 7.4375 | 21.2500 | 22.0625 | 5/4/7 | 4 |
| M | 7.1250 | 20.8125 | 22.9375 | 5/4/7 | 4 |
| J1 | 7.1875 | 20.3125 | 22.5000 | 1/15/0 | 0 |
| J2 | 7.1250 | 20.8125 | 22.9375 | 5/4/7 | 4 |

J1's only fixed-lineup primary improvement is fork-5101, 5->9 brands.
Its paired primary mean change is +0.25, with exploratory map-resampled
95% bootstrap interval [0,0.75]. M/J2's change is +0.1875 with interval
[-0.75,1.0625]. The mean hides four primary regressions, including 8->4.
M and J2 tie on **all 24 development/held-out fixed-match tuples**: the extra
joint suffix operator adds no observed benefit to the matching variant here.

Held-out automatic selection, 16 complete matches per variant, separate
2,500 ms selection allowance:

| Variant | Mean primary | Mean daily | Mean bowls | W/T/L vs B | Primary losses vs B |
|---|---:|---:|---:|---|---:|
| B | 8.6250 | 28.5625 | 32.5625 | 0/16/0 | 0 |
| BC | 8.4375 | 28.0000 | 32.0000 | 2/8/6 | 3 |
| J1 | 8.8750 | 29.0625 | 34.8125 | 3/13/0 | 0 |
| J2 | 8.7500 | 29.3125 | 35.7500 | 5/7/4 | 2 |

These auto outcomes are end-to-end measurements, not pure route-search
ablations: selected supplies differ on several maps. For example J1's
six-agent bowl gains occur with different supply lineups. The fixed-lineup
comparison is the relevant isolation of the operator.

Full primary histograms, scalar distributions, all baseline/parent pairings,
bootstrap calculations and resource metrics are in
`results/solver-round6/summary.json`. These columns are separate scalar
means, **not** invented "average/median score tuples". The bootstrap describes
this small synthetic sample, not a guaranteed competition win rate; no
single-map competition or repeated-map confirmation confidence interval is
reported.

### Competition-scale replay

Allowance: **57,000 ms/day**, with the existing **48,450 ms planner allocation**;
selection has its own **28,500 ms** allowance. All eight recorded matches
select 000. The C-family's existing 80% inner allocation usually returns
non-final days around 38,762 ms after cheap postprocessing; B/J1 use nearly
48,451 ms. Unused time is not reassigned or converted into extra search.

| Map | Variant | Actual tuple | Selection ms | Match wall seconds |
|---|---|---|---:|---:|
| diagnostic bridge-2207 | B | (10,21,21) | 28505.23 | 222.33 |
| diagnostic bridge-2207 | C | (9,14,14) | 27126.23 | 191.89 |
| diagnostic bridge-2207 | BC | (9,14,14) | 28506.23 | 193.25 |
| diagnostic bridge-2207 | J2 | (10,20,20) | 27128.14 | 191.88 |
| held bridge-7101 | B | (10,19,23) | 28505.72 | 222.32 |
| held bridge-7101 | BC | (10,17,17) | 28505.52 | 193.25 |
| held bridge-7101 | J1 | (10,19,23) | 28505.38 | 222.32 |
| held bridge-7101 | J2 | (10,22,22) | 27125.06 | 191.88 |

J2 recovers C/BC's missing bridge-2207 primary brand but still loses to B
lexicographically on that diagnostic. It wins the fresh bridge on cumulative
daily brands despite one fewer bowl. J1 ties B. One fresh long-budget bridge
does not establish broad full-budget superiority. Other families have not
been exhaustively tested at this expensive budget.


### Additional confirmation and follow-up benchmarks

1. **J1 confirmation on fork-5101 across 4 seeds (72, 73, 74, 75)**:
   In all four independent trials, J1 scores (9, 30, 37) while B scores
   (5, 21, 29). This is a consistent +4 primary brand improvement on this
   specific fork topology (4 wins / 0 ties / 0 losses). The operator log
   shows 10 surrogate improvements in 2.3 seconds of joint LNS time.

2. **Follow-up fixed suite (fresh map seeds 8100..8107, 8 complete matches per variant)**:
   - **B**: Mean primary 6.500, daily 20.625, bowls 23.500 (vs B: 0/8/0).
   - **M**: Mean primary 7.000, daily 21.750, bowls 23.000 (vs B: 1 win / 5 ties / 2 losses, 1 primary loss).
   - **MS**: Mean primary 7.750, daily 23.250, bowls 24.125 (vs B: 2 wins / 4 ties / 2 losses, 1 primary loss).
   MS notably reaches 10 primary brands on `patrol-8107` where B and M score 4,
   confirming that permitting store departures unlocks high-value multi-day chains.
   Both M and MS suffer a primary loss on `multi-8106` (1 brand vs B's 2), showing
   that candidate evaluation still lacks complete joint coordination on 6-patrol maps.

### Runtime, memory and deadline accounting

Held-out fixed-lineup timing (milliseconds), ordered P50 / P95 / maximum:

| Variant | Daily planner elapsed | Complete-match wall elapsed | Maximum RSS KiB |
|---|---|---|---:|
| A | 850.60 / 851.71 / 860.61 | 4263.45 / 4270.62 / 4279.24 | 20352 |
| B | 850.59 / 851.34 / 857.57 | 4263.35 / 4268.40 / 4278.78 | 20352 |
| BC | 681.18 / 850.61 / 852.77 | 3585.92 / 3590.89 / 3614.80 | 20352 |
| M | 681.85 / 850.60 / 850.79 | 3586.23 / 3591.12 / 3608.68 | 20352 |
| J1 | 850.63 / 851.86 / 857.47 | 4265.27 / 4273.89 / 4290.32 | 20352 |
| J2 | 681.84 / 850.64 / 853.45 | 3587.97 / 3593.80 / 3595.11 | 20352 |

Quantiles use the lower order statistic at `floor((n-1)*q)`. Wall time includes
process/capture overhead; RSS is the executable's native peak resident set.
All frozen development/held-out/competition trials are valid, with **zero
outer daily deadline misses**. Some exceed the *internal* 85% planner
allowance by a few milliseconds; those overruns are counted separately in
the JSON, not confused with the outer deadline. Maximum observed daily
elapsed in these frozen suites is 860.61 ms at development scale and
48,451.06 ms at competition scale. Maximum frozen-suite RSS is 21,940 KiB.

Held-out auto selection timing and strict selection-deadline misses:

| Variant | Selection P50 / P95 / max ms | Misses / 16 |
|---|---|---:|
| B | 2506.30 / 2507.27 / 2508.25 | 16 |
| BC | 2506.16 / 2506.99 / 2508.37 | 16 |
| J1 | 2506.00 / 2507.31 / 2507.34 | 16 |
| J2 | 2384.68 / 2502.29 / 2502.42 | 2 |

Competition selection misses are 5/8, all about 5-6 ms beyond 28,500 ms.
Therefore the result is **not** "zero deadline misses": daily planning fits
the outer allocation, but selector deadline compliance is still unresolved.
HTTP submission latency, opponents, thermal variation and server validation
are not exercised here.

### Joint operator cost versus actual benefit

Visible-worker diagnostics for held-out **fixed** matches, excluding selection:

| Variant | Attempts | Generated | Valid | Best-surrogate updates | Operator ms | Zero-update-call ms |
|---|---:|---:|---:|---:|---:|---:|
| J1 | 12074895 | 1030275 | 804131 | 3 | 6141.16 | 5685.51 |
| J2 | 10348231 | 970607 | 744867 | 1 | 5776.51 | 5652.32 |

Mean measured operator time per attempted selection is 0.000509 ms for J1
and 0.000558 ms for J2, including cheap rejected attempts. Generated and
valid counts must accompany these tiny averages; they are not full proposal
repair timings. At least 92.6% / 97.9% of the measured operator time belongs
to calls with no best-surrogate update. There may be additional failed
proposals within calls that do improve. Counts for auto/competition split
final planning from selection in the analysis JSON. Worker-zero surrogate
updates cannot be causally equated to the final selected worker's match gain.

Actual official gains remain the paired results: J1 1/15/0 vs B on held-out
fixed maps, and J2 0/16/0 vs M. Adding a tenth operator also changes RNG
consumption and the search trajectory; there is no sham-operator causal
control, so one winning match does not prove its winning plan was produced
solely by the new suffix exchange.

## G. Failure Analysis

The analysis artifact records every primary regression of BC/M/J1/J2 against
B, with the first differing plan or selector decision, lost brands, complete
daily plans, endpoints, fuel consumption and replenishment. A differing first
decision is observational evidence, not by itself a causal attribution.

### Primary losses in the frozen development/held-out experiments

All fixed-lineup losses below first differ on day zero. All have **zero supply
vehicles and zero replenishment**, so none can be attributed to a failed
actual supply rendezvous. Native simulation accepts every plan; none misses
the 1,000 ms daily deadline. The candidate fuel rule and opportunity ranking,
not deadline starvation, are implicated by the recorded waypoint choices.

| Case | Losing variants | B -> candidate primary | Brands B gets but candidate misses | First B / candidate endpoints | Total fuel consumed B / candidate |
|---|---|---|---|---|---|
| dev fork-4101 | BC, M, J2 | 9 -> 7 | 2,9 | 170,212,59 / 58,201,172 | 57 / 53 |
| held bridge-5100 | BC | 10 -> 9 | 3 | 87,183,133 / 118,183,96 | 80 / 70 |
| held fuel-5102 | BC | 9 -> 7 | 4,5 | 178,249,85 / 226,249,85 | 43 / 41 |
| held fuel-5102 | M, J2 | 9 -> 7 | 4,5 | 178,249,85 / 210,249,85 | 43 / 40 |
| held multi-5106 | BC | 3 -> 2 | 4,6 | 163,52,160,176,146,145 / 161,66,160,176,146,145 | 20 / 20 |
| held multi-5106 | M, J2 | 3 -> 2 | 4,6 | 163,52,160,176,146,145 / 162,66,160,176,146,145 | 20 / 20 |
| held rendezvous-6103 | BC | 8 -> 7 | 8 | 115,181,50 / 115,196,80 | 39 / 40 |
| held rendezvous-6103 | M, J2 | 8 -> 4 | 2,6,8,9 | 115,181,50 / 131,148,80 | 39 / 40 |
| held patrol-6107 | M, J2 | 8 -> 7 | 4 | 211,19,202 / 203,123,67 | 46 / 72 |

- **fork-4101:** all three patrols move, but matching ranks the same geographic
  distribution as C. Its conditional union increases 0->1->2->3 during
  coordinate descent without preserving B's longer-horizon coverage. This
  is a continuation/evaluation failure, not failure to mobilize a patrol.
- **bridge-5100:** BC leaves the third patrol at 96 with 32 fuel. M/J2 advance
  it and recover the missing primary brand. This supports the original
  redundancy diagnosis on a new map, but does not cancel losses elsewhere.
- **fuel-5102:** B moves the idle first patrol from 226 to 178. BC waits; M/J2
  move only to 210, then 194. Their conditional tomorrow key improves, but
  realized coverage stays two brands for two days and misses brands 4,5.
  The bounded fuel-reserved prefix set and uncommitted future witness do not
  reproduce B's productive longer advance. Remaining fuel alone is not value.
- **multi-5106:** B advances two patrols across several days. M advances only
  one cell initially, then leaves the first two endpoints unchanged through
  day three. Its witness already predicts two brands and cannot distinguish
  useful earlier progress from WAIT. All variants spend 20 fuel in total;
  *when and where* it is spent differs. The loss set has two brands despite
  a net primary loss of one because the candidate also gains another brand.
- **rendezvous-6103:** despite the family name, this test has no supplies.
  M's first key rises from three to four conditional brands, then the third
  patrol remains WAIT at cell 80. Actual daily brands are 0,0,0,1,4, versus
  B's 0,0,1,5,7. Fuel usage is nearly equal. One-target/frozen-traffic
  next-day feasibility, later-day fuel reservation, and no commitment to the
  witness leave a serious multi-day continuation error. J1's suffix exchange
  cannot rescue the empty/idle routes at the decisive earlier states.
- **patrol-6107:** plentiful fuel rules out a simple fuel shortage. M/J2's
  new assignment gains bowls (43 versus 30) but loses brand 4 and repeats
  the same seven daily brands. BC gets nine primary brands here. Thus the
  joint matching rank can actively worsen C's future distribution; it is
  not a monotonic improvement over either B or BC.

Automatic selection adds these primary-loss observations:

- BC repeats the fixed-lineup bridge-5100 and fuel-5102 losses with the same
  000 lineups; these are planner losses, not selection mistakes.
- On fork-6101, B and BC both select 010 but first rendezvous at 98 and 163,
  respectively; the third patrol ends at 220 in both. B gets seven brands,
  BC six; the missed-B set is 4,6,9. Both replenish five fuel; consumption
  is 53 versus 45. The initial supply schedule/search trajectory differs.
  This trace does not isolate whether stochastic search, the different inner
  time allocation, or its evaluation drives that schedule choice; calling
  it a proven repair defect would overstate the evidence.
- On fuel-5102, J2 selects 001 rather than B's 000. Its selector predicts
  (8,18,37) for 001 and (7,18,36) for 000; final 001 realizes (6,15,15),
  losing brands 4,5,6 relative to B's (9,20,20). Day-zero endpoints are
  195,221,228 rather than 178,249,85; total fuel consumption/replenishment
  is 47/19 versus 43/0. This is selector calibration plus a planner gap:
  frozen J2-000 already scores only seven. Supply is used, not idle.
- J2's patrol-6107 loss repeats with identical 000 lineups; selection cannot
  explain it. J1 has no primary regression in either frozen held-out suite.

No map-specific exception was added in response to these losses. The exact
store-start exclusion motivates one narrow, separately named follow-up MS:
remove that eligibility exclusion, retain the no-movement requirement and
today's exact-score guard. This is a candidate-generation correction, not
another LNS operator or new heuristic weight. It is tested after freezing
the main variants, on fresh map seeds and fresh exact cases.

## H. Deployment Decision

**CONTINUE STRUCTURAL RESEARCH. Do not deploy M, J1, J2 or MS on this evidence.**

The bridge milestone is real: joint simulation exposes value that independent
union reachability hides. But matching is only a restricted next-day witness;
it is neither a multi-day policy nor a complete joint waypoint neighborhood.
J1 has limited positive evidence without primary losses against B, but its
benefit is concentrated, overhead is measurable, and selector deadlines
still overrun. J2 loses primary brands on independent maps, even though it
recovers the old bridge and wins a fresh long-budget bridge.

The next justified structural change is to represent intermediate endpoints
and target ownership inside the joint route state, including patrols already
serving stores, and condition the next-day planner on the simulator-checked
assignment while revalidating traffic/fuel. The exact 7303/7304 witnesses
provide falsifiable acceptance cases for a pairwise reassignment that can
undo an already-moving patrol's choice. More weights, more independent
reachability or extra wall time do not address that missing transition.

The bounded MS correction is a separate candidate-generation result, not a
claim that those harder joint-assignment transitions now exist. Production,
GUI and the release executable remain unchanged; no commit or push is made.
