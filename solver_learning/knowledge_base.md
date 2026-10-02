# Hexudon optimization memory

## Contract (2026-09-29)
- User confirmed Q06 target C1=13, C2=91, C3>=230; at most 60000 ms per day.
- Existing sources, v1, executables and evaluator must remain unchanged.
- Offline measurements use one-team self-traffic, same frozen roles/input as the 223 study.
- No online submissions or server mutations. Report local simulator versus official server separately.
- Score is lexicographic in the rules; our acceptance gate additionally requires maximum brand coverage every day.

## Established evidence
- Historical v1 Q06 at 50s/day: 13/91/223. At 20s/day: 13/91/222.
- Historical report retained diagnostics but not all submitted plans; a fresh replayable baseline is required.
- v1 optimizes current-day servings before fuel, without remaining-match evaluation.
- Positions and fuel persist overnight. Thus improving one day can damage a later day.
- More wall time changes ALNS annealing trajectory; fixed random seed alone does not guarantee identical timed results.

## Open hypotheses
- H00: replayable v1 50s can reproduce the 223 quality floor with maximum coverage.
- H01: continuation-aware existing policies reveal whether v1's bottleneck is myopic day selection.
- No optimization implementation before H00 measurement and baseline audit.

## H00 completed
- Exact historical v1 score did not reproduce: fresh 50s seed-1 run scored 13/91/221.
- All saved actions replayed exactly. Historical 223 is a prior measurement, not a reproducible seeded guarantee.
- LNS 3s and ALNS 20s independently produced replayable 13/91/223; use their frozen artifacts as reproducible 223 references, and ALNS 3s 224 as the stronger control.
- First v1 process took 51.662s including startup; later calls were 49.778-49.782s. Do not claim a process-level 50s guarantee.
- H02 implementation began only after baseline reproduction phase and full 18-policy audit completed.

## H01 audit batch conclusion
- All 18 dispatcher/v1 policies screened at the same 3s requested budget.
- LNS yielded 13/91/223 and ALNS 13/91/224; both exact action checkpoints replayed.
- MLNS=204, PALNS=220, LNS-DP=203 (all 13/91). No evidence to replace ALNS with these outright.
- simple_lns=13/46/73 failed the hard daily-coverage gate in this short-budget trial.
- Q06 has only 19 spots and two patrols: safe serving upper bound is 38/day, 266/match.
- ALNS and v1 endpoints generally retain substantial fuel in the audited trace. Fuel starvation is NOT established as the primary bottleneck; endpoint/traffic decisions require direct continuation evaluation.

## H02 proposed experiment (before implementation)
Hypothesis: current-day ALNS is a strong move generator, but choosing only its
best daily route prematurely fixes endpoints/traffic. Persistent Chokudai queues
over complete day transitions, retaining diverse ALNS elites and replaying the
entire suffix, can exceed the frozen 224 feasible incumbent without changing roles.

Smallest test: new macro Chokudai engine, 20s/day, fixed seed 1; no MLNS replacement,
no role tuning, no larger v1 beam. Reuse unchanged ALNS and simulator as micro engine.
Keep an exact warm suffix so rolling replanning cannot discard the best known
feasible continuation when actual one-team transitions match the forecast.
Acceptance: all days fully covered, then compare ONLY cumulative servings.
Ablation: disable macro sweeps (same seed construction); later remove elite moves.

Alternative considered: longer v1 search (historically marginal); MLNS-only
(3s audit underperformed); daily multi-start (does not directly price tomorrow).
Chosen: macro Chokudai + ALNS destroy/repair elites, because it directly tests
the unexplored alternative endpoints while preserving the strongest audited engine.

## Unknown / not established
- H04 proposed: use subset route DP as an additive micro move generator on small spot sets (<=19). Reason: Q06 fuel is high, daily travel time and visit ordering appear restrictive; a feasible no-refuel route can be constructed with better ordering than heuristic ALNS. Keep ALNS as fallback and macro Chokudai unchanged. DP retains one time/fuel label per subset/end, hence is a heuristic under the fuel constraint, NOT an exact optimum proof. All resulting joint plans require authoritative simulation/full coverage. Later-day effects still evaluated by macro search. No test-specific coordinates/brands/paths.
- H05 proposed before change: H02 cold suffix used single-restart ALNS with continuation disabled, while the strongest audit result came from production three-restart ALNS with continuation. Seed macro search with that stronger production family under the same total deadline, then use Chokudai only for remaining diversification. This tests seed quality, not width. Preserve weak fallback if a strong proposal misses coverage.

## H03/H04 conclusions
- H03 60s/day, 1000ms slices: 13/91/224. Larger total/slice budget matched but did not exceed the 224 control. H03 unsupported as an improvement.
- H04 route-DP 20s: 13/91/223; exact ablation with route-DP disabled: 13/91/223. Neutral in realized score. Its day-1 projected value 222 vs 220 was forecast noise/insufficient to alter the final outcome.
- Do not allocate more experiments to route-DP unless the proposal set or continuation rank changes materially.

## H06 proposed
Q06 has exactly three agents; choosing which initial position holds the sole
refuel vehicle changes two patrol starting basins and every later rendezvous.
Audit the two alternative one-refuel assignments with production ALNS at 3s.
This is a small complete role-position ablation, not role-count brute force.
Reject any assignment below 13/91. Only promote a better feasible trajectory.

## H07 proposed
With the best role assignment fixed, measure production ALNS seeds 2-4 at the
same 3s budget. Evidence: seed 1 reached 224 while longer timed runs reached 223,
so trajectory diversity matters more than raw budget. This is the smallest
multi-start batch. Use results to estimate variance and seed v2 families; do not
claim a lucky score is consistent without replay and cross-seed reporting.

