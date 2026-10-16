# promax26-3 algorithm comparison

Test: supplied 32x32 snapshot, idle traffic, roles `0,0,0,0,1,0,0`, seed 1,
8 workers, 45,000 ms/day. Every plan was replayed by `bin/hexudon.exe trace greedy`.

| Solver | Daily servings | Match score | Valid |
|---|---|---:|---:|
| Hieu v2 baseline | 84, 77, 81, 87, 92, 99 | 26/156/520 | yes |
| Cross-route before this change | 84, 78, 82, 87, 92, 100 | 26/156/523 | yes |
| `promax26-3` history | 83, 77, 83, 88, 94, 101 | 26/156/526 | yes |
| Cross-route + history | 84, 78, 82, 88, 94, 102 | **26/156/528** | yes |

The imported idea gives uncollected match brands priority in regret assignment,
repair order and the annealing objective. It preserves the hard lexicographic
coverage objective. Once all 26 brands have already been collected, the additional
match-history bonus becomes inactive.

The combined result is the best validated run currently recorded, but it is one
wall-clock-bounded run and is not proof that every repeat scores 528. It remains
2 servings below the 530 target.

Artifacts:

- `build-pro26-hieu/udon530_cross_runner.exe`
  SHA-256 `601b513396327657b4c49e4eef7541d088c5516d7dce01882bf78b0b6e61375f`
- `reports/cross-history-idle-45s-s1.json`
  SHA-256 `8273a0cae530b902217d052a52bc7ebc59e4d752ffd17959c6efd136f883ac6f`
- `build-promax26-3/promax26_3_history_runner.exe`
  SHA-256 `d54e2b30be9066dff86d19150ef12bfdaef13ff0761ae40c06b4dfcaca69e741`
- `reports/promax26-3-idle-45s-s1.json`
  SHA-256 `586c06fad7b85609c8f696b99a104ef2c418e756d046dc52ee07b328dc49f8cd`

`promax26-3` and `pro26-hieu/promax26` were used read-only and remained clean.
