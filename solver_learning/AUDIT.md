# Audit before optimization

## Rules and feasibility

Source: problem.md:117-123, src/core.cpp:190-207 and 2090-2099.
C1 = cardinality of union of acquired brands over the match.
C2 = sum of daily cardinalities (NOT sum of newly discovered brands).
C3 = sum of successful acquisitions. A patrol can collect once per spot/day;
stock is shared within its team and reset each day. Refuel vehicles never collect.
Fuel and positions persist overnight; traffic uses the previous two days.
Agents may share cells: placement collision/empty-region fragmentation examples
in prompt.md are not literally mechanics of this routing problem.

The rules rank numeric scores lexicographically, not Boolean thresholds.
The user adds a strict maximum-coverage contract. On fixed Q06: C1=13 and C2=91.
For generic maps, derive B=number of brands and require B brands on every day.
A complete day's missing brand cannot be repaired on a later day for C2.
Thus rejecting such an already-completed-day prefix is safe for this contract.
It is NOT safe to prune a partial intra-day route just because it lacks a brand.

Q06 has 19 spots, 2 patrols and 1 refuel under frozen roles. Each spot has stock
3 but only two patrols can acquire there: 38 servings/day is a safe upper bound;
7 days give 266, not the naive stock sum 399. Day horizons are
136,103,133,91,105,79,169. The short day 6 and its incoming state warrant analysis.

## Solver inventory and mechanisms

All core dispatcher policies are in src/core.cpp:588-595,1680-1785.
All use simulator validation; legality is different from full brand coverage.
None proves full coverage is feasible on arbitrary input.

| Family | State and moves | Ranking / pruning / ordering | Search control and refinement |
|---|---|---|---|
| wait, hotspot | Fixed waits or movement toward one location | No global coverage objective | Sanity controls, not competitive solvers |
| greedy | Per-agent position, fuel, time, visited spots and stock; append target paths | New match/day brands, stock, distance; discard unreachable moves | Constructive, no beam/backtracking |
| utility_greedy | Same routing state | Weighted construction utility; not a hard full-coverage guard | Deterministic seed heuristic |
| fuel_aware | Same plus reserve/return checks | Fuel feasibility before target selection; retreat to refuel | Local safety does not guarantee daily brand coverage |
| stock_maximiser | Same | Remaining stock before novelty/distance | Myopic construction |
| coordinated | Joint first-target assignments and resource paths | Coordinate patrol targets and refuel staging | Bounded construction, useful seed |
| local_search | Complete action plans, replace one agent route from alternate seeds | Authoritative lexicographic tuple incl. fuel tie-break; invalid mutations rejected | Best-improvement coordinate descent, default passes=agent count |
| aco | Per-agent elapsed time/fuel, bitset visits, stock, meeting schedule | Pheromones on travel/meeting alternatives; reward novelty; simulator final rank | Configurable ants/rounds, config-derived RNG; can finish before wall limit |
| aco_ls | ACO with route substitution per ant | Same simulator score | One local pass before ranking each ant |
| lns / alns | Patrol visit skeleton + stable travel choices; ruin, repair, travel mutation | Simulator lexicographic score; UCB/MCTS operator selection, SA/reheat; optional admissible exact bounds | ALNS defaults 3 restarts vs LNS 1; continuation allocation on nonfinal days |
| palns | ALNS state + projected suffix | Current-day score primary, projected future breaks ties | Shared iteration ledger, cached projections; projection fallback near deadline |
| mlns | Routes/travel/replay plans for whole suffix | Simulates fuel/position/traffic transitions; official and discounted continuation ranking | Warm planner_state, beam seed (width 2/4/8 by mode), multi-day ruin/repair, SA |
| simple_lns | Whole-match patrol routes + explicit refuel task lists | Full replay with fuel/time and coverage ranking | SISR, route refill, refuel-task repair; warm suffix persisted |
| lns_dp | Request-bank routes + recharge DP + global rendezvous schedule | Current-day and scenario-graded two-day rank; adaptive ruin/repair | Five finalists; 60% main phase, reserved joint continuation phase |
| stop_bp / bp | Fuel-relaxed patrol columns and set-partition master | LP/label pricing, dominance and branching; exact simulator checks proposals | 70% timed ALNS warm start; capped instances; fuel/brand guard on nonfinal day |
| Chokudai v1 | Per-depth priority queues of visit skeletons; ruin 1-6 and reinsert visits | C1/C2 componentwise guard; current-day servings then fuel | Depth 6, width 96, branching 18, randomized quarter; exact signature by layer; restart each 128 expansions |

v1 keeps earlier depth queues between sweeps, so it is genuinely Chokudai rather
than a one-pass beam. Its search nodes omit persistent rendezvous choices and
whole-match future value. Seed ALNS gets min(12s,30% budget), continuation disabled.
The legacy solver's continuation-aware alternatives are therefore not equivalent
to v1's embedded ALNS seed, even with the same wall-clock budget.

## Measurement protocol

All 18 named audit policies use the exact frozen Q06 JSON, roles [0,0,1], seed 1,
4 workers, 3000 ms requested per day. `bp` is an alias of `stop_bp` and is not a
distinct algorithm. Native persistent planner_state is passed through for
policies supporting it. Actual time is recorded because some policies are
iteration-controlled, and time limits are cooperative rather than hard kills.

The 50s v1 run is a separate historical-baseline reproduction, NOT a fair-time
3s comparison. Every completed trial saves actions and is replayed a second time.
All local scoring uses the unchanged bin/hexudon.exe trace; this is not a claim
of independent verification by the competition server. No server requests made.

## Early evidence (not conclusions about all maps)

- LNS 3s: 13/91/223; ALNS 3s: 13/91/224. Replayable checkpoints saved.
- MLNS 3s: 13/91/204. Multi-day formulation alone does not establish superiority.
- Pure greedy 13/89/120 and coordinated 13/87/127 fail the required C2 maximum.
- ACO 13/91/185, ACO+LS 13/91/190: feasible inexpensive seed families.
- No claim that a heuristic's default numerical weights implement the user's
  strict constraint. The new solver must impose its own acceptance gate.

## Baseline bottleneck hypothesis to test, not assumed fact

v1's retained terminal fuel is only a tie-break after today's servings. For
Q06 the maximum current-day 38 does not imply a strong incoming state for the
next short day. Compare fuel/endpoints and actual replay of alternative suffixes,
not hypothetical blocked placements. Improving tomorrow at the cost of one
serving today is allowed only if the whole feasible suffix improves.
