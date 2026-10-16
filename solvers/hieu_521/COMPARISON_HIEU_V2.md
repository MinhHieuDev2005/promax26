# Hieu v2 versus cross-route solver

Measured on 2026-10-14. Both executables ran sequentially on the same supplied
32x32 snapshot with idle traffic, roles `0,0,0,0,1,0,0`, seed 1, 8 workers and
45000 ms requested per day. Every day passed the independent validator and the
complete match replay.

| Day | hexa_udon_hieu_runner_v2 | udon530_cross_runner |
|---:|---:|---:|
| 1 | 84 | 84 |
| 2 | 77 | 78 |
| 3 | 81 | 82 |
| 4 | 87 | 87 |
| 5 | 92 | 92 |
| 6 | 99 | 100 |
| **Final** | **26/156/520** | **26/156/523** |

This direct run gives the cross-route solver +3 udon without losing either
hard coverage criterion. It is one timed run, not a statistical guarantee.
The earlier best validated cross-route run remains 26/156/525.

Raw reports:

- `benchmark/results/compare_hieu_v2_45s_8t_s1.json`
- `benchmark/results/compare_cross525_45s_8t_s1.json`

## Worker-count check

Fixed day-1 state, same cross-route executable, 45000 ms and seed 1:

| Workers | Udon | Search iterations | Evaluated plans | Peak RAM |
|---:|---:|---:|---:|---:|
| 4 | 83 | 711,994 | 532,211 | 65.0 MiB |
| 6 | 83 | 1,100,217 | 819,969 | 94.3 MiB |
| 8 | 84 | 2,247,071 | 1,647,445 | 131.4 MiB |
| 12 | 84 | 2,194,819 | 1,638,851 | 182.5 MiB |
| 16 | 84 | 3,191,260 | 2,364,976 | 245.3 MiB |

The 16-worker full match scored 26/156/519. Twelve workers evaluated fewer
plans than eight in this fixed run. Eight workers match the CPU's eight
physical cores and are the recommended default. SMT workers consume more CPU
and memory but did not improve the full-match objective.

Thread-sweep raw report:
`benchmark/results/cross_thread_sweep_day1_45s.json`.
