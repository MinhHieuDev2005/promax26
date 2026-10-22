# Round 6 audit and bounded multi-day joint search

Date: 2026-10-15. Research only. Production and GUI are not modified.

## 1. Audit of the frozen experiments

Source of truth: `results/solver-round6/`, `round6.py`, `round6_joint.hpp`,
`round6_exact.cpp`, frozen optimizer patches, and the source snapshots in
`/home/hexa/solver-experiments/round{5,6}`. Full original tables and individual
regression traces remain in `solver-research-round6.md` and
`results/solver-round6/primary-regressions.json`.

### Q1-Q2: Algorithms and differences from B

| Variant | Actual algorithm | Difference from B |
|---|---|---|
| M | C plus bipartite patrol-brand assignment, joint simulator witness prepended to the key | Removes B relocation; postprocesses stationary non-store patrols; retains C's 80% inner allocation |
| J1 | B plus atomic exchange of two nonempty store-route suffixes | Adds an LNS operator and changes RNG consumption; retains B relocation |
| J2 | M plus J1 suffix exchange | Neither simultaneous waypoint search nor multi-day search |
| MS | M with store-start exclusion removed | Still excludes patrols with any MOVE, retains today's score guard |

M evaluates the whole team but changes one patrol at a time. A shortest-path
half/full prefix can end on a non-store cell. LNS route nodes are still stores.
One explicit target per patrol does not imply only one collected brand:
incidental store acquisitions are counted by the simulator.

### Q3: Actual number of recorded matches

There are **326 command-bearing match records**, not 332. The earlier helper
counted six manifests as matches. Breakdown: 248 main benchmark trials,
72 exact-suite heuristic trials, six bridge diagnostics. Exact oracle JSON
files are not heuristic matches. Two direct M replays in this audit reproduced
7303/7304 but did not save full records; they are excluded from these totals.

| Directory | Matches |
|---|---:|
| bridge-919 | 6 |
| dev-fixed | 48 |
| held-fixed | 96 |
| held-auto | 64 |
| followup-fixed | 24 |
| confirmation | 8 |
| competition-diagnostic | 4 |
| competition-held | 4 |
| exact | 48 |
| exact-followup | 24 |

### Q4: Paired full-match lexicographic W/T/L against B

| Suite | M | J1 | J2 | MS |
|---|---|---|---|---|
| dev-fixed (8) | 2/4/2 | 0/8/0 | 2/4/2 | not run |
| held-fixed (16) | 5/4/7 | 1/15/0 | 5/4/7 | not run |
| held-auto (16) | not run | 3/13/0 | 5/7/4 | not run |
| followup-fixed (8) | 1/5/2 | not run | not run | 2/4/2 |
| confirmation (4 search seeds, same map) | not run | 4/0/0 | not run | not run |
| competition diagnostic (1) | not run | not run | 0/0/1 | not run |
| competition held (1) | not run | 0/1/0 | 1/0/0 | not run |
| exact (8, diagnostic) | 0/7/1 | 0/8/0 | 0/7/1 | 2/5/1 |
| exact-followup (8, diagnostic) | 0/8/0 | not run | not run | 1/7/0 |
| bridge-919 fixed diagnostic (1 paired) | 0/0/1 | not run | not run | not run |

Do not aggregate these unequal, partly repeated samples into a purported
independent-map win rate. M and J2 tie all 24 dev/held fixed score tuples.

### Q5: Improvements

M/J2 fixed primary gains: patrol-4107 +1, rendezvous-4103 +2,
fork-5101 +4, fork-6101 +3, fuel-6102 +2, rendezvous-5103 +2.
They also win secondary on bridge-5100. J2 auto gains primary on fork-5101
(+4), fork-6101 (+2), and secondary on bridge-5100 and multi-5106/6106.
J1 gains primary on fork-5101 (+4), confirmed with search seeds 72-75;
its other auto wins are secondary on multi-5106/6106.
M/MS followup gain five primary brands on fork-8101; MS additionally gains
six on patrol-8107 (4 -> 10). J2 wins competition bridge-7101 on daily brands
(10,22,22) vs B (10,19,23), but loses bridge-2207 (10,20,20) vs (10,21,21).

### Q6-Q7: Primary losses and evidence about causes