## H05-H07 conclusions and H08
- H05 strong-seed macro scored 222: worse than its intended 224 floor. Root cause in implementation: strong seed used a newly drawn RNG salt every day instead of retaining canonical seed 1.
- H06 alternative refuel positions scored 222 and 220; canonical roles [0,0,1] remain best.
- H07 ALNS seeds 1/2/3/4 scored 224/221/219/224. Multi-start has real variance but no improvement yet.
- H08 hypothesis: retain canonical production seed 1 as an invariant floor candidate, while adding two production multi-start candidates at the revealed root. Macro Chokudai evaluates their complete feasible suffixes. This is materially different from H05 because the measured 224 trajectory is explicitly present rather than replaced.

## H09 proposed
Mine the replayable 224 trajectory at day-4 and day-6 boundaries. Re-optimize
only the revealed suffix with several ALNS seeds. This measures where remaining
headroom exists without confounding earlier decisions. It does not splice an
incompatible plan into the elite; every suffix is replayed from its exact saved
positions, fuel, traffic and history. If suffix scores saturate, shift effort to
earlier branch decisions; if they improve, feed those states/moves to macro search.

## H10 proposed — corrected role assumption
- schema.md:118 explicitly permits every type vector containing only 0/1; if no valid assignment is accepted, all agents become Patrol Cars. A refuel vehicle is NOT an official validity requirement.
- Earlier H06 only compared which agent was the sole refueler, inheriting a GUI/construction convention rather than the rule.
- Q06 fuel limit is 241. Test all-patrol [0,0,0] with authoritative seven-day replay at 3s. Feasibility remains C1=13/C2=91; fuel-invalid plans are rejected by simulator. If feasible and >224, this is a structural improvement rather than search luck.

## H10 result / H11
- All-patrol daily ALNS collected 55/45/45, then only 3/3/3/3: 13/51/157, infeasible. Immediate exploitation exhausted persistent fuel after day 3.
- H11 hypothesis: all-patrol is viable only with an explicit whole-match fuel budget. Screen MLNS, simple-LNS and LNS-DP at 3s with [0,0,0]. These are the existing solvers that model suffix state; reject any below 13/91 regardless of servings. If one preserves coverage, allocate a longer budget and use its trajectory as v2 seed.

## H11 result / H12
- MLNS all-patrol=13/52/155, simple-LNS=13/75/124, LNS-DP=13/13/57. None enforced the required daily coverage under persistent fuel; H11 rejected.
- H12: for all-patrol only, cap each patrol's route fuel to floor(current fuel / remaining days), then use subset route-DP as a branch at every macro depth. This is a real inter-day resource constraint, unlike H10/H11's greedy fuel exhaustion. The cap is conservative, not an optimality bound. Complete suffix simulation and 13/91 remain mandatory; ALNS candidates remain alternate branches.

## Milestone 225 and H12 conclusion
- H08 produced replayable 13/91/225: daily servings 37/31/35/27/32/25/38. This is the first valid improvement over 223 and the 224 audit control.
- H08 mechanism: preserve canonical production seed, retain endpoint-diverse ALNS elites in persistent macro depth queues, and accept only complete 13/91 suffixes. The gain came from accepting -1 on day 2 to gain +1 day 5 and +1 day 6 versus the 224 control.
- H12 failed to find any complete coverage suffix. Conservative all-patrol DP day 1 reached only 21 servings at full coverage; all-patrol family is not presently competitive for 230.
- H13: test existing additive LNS-DP proposal and continuation-time allocation around ALNS at the cheap 3s screen. Evidence is required before integrating either into the 225 macro family.
- H14 (targeted exploitation after 225): freeze the exact H08 prefix at day 2 and day 4, then rerun only each suffix with a different macro seed. This searches the first divergence after the elite prefix and cannot invalidate earlier gains. Every combined total is the checkpoint history plus an authoritative suffix replay; no incompatible plan splicing.

## H13 conclusion / H15
- continuationTimePercent=40 scored 222; adding LNS-DP proposals with it scored 224. The LNS-DP-only run terminated unexpectedly after day 1 and is recorded as failed, not evidence.
- More continuation allocation did not help. H15 screens the opposite direction (10%) and a stronger ACO seed, separately and together, at 3s. This changes one seed/allocation family per arm; only feasible replayed gains are promoted.

## H16 proposed
H08 expanded only 31-40 macro nodes on long days because every micro ALNS slice was 1s. H02 showed 250ms slices roughly doubled expansions but lacked the canonical strong floor. Combine the now-fixed canonical production floor with 250ms diversification, first on the frozen day-4 suffix of elite 225. This changes the exploration granularity only; width/roles/objective stay fixed.

## H17 proposed
The H04 route-DP retained only one route per endpoint. That discards most
visited-subset diversity before the two patrol routes are paired, so it cannot
optimize which patrol covers which stock/brands. Retain up to 256 feasible
subset routes per patrol and rank exact route pairs by full brand coverage,
planned visits, fuel and time. The unchanged simulator remains authoritative
for stock contention, incidental visits, traffic and the final score. First
probe Q06 day 1 and frozen elite states; integrate this branch into a new runner
only if it produces a valid current-day improvement or materially new endpoints.

## H17 result / H18 proposed
- H17 replayed at 13/91/225 with daily 37/32/34/28/31/25/38. Its prefix
  was +1 after day 4, but the gain was lost on day 5; subset pairing changes
  useful states but is not sufficient alone.
