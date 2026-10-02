# Pareto Route-Pool Chokudai v2

## Understanding lock

- Build a new independent solver; never modify ACO/ALNS/MLNS/H22.
- C1/C2 are hard lexicographic constraints; maximize bowls only afterward.
- First target: 25x25, 45 s/day, server H22=16/112/324, target 16/112/370.
- Legacy solvers are immutable seed/fallback providers, not the main engine.
- No exact-map hard-coding; later regress 16x16/24x24/32x32.
- Provisional memory limit is 1 GiB.

## Selected architecture

Precompute important-node paths/fuel reachability; generate and immediately
micro-validate macro routes; keep a bounded diverse per-agent route pool;
combine timed routes with simulator-checked set packing; then, if ablations
justify it, add turn-layered Pareto-Chokudai and targeted repair. Team states
store route IDs rather than copied action vectors.

## Objective and feasibility

C1 is distinct brands across committed history plus candidate suffix; threshold
is the brand count in config. C2 is summed distinct brands over all committed
and candidate days; threshold is `C1_threshold * day_count`. Both are capped at
threshold while ranking. After both pass, C3 bowls decides official rank;
coverage surplus cannot beat more bowls.

`possibleGlobal` and `possibleDaily` union current coverage with brands having
a relaxed time-and-fuel-reachable spot. They are optimistic feasibility filters,
not bonuses. V1 has no bowl-bound pruning. It is enabled only after exhaustive
small-case tests prove an upper bound admissible.

## State safety and composition

Safe dominance requires equal turn, positions, road input, stock vector, supply
state, acquisition prefix, rendezvous commitments, and macro frontier. A wins
only with superset type mask, no fewer bowls/fuel, and no greater shared-resource
use. Opponent-dependent reductions are approximate and cannot remove the final
feasible representative.

Every macro is micro-reconstructed and evaluated before pool insertion. A team
combination revalidates stock, timed acquisitions, movement, congestion,
rendezvous, transfer, fuel, and horizon in the unchanged simulator. Variable
macros enter queues by ending turn and must strictly advance the event frontier.

Hash entries store a 64-bit fingerprint and equality witness; collisions invoke
comparison, never blind pruning. Full tables use age/rank replacement while
protecting the incumbent and final feasible member of each bounded class.

## Runtime and memory

- 2 s precompute and validated incumbent
- 8 s gated route generation
- 8 s route-pool combination
- 14 s Pareto-Chokudai after its gate passes
- 4 s targeted repair
- 4 s reconstruction/final validation
- 5 s process, GUI, serialization, submission reserve

Search hard-stops five seconds before the external deadline. A restored seed is
usable only when config, roles, day, history, stock, and roads fingerprints all
match. The enforceable default is **768 MiB peak committed memory for the whole
solver process tree**, not only resident bytes in the main module. The solver's
own caps are 192 MiB route arena, 160 MiB state arena, 64 MiB hash, and 32 MiB
indexes/frontiers (448 MiB total); 320 MiB remains for runtime, libraries, seed
providers, serialization, and measured overhead. Deployment may lower but not
raise this default without an explicit configuration check. Allocation failure
stops expansion and returns the serialized incumbent.

For the 25x25 profile, each agent route pool is capped at 4096 entries, each
Pareto bucket at 16 states, total live team states at 300000, transposition
entries at 2^20, and set-packing nodes at 200000 per invocation. Smaller/larger
standard maps scale these downward/upward only within the same byte caps.
Cancellation/deadline checks occur at least every 256 expansions or 2 ms,
whichever occurs first; simulator calls check before and after each candidate.

One monotonic deadline is constructed at request receipt. If server `endsAt` is
present, its converted remaining duration is the upper bound; otherwise the
requested budget is. Reserve is `min(5s, max(1s, 20% of remaining))`. When less
than 2 s remains, no search starts and an already serialized valid incumbent is
returned. The incumbent must be validated and serialized before every phase
transition, not only at the end.

Legacy seed providers are linked library calls in v1, not spawned executables.
Their wall time, threads, allocations, exceptions, and diagnostics count inside
the same deadline and 768 MiB process-tree cap. If a later provider uses a child
process, it must have a job-level memory/time limit, bounded captured output,
and forced termination before it can pass its ablation gate.

## Staged implementation and ablation gates

V1 contains precompute, validated legacy/greedy generation, bounded route pool,
simulator-checked coordinate/set-packing combination, and fallback. Weighted LDS
is added only for measured route-diversity deficiency. Pareto-Chokudai is added
only if pool combinations improve a replay parent. Ejection chains and exact DP
require a demonstrated assignment/local-optimum bottleneck; DP is skipped above
18 candidate targets.

A module must improve one retained case without regression, or produce a
diagnostic gain directly enabling the next experiment. After two controlled
failed ablations it is disabled rather than tuned indefinitely.

## Opponents, promotion, and overfit

Multiple arrival profiles hedge opponent uncertainty; future opponent stock is
never guaranteed. Server is authoritative. Promotion uses paired fresh matches
with exact H22 as control where possible. If local ordering disagrees twice,
local absolute C3 is removed as a promotion signal and semantics are audited.

Profiles are keyed by resource features, never exact map fingerprint. The 25x25
case is the first development case; general promotion later requires retained
16x16/24x24/32x32 regressions.

Promotion needs at least three authoritative paired comparisons against the
exact H22 control on fresh matches/configurations, with C1/C2 preserved in all
three and higher C3 median plus no worse C3 worst case. If three comparable
server observations cannot be obtained, release promotion is explicitly
`BLOCKED`; local evidence may continue research but cannot label the runner an
improvement. Logs/checkpoints must exclude tokens, authorization headers, and
GUI credentials.

