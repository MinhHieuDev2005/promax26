# H61: boundary diversity and joint staging campaign

User authorization (2026-10-02, Asia/Bangkok): continue the approved separate
solver work, target >=16/112/389 within a 24-hour research window, retain all
verified improvements. Per-request runtime remains <=45 seconds. The deadline
is a research limit, not a promise that an infeasible target will be reached.
Campaign starts 2026-10-02 02:22 Asia/Bangkok; absolute deadline is
2026-10-03 02:22 Asia/Bangkok (2026-10-02 19:22 UTC), retained on restarts.

## Locked scope

- Input is the current cases/user-input-25x25.json; no embedded answers.
- Preserve every legacy solver, GUI, role selection and evaluator unchanged.
- Work in new solvers/boundary_joint files and separately versioned exports.
- Maintain lexicographic scoring and require 16 types every day for promotion.
- Benchmark serially using the original trace evaluator, explicit idle traffic,
  both single-supply role masks [1,0,0,0] and [0,0,1,0], multiple seeds.
- No server writes, credentials or opponent-path access. No unbounded jobs.
- Target >=389 is not achieved; exact-input relaxed bound 339 must be audited
  independently. Resolving that discrepancy is a separate correctness gate.

## Alternatives and first experiment

1. Blindly widen Chokudai/rollouts: rejected as initial choice, measured 324
   with almost the entire time budget in H60.
2. Repair endpoint diversity in the route DP (selected): the old implementation
   keeps only ONE minimum-fuel endpoint for every visited mask, then the pool
   keeps only globally maximal-bowl combinations. This discards structural
   alternatives needed for short-day staging before a preview can rank them.
3. Rewrite general Pareto-RCSP/VND/TT immediately: defer until this specific
   restriction is measured. Catalogue all requested technologies explicitly;
   do not claim unimplemented or untested items are complete.

## Proposed bounded implementation

- Fork the small Boundary Pool module; link unchanged shared core.
- Keep the old one-endpoint mask list; augment bounded <=96 labels per
  endpoint for shortlisted masks (not K copies of all masks). Keep diversity
  among best-depth and near-best-depth routes with endpoint quotas. Parent
  reconstruction uses compact DP; no arbitrary large state copy.
- Optional current-day bowl slack at a long-to-short boundary only (0/1/2),
  while preserving full coverage. Never prune this archive using a later
  higher current-day bowl incumbent; retain per-score diverse buckets.
- Combine independent no-refuel patrol routes using the existing exact stock
  counter/undo and optimistic bounds restricted to the fixed route pool.
- Keep baseline, endpoint-diverse, coverage-diverse and lower-bowl candidates
  separately; cap archives, use exact action-key dedup, validate every plan.
- Cheap next-day DP ranks a bounded shortlist; ALNS validates continuations.
  Preview is a feasible lower estimate, not a global upper bound. Always
  compare against original incumbent continuation; no fake coverage in history.
- Follow-up (after the first ablation): supplier/patrol tail synchronization
  using the existing short_day macros, under a strict time slice and exact
  simulation. Add only if the smaller endpoint experiment supports it.

## Budget, reliability and promotion

Cap requests at 45 s with 3 s return reserve. Limit DP targets to20, scale route
caps down for >=4patrols, cap archive memory (planned <256 MiB target case).
Deadline checks cover reconstruction/materialization as well as DP/search.
On insufficient budget retain the validated incumbent. Old release326 remains
available even if all candidates fail. Time-based search nondeterminism is
reported; action replay is deterministic.

First measure fixed day3/day5 checkpoints and full-match seed1. Compare against
the previous release326 trajectory and its three-seed results324/326/324. Only
valid, full-coverage, within-deadline full matches can set a new best. If an
improvement appears, repeat other seeds, test the other role mask, package EXE
plus matching source/hashes/trace. Do not promote on forecasts or one prefix.

## Review log

Skeptic: no counterexample to339/283 in the unchanged input/model; both
relaxations are optimistic. Accepted objections: (1) keep separate bowl buckets
through enumeration and eviction, (2) require a valid full-coverage incumbent
continuation BEFORE any lower-bowl replacement, (3) deadline checks also in
reconstruction/materialization/selection, (4) cap both labels and routes/archive.
Resolution: implement these as correctness tests, retain explicit heuristic
label/path caveat. Target389 supersedes older390 wording, no evaluator changes.

Constraint Guardian: conditional pass. Accepted: entire request <=45s, optional
work stops42s; memory bounded before new-module allocation (DP <=20targets,
one car at a time, old mask candidates <=2^n-1, <=96 extra labels/endpoint,
materialized routes <=256/car, combination archive <=4096/bowl bucket,
candidate plans <=32). New-module scratch estimate must fit192MiB; process
peak256MiB is a measured promotion gate because unchanged ALNS owns its own
allocations. This is not represented as an OS-enforced cap on the legacy core.
Verified improvements are stored with source/binary hashes and replay before
any later build; unique exports never overwrite a release. Absolute deadline
recorded above; no trial launched unless enough time remains for its upper bound.

User Advocate: PASS. No blocking misleading claims. Keep model-specific bound,
verified solver score and unachieved389 target separate in every handoff.

Arbiter: APPROVED for bounded H61 implementation and serial benchmarking.
All accepted objections become implementation/test gates above. No change to
legacy defaults; full-match verification and matching artifacts before promotion.

## H62 proposal after first H61 full match

H61 initial full match ties326, not a new best. Endpoint/slack archive is now
exercised, but preview repeatedly rebuilds subset DP for every alternative
starting position. Add a separate reusable reverse-subset future oracle under
the same architecture: one table of (visited mask, FIRST spot), with successor
parents, time/fuel labels, and the same frozen next-day roads. It supports all
spot starting positions in one preprocessing pass; one-label resource choice
remains heuristic. Query by actual ending position/fuel; no lookup by map hash
or test-specific route. Starts outside spots fall back to existing preview.

Cap table20targets, one oracle per future horizon,32routes per queried vehicle,
96cached position/fuel queries,32candidate team previews. Tables/materialized
routes obey existing memory gates; deadline-aware build/query/reconstruction.
Combine routes with exact stock accounting and coverage masks, then simulate
the complete next-day plan. Use only as a feasible LOWER estimate before ALNS;
keep valid incumbent comparison and time reserve. Tests compare ample-fuel tiny
queries against independently generated routes for every starting spot.

Alternatives: brute repeated forward DP wastes shared work; general full
cell/fuel/turn RCSP is broader and not supported by the current hotspot evidence.
This change targets precompute reuse, not a larger blind beam or claimed exact
Pareto optimizer. Pending sequential review for H62.