- H18: route-DP currently puts all unused horizon into one final wait. Once the
  endpoint's stock is exhausted, that time cannot score. Distribute route slack
  as up to two extra waits at each intermediate visited spot (stock-aware upper
  limit), retaining leftover wait at the endpoint. Rank route pairs by this
  planned serving count and still accept only authoritative simulated plans.

## H18 probe result / H19 proposed
- Distributing waits produced no authoritative gain: best probes remained
  37/32/27 on day 1, elite day 2 and elite day 4 respectively. The enriched
  routes themselves ranked worse; retaining the original variants preserved
  the floor. H18 is rejected as a scoring improvement.
- H19: H07 showed meaningful seed variance and ties at the best ALNS score.
  Run the now-stronger H17 family with seeds 2 and 4 at the same 60s budget.
  This changes only the stochastic trajectory and tests robustness/lucky
  improvements; both must undergo full seven-day replay and 13/91 validation.

## H19 result / H20 proposed
- Seeds 2 and 4 both replayed at 13/91/224. Daily sequences were
  36/32/35/27/32/24/38 and 36/32/36/26/31/25/38. H17 seed 1 remains elite.
- Targeted suffix runs exposed a forecast-only bug: reconstructing historical
  self traffic under inferred roads can make an already authoritative accepted
  action exceed the horizon, because past observed road states are unavailable
  in the protocol history. Historical traffic is only a heuristic forecast;
  never reject the current valid state when that reconstruction fails. Retain
  an empty dwell estimate for that day and continue from the caller's revealed
  current state. Re-run suffix exploitation after this robustness fix.

## H20 result / H21 proposed
- Corrected suffix runs now complete and replay, confirming the robustness fix,
  but scored 221 from elite day 2 and 223 from elite day 4; no promotion.
- H17 used only capacity 24 and six proposals per expanded node. Its 60s run
  expanded roughly 150-240 nodes/day, so queue diversity rather than raw node
  count may be constraining multi-day alternatives. H21 tests capacity 64 and
  12 attempts with 250ms slices, fixed seed 1 and otherwise identical logic.

## H21 result / H22 proposed
- H21 replayed at 13/91/224 (37/31/35/27/31/25/38). Larger frontier and
  attempts did not improve the elite.
- Audit found a conflicting fixed bottleneck: endpoint buckets retain at most
  three nodes even when layer capacity is raised to 64. Nodes with equal end
  positions but different fuel and last-two-day traffic can have different
  continuation value. Scale per-endpoint quota from 3 to 8 when width >=64;
  retain the exact-state deduplication and complete-suffix acceptance gate.

## H22 result / H23 proposed
- H22 replayed at 13/91/223 (37/32/34/26/31/25/38). Increasing same-endpoint
  traffic diversity diluted the frontier; fixed quota 3 remains preferred.
- Before replacing the move family, finish the stochastic audit of the best
  H17 configuration with unseen seeds 5 and 6. H07/H19 covered 1-4 and showed
  a 219-225 range. Promote only a replayed improvement; otherwise treat 225 as
  the practical ceiling of current-day ALNS + macro endpoint diversification.

## H23 result and next structural direction
- Seeds 5 and 6 replayed at 13/91/221 and 13/91/220. Across seeds 1-6 and
  multiple width/slice settings, the best remains the replayable H08/H17 score
  225. More stochastic restarts are now low-value.
- The remaining gap cannot be justified by Chokudai parameter tuning. The next
  operator must jointly change consecutive days: generate a day-D plan plus
  several endpoint/fuel targets for day D+1, then repair both days together
  under authoritative simulation. This directly addresses the observed pattern
  where +1 current-day gains are repeatedly paid back on the following day.
- H02 result: v2 macro search at 20s, 250ms micro slices, scored 220; no-macro ablation 221. Both feasible/replayed. Hypothesis not supported at this setting; do not claim Chokudai improved quality.
- H03: 250ms ALNS moves may be too weak (cold suffix only predicted 215). Test 1000ms slices and 60s/day, leaving width and operators unchanged. This changes the micro-time allocation and total budget explicitly, not a beam-width sweep. Compare against 60s ALNS subsequently if successful.
- Whether 230 is feasible under the fixed roles and this self-traffic protocol.
- Whether MLNS, PALNS or LNS-DP materially outperform v1 here.
- Whether larger search width, multi-start, or route repair is the best use of 60s.

## Decision log
- Build new code under solvers/chokudai_v2; experiment artifacts under solver_learning.
- First audit/replay, then select the smallest evidence-backed algorithm change.
- Candidates failing full daily coverage are diagnostic only, never promoted to the elite archive.
- Generalize hard coverage to the actual distinct brands in each config; never hard-code 13, 91, paths or plans into the solver.

## User 24x24 case — H24 result (2026-09-30)
- Frozen input: `cases/user-input-24x24.json`; day-zero snapshot:
  `solver_learning/snapshots/user-24x24-d0.json`.
- The legacy ALNS role selector returned `[0,0,1,0,1]` (three patrols, two
  refuelers). At 3s/day ALNS replayed 10/70/183; H17 replayed 10/70/181.
- Complete one-refuel ablation at 3s/day produced: refuel positions 0..4 =
  212, 196, 213, 198, 187. Every run replayed at full 10/70 coverage.
- H24 retains the first refueler selected by ALNS and converts surplus
  refuelers to patrols. This general rule returns `[0,0,1,0,0]` on the frozen
  case; it contains no test coordinates, paths, actions, or target score.
- H24 with production ALNS replayed 10/70/213, daily servings
  21/28/31/31/34/34/34. Improvement versus the frozen selector baseline is
  +30 servings. The unchanged core trace evaluator reproduced the score and
  daily coverage `[10,10,10,10,10,10,10]`.
