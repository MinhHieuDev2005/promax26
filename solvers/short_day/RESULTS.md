# Short-day experiment on 25x25

Roles: `[0,0,1,0]`. Scenario: other 38 teams idle, using unchanged C++ trace
evaluation and explicit traffic averaging. User reports the previous exported
solver scored 323; its full trace is unavailable, so that is not a paired run.

| Day | Steps | ALNS 8 s baseline | Short-day runner |
|---|---:|---:|---:|
| 1 | 126 | 50 | 50 |
| 2 | 110 | 51 | 51 |
| 3 | 130 | 54 | 54 |
| 4 | 63 | 33 | 34 |
| 5 | 97 | 45 | 47 |
| 6 | 66 | 34 | 34 |
| 7 | 131 | 54 | 54 |
| Total | | **321** | **324** |

Both runs maintained 16 global types and all 16 types on each day (112 total).
New runner maximum measured wall time: about 41.3 s; ordinary days used about
6--9 s. Each complete action sequence was replayed successfully.

Evidence:

- `solver_learning/runs/u25-shortday-role2-alns8.json`
- `solver_learning/runs/u25-shortday-v1-role2-idle45.json`

The selected day-3 tail variant kept 54 bowls and staged the refuel vehicle at
447 instead of the baseline endpoint 623. The next-day forecast increased from
33 to 34 bowls and the executed day 4 achieved 34. Starting patrol fuel was not
the binding issue: the baseline already had two patrols with full tanks.

On day 5 the chosen alternate root gave 47+34 over two days, compared with the
same invocation's baseline forecast of 46+34. The full baseline trajectory had
45+34; the extra difference is entangled with changed earlier states and timed
ALNS search. Do not attribute all three bowls solely to tail staging.

This is one paired scenario/seed comparison, not a statistical improvement
claim. Baseline and new runner use different time allocations; an equal-budget
ALNS control and more seeds are needed to isolate algorithm benefit. It does
support the user's short-day bottleneck hypothesis with a concrete validated
boundary change. The result does not establish the requested 390+ objective.

## H62 joint tail staging (rejected)

An opt-in `jointStage` variant generated bounded two-vehicle tail combinations
and validated each complete plan with the unchanged evaluator. Full replay on
`user-input-25x25`, idle traffic, roles `[0,0,1,0]`, seed 1 scored
`16/112/324` (`50/51/54/34/47/34/54`), equal to the earlier short-day runner
and below the verified boundary best `326`. Peak memory was about 24 MiB and
the longest day was 41.3 s, within the 45 s limit. The option remains
available for future paired studies but is disabled by default.

Next meaningful extension: jointly reposition two patrols plus the supply car,
and preserve multiple promising boundary states through a third day when the
two-day gain might damage later fuel or traffic. Prioritize these states before
short days; do not run shallow full-match rollouts on every request.
