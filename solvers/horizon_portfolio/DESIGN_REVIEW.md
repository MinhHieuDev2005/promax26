# Practical algorithm assessment

Objective: lexicographic global types, daily coverage, bowls; accepted suffixes
must have full daily coverage. Actual current-day roads are authoritative.

## Implemented experiments

1. Day-layer Chokudai: queues retain endpoint/fuel alternatives across sweeps.
   An expansion runs ALNS, ACO-LS or LNS to generate a complete-day macro action.
   Full suffix score accepts solutions; incomplete layers use bowls/fuel ranks.
2. Independent current-day portfolio: longer engine slices, same validation.
3. Subset route repair: shortest paths between spots, bitmask DP, fixed endpoint,
   fuel feasibility, then enumerate combinations and validate the joint plan.

The first is appropriate when today loses a little but enables a much better
short day tomorrow. Its measured weakness here is expensive macro generation:
only dozens of expansions fit in 45 seconds, and small slices weaken ALNS.
Ordinary beam would discard unexpanded alternatives; Chokudai preserves them,
but this alone does not compensate for low proposal quality.

## Next algorithms ranked by specific value

1. Fast multi-label subset route generation: retain Pareto time/fuel labels,
   warm start from incumbent, bound by remaining reachable spots. Current
   single-label DP can miss resource-efficient alternatives.
2. Exact route-pool assignment: with 3 patrols and 8 routes each, 512 joint
   combinations are tractable; larger pools need stock/type-mask pruning.
3. ALNS repair with multi-label routes: replace its repair component in a new
   module, keep adaptive destroy and the production incumbent as a baseline.
4. Endpoint-conditioned two-day repair: particularly before days 4 and 6,
   whose horizons are 63 and 66. Optimize access to rare brands and refuel.
5. Rendezvous scheduling: explicit patrol/time/location requests, then refuel
   route insertion. No complete team movement Cartesian product.
6. Micro Chokudai over route fragments: candidate macros are spot visits or
   refuel meetings, not entire expensive ALNS calls.
7. Weighted LDS over near-tied target choices: useful for a strong greedy
   decoder, but cannot improve a planner whose resource model is wrong.
8. ACO pheromone sharing across independently generated feasible route pools:
   helps preserve uncommon orders, but requires an ablation against seeds alone.
9. Ejection chains across the three patrols: short chain lengths 2--3 only,
   with exact simulation after repair. Stronger than single-route replacement
   when gaining a rare type displaces a target on another car.
10. Faster hashing/arena storage only after profiling shows queue overhead
    matters. Current bottleneck is proposal generation, not hash lookup.

MCTS, NRPA and genetic search are deferred: no current evidence their rollout
cost is justified over ALNS route proposals. Parameter tuning cannot resolve
the input/model contradiction documented in AUDIT_389.md.

## Three architectures

| Architecture | Pipeline | Practical cost / memory | Tradeoff |
|---|---|---|---|
| A | ALNS 8 s + ACO/LNS + route substitution | bounded by 45 s; legacy engine arenas | implemented day variant; 325, no gain over ALNS |
| B | A + subset Pareto routes + exact small pool assignment | O(2^S S^2 L) labels; S=20 single label costs about 100 MiB per patrol processed sequentially | single-label prototype implemented; Pareto version pending |
| C | B + macro Chokudai + two-day rendezvous repair | bounded queues, route-pool caps, time-driven search | full-day Chokudai prototype gives 319; micro repair is needed |

Online: use revealed state, validate every returned plan, recompute forecasts.
Offline: compare scenarios/seeds, tune budgets, inspect route bottlenecks.
Offline test-specific actions must not be embedded as general solver behavior.