| Cases | Variant | Primary delta | Verified observations |
|---|---|---:|---|
| fork-4101 | M/J2 | -2 | All patrols move; tomorrow witness fails to preserve longer coverage |
| fuel-5102 fixed | M/J2 | -2 | Short initial advance 226->210, versus B 226->178; no supplies |
| multi-5106 | M/J2 | -1 | Same total fuel 20, but first two endpoints stall through day three |
| rendezvous-6103 | M/J2 | -4 | No supplies despite family name; daily brands 0,0,0,1,4 vs 0,0,1,5,7 |
| patrol-6107 | M/J2 | -1 | 43 bowls vs 30, but repeated coverage misses brand 4; plentiful fuel |
| fuel-5102 auto | J2 | -3 | Chooses 001 vs B 000; prediction (8,18,37), actual (6,15,15) |
| patrol-6107 auto | J2 | -1 | Same all-patrol lineup, so not a selection explanation |
| multi-8106 | M/MS | -1 | Eligibility repair alone does not fix six-patrol coordination |

J1 has no recorded primary regression in these suites. Exact counterexamples
prove candidate eligibility and single-day assignment failures. On large maps,
the traces establish continuation/prediction mismatches, not the unique causal
contribution of fuel reservation, traffic forecasting, or stochastic search.
No actual supply failure explains the all-patrol fixed-lineup losses.

### Q8: Time, search and memory limits

M/MS/J2 retain C's 80% of the planner allowance for non-final-day LNS;
the outer harness gives the planner 85% of the daily allowance. Candidates
are limited to a four-item shortlist. J1's additional operator yielded
804,131 valid visible-worker proposals and three best-surrogate updates in
held-fixed; J2 yielded 744,867 and one. These counters are not match wins.

Held-fixed daily P50: B 850.59 ms, J1 850.63, M 681.85, J2 681.84.
Frozen-suite maximum RSS: 21,940 KiB. No recorded outer daily misses there,
but held-auto selector misses: B/J1 16/16, J2 2/16, BC 16/16.
Competition selector misses: 5/8, approximately 5-6 ms over 28,500 ms.
57-second daily experiments do not establish server submission compliance.

### Q9: Implementation/evaluation problems hiding useful ideas

MS fixes a genuine eligibility restriction: exact 7301/7302 improve from
(3,8,8) to (4,8,8), and fresh 8303 from (2,6,6) to (4,6,6).
J1 is the lowest-regression full-match candidate in the frozen data, but
its primary gains are concentrated on one topology. File-backed unbuffered
stderr caused selector starvation in a diagnostic; main comparisons use
pipes. That artifact must not be generalized to normal GUI operation.

### Q10: Proven versus hypothetical

Scores, validity, recorded timings and exact witnesses are measured. Exactness
is confined to the oracle's tiny plain-only, no-supply/no-traffic model.
The first differing action is not a causal ablation. J1 has no sham-operator
control for RNG and search-budget effects. Neither matching nor MS has proven
general superiority. Statistical statements about competition are unsupported.

## 2. Structural review

`table.t[target.pos] > steps` uses tomorrow's steps, not cumulative remaining
steps. A target two days beyond the candidate endpoint has no matching edge.
Later independent-union tie breakers do not repair the leading next-day rank.

Matching avoids duplicate explicit brand ownership but keeps one path per edge
and one target per patrol. Its independent reachability is not simultaneous
feasibility; native joint simulation checks stock, incidental collections and
agent order afterwards. Supplies WAIT in this witness; refueling-dependent
edges can be missing. Frozen current traffic is conditional, not a forecast
guarantee. The witness is not passed to tomorrow's planner as a warm start.

`chooseOvernight` sequentially edits only all-WAIT patrols. The store-start lock
is removed only in MS. Its today-score guard prohibits sacrificing today's
coverage/daily brands/bowls for the match. It cannot jointly undo a moving
patrol's assignment and give that target to a different patrol. J1/J2 exchange
store suffixes inside a single day, not intermediate overnight waypoints.

7303: optimum day-one endpoints 2,17, then 3,10; existing variants use 10,17,
then 2,17 and miss brand 3. 7304: C-family starts with 9,8, whereas optimum
starts 1,9. B/J1 already find that second case; it is not a universal B failure.

An early J3 pair-candidate prototype solves 7301-7304 but regresses progression
from (2,3,3) to (1,2,2): the first patrol WAITs because a three-day target is
outside its two-day matching horizon. This negative result is retained, not
treated as success. J3 still uses the old conditional witness and is not the
final multi-day action search.

## 3. New prototype definition