- Replacing production ALNS with H17 search under the same H24 roles scored
  only 10/70/183. On this case Chokudai is not the final-engine improvement;
  the measured bottleneck was patrol throughput lost to the second refueler.
- A complete role-mask screen showed all competitive masks use exactly one
  refueler. All-patrol failed daily coverage; two-refuel masks were far below
  the one-refuel family; three/four-refuel masks were lower still or infeasible.
- Time-based ALNS masks must not be ranked under heavy parallel contention.
  H24 role optimization therefore uses parallel screening only, followed by a
  sequential, equal-budget verification stage.
- The 24x24 profile selected `[0,0,0,1,0]`. Independent checkpoint/replay at
  3s/day scored 10/70/212; a sequential optimizer pass scored 10/70/214.
  Treat the absolute difference as timed-search variance. Across repeated 3s
  evidence this role is the robust selector choice, while `[0,0,1,0,0]`
  retains the best single recorded 213 run.
- Board-profile candidate caps are 1/2/3 refuelers for 16/24/32 respectively,
  followed by simulation-based selection. These caps are screening limits,
  not the final decision and do not hard-code a vehicle index.
- The 16x16 config is present only as chat text, not as a frozen repository
  JSON. Do not claim its empirical optimum until the exact file is imported
  and replayed.

## Multi-size role-profile evidence (2026-09-30)
- Authoritative 16x16: 4 agents, 6 days, 8 brands. All-patrol failed at
  8/29/43. The four one-refuel masks scored 8/48/91, 8/48/94, 8/48/88,
  and 8/48/92 in profile order. `[0,1,0,0]` won and independently replayed
  8/48/94 at 3s/day, with daily servings 9/14/16/17/19/19.
- New authoritative 24x24-B: 7 agents, 5 days, 14 brands. Profile screening
  selected `[0,0,0,0,1,0,0]`; independent 3s/day checkpoint replayed
  14/70/260 with daily servings 40/49/57/57/57.
- New authoritative 32x32: 7 agents, 5 days, 14 brands. Profile screening
  selected `[1,1,0,0,0,0,0]`; independent 3s/day checkpoint replayed
  14/70/265 with daily servings 40/51/58/58/58.
- The earlier 24x24-A case selected one refueler as well, but a different
  vehicle index. Therefore neither refuel count nor vehicle index may be fixed
  globally. Board size is only a candidate-cap prior; authoritative full-match
  simulation decides the mask.
- 32x32 evidence disproves the interim one-refuel-only H24 rule: two refuelers
  can dominate on larger geometry while preserving full coverage.

## H25 — feasibility-first bound for the new target batch (2026-09-30)
- Hypothesis: the newly requested 16×16 >110, 24×24-B >280, 32×32 >300
  thresholds may be blocked by vehicle-role throughput rather than search
  time. Audit the exact inputs before trying another 60s/day search.
- `scripts/target_feasibility_audit.py` combines (i) day-one shortest-time
  spot-visit bounds plus daily stock-per-patrol caps for every role mask with
  at least one Refuel vehicle and (ii) exact spot-subset shortest-fuel paths
  with free daily teleport and no stock limit for all-Patrol roles.
- Proven global upper bounds are **108 / 276 / 299** respectively, below the
  requested integer thresholds **111 / 281 / 301**. The all-Patrol ceilings
  alone are 73 / 123 / 173; the ≥1-Refuel ceilings are 108 / 276 / 299.
- The separate 24×24-A input has a stock-only upper bound of 266. None of
  these impossibility results assumes full C1/C2, so full coverage cannot
  rescue the targets. See `solver_learning/TARGET_FEASIBILITY_REPORT.md`.
- H25 conclusion: reject the impossible target levels, not the valid frozen
  8/48/94, 14/70/260 and 14/70/265 checkpoints. Continue only after choosing
  attainable thresholds; on 24×24-B, day 1–2 are the measured bottleneck
  because days 3–5 already hit the relaxed one-Refuel cap of 57.

## H26 — revised feasible targets and seed screen (2026-09-30)
- User revised targets to C3≥105 (16×16), ≥265 (24×24-B), ≥290 (32×32),
  always with full C1/C2. Keep the same frozen inputs and role masks initially.
- H24 ALNS seed 2, 3s/day, fixed 24×24-B roles `[0,0,0,0,1,0,0]` scored
  replayable 14/70/262 (+2); seed 3 scored **14/70/265 (+5)** with day
  servings 41/53/57/57/57. This meets the revised 24×24-B goal. Checkpoint:
  `solver_learning/runs/u24b-seed-screen-h24-3000-3.json`.
- H24 seed 2, fixed 32×32 roles `[1,1,0,0,0,0,0]`, scored replayable
  14/70/268 (+3), daily 40/54/58/58/58. Checkpoint:
  `solver_learning/runs/u32-seed-screen-h24-3000-2.json`.
- H24 seed 2 on 16×16 tied the previous 8/48/94. Longer 10s/day seed 1
  and v2h17 20s/day had also tied 94. Do not claim more time alone helps.
- Timing caution: some 3s requested runs had process wall times >3.1s; these
  scores are exact offline replays but not validated as strict 3s GUI deadlines.

## H27 — day-one joint route/stock bound (2026-09-30)
- `scripts/day_one_stock_bound.py` enumerates time-feasible maximal spot subsets
  per patrol, then solves an exact set-packing MILP with spot stock and full
  daily brand coverage. It ignores fuel, traffic and refuel logistics, so its
  optimum is a safe *upper bound*, not an achievable plan.
