# Solver milestones

Benchmark contract: `cases/master/32japan.snapshot.json`, idle traffic, roles
`0,0,0,0,1,0,0`, 8 threads, seed 1, 55,000 ms per day.

| Artifact | Score | SHA-256 | Status |
|---|---:|---|---|
| `udon530_cross_548_baseline.exe` | 24/240/548 | `8f82725df1cdc35f2a8a164b48c991485ad25e04f3f1a2427b0d2b2e7e42f0a3` | Rebuilt source-equivalent baseline; paired report is the validation record. |    
| `udon530_cross_targeted_ruin_candidate.exe` | 24/240/548 | `09ce9590323b89bcc1f324c2c293d89654af0e6e8b4684f6b46d461dc0649036` | Validated, retained experiment. |
| `udon530_cross_joint_target_supply_candidate.exe` | 24/240/548 | `4eee02ff59fa57c3552b45452264e49162d62d770370a6dae49e8da4670639d4` | Validated, retained experiment. |
| `udon530_cross_550_validated.exe` | **24/240/550** | `b737eec2bf006e136332d23dc7886927d2c2f14442c7b43805cd5adf91e41de8` | Current validated best. |
| `udon530_cross_550_gui_default.exe` | Smoke-tested; full default score unverified | `ed88feabfae13e1f81b4ca5b1a9ed3efa2bfa423c18366266bdb458576d7d6ce` | Defaults to `crossMoves=7`, but `endSpotWeight=-1` differs from the 550 benchmark's explicit zero. |

`build-pro26-hieu/udon530_cross_runner.exe` currently matches the GUI-default binary.

The validated 550 configuration explicitly requires `crossMoves=7` and
`endSpotWeight=0`. The 550 result is one observed full-match run, not a guaranteed floor.
See `RESEARCH_NEXT_570.md` for the source audit and next experiments.
