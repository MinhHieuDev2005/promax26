# Boundary route-pool experiment (H57)

Continuation of the already approved separate-solver/route-pool direction.
No legacy solver, evaluator, role-selection UI or submitted match is changed.

## Understanding and assumptions

- Build a general JSON runner for the user's GUI and offline evaluator.
- Keep full global and daily type coverage ahead of bowls, lexicographically.
- Maximum request budget is 45 s including preprocessing; reserve 3 s.
- Use the actual daySteps and observed roads; future roads are a forecast only.
- Keep the ALNS incumbent and validate every replacement with the unchanged core.
- Inputs and benchmark artifacts stay local; no server writes or credentials.
- Target remains 390+ on the supplied case, not a claim of achievement. The
  earlier 339 relaxed bound remains an unresolved contradiction with the
  reported opponent result; do not change rules to bypass it.

## Decision log

1. Rejected simply increasing full-day Chokudai width: earlier macro calls were
   too expensive and weakened the ALNS floor (319 versus 325).
2. Continue route-pool architecture, but remove the fixed-endpoint restriction
   of the failed subset repair. This is a materially different neighborhood.
3. Generate time/fuel-constrained subset routes, retain coverage diversity,
   enumerate small route combinations, then resimulate the joint plan. A single
   time-first label is a proposal heuristic, NOT an exact multi-resource solver.
4. Keep supplier routes as incumbents initially; independently fuel-feasible
   patrol proposals need no assumed rendezvous. Any actual refuel is a bonus.
5. Compare promising changed endpoints against the incumbent using next-day
   ALNS rollouts before accepting a daily bowl gain. Forecasts are labelled;
   cached next plans are revalidated against real state before reuse.
6. Later joint tail Chokudai is conditional on this smaller experiment. Do not
   bundle unmeasured mechanisms merely to attach algorithm names.

## H58/H59 updates from measured results

- The first pool-only variant tied 323. Equal-bowl boundary states were being
  rejected for lower fuel, despite possible next-day access benefits.
- Keeping such states before short days produced 326/325/324 over three seeds;
  ALNS 8 s measured 323/323/323. This is a single-case, unequal-runtime result,
  not a general promotion claim.
- Add exact shared-stock accounting and safe optimistic bounds in the fixed
  independent-route pool. No-refuel routes are evaluated in isolation before
  joint recombination. Six-patrol cases no longer bypass the pool entirely.
- Add an optional bounded Chokudai tail neighborhood (one or two edited cars),
  with exact action-key dedup, bounded endpoint-diverse queues and full-plan
  validation. This is an experimental switch, not a promoted default.
- Do not claim all requested modules exist: multi-label RCSP, general VND,
  path relinking, CABS/BULB and online hyperparameter tuning remain deferred.

## Test and promotion gate

First reproduce ALNS with roles [1,0,0,0] in the explicit idle-opponent scenario.
Then run seven days, replay through bin/hexudon.exe trace, record per-day times,
coverage, route counts and changes. Test another seed and [0,0,1,0]. Retain
improvements with source/EXE hashes. No test-specific route embedding.

## H60: bounded preview, not wider blind search

- Fixed day-3 experiments show that four expensive continuation slots can miss
  useful endpoint assignments. Eight blind rollouts instead used over 42 s and
  the tested full match scored only 324. Do not promote width alone.
- Use a no-refuel subset-DP/stock-aware pool as a cheap next-day preview for up
  to 16 boundary candidates. Preserve the ALNS incumbent and an exploration
  slot, then validate a few shortlisted continuations with ALNS.
- These feasible preview scores are lower estimates, NOT admissible upper
  bounds. They rank candidates; they cannot justify globally safe pruning.
- A pre-release three-seed batch scored 326/326/325, full 16/112. Final-build
  measurements are recorded separately in RESULTS.md rather than attributing
  old EXE results to new source. ALNS remains time-budget-dependent.
- Fix a coverage-edge-case before packaging: initialize a bowl pruning floor
  from the incumbent only if its primary and daily coverage are already full.
  Compare two-day global coverage, summed daily coverage, then bowls. The
  regression case must prefer 2/2/6 over 1/1/8.
- Initial 16/24/32 first-day regressions gave four ties and two one-bowl losses.
  In all six preview runs the ALNS seed remained selected. Thus the pool did
  not replace it with a worse current-day plan, but no cross-map superiority or
  whole-match non-regression has been established. Leave legacy defaults alone.
