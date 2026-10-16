# Boundary Joint Stable (experimental)

This is a separate runner; `solvers/boundary_joint` and its executable remain unchanged.

The runner makes three independent single-restart ALNS proposals using a fixed internal seed portfolio, keeps the best simulator-valid proposal by the official `(C1, C2, C3)` tuple, then checks the existing boundary route-pool and bounded tail-search proposals against that same tuple. Equal-score plans use a deterministic plan ordering. It does not perform the old runner's deadline-sensitive fast-future preview, rollout selection, or cross-day bowl trade. It returns no planner-state hint.

The caller's `randomSeed` is intentionally ignored for selection stability. `stableBaseSeed` changes the internal portfolio for an explicit experiment. `stableStarts` (default 3), `baselineMs` (default 12000), `enablePool`, `poolCapacity`, `endpointQuota`, and `enableTailSearch` are available in `search`. Time is still wall-clock bounded, so exact repeatability is **not** guaranteed.

Build with MinGW/Ninja:

```text
cmake -S solvers/boundary_joint_stable -B build-boundary-stable -G Ninja -DCMAKE_CXX_COMPILER=C:/msys64/ucrt64/bin/g++.exe -DCMAKE_BUILD_TYPE=Release
cmake --build build-boundary-stable --target boundary_joint_stable_runner
```

This runner is not promoted over the original. Fixed first-day checkpoint benchmarks with three repetitions and a 45-second budget produced C1/C2 complete and C3 of 9/9/9 on 16x16, 22/22/22 on 24x24, and 45/45/46 on 32x32. These are single-day results, not evidence of full-match superiority or a guarantee for all maps.