J4 replaces C's overnight phase with bounded joint action beam search, horizon
up to three days. J4H2 is the same search with a two-day horizon ablation.
Each node contains all agents' positions/fuel, collected brands, predicted
traffic, previous stay, cumulative daily/bowl reward and the first joint plan.
Each layer calls the native simulator and resets stock through its day boundary.

For each pair, replace both patrol plans atomically; other current-day agents
retain incumbent actions. Options include incumbent, WAIT, each legal adjacent
cell, and half/full time-and-fuel-feasible store-directed prefixes. Moving
patrols and store departures are eligible; currently acquired brands are not
excluded. There is no today-score rejection guard. Future layers generate
their own actions, not just a reachability score. Supplies keep today's actual
schedule; future baseline supply schedules are stationary, with any resulting
native refueling still simulated.

Bounds: 24 options/patrol, 64 beam states, prune pool at 512 states, 24,000
simulated transitions, and the unchanged overall planner deadline. Pairwise
enumeration costs O(P^2 K^2), not a K^P full-team Cartesian product.
The intermediate pruning key uses a fuel/time reachability estimate; terminal
ranking uses only simulator-realized lexicographic reward, then fuel. This is
not an admissible exact search, nor optimal on large maps. Current traffic is
used for the intermediate estimate; future execution uses a conditional
forecast combining own two-day stays and the existing predictor. Missing
opponent/history information remains a modeling limitation.

Only a fully expanded horizon replaces the incumbent. Exhaustion returns the
original C single-day plan; this fallback is intentionally logged and must be
counted when assessing scale. Tomorrow replans; no persistent commitment is
claimed. Large-instance multi-stop routes rely on the native greedy baseline;
the new options are path prefixes, not arbitrary action-sequence enumeration.

Reproduction (run sequentially under WSL HexaUdon):

```sh
python3 tests/benchmark/round6_audit.py build --variants J4 J4H2
python3 tests/benchmark/round6_audit.py exact --variants J3 J4H2 J4
python3 tests/benchmark/round6_audit.py suite --name fixed
python3 tests/benchmark/round6_audit.py suite --name auto --lineup auto
python3 tests/benchmark/round6_audit.py suite --name competition-fixed --day-ms 57000 --selection-ms 28500
python3 tests/benchmark/round6_audit.py suite --name competition-auto --lineup auto --day-ms 57000 --selection-ms 28500
```

Builds refuse existing source trees. No production rebuild, commit or push.
New fixtures use seeds 9100/10100; competition uses fresh fork-11101 fixed and
multi-11106 auto, not another bridge-only confirmation. J1 is the frozen best
low-regression Round 6 comparator, not a universally best algorithm.

## 4. Exact verification and a necessary sacrifice

J4 matches the oracle on all 12 unique original/fresh fixtures. J4H2 and J3
match 10/12, missing progression and competing-8303. The new action search
therefore fixes 7303/7304 without retaining the three-day blind spot of J3.

| Fixture | Exact | B | M | MS | J3 / J4H2 | J4 |
|---|---|---|---|---|---|---|
| stock | 1,3,3 | 1,3,3 | 1,3,3 | 1,3,3 | 1,3,3 | 1,3,3 |
| distinct | 2,2,2 | 2,2,2 | 2,2,2 | 2,2,2 | 2,2,2 | 2,2,2 |
| progression | 2,3,3 | 2,3,3 | 2,3,3 | 2,3,3 | 1,2,2 | 2,3,3 |
| fuel | 0,0,0 | 0,0,0 | 0,0,0 | 0,0,0 | 0,0,0 | 0,0,0 |
| competing-7301 | 4,8,8 | 3,8,8 | 3,8,8 | 4,8,8 | 4,8,8 | 4,8,8 |
| competing-7302 | 4,8,8 | 3,8,8 | 3,8,8 | 4,8,8 | 4,8,8 | 4,8,8 |
| competing-7303 | 4,6,6 | 3,5,5 | 3,5,5 | 3,5,5 | 4,6,6 | 4,6,6 |
| competing-7304 | 4,8,8 | 4,8,8 | 3,6,6 | 3,6,6 | 4,8,8 | 4,8,8 |
| competing-8301 | 3,7,7 | 3,7,7 | 3,7,7 | 3,7,7 | 3,7,7 | 3,7,7 |
| competing-8302 | 4,9,9 | 4,9,9 | 4,9,9 | 4,9,9 | 4,9,9 | 4,9,9 |
| competing-8303 | 4,6,6 | 2,6,6 | 2,6,6 | 4,6,6 | 3,7,7 | 4,6,6 |
| competing-8304 | 3,7,7 | 3,7,7 | 3,7,7 | 3,7,7 | 3,7,7 | 3,7,7 |