## Runner and user contract

The separate executable is `pareto_route_pool_v2_runner.exe`, registered under
the distinct policy name `pareto_route_pool_v2`. It implements the existing
JSON runner contract: `op=roles` and `op=plan`, with exactly one JSON response
on stdout and diagnostics/errors on the response object rather than stray
stdout. Planner state is match/config/day fingerprinted; stale future history
is rejected or trimmed using the GUI's existing reconciliation rules, never
silently reused across a new match.

The solver does **not** alter GUI role-selection behavior. For `op=plan`, roles
must exactly equal the roles already present in `day_info` and confirmed by the
GUI/server. `op=roles` is provided only for protocol compatibility and delegates
to the existing read-only selector; it cannot resubmit or override confirmed
roles. No changes to `gui.py` are part of this solver build.

Diagnostics expose requested budget, effective deadline budget, reserve,
elapsed time per phase, stop reason, pool sizes, selected engine lineage, and
whether the returned plan is `NEW_ENGINE`, `LEGACY_SEED`, or `FALLBACK`. Early
completion must name the reason (exhausted candidates, gate disabled, deadline,
memory cap, or error); it may not imply that the full requested time was used.

Response status is one of: `VALID_NEW_CANDIDATE`, `VALID_FALLBACK`,
`NO_VALID_PLAN`, or `SERVER_PROMOTION_UNCONFIRMED`. Warnings are non-fatal and
retain a validated plan; errors that leave no validated serialized incumbent
return `ok=false` and must not be submitted.

Disabling a module after two failed ablations ends only that hypothesis. Work
continues with the next evidence-backed bottleneck until 370 is confirmed or an
external authority/input requirement blocks further validation. Promotion may
be BLOCKED while research and local ablations continue; blocked is never
reported as success.

Minimum handoff artifacts are the independent C++ source/CMake files, separate
EXE, exact reproduction command, per-run JSON checkpoint/replay, diagnostics,
C1/C2/C3 result, runtime, and an H22 comparison table. Reuse of legacy code is
link/call-only: no legacy source edit, EXE overwrite, state write, or behavior
change is permitted and `git diff` is checked before handoff.

## Decision log

1. Selected independent Route Pool + Set Packing + Pareto-Chokudai over legacy
   LNS-only improvement and a full cell-level rewrite.
2. Selected macro branching with immediate validation over deferred legality.
3. Selected real end-turn layering over macro depth.
4. Selected threshold-capped lexicographic coverage over weighted sums.
5. Selected staged ablation gates over implementing the full research list.
6. Mandated five-second reserve and subsystem memory caps.
7. Server H22=324 is authoritative; local H22=299 is diagnostic only.
8. Apply a 768 MiB cap to the complete solver process tree and numeric caps to
   every unbounded search container.
9. Use one request-scoped monotonic deadline and keep a serialized incumbent at
   every phase boundary.
10. Require three paired server comparisons or mark promotion BLOCKED.
11. Preserve GUI role authority and expose lineage, phase timing, stop reason,
    validation status, and fallback status in every runner response.
12. Deliver separate source/EXE/replay/command/comparison artifacts.

## Review log — Skeptic / Challenger

- Accepted local/server ranking risk: paired server control and correlation gate.
- Accepted underspecified objective, dominance, layering, compatibility, hash,
  memory, and deadline objections: invariants are explicit above.
- Accepted YAGNI objection: staged gates and two-ablation disable rule.
- Accepted opponent/reproducibility limitations: retain timing diversity and do
  not guarantee opponent-dependent stock.
- Rejected proof of 370 as an implementation prerequisite: the architecture is
  an empirical hypothesis bounded by gates, not an advance guarantee.
- Accepted 25x25 overfit risk: feature profiles and later standard-size gates.

## Review log — Constraint Guardian

- CG-1 accepted: 768 MiB whole-process-tree accounting replaces the provisional
  1 GiB assumption; own arenas total 448 MiB.
- CG-2 accepted: route, bucket, state, hash, node, and cancellation caps are now
  numeric and deadline-aware.
- CG-3 accepted: one monotonic deadline, shortened-window reserve, and serialized
  incumbent invariant are specified.
- CG-4 accepted: v1 seed providers are in-process and share all resource caps;
  future child providers require bounded job controls.
- CG-5 accepted: promotion requires three paired authoritative comparisons;
  absence of those observations yields BLOCKED, not inferred success.

## Review log — User Advocate

- UA-1/UA-2 accepted: exact runner protocol, history fingerprinting, and GUI/
  server role authority are now fixed; the solver never changes GUI roles.
- UA-3/UA-4 accepted: phase timing, budget, stop reason, engine lineage, and
  fallback class are mandatory diagnostics.
- UA-5 accepted: failed-module gates redirect research; they do not terminate
  the 370 objective. Promotion BLOCKED is distinguished from research stopped.
- UA-6 accepted: source, EXE, command, checkpoint/replay, score, runtime, and
  H22 comparison are mandatory handoff artifacts.
- UA-7 accepted: four user-visible validation states distinguish safe plans,
  fallback, no plan, and unconfirmed server promotion.
- UA-8 accepted: legacy integration is read-only link/call reuse; legacy files
  and executables are immutable and checked by diff.

## Remaining accepted risks

- Server/local semantics may remain insufficiently correlated.
- Rendezvous compatibility may dominate combination cost.
- Fresh identical server matches may not always be available.
- OS-level process-tree enforcement must be verified on the deployment machine.

## Arbiter disposition

**APPROVED.** Understanding Lock, ordered reviews, objection resolutions,
Decision Log, and remaining-risk acknowledgement satisfy all exit criteria.
Implementation may proceed while legacy solver sources and executables remain
unchanged.