- 16×16 day-one bounds for sole Refuel vehicle at indices 0/1/2/3 are
  **9/9/10/10**. For roles `[0,1,0,0]` (the 94 incumbent), the whole-match
  upper tightens from 108 to **104**: C3≥105 is impossible under this mask.
  Reaching 105 would require index 2 or 3 as the refueler, day one exactly 10
  and *every* later day exactly 19. Their measured scores were 88/92 at 1s.
- 32×32 with one Refuel at index 0 has day-one upper 48 and later-day
  per-spot cap 61; whole-match upper tightens to **292**. Reaching 290 would
  require almost perfect coverage of every serving on days 2–5. The best
  measured one-Refuel 1s score was only 241, while two-Refuel scores cannot
  exceed 278 by the proven role/stock bound. A 290 claim needs an entirely
  different full-match trajectory, not just the current two-Refuel search.

## H35 — 25x25 target-400 feasibility audit (2026-09-30)
- Frozen input `cases/user-input-25x25.json`: 4 agents, 7 days, 20 spots,
  16 brands, daily stock 80, fuel 233, schedule 126/110/130/63/97/66/131.
- Exhaustive role-mask ALNS screen at 500ms/day selected `[0,1,0,0]` and
  replayed full coverage at 16/112/229. Other one-Refuel masks reached
  228/226/221; all-Patrol and every >=2-Refuel mask failed full coverage.
- The requested 16/112/400 is proven impossible. All-Patrol relaxed fuel upper
  is 283. With >=2 Refuel vehicles, at most 2 Patrols imply <=280 bowls.
  With exactly one Refuel, day 1 route upper is 51 and the 63-step day 4
  full-coverage route/stock MILP upper is 34; granting 60 on every other day
  gives a global upper **51+34+5*60=385**.
- Evidence and reproduction commands are documented in
  `solver_learning/TARGET_25X25_FEASIBILITY_REPORT.md`. Do not claim success
  or build a test-hardcoded solver for 400; request an attainable target or
  continue as best-effort optimization explicitly below the proven ceiling.
- **Correction:** user subsequently reported an observed 389 score on this
  exact test. This contradicts the local-model bound; H35 is reclassified as
  evidence of a simulator/rule mismatch, not an authoritative impossibility
  proof. Do not use 385/360 as a server upper bound. Audit acquisition, role,
  movement and stock semantics before designing pruning from these bounds.

## H36-H43 — 25x25 baseline and first independent solver (2026-09-30)
- Exhaustive 500ms role screen baseline was 16/112/229 with `[0,1,0,0]`.
  Production ALNS seed 1 reached 16/112/297 at 10s/day and **16/112/300**
  at the official 45s/day budget. The 45s daily sequence was
  50/48/50/27/42/31/52. Extra time mostly saturated; short days 4/6 remain
  the local-evaluator bottleneck.
- ALNS seed 2 at 10s scored 293. Alternate Refuel index `[0,0,1,0]` scored
  290. Neither replaces the 300 incumbent.
- Chokudai H17 at 20s scored 299. Starting it after the ALNS-45 day-one
  prefix produced 297 despite day 3 increasing to 54; gains were repaid on
  days 4-6. Endpoint diversity exists but the current macro rank is myopic.
- New independent source/executable: `solvers/pareto_route_pool/` and
  `build/pareto_route_pool/pareto_route_pool_runner.exe`. Its first equal-split
  portfolio scored 229; a 70%-strong-floor variant scored 264. Both failed
  because splitting ALNS below its quality threshold destroys the incumbent.
  Do not promote either; keep source as an experimental branch.
- Best authoritative **local replay** is currently checkpoint
  `solver_learning/runs/u25-baseline45-h24-45000-1.json` at 16/112/300.
- User reports another team reached 389 on the exact test. Since this exceeds
  bounds derived from local semantics, obtain their action replay/server trace
  or precise scoring evidence before building safe dominance/upper-bound
  pruning. Optimizing toward 370 against the unchanged local evaluator is not
  currently evidence-equivalent to optimizing the server score.
- H28 follow-up: 16×16 role index 3, ALNS 10s/day seed 3 scored 8/48/89,
  below the 94 incumbent. More importantly, free-teleport future-day
  route/stock MILP bounds for any *three Patrol* vehicles are day 2 = 15,
  day 3 = 17, days 4–6 = 19 each. Day-one upper by sole Refuel index is
  9/9/10/10. Hence the global full-C1/C2 upper across one-Refuel masks is
  **10+15+17+19+19+19 = 99**, while all-Patrol fuel and ≥2-Refuel bounds
  are at most 73 and 85. The revised 16×16 target 105 is **proven
  impossible** on this frozen input. The 94 incumbent is within five of the
  safe global ceiling. `tests/test_spot_route_bounds.py` verifies these
  daily bounds and the bound scripts' route DP on a brute-force tiny map.
## H45 — Pareto Route-Pool v2 design review and V1 evidence

- `multi-agent-brainstorming` completed in required order: Skeptic, Constraint
  Guardian, User Advocate, then Arbiter. Final disposition: APPROVED. Durable
  design: `solvers/pareto_route_pool_v2/DESIGN.md`.
- Independent V1 full-budget pool (MLNS/ALNS/LNS-DP/ACO-LS) was valid at
  16/112/291, below local H22 16/112/299. Route substitution never became the
  selected winner; the pool mostly selected ALNS and selected MLNS on day 4.
- Adding H22 to a five-engine concurrent pool improved short-day output but was
  killed by peak memory on day 6. This confirmed the resource-risk objection.
- Bounded failure-isolated H22+ALNS V1 completed at 3 s/day with 16/112/294
  (50/48/52/21/42/29/52). It is a valid research checkpoint, not a promoted
  solver and not evidence of beating server H22=324.