Baseline columns reuse frozen records, not newly executed matches. On 7301-7304,
C/J2 equal M and J1 equals B. Stock/distinct/progression/fuel baseline variants
all agree. New J3/J4H2/J4 records are saved with full commands and hashes.
Fresh C/J1/J2 comparators were subsequently run on all four 830x fixtures:
they match the oracle except 8303, where each scores (2,6,6).

### Two-day sacrifice-9401

`round6_sacrifice.py` searches predetermined seeds 9400..10399 and stops at the
first proven strict-primary sacrifice (9401; two candidates examined). This
is a diagnostic fixture search, not an unbiased benchmark sample. No algorithm
branch references its seed, coordinates or topology.

Plain 8x8 map, two patrols start at 10 and 11, fuel three, day lengths two and
four. Four unit-stock brands are at 25, 2, 26 and 1. The unconstrained exact
optimum is **(4,5,5)**. Constraining the first day to collect at least two
brands gives the exact best remaining-match score **(2,4,4)**. Consequently,
retaining today's best two brands cannot reach four match brands, even with
an optimal continuation. This is stronger than comparing two heuristic runs.

All B/C/M/MS/J1/J2 choose day-zero endpoints **1,2**, collecting two brands,
and finish (2,4,4). Both J4H2 and J4 choose **2,18**, collecting only one brand,
then finish (4,5,5). Cell 18 is a non-store waypoint. On day one J4 moves the
second patrol 18->26->25 while the first collects the remaining nearby brand.
This is a real joint action transition, a current-day sacrifice, and a native
simulator-valid continuation across the day boundary, not a larger estimate.

The oracle was extended with optional `minimum-first-day-brands` (0..4).
Filtering day-zero frontier states before later DP layers preserves the exact
scope; other oracle restrictions are unchanged. It reports infeasibility rather
than indexing an empty frontier. The runnable checks also exercise invalid
arguments and an impossible constraint.

Three additional explicit two-day fixtures pass for all eight tested variants:
shared starting-store stock (1,2,2), two non-store overnight waypoints (2,2,2),
and one patrol WAIT while the other MOVE (2,3,3). Assertions verify J4/J4H2's
actual first-day actions/endpoints, not just scores. These are coverage checks,
not claimed wins over B. Including sacrifice-9401, J4 matches the exact optimum
on **16/16 unique small fixtures**; J4H2 matches 14/16.

```sh
python3 tests/benchmark/round6_sacrifice.py
python3 tests/benchmark/round6_audit_analyze.py
```

J3 is retained as a negative experiment. Its source delta is archived as
`results/solver-round6-audit/J3-optimizer.patch` against frozen Round 5 C and
requires `round6_joint.hpp`. The earlier scratch builder (which deleted its
output tree) was removed; no reproducibility path requires that deletion.

## 5. Independent full-match benchmark

Algorithms were frozen before the new suites. Seeds 9100..9107 and
10100..10107 cover eight families twice, all at 1,000 ms/day, eight workers,
affinity CPUs 0-7. Auto selection separately receives 2,500 ms. All processes
run sequentially on the same WSL host; stderr is captured through a pipe.
These are synthetic same-family maps, not actual server matches or a claim
of independence between related family topologies. `environment.txt` records
the host/compiler. Each manifest records binary/runner hashes and budgets.

| Variant | Fixed W/T/L vs B | Fixed primary losses | Auto W/T/L vs B | Auto primary losses |
|---|---|---:|---|---:|
| BC | 5/8/3 | 1 | 2/10/4 | 2 |
| J1 | 1/14/1 | 1 | 5/8/3 | 1 |
| J4 | **2/5/9** | **7** | **5/5/6** | **5** |

J1 now has a primary regression on bridge-9100 (10 -> 9) in both fixed and
auto, so its old zero-regression sample did not generalize. It remains a
comparison variant, not a deployment recommendation.

J4 fixed primary regressions against B:

