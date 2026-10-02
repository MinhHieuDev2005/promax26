# 25x25 target feasibility audit

Date: 2026-09-30

Input: `cases/user-input-25x25.json`

Input SHA-256: `b2848254d440fbd277f7e26982fffdb4957f187eb844bb7141bfe7e35540e544`

Requested score: **16 / 112 / 400**, with 45000 ms per day.

## Status correction

**RETRACTED.** The user has confirmed that local and server scoring are the
same. The earlier claim of a semantic local/server discrepancy was therefore
incorrect. The 389 observation also disproves the bounds below as models of
the actual scoring problem; they are retained only as records of failed bound
assumptions and must not be used for solver decisions.

## Proof by fixed role count

Roles are fixed for the match, and only Patrol vehicles acquire servings.

### No Refuel vehicle

The four Patrol vehicles have 4 × 233 = 932 initial fuel and no way to replenish
it. `scripts/target_feasibility_audit.py` gives every vehicle a free teleport to
any first spot on every day, ignores traffic, stocks, day horizons and coverage,
and solves exact subset shortest-fuel routes. Even in that relaxed problem the
maximum score is **283**. Therefore all-Patrol cannot reach 400.

### Two or more Refuel vehicles

With at most two Patrol vehicles, each of the 20 spots can be acquired at most
once per Patrol per day. Thus at most 40 servings/day and 280/match are possible.
The day-one route bound tightens this to 274, but 280 is already below 400.

### Exactly one Refuel vehicle

Three Patrol vehicles can take at most 60 servings/day from the 20 spots.
On day 1, exact shortest-time subset DP gives at most 17 distinct spot visits
per Patrol, hence at most **51** servings.

Day 4 has only 63 steps. `scripts/day_one_stock_bound.py` permits every Patrol
to teleport for free to its first spot, ignores fuel, traffic, refuel movement
and synchronization, enumerates all time-feasible maximal spot subsets, then
solves an exact set-packing MILP with daily stock and all 16 brands required.
Its proven optimum is only **34** servings.

Giving every other day its unattainably generous stock cap of 60 produces:

```text
day 1 + day 4 + five other days
  51  +   34  + 5 × 60 = 385
```

Under the current local simulator assumptions this implies C3 < 400. It is not
an authoritative impossibility proof after the external 389 counterexample.

## Baseline evidence

### Authoritative observed baseline

The user reported ALNS 8 s = **16/112/316** and an H22 observation of
**16/112/324**. Since local and server scoring are the same, these are elite
trajectory targets, not evidence for a score conversion. A new solver must
itself produce and locally verify a score above 320.

### Local reproduction status

Replaying H22 with seed 1, roles `[0,1,0,0]`, and 45000 ms/day produced
**16/112/299**, with daily bowls `49/50/51/30/37/30/52`.

Artifact: `solver_learning/runs/u25-h22-45-v2h22-45000-1.json`.

This does not establish an evaluator gap; it only shows that the stored run did
not reproduce the reported elite trajectory. ALNS 8 s seeds 3--8 subsequently
scored 301, 290, 298, 300, 291, and 299. The 316/324 trajectories have not yet
been recovered as action checkpoints.

An exhaustive role-mask screen using full-match production ALNS at 500 ms/day
found the best valid mask `[0,1,0,0]` with **16/112/229**. The other valid
one-Refuel masks scored 228, 226 and 221. This is a screening baseline, not a
claim of practical optimality under 45 seconds/day.

Artifact: `solver_learning/role_optimizer_user_25x25_500ms.json`.

## Reproduce

```powershell
rtk python scripts/target_feasibility_audit.py cases/user-input-25x25.json --target 400
rtk python scripts/day_one_stock_bound.py cases/user-input-25x25.json --roles 0,1,0,0 --day 4 --free-start
```

The second command must report `day_one_serving_upper_bound: 34`. The first
reports all-Patrol upper 283 and role-count bounds. No evaluator, solver or
input rule is modified by either audit.