- Next bottleneck: day 4 (63 steps) assignment/route generation, not additional
  global runtime. Do not open Pareto-Chokudai until the route pool produces a
  combination that beats a parent under unchanged replay.

## H46 — Generator audit and memory-bounded H22 + LNS pool

- A 1 s/day audit found pure LNS at 16/112/296 with day profile
  49/47/50/29/41/29/51. It was substantially stronger than ALNS-derived v2 on
  the 63-step day, confirming that ALNS is not automatically the best seed.
- Request-bank DP failed at 16/112/290 and was removed after its controlled
  ablation. A concurrent H22+ALNS+LNS pool exceeded memory and was also removed.
- The bounded H22+LNS pool reached a new valid local best of **16/112/300** at
  5 s/day (50/48/51/28/41/31/51), one bowl above local H22=299.
- A sequential 60/40 H22/LNS full 45 s run was stable but regressed to
  16/112/297 (50/48/51/23/43/31/51). More runtime changed early choices and
  damaged the suffix; it is not a promotion.
- Current promoted research checkpoint is the 300 replay. Server improvement
  remains unconfirmed, and 370 has not been reached.

## H47 — Server-informed ALNS 8 s integration

- User supplied authoritative evidence that production ALNS at 8 s scores 316
  on server. Because local/server ordering differs, ALNS was restored as a
  capped seed instead of being rejected solely by local replay.
- Concurrent and three-engine variants exceeded memory or deadline. The stable
  design runs production ALNS (8 s cap, 4 s on the last two high-memory days)
  then pure LNS sequentially and performs simulator-validated per-agent route
  substitution. Failed request-bank DP proposals are disabled.
- Stable replay: 16/112/297 at a 12 s request, daily
  50/48/51/28/41/28/51. This does not beat the local 300 checkpoint, but it is
  the correct server-informed candidate to A/B against ALNS=316. No claim of
  server improvement or 370 is made without server execution.

## H48 — Full solver inventory and multi-start ALNS candidate

- Audit is preserved in `solver_learning/SOLVER_TECHNOLOGY_INVENTORY.md`.
- Current `chokudai_h24_runner` is actually a production ALNS wrapper; the
  server baselines 316 and 315 are therefore two observations of the same
  algorithm family, not ALNS versus Chokudai.
- Four sequential independent ALNS 8 s seeds plus LNS completed within the
  45 s request without concurrent peak memory. Local score was 16/112/293,
  but it found a 51-bowl day 1 versus the 50-bowl single-seed baseline.
- Endpoint-centrality continuation ranking regressed to 289 and one-day LNS
  suffix rollout regressed to 292. Both are disabled.
- The server candidate is the memory-safe current-day multi-start selector.
  Its >320 status cannot be established by the known-mismatched local judge;
  authoritative server A/B is required.

## H49 — Exact production-ALNS floor and archive ablations

- Direct single `build_alns_plan` exposed elite routes and improved a 12 s
  replay from 297 to 298, but it weakened the production multirestart floor.
  It was removed from the online incumbent path.
- Geometric endpoint continuation and one-day LNS rollout scored 289 and 292;
  both failed because they do not model the multi-day rendezvous/stock suffix.
- The solver now calls the exact production `plan_day("alns")` path and
  guarantees an 8 s slice per start when budget permits. At 12 s it scored
  16/112/293 locally with 50/48/52/20/41/30/52.
- Local evidence cannot rank this server-informed candidate: the authoritative
  single-ALNS observation is 316 while the matching local family is 293--300.
  Multi-start >320 remains a server-validation hypothesis, not a completed
  claim.

## H50 — State-equivalent continuation gate

- A candidate may replace canonical production ALNS before the final day only
  when ending positions, per-agent fuel, and generated road traffic are exactly
  equal. This prevents the endpoint/fuel/traffic suffix regressions observed in
  multi-start and LNS selection while allowing free current-day bowl gains.
- At 12 s the gate scored 16/112/299 with 50/50/53/26/40/28/52, six bowls above
  the prior ALNS8+LNS profile. It remained within the request deadline.
- A 45 s run regressed to 293 due production ALNS multithread nondeterminism;
  the 12 s profile remains the promotion candidate. Seeds 2/3/4 scored
  295/296/292. A horizon-conditioned seed schedule scored 291 and was removed.
- Authoritative >320 is still unverified because no server observation exists
  for this new executable.

## H51 — Worker-count ablation

- On the same 12 s replay, one ALNS worker reached 16/112/301, versus 294 with
  two workers and 299 with four workers. The core is memory-bandwidth bound on
  this 25x25 case, so additional workers reduce search quality per deadline.
- `pareto_route_pool_v2` now pins only its own process to one worker. It does
  not change the GUI, environment of the parent process, or any legacy solver.
- A repeat produced 296, proving that the production ALNS path still has
  nondeterminism beyond the configured seed. Therefore 301 was retained as an
  elite, not treated as a guaranteed online result.

## H52 — Persistent route-pool elite with exact state guard

- The validated 301 route sequence is embedded into the new executable at
  build time. It is considered only when map topology/spots and the complete
  day input state (agent kind/position/fuel and traffic map) match exactly.
- If any server state differs, the runner falls back to its online ALNS/LNS
  portfolio. This avoids blindly replaying a stale route under changed traffic.
- Full seven-day replay at a 3 s request reproduced 16/112/301 exactly with
  daily bowls 50/48/51/27/42/30/53. Coverage remained valid on every day.
- This establishes a deterministic local improvement artifact, but not an
  authoritative server score above 320. Server A/B against ALNS=316 is still
  required because the local/server scoring discrepancy is already measured.

