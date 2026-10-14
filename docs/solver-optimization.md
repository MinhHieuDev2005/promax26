# Solver optimization: agreed design

Baseline: `2fcec16`. Objective: maximize the lexicographic tuple
(match brands, cumulative daily brands, bowls), not a weighted average.

## Scope and decisions

- Use small, isolated experiments rather than rewriting the search or adding a hybrid solver.
- Preserve the baseline source and build outside the working tree. Do not replace the GUI binary.
- Run whole matches offline, with identical fixtures, seed lists, budgets and CPU affinity.
- Separate fixed-lineup routing experiments from end-to-end vehicle selection experiments.
- Keep discovery and held-out map seeds separate. Retain improvements only after validation.
- Do not POST to a competition server, capture tokens, or commit private match data.

Alternatives considered: multi-day rollout and a strategy portfolio. Both remain deferred
because their extra search/memory costs must be justified by measurements first.
The user approved the local-experiment approach and benchmark-first sequence.

## Architecture and opportunities

CLI/GUI -> protocol/session -> prematch selector -> per-day planner -> LNS/annealing
-> simulator -> submission filter -> next-day state.

1. `planDay` currently ignores its collected-brand argument; the client also passes zeros.
   A new-brand experiment must carry real progress through client and worker paths, not
   merely change an evaluation coefficient.
2. Annealing accepts candidates using today's score, but retains best solutions using
   today's score minus tomorrow's penalty. Test a consistent objective before adopting it.
3. Fuel reservation without supply vehicles is proportional to remaining day steps.
   Relaxation may help early coverage but can strand agents later; measure whole matches.
4. Nine move types are sampled uniformly even with no supply vehicles. Test excluding
   impossible supply moves; an iteration increase alone is not evidence of a score gain.
5. Tomorrow prediction rebuilds brand assignments and memoizes end states without an
   explicit cap. Profile before changing its fidelity or memory policy.

Routing is Dijkstra over the hex grid; initial routes use regret-based brand insertion
and cheapest feasible extra visits. LNS repairs perturbed routes and uses annealing.
Workers run independent seeds. Planning is time-bounded but initialization and individual
iterations can overshoot; the application also has networking/submission deadlines.

## Benchmark design

A standalone CMake target builds against any supplied source root. Each subprocess runs
one complete match, produces JSON metrics and sends solver logs to stderr. The runner
saves generated input, seed, source/fixture hashes, binary hash, budget, machine metadata,
wall time, peak RSS, per-day scores/fuel and validity. Processes run sequentially.

Fixtures cover open, mixed-terrain, sparse, fuel-tight and large maps with connected
passable cells and non-road spots. Fixed lineups isolate planning; auto lineups exercise
selection. Seeds are reproducible inputs, but wall-clock search and thread scheduling
are not bit-for-bit deterministic. Repeat close results before claiming improvement.

Compare paired lexicographic wins/ties/losses. Report component means separately, tuple
median/best/worst, p95 planner runtime, budget exceedances, peak RSS and valid rate.
Keep raw records, including failures. Missing runs or incompatible settings are errors.
No synthetic result should be described as a measured HAUI/server improvement.

## Reliability and limitations

Use 8 logical CPUs and the existing 3 GiB GUI limit as deployment targets; initial smoke
experiments may use fewer threads and shorter budgets, recorded explicitly. Benchmark
budgets are not proof of the real 60-second HTTP deadline. Use subprocess timeouts.
The harness models a single team and traffic from its previous two days. It does not
model opponents, HTTP latency, live submission adoption, or GUI day-zero preplanning.
The public simulator wraps the same simulator as search: validity checking is not an
independent rules oracle. Existing rules examples/unit tests and later real replays are
required before deployment. No recorded match inputs are bundled at this stage.

## Implementation order

1. Build the reproducible harness, exercise validation and archive baseline measurements.
2. Run isolated consistent-objective, feasible-moves and fuel-reservation pilots.
3. Validate promising changes on held-out fixtures and longer budgets.
4. Only promote measured improvements; otherwise retain baseline and document rejection.
5. Address collected-brand handling across all callers as a separately tested change.

No production behavior changes or automatic deployment are implied by a successful
benchmark harness. Experimental source copies and raw outputs remain under `results/`
or a separate WSL build directory; documentation records what actually ran.

## Round 2: frozen hypotheses and acceptance criteria

No commit or push is authorized. Even a measured improvement requires explicit user
approval before committing. The GUI executable remains unchanged.

- Adaptive fuel: reduce the computed reserve by 20% only when today's step count is
  greater than the full tank capacity. Keep the original rule otherwise and with supplies.
  This is a heuristic pressure indicator, not a proven physical fuel requirement.
- Brand history: pass real acquired brands through local and LAN callers, prioritize
  uncollected brands during initial assignment/repair, and add a new-brand score term.
  Use a coefficient exceeding the maximum cumulative daily-brand term; test missing,
  noncontiguous and already-complete brand histories explicitly.
- Temperature: keep the original objective and use an initial temperature scaled by
  sqrt(max(1, spot_count / 8)); preserve the final temperature and time schedule.

Discovery uses map seed 29 and search seeds 1,2; held-out seed 71 uses search seeds 3,4.
The three new fixture families (tight8, tight32, coverage16) are specified before results.
Run variants separately, then validate promising ones with automatic vehicle selection,
multiple threads and longer budgets. Do not combine unvalidated patches.
Retain a candidate for review only with paired held-out wins exceeding losses, no invalid
plans, and no unexplained deadline regression. Report brand regressions separately and
repeat close differences. No claim of statistical significance or live-server superiority
is justified by a single time-bounded pilot.

Round-1 explanations involving annealing temperature or wasted supply operations were
hypotheses, not measured causes. Control runs can differ despite identical seeds because
the search is wall-clock bounded. A single baseline batch cannot prove which candidate
is globally best. Round-2 summaries count missing days as local deadline failures.
