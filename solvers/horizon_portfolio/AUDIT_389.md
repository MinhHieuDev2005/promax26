# Audit of the 389 target on the current input

The opponent result is user-reported and its actions are unavailable. This
document does not claim that report is false. It records a reproducible
incompatibility between 389 and the exact file plus evaluator available here.

Input: `cases/user-input-25x25.json`
SHA256: `b2848254d440fbd277f7e26982fffdb4957f187eb844bb7141bfe7e35540e544`

The file has four agents, 20 spots, stock four at every spot, initial fuel 233,
16 brands, and horizons `[126,110,130,63,97,66,131]`.

`src/core.cpp` permits only patrol agents to acquire, once per spot per agent
per day. Refuel agents do not acquire. Patrol fuel carries across days.

The new `reachability_audit` links the unchanged C++ core. It computes shortest
distances using `neighbor`, `terrain_time`, and `terrain_fuel`, then Held–Karp
subset DP over all 20 spots. The DP allows a free first spot and ignores fuel,
stock, synchronization, traffic, starting positions, and daily coverage in its
time relaxation. Thus it can only overestimate attainable bowls.

Minimum travel time for 0..20 distinct spot acquisitions:

`0,0,2,7,11,17,22,28,33,37,44,48,55,60,71,82,91,108,116,133,142`

With three patrols, the resulting optimistic daily bounds are:

`54,51,54,39,48,39,54`, totaling **339**.

With two patrols the time bound is 226; with one it is 113. With four patrols
and no refuel agent, a separate relaxation gives each agent a free start every
day, then allocates the total initial fuel to all agent-day routes using
knapsack DP. Its bound is **283**. This ignores per-agent fuel distribution,
so it too is optimistic.

Consequently 390 cannot be certified by this exact evaluator on this exact
configuration under any fixed role mask. Extra Chokudai width, ACO ants, or LNS
iterations cannot bridge an upper-bound contradiction. Differences worth
checking are the opponent's day horizons, agent count, fuel reset rules, or
the once-per-spot acquisition rule. There is no assumption here that server
and local scoring differ.

Separate traffic finding: the legacy Python benchmark effectively assumes all
39 teams generate identical traffic. The new benchmark explicitly distinguishes
that scenario from 38 idle opponents. ALNS 8 s scored 325 in the latter. This
is a scenario difference, not a change to the action evaluator or score formula.

New generic solver measurements, all under the idle-opponent scenario:

| Solver | C1/C2/C3 | Budget | Conclusion |
|---|---|---|---|
| Existing ALNS | 16/112/325 | 8 s requested | baseline; some requests slightly exceed 8 s |
| Horizon portfolio | 16/112/319 | 45 s | macro search slices weaken route generation |
| Day portfolio | 16/112/325 | 45 s | no gain over baseline |
| Subset route portfolio | 16/112/325 | 45 s | no gain; about 33--35.3 s/day |

These are honest intermediate measurements, not attainment of the 390 target.
The older pool-v2 embedded 303 checkpoint is not evidence of general solver
improvement and is not embedded in any of these new runners.
