# Short-day boundary planning

This independent runner tests whether end-of-day staging improves short days.
No prior solver is edited, and no test route is embedded.

Before a day with less than 80% of today's steps it:

1. Keeps a full-coverage ALNS incumbent.
2. Generates alternative full-day routes.
3. Rebuilds the last 12/20 turns of one vehicle toward a reachable spot.
4. Retains only simulator-valid, full-coverage plans losing at most 3 bowls
   relative to the staging source. Alternate ALNS routes are also considered.
5. Simulates the following day for diverse endpoint combinations and maximizes
   the unweighted two-day bowl sum subject to full coverage on both days.
6. Returns the selected current actions plus the generated next-day plan as
   optional online planner state. Next request resimulates this hint.

Revealed roads are used for today. Future roads are held constant as an explicit
forecast; this is not a prediction of opponent actions. State hints are tied to
the configuration, source day, and last committed actions.

On ordinary days the runner calls production ALNS for up to 8 s and compares a
valid warm plan if supplied. 45 s is the maximum permitted budget, not an
instruction to idle. Lookahead requests reserve 3 s for overhead.

Input/output follows the existing JSON runner protocol, including `op=roles`.
Explicit `day_info.agents.kind` determines roles for planning; no role is changed.

Build:

```powershell
rtk cmake -S solvers/short_day -B build/short_day -G Ninja -DCMAKE_BUILD_TYPE=Release
rtk cmake --build build/short_day --target short_day_runner -j 4
```

Benchmark role mask supplied by the user:

```powershell
rtk python solvers/horizon_portfolio/benchmark.py --exe build/short_day/short_day_runner.exe --budget 45000 --traffic idle --roles 0,0,1,0 --label my-shortday-run
```

Limitations: one-car tail changes cannot model all coordinated repositioning;
time-limited rollout estimates are noisy; two-day gains may affect later days.
Promotion requires complete-match replay, not just a favorable rollout sum.
