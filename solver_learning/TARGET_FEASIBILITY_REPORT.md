# Feasibility audit for the three requested C3 targets

Date: 2026-09-30. The inputs are the frozen JSON cases listed below. All
scores are `(distinct brands, cumulative daily brands, servings)`; C1/C2 are
required at their maxima. This audit changes neither a solver nor the judge.

| Input | Best replayable full-C1/C2 checkpoint | Requested C3 | Proven global C3 upper bound |
|---|---:|---:|---:|
| `cases/user-input-16x16.json` | 8/48/94 | >110 (at least 111) | **108** |
| `cases/user-input-24x24-b.json` | 14/70/260 | >280 (at least 281) | **276** |
| `cases/user-input-32x32.json` | 14/70/265 | >300 (at least 301) | **299** |

The separate `cases/user-input-24x24.json` (24×24-A) contains only 38 servings
of daily stock across seven days: its stock-only limit is **266**, already
below 281.

## Why the bounds are safe

In the unchanged simulation (`src/core.cpp`), only Patrol vehicles collect;
each Patrol collects at most once per spot per day. A spot has a fixed daily
stock, and positions/fuel persist between days. Moving spends the fuel cost of
the *source* terrain; road congestion can increase travel time, never decrease
it below the free-road time.

For every fixed role mask with at least one Refuel vehicle, the audit computes
the maximum number of distinct spots each remaining Patrol can reach on day 1,
using shortest free-traffic travel time and ignoring fuel. For later days it
allows each Patrol to serve every spot once, ignoring distance and congestion.
Each spot is capped only by `min(stocks, patrol count)`. These generous
relaxations yield the best one-or-more-Refuel bounds **108, 276, 299**.

All-Patrol roles are treated separately: they have no way to replenish fuel.
The audit even allows every vehicle to teleport for free to any spot at the
start of *every* day, ignores stocks/traffic/day length, and takes the shortest
fuel path between spots. Exact subset path DP gives the minimum fuel needed to
visit `k` distinct spots on one such relaxed route. A whole-match DP then
allocates the initial fuel across every vehicle-day. The resulting optimistic
all-Patrol score ceilings are **73, 123, 173**, respectively. Required fuel
even in this relaxed model is **297 vs 128**, **1196 vs 336**, and
**1615 vs 448** for the requested targets. Thus the all-Patrol exception
cannot reach them either.

The larger of the one-or-more-Refuel bound and all-Patrol bound, capped by
total stock, is a global upper bound over **every role assignment**. C1/C2
were deliberately *not* enforced in either relaxation, so requiring them
cannot invalidate the impossibility conclusion. These are upper bounds, not
claims that scores 108/276/299 are attainable.

## Reproduce

```powershell
rtk python scripts/target_feasibility_audit.py cases/user-input-16x16.json --target 111
rtk python scripts/target_feasibility_audit.py cases/user-input-24x24-b.json --target 281
rtk python scripts/target_feasibility_audit.py cases/user-input-32x32.json --target 301
rtk pytest -q tests/test_spot_route_bounds.py
```

The three checkpoint files are:

- `solver_learning/runs/u16-roleopt-final-h24-3000-1.json` — 8/48/94;
- `solver_learning/runs/u24b-roleopt-final-h24-3000-1.json` — 14/70/260;
- `solver_learning/runs/u32-roleopt-final-h24-3000-1.json` — 14/70/265.

Each checkpoint records `valid=true` and an exact replay through the unchanged
`bin/hexudon.exe trace`; all daily brand counts equal the number of brands.

## Search consequence

Increasing a day budget to 60 s or adding Chokudai cannot meet the three
requested thresholds on these exact inputs. Feasible improvement remains
possible: the valid baselines are 14, 16 and 34 servings below the respective
global *upper bounds*. The 24×24-B one-Refuel checkpoint already reaches its
relaxed later-day cap of 57 on days 3–5; further gain must come primarily from
days 1–2 and/or changed roles. The 16×16 checkpoint reaches its relaxed
one-Refuel cap of 19 on days 5–6, pointing to days 1–4. A revised, achievable
target should be chosen before claiming success or replacing a solver.
