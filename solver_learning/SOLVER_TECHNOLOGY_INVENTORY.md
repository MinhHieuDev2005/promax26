# Solver technology inventory

Date: 2026-09-30

## Production core

| Family | Implemented technology | Practical status on 25x25 |
|---|---|---|
| Greedy variants | nearest/utility/fuel-aware/stock-max/coordinated routing, precomputed shortest paths | Fast seeds; most fail full daily coverage alone |
| Local search | per-agent route substitution, deterministic best improvement | Useful safe mixer; limited by quality/diversity of input plans |
| LNS | route skeleton, four destroy and three repair modes, adaptive weights, simulated acceptance, fuel-aware decoding | Strong short-budget baseline: 16/112/296 at 1 s/day; day 4=29 |
| ALNS/PALNS | adaptive destroy/repair, ACO/legacy seeds, exact safe bounds, continuation projection, multi-restart | Strongest server evidence: ALNS 8 s=316; H24=315 |
| MLNS | rolling multi-day suffix, continuation-aware rank, portfolio restarts, planner state | Preserves future state but underperformed on this case at short budget |
| Simple LNS | whole-match genome, semantic refuel tasks, annealing, rolling route repair | Experimental; coverage failure on this case |
| LNS-DP | request-bank state, seven destroy/four repair modes, refuel schedule state | Experimental; 25x25 ablation regressed and sometimes overran deadline |
| ACO / ACO-LS | pheromone construction, nondominated resource paths, route substitution local search | Valid diversity seed but materially below ALNS/LNS here |
| STOP BP | column generation, label-setting pricing with dominance, revised simplex, branch-and-bound | Disabled for repeated brands/multi-stock, which this case uses |

## Standalone solver families

| Solver | Actual engine/technology | Important limitation |
|---|---|---|
| `chokudai_runner` | ruin/repair Chokudai queues over ALNS-derived candidates, hash/diversity | Older independent implementation |
| `chokudai_v2` / historical Hxx | suffix Chokudai, warm/elites, approximate diversity, optimistic bound, optional subset route DP | Route DP refuses more than 19 spots and joint combiner specializes in two patrols |
| `chokudai_h24_runner` | Despite its name, current `main.cpp` calls production ALNS directly | H24 is an ALNS profile/build, not a distinct Chokudai engine |
| `pareto_route_pool` v1 | feasibility-first ALNS portfolio | Equal/weighted portfolio allocation weakened the production floor |
| `pareto_route_pool_v2` | sequential multi-start ALNS, pure-LNS diversification, simulator-validated route substitution | New independent candidate; server promotion still required |

## Techniques present but not yet production-effective on this case

- Pareto/dominance resource paths in the important-node graph.
- Exact subset route DP, limited to at most 19 spots.
- Branch-and-price/set packing, limited to unit-stock unique-brand instances.
- Whole-match request-bank DP and refuel scheduling.
- Chokudai suffix search with warm states and diversity buckets.
- Multi-start/portfolio execution and continuation-aware ranks.

## Evidence-driven selection for the >320 candidate

1. Preserve production ALNS because server evidence is 316 at 8 seconds.
2. Run several independent 8-second ALNS seeds sequentially within 45 seconds;
   this adds stochastic basin diversity without concurrent peak memory.
3. Use remaining time for pure LNS, whose short-day profile is complementary.
4. Run authoritative simulation after every plan and per-agent substitution.
5. Reject request-bank DP, three-engine concurrency, and current STOP BP for
   this configuration based on measured regression, timeout, or applicability.

