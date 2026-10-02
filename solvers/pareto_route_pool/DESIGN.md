# Pareto Route-Pool Solver Design

## Understanding summary

- Build a new independent Hexudon solver for `cases/user-input-25x25.json`.
- Hard acceptance is C1=16, C2=112, then maximize C3 with target C3>=400.
- The authoritative limit is 45000 ms per day and the unchanged core trace evaluator wins.
- Existing solvers, evaluator, GUI and role-selection code are not modified.
- The implementation must be general: no case coordinates, fixed routes or answer hard-coding.
- Every meaningful experiment is logged; only full-coverage replayed checkpoints are promoted.

## Assumptions and risks

- The 25x25 case is an intentional test even though contest profiles normally list 16/24/32.
- Offline testing uses the repository's one-team self-traffic replay protocol.
- Timed heuristic runs can vary; best score and consistency are reported separately.
- Route-pool quality and cross-day fuel/rendezvous coupling are the largest implementation risks.
- A valid incumbent is retained as an anytime fallback before experimental operators run.

## Selected architecture

1. Precompute important-node time/fuel paths and compact masks.
2. Produce feasible seeds with existing ALNS and multiple role masks.
3. Generate diverse per-patrol route fragments with subset DP and bounded search.
4. Combine routes through small set-packing branch-and-bound with stock and coverage constraints.
5. Keep cross-day alternatives in Pareto-Chokudai queues keyed by day/decision turn.
6. Improve incumbents using Hexudon-specific destroy/repair and local route exchanges.
7. Validate every promoted candidate with unchanged `bin/hexudon.exe trace`.

Comparator is lexicographic: coverage feasibility, guaranteed coverage, possible coverage,
bowls, optimistic bowls, fuel slack, endpoint/route diversity. C1/C2 are never traded for C3.

## Initial 45-second allocation

- 3s: valid seed and fallback.
- 12s: route generation/pool diversification.
- 20s: set-packing and Pareto-Chokudai.
- 8s: LNS/local exchanges and rendezvous repair.
- 2s: validation and safe output.

Allocation is adaptive after profiling and is not a correctness assumption.

## Decision log

- Route-level macro search is primary; cell-level pathfinding is delegated to precomputed paths.
- ALNS is retained as a seed and fallback, not assumed to be the final engine.
- Chokudai queues persist alternatives across decision layers; route pools prevent beam collapse.
- Exact subset/packing optimization is used only where measured candidate counts remain tractable.
- A separate directory and executable are mandatory.
- Target acceptance for this case is exactly 16/112/400 within 45s/day.

## Validation plan

- Reproduce baselines before implementation changes.
- Log hypothesis, seed, roles, budget, score, daily coverage and wall time.
- Replay every checkpoint using the unchanged evaluator.
- Run ablations for route pool, Pareto diversity, upper bound and LNS after improvement.
- Export matching C++ source and EXE only after verified improvement.