| Map | B primary | J4 primary | Delta |
|---|---:|---:|---:|
| bridge-9100 | 10 | 4 | -6 |
| fork-9101 | 6 | 2 | -4 |
| rendezvous-9103 | 4 | 2 | -2 |
| patrol-9107 | 9 | 6 | -3 |
| bridge-10100 | 10 | 0 | -10 |
| rendezvous-10103 | 3 | 1 | -2 |
| patrol-10107 | 10 | 1 | -9 |

Fixed wins: fuel-9102 (7,34,36) -> (8,34,35), multi-10106
(2,2,4) -> (2,2,5). Other fixed losses are secondary on fork-10101 and
multi-9106. The multi-10106 improvement is not attributable to a completed
multi-day search; stochastic single-day search/time allocation also differ.

Auto primary regressions: bridge-9100 -2, patrol-9107 -3,
bridge-10100 -1, fork-10101 -1, patrol-10107 -4. Its remaining loss is one
bowl on multi-9106. Auto primary wins: rendezvous-9103 +1, wait-9105 +1,
fuel-10102 +1; secondary wins: fuel-9102 and multi-10106. Several selected
lineups differ, so these are end-to-end gains/losses, not pure operator effects.

### Runtime and validity at 1,000 ms

All 128 complete matches are valid, with zero outer daily misses. Every auto
variant exceeds the strict 2,500 ms selection allowance in all 16 matches.
Quantiles below are P50 / lower-order P95 / maximum, in milliseconds.

| Variant | Fixed daily | Auto daily | Auto selection |
|---|---|---|---|
| B | 850.61 / 851.44 / 858.64 | 850.73 / 851.40 / 853.77 | 2506.40 / 2508.43 / 2527.91 |
| BC | 681.30 / 850.61 / 852.17 | 680.76 / 850.74 / 859.05 | 2506.47 / 2506.95 / 2507.37 |
| J1 | 850.59 / 851.48 / 855.47 | 850.68 / 851.08 / 851.27 | 2506.65 / 2507.84 / 2507.93 |
| J4 | 798.93 / 850.90 / 860.54 | 839.65 / 853.63 / 857.21 | 2503.59 / 2504.31 / 2505.39 |

J4 fixed wall P50/P95/max: 4035.67 / 4081.56 / 4098.63 ms;
auto: 6657.74 / 6716.35 / 6721.38 ms. Maximum observed RSS is
20,016 KiB in fixed and 23,940 KiB in auto. Memory pressure is not an
observed explanation for the score failures.

### Verified scaling failure

Of 62 final-planning J4 calls in fixed, only **1** completes the requested
horizon; **61** hit 24,000 transitions. In auto, **3/62** complete,
**51** reach the transition cap, and **8** stop earlier at the time limit.
The fixed completed call is fuel-9102 with horizon two, 20,212 transitions,
89.20 ms; it is not representative of three-day completion on larger teams.

Incomplete horizons discard the experimental replacement and return the
single-day incumbent. That incumbent comes from C's inner solver, **without
either B's relocation or C's removed waypoint postprocessor**. This verified
fallback defect makes a bounded-search failure a large behavioral regression;
on bridge-10100 it leaves all brands uncollected. The problem is not that all
24,000 transitions are illegal, nor a memory crash. It is excessive branching
for the fixed cap plus a fallback that drops productive relocation behavior.
More wall time alone cannot remove that fixed transition cap.

### Competition-budget check

Eight additional complete matches use 57,000 ms/day and a separate 28,500 ms
auto-selection allowance. One fresh fixed fork and one fresh auto six-agent
map are deliberately different families; this does not isolate lineup mode
on the same map, and is not a broad competition-distribution estimate.

| Map / mode | Variant | Score | Lineup | Selection ms | Match wall seconds |
|---|---|---|---|---:|---:|
| fork-11101 fixed | B | 4,17,21 | 000 | 0 | 242.27 |
| fork-11101 fixed | BC | 8,30,30 | 000 | 0 | 203.51 |
| fork-11101 fixed | J1 | 4,17,21 | 000 | 0 | 242.28 |
| fork-11101 fixed | J4 | 4,16,20 | 000 | 0 | 203.95 |
| multi-11106 auto | B | 10,46,75 | 011000 | 28506.43 | 270.78 |
| multi-11106 auto | BC | 10,46,75 | 011000 | 28507.39 | 232.03 |
| multi-11106 auto | J1 | 10,46,76 | 000011 | 28506.26 | 270.79 |
| multi-11106 auto | J4 | 10,46,76 | 001010 | 28504.23 | 232.53 |