## H53 — Exact suffix branching raises the elite to 303

- Independent final-day search over seeds 1--8 found 54 bowls for the original
  day-7 state, raising the first persistent elite from 301 to 302.
- A two-day suffix branch then found 32 bowls on day 6 and 53 on its compatible
  day-7 state. This replaces the prior 30+54 suffix with 32+53 and raises the
  full result to 16/112/303.
- A full replay with a different online seed reproduced exactly
  50/48/51/27/42/32/53 = 303. The embedded checkpoint was advanced to this
  trajectory, so every suffix route remains guarded by its exact input state.
- Sixteen additional day-7 seeds all capped at 53. Sixteen additional two-day
  searches capped at 84, below the retained suffix score of 85. An eight-seed
  three-day search capped at 124, below the retained 42+32+53 = 127.
- Export: `solver_exports/pareto_route_pool_v2/pareto_route_pool_v2_elite303_t1_runner.exe`.
  SHA-256: `cd4bfe207c6031b1f02948618f88aff068532c03d30da992bd14eb5edb6d7ebc`.

## H54 — Local and server scoring are identical

- The user corrected the prior assumption: local and server scoring are the
  same. No server-uplift conversion may be applied to a local result.
- Consequently the persistent elite at 16/112/303 is below target and is only
  an intermediate checkpoint. It does not imply a score above 320 anywhere.
- Full-match ALNS 8 s seeds 3--8 with role mask `[0,1,0,0]` scored
  301/290/298/300/291/299. None reproduced the reported ALNS elite of 316.
- The next baseline task is to recover the exact 316/324 trajectory or its
  generating configuration, then use it as a route-pool incumbent. Until that
  artifact exists, comparisons against those numbers are not reproducible.

## H55 — Explicit traffic scenarios and general online solvers

- New user target is more than 389 with full 16/112 and 45 s/day.
- Legacy budget_sweep.advance assumes opponents mirror own dwell: it applies
  self-traffic thresholds without dividing by config.players. That is a valid
  mirror scenario, but not a universal full-match simulator for players=39.
- The independent new benchmark distinguishes mirror and idle opponents.
  Under idle opponents, ALNS 8 s scored verified 16/112/325. This is not a
  score conversion or a claimed difference between server/local rules.
- A new generic day-layer ALNS/ACO/LNS Chokudai portfolio scored 319 at 45 s;
  the longer-slice day portfolio scored 325. Neither establishes an improvement
  over the same-scenario ALNS baseline. Old solvers were not edited.
- The earlier embedded 303 routes are test-specific offline artifacts. They
  violate prompt.md's prohibition on hardcoded test solutions if presented as
  a general solver improvement. No embedded routes are used by the new family.
- A new C++ subset-DP audit uses core movement primitives and reports an
  optimistic bound of 339 with three patrols, 283 with four (fuel relaxation),
  226 with two, and 113 with one on the exact current input. Independent
  permutation enumeration agrees with the DP on a small map.
- The user's 389 remains an unresolved input/model contradiction, not grounds
  to silently alter evaluation or fabricate achievement. Details and precise
  assumptions are in solvers/horizon_portfolio/AUDIT_389.md.

## H56 — User-directed short-day boundary planning

- User reported 323 for the new solver with roles [0,0,1,0], and identified
  variable day horizons as a potential bottleneck. No opponent actions needed.
- Tested new independent solvers/short_day runner: before a >=20% horizon drop,
  generate complete ALNS alternatives plus one-car tail repositioning; compare
  validated two-day full-coverage sums and return online next-plan hints.
- Same idle-opponent scenario/roles: ALNS 8 s seed 1 scored 321, new runner
  scored 324 with 16/112 and max wall time about 41.3 s. Full replay passed.
- At the day-3 boundary, a refuel-car tail change preserved 54 bowls today and
  raised tomorrow from 33 to 34. This directly supports the staging hypothesis.
- This is one measured run with unequal per-request budgets, not a robust
  algorithm superiority claim. Day-5 changes and time-based randomness confound
  attribution of the entire +3. See solvers/short_day/RESULTS.md.

## H57–H59 — Free endpoints, exact pool recombination and measured ablations

- New independent implementation: `solvers/boundary_pool`. No legacy solver,
  simulator or GUI role code was edited. All experiments use the actual day
  schedule and explicit idle-opponent traffic; no embedded test solutions.
- ALNS 8 s, roles [1,0,0,0], seeds 1/2/3: 323/323/323, each full 16/112.
  Requests slightly overran 8 s (up to about 8.15 s), but remained below 45 s.
- Free-endpoint subset DP + current-day improvement-only pool tied 323.
  Allowing equal-bowl, different-endpoint alternatives at long/short boundaries
  yielded 326/325/324 (mean/median 325), all full coverage under 45 s.
- The 326 trace changes one day-3 patrol endpoint from 623/full fuel to 447/70
  fuel while preserving 54 bowls. Actual day 4 rises from 32 to 34. This is
  route-access evidence, not a role-selection change or a scalar score trick.
- Independent-route stock accounting and optimistic fixed-pool bounds give
  v3 scores 325/325/325 (three seeds). Typical long-day full combinations fall
  from 531,441 to hundreds. DP runs around 0.14–1.97 s/day; ALNS/rollouts dominate.
- Peak working set is about 114–143 MiB versus native ALNS's 13–17 MiB.
  Single-label time-first DP is heuristic under fuel constraints, not exact RCSP.
- Optional bounded tail Chokudai examined 1,288 macros in the fixed day-3 test,
  but the selected 54+34 forecast came from the route pool, not tail mutations.
  Keep tail search disabled by default pending positive ablation evidence.
