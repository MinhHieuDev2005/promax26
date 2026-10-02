# Horizon portfolio — experimental, no embedded test solutions

Target: full global/daily coverage and more than 389 bowls on the supplied
25x25 case, with at most 45 seconds per request. Target is NOT achieved.

Two independently selectable executables share only the new implementation:

- `horizon_portfolio_runner.exe`: day-layer Chokudai over complete remaining
  match trajectories. ALNS elites, ACO-LS and LNS provide macro actions.
- `day_portfolio_runner.exe`: an ablation with horizon one and longer engine
  slices. This measures whether broad future search loses to stronger routes.
- `subset_portfolio_runner.exe`: day portfolio with endpoint-preserving subset
  route proposals. It uses a single time-first fuel label, so it is heuristic
  under resource constraints. Full joint simulation validates up to eight
  alternatives per patrol. It reserves search time for route recombination.

Both use unchanged `hexudon_core` simulation to reject illegal or incomplete
coverage plans. Final acceptance maximizes bowls among fully covered suffixes.
ALNS adaptive destroy/repair supplies exploitation; ACO supplies different
route orders; route substitution tests joint plans, including fuel rendezvous
and stock constraints. The substitution step is coordinate local search,
not exact global set packing. State deduplication uses full serialized state
keys. Endpoint buckets and bounded queues are approximate diversity selection,
not safe Pareto dominance. No claim of full Pareto-Chokudai is made.

Warm suffixes are generated online, tied to map and last committed plan, and
resimulated under the next day's revealed roads. They are not test checkpoints.
The default future traffic forecast holds current observed roads constant.
An optional `search.trafficForecast` may be `observed`, `mirror`, or `idle`.
The latter two are scenarios, not observations of real opponents.

Build:

```powershell
rtk cmake -S solvers/horizon_portfolio -B build/horizon_portfolio -G Ninja -DCMAKE_BUILD_TYPE=Release
rtk cmake --build build/horizon_portfolio --target horizon_portfolio_runner day_portfolio_runner -j 4
```

Interface: JSON stdin/stdout, `op=roles` or `op=plan`, `config`, native
`day_info` (zero-based) or GUI `state` (one-based), `history`, optional
`planner_state`, and `search.timeLimitMs` / `randomSeed`. Return contains
`ok`, `plan`, `planner_state`, and diagnostics. Preserve `planner_state` between
days to use online suffix reuse. On failure no infeasible plan is submitted.

Benchmark:

```powershell
rtk python solvers/horizon_portfolio/benchmark.py --exe build/horizon_portfolio/horizon_portfolio_runner.exe --budget 45000 --traffic idle --label my-horizon-run
```

`--traffic idle` averages our observed dwell over all configured players and
assumes every opponent contributes zero. `--traffic mirror` assumes every
opponent contributes the same dwell as us, equivalent to the older benchmark.
Both use unchanged `bin/hexudon.exe trace` for every action and replay the full
sequence independently. Scores from different traffic scenarios must not be
ranked as solver improvements. Real-server equivalence needs matching traffic.

The subset variant retains the incumbent endpoints to preserve rendezvous
opportunities. It does not guarantee identical next-day fuel or road traffic;
the complete-match benchmark, not a one-day gain, decides whether to promote it.

Current limitations: graph/state copying and expensive complete-day proposal
generation limit expansions; forecast errors can invalidate stored suffixes;
the deadline reserve is empirical rather than preemptive; no exact joint route
pool optimizer or resource-label Chokudai micro-repair has yet been added.