All eight are valid; no outer daily deadline miss. Maximum daily elapsed is
48,459.08 ms. All four auto selectors exceed 28,500 ms. Maximum RSS is
35,188 KiB. J4's eight final-planning calls all stop at 24,000 transitions,
completing only depth one. Thus the extra bowl in auto is **not evidence of
a successfully executed final-planning multi-day replacement**. Different
selection lineups and inner search trajectories remain confounders.
The 24,000 cap takes only 85-139 ms here, leaving much of the reserved phase
unused despite ample wall time. This is an implementation/search-scheduling
ceiling, not proof that multi-day coordination cannot scale at 57 seconds.

## 6. Engineering decision

**REJECT J4 as a deployment candidate; CONTINUE the structural research.**
Keep the exact witnesses and action-space tests, not the benchmark-losing
integration. J3/J4H2 are also rejected as general multi-day replacements:
their two-day horizon demonstrably loses reachable three-day brands.

| Possible cause | What this audit establishes |
|---|---|
| Representation | J4 can express and find joint moving-patrol reassignment, store departure, non-store waypoints, WAIT/MOVE and necessary current-day sacrifice in the exact model |
| Evaluation | Terminal comparison is realized multi-day lexicographic reward; intermediate pruning remains heuristic. Twelve small matches do not validate ranking on larger maps |
| Neighborhood | Bounds are explicit; a pair is changed at a time and path options are restricted. No full joint-orienteering optimality claim |
| Search budget | Dominant measured failure: fixed transition cap prevents completed horizons in 61/62 fixed, 51/62 auto and 8/8 competition final calls; another eight short-budget auto calls exhaust time |
| Integration/fallback | Returning C's bare inner plan drops both earlier relocation mechanisms. This amplifies search noncompletion into large primary losses |
| Multi-day prediction | Roads/opponents and prior stay history remain approximate; small plain fixtures do not test those errors |
| Supply | Current-day stock/refueling are jointly simulated; future supply schedules are not jointly optimized. Supplies cannot explain all-patrol fixed losses |

The proof of new capability is sacrifice-9401 and 7303, not a claim that B can
never express any optimum on any other map. B/J1 already solve 7304. The new
method succeeds where the recorded B/C/Round 6 runs fail, under a clearly
bounded exact model. Its deployed behavior on independent maps is nevertheless
unacceptable: 2/5/9 fixed and 5/5/6 auto, with seven/five primary regressions.

A next revision must preserve a productive incumbent when interrupted and
allocate its bounded expansion across days/pairs so that a usable horizon
finishes. It must then face a new frozen independent suite; removing the cap
or changing fallback after observing these results would be a new variant,
not a reinterpretation of J4's failed benchmark. No such untested revision is
silently applied here. The existing production executable remains unchanged.

## 7. Final validation and artifacts

This follow-up saves **216 new valid complete-match records**: 128 short-budget
benchmark matches, eight competition-budget matches, and 80 small-instance
heuristic trials. Together with the 326 frozen records there are 542 archived
match records, not 542 independent maps. Oracle invocations, manifests and
earlier unarchived exploratory replays are excluded. Before the new archive,
the scratch work also ran two M and nine J3 replays without persistent trial
records; their available terminal output is not used for performance aggregates.

Validation completed:

- Release builds of J4/J4H2 and the extended exact oracle, with no reported compiler warnings.
- 16 exact acceptance fixtures, first-day constrained optimum, invalid constraint inputs and infeasibility handling.
- Strict full-record validation: success exit, all expected valid days, fixture and binary hashes, matching seeds/budgets, pipe capture and eight workers.
- All three archived optimizer patches pass `git apply --check` against the frozen C source.
- Python syntax and edited-file whitespace checks.

`results/solver-round6-audit/summary.json` contains paired B/BC/J1 comparisons,
every score change, primary losses, timing quantiles, memory, deadline misses,
and per-call completion/cap diagnostics. The individual JSON/log files retain
actual plans and simulator endpoints. Patches, build logs, environment and
source/oracle hashes are retained alongside them. Research entry points are
`tests/benchmark/round6_audit.py`, `round6_sacrifice.py`, and
`round6_audit_analyze.py`; the new action search is `round6_multiday.hpp`.

Final production SHA256, identical to the initial value:
`d864d3fd2f325773cbcd594dc93063b63882ca07fa5947365944fa0e8ec7b903`.
Production source and GUI were not edited. No commit, push or deployment.