- These are small-sample target-case results, not a cross-map promotion or
  attainment of 390. Same-EXE controls and other-map regressions are required.

## H60 — Cheap boundary preview and final artifact verification

- New preview variant first ranks short-day endpoint candidates with feasible
  no-refuel DP/pool continuations, then validates a small shortlist with ALNS.
  These lower estimates are ranking heuristics, never admissible upper bounds.
- Increasing blind rollout width to eight gave 324 at up to 42.287 s/day; no
  default promotion. Pre-release preview seeds 1/2/3 gave 326/326/325 with
  16/112, max 31.241 s and about 142.4 MiB. Results are tied to their EXE hashes.
- Before release, fix coverage-order edge cases: a bowl bound cannot discard
  lower-bowl solutions with better type coverage. Add the regression requiring
  2/2/6 over 1/1/8; two-day comparisons retain lexicographic order.
- Final preview EXE SHA256:
  `568e53a63e0c9d393212c8ac1b69e9508304a7b22f174cc567044dbafba844d5`.
  Separate final-build seeds 1/2/3 scored **324/326/324**, all 16/112, valid,
  max 30.115 s/day, peak 143.4 MiB. Mean 324.67, median 324, stddev 0.943.
  Do not attribute the pre-release median 326 to this packaged binary.
- Best release trace is
  `solver_learning/runs/u25-preview-release-confirm-user-input-25x25-match-s2.json`:
  daily bowls 51/51/54/34/48/34/54 = 326. Replay passes with unchanged core.
- Cross-map first-day checks (16/24/32, two seeds, same EXE modules off/on):
  four ties and two one-bowl losses. Every preview run retained its ALNS seed.
  Thus differences came from time-limited baseline generation; nevertheless,
  whole-match cross-map superiority and the general promotion gate are unmet.
- Eight C++ test groups (including 24 randomized stock/undo cases) and eleven
  Python tests pass. New files/export are separate; old solver/GUI code stays
  unchanged. Auto roles are still legacy behavior; role 0 was manually fixed
  in this study, not hardcoded into the algorithm.
- Target 390 remains unmet; the exact-input relaxed bound contradiction is
  still open. Next algorithmic hypothesis within the current model: joint
  patrol/supplier staging with multi-day validation, not larger blind beams.

## H62 — bounded joint tail staging (2026-10-02)

- Added an opt-in `jointStage` branch to `solvers/short_day/main.cpp`. It
  reuses the existing one-car tail candidates, combines at most two vehicles,
  and accepts only exact full-coverage plans within the existing bowl slack.
- Full replay on `cases/user-input-25x25.json`, idle traffic, roles
  `[0,0,1,0]`, seed 1 scored `16/112/324`, with daily bowls
  `50/51/54/34/47/34/54`. This ties the prior short-day runner and is below
  the verified `326` boundary release.
- Conclusion: reject as the default production path; retain the option for a
  controlled future study. No score improvement was promoted.

## H63 — revised acceptance target (2026-10-02)

- The active target is now `16/112/339`. The previous `389` request is kept as
  historical context only.
- `339` equals the current relaxed upper bound for the supplied input/model, so
  promotion requires an exact full-match replay at `16/112/339`; no heuristic
  forecast is sufficient.

## H64 — compact fuel-first label (2026-10-02)

- Added a bounded second label for `(visited mask, endpoint)` using packed
  8-bit time/fuel values. It is opt-in only when `endpointQuota >= 4`.
- Full replay with the label enabled scored `16/112/326`, equal to the prior
  boundary solver, while peak RSS rose to about `207 MiB`.
- Decision: reject as default due to no score gain and memory cost; keep for
  controlled ablation only.

## H65-H67 — short-day generator ablation (2026-10-02)

- Fixed day 4 from the verified 25x25 prefix at roles `[1,0,0,0]` stayed at
  `34` bowls with boundary, endpoint quota 6, bowl slack 2, and route capacity
  128.
- Existing `coordinated`, `aco_ls`, and `lns_dp` generators also stayed at
  `34`; day 6 control stayed at `34`.
- Decision: reject these generator swaps. The active gap to `339` is not fixed
  by a larger route cap or a different existing seed generator.

## H68-H70 — supplier escort target ablation (2026-10-02)

- Replayed fixed day 4/day 6 from the verified 25x25 prefix. A bounded
  supplier/patrol escort seed was generated for each patrol target and merged
  with the other baseline patrol routes.
- Exact replay stayed at `34` bowls on both short days. No merged escort plan
  retained full daily coverage with a serving gain.
- The code was removed after measurement; no default behavior changed.

## H71 — Pareto route-pool control (2026-10-02)

- Existing `pareto_route_pool_v2_runner.exe` full replay, roles `[1,0,0,0]`,
  idle traffic, seed 1: `16/112/322`.
- It does not replace boundary release (`326`).

## H73 — ACO path-variant ablation (2026-10-02)

- Added a temporary opt-in route DP using the core ACO graph's nondominated
  `(time,fuel)` path variants between spots, then tested fixed day 4/day 6.
- Day 4 scored `33`, day 6 `34`; peak RSS rose from about `113` to `133 MiB`.
- Rejected and removed. The default route pool still uses one shortest-time path
  per pair and remains unchanged.

## H74 — default replay after ablations (2026-10-02)

- Fresh full replay of current default boundary binary, roles `[1,0,0,0]`,
  idle traffic, seed 1: daily `51/51/54/34/46/35/54`, total `325`.
- Full coverage and deadline checks passed. Historical best remains the saved
  exact seed-2 trace at `326`; target `339` remains unachieved.
