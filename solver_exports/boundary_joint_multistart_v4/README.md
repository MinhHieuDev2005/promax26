# boundary_joint_multistart_v4

Rebuilt candidate for contest maps 16x16, 24x24, and 32x32.

- Keeps `../boundary_joint_h61_326/boundary_joint_runner.exe` unchanged.
- Enables checkpointed ALNS multi-start on 16x16 and 24x24 for budgets of at least 10 seconds.
- Keeps the proven baseline algorithm on 32x32.
- Set `search.enableMultiStart` to `0` to disable the new path.

Run repeated-seed benchmarks before promotion.
