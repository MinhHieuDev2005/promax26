# Mock Server Audit And Validation

Date: 2026-10-15 (Asia/Saigon). Scope: local Procon HTTP contract and repository rules only.

This report supersedes the earlier claims of absolute deadline safety and complete
competition-server compatibility. No such conclusion follows from these tests.
No solver algorithm, GUI production binary, release binary, commit, or deployment
is changed by this audit.

## Corrections

- POST / previously stored any plan and returned valid=true. It now validates the
  complete plan before assigning a revision or modifying the accepted plan.
- Validate agent count, nonempty rows, integer (not bool/float) actions, action
  range, exact step sums, hex-map boundaries/ponds, and fuel using the same event
  ordering as src/simulator/simulator.cpp. Patrols consume fuel; supply vehicles
  refill collocated patrols. Stores share stock in agent order and reset each day.
- Malformed JSON/body length, wrong credentials, invalid lineups, registration
  after startsAt, pre-start state access, expired action windows, and completed
  matches are rejected without assertion crashes. Invalid plans leave revisions
  unchanged; valid revisions replace the current day's plan, not accumulate it.
- Invalid plans use HTTP 200 with revision=-1 and valid=false, which the repository
  decode_revision explicitly supports. Malformed requests use 400, authentication
  uses 401, and unavailable windows use 403. These are the mock's explicit policy;
  exact official-server rejection codes and registration replacement semantics
  have NOT been independently verified.
- Multi-agent fallback is one [-steps] row per agent, not one row containing N
  waits. Missing days are simulated with this fallback.
- startsAt no longer changes on each GET /setting. Daily endsAt advances from the
  prior deadline, not from the time of a late poll. Finalization uses the actual
  elapsed deadline; tests no longer force current_ends_at=0 to manufacture success.
- daySeconds in the returned setting now matches the configured mock day window.
- Trace actual request bodies/responses, server receipt, completed validation,
  response flush completion, deadline, and delivery status. Server elapsed time
  uses monotonic_ns, not wall-clock subtraction.
- The old POST=0 measurements selected session-level accepted log entries whose
  default elapsed value overwrote the API timing entry in SessionController's
  pending-record update. Read startedAtMs/finishedAtMs from persisted submissions
  instead and correlate each one with the server's day/revision trace. Release
  logging itself is not modified.
- Response flush timestamp is not a precise client-receive timestamp: a client can
  receive bytes and issue another request before the server thread records flush
  completion. State-to-submission time is therefore reported as a bound using
  state-ready/flush timestamps, not as an exact client receive-to-send duration.

## Evidence And Reproduction

Run from the repository root inside WSL HexaUdon:

```sh
python3 tests/benchmark/deadline_stress_test.py --checks-only
python3 tests/benchmark/deadline_stress_test.py --gui-only
python3 tests/benchmark/deadline_stress_test.py --stress-only
python3 tests/benchmark/deadline_stress_test.py --recovery-only
python3 tests/benchmark/deadline_stress_test.py --competition-only
python3 tests/gui_check.py
```

Every run uses a new results/mock-audit-* directory and new sessions; old sessions
and logs are never reused. Each match saves http.json, history.json, session.json,
client.log, result.json, plus the original session/log directories. Recovery runs
save separate before-stop/after-recover logs and the stopped session snapshot.
Nonzero exit status means at least one scenario failed; an overloaded match is
not relabeled PASS just because detecting its failure was expected.

Reference checks replay B and H2 action traces on all eight dev-fixed fixtures:
78 days compared against recorded C++ simulator outputs (positions, fuel, traffic,
stays, brand hits, bowls). This is an independent Python port checked against
existing C++ evidence, not an independent official competition server. Synthetic
co-located patrol/supply checks cover shared store stock and replenishment.

Negative HTTP checks cover malformed JSON, invalid lineup enum/count/bool, missing
agent plans, invalid action enum/bool/float, step overflow, boundary movement,
insufficient fuel, valid revisions, expired windows, post-completion submissions,
authentication, multi-agent WAIT fallback, and delayed rejection. Raw negative
traces include both test-client timestamps and server request/response events.

Full matches must finish naturally, exit zero, have all accepted days, and match
server history to persisted client simulations. Additional offline checks compare
accepted day/revision/actions with the server's final selection. Recovery stops a
client after a persisted planning result, restarts recover --execute against the
same local server/session, and checks no duplicate vehicle registration occurs.
This does not test recovery from an unknown POST outcome or machine power loss.

## Measurement Limits

POST request start and acknowledgment come from persisted client submission times
(milliseconds, wall clock); server receipt/validation/response completion have
nanosecond timestamps. Server request durations use monotonic time. A timing
inconsistency fails validation, rather than producing a zero-latency PASS.

The existing binaries do not expose precise GET-body-consumed timestamps or a
separate parse/planner/waypoint/serialization/fsync breakdown. Exact attribution
of those phases and exact state-receive-to-server-receipt latency remain NOT
VERIFIED. State-ready-to-receipt upper bounds and state-flush-to-receipt lower
bounds include client processing and HTTP submission, but are not phase profiles.

The 60-second/day suite uses four threads, a 500ms kind-selection cap and a 1s
client safety reserve. GUI suites use GUI defaults (eight threads, 3s safety
reserve) with 12-second mock days. These are different configurations; neither
proves a 50ms reserve or a fixed percentage is universally sufficient. Select a
reserve from measured RTT tails plus validation/persistence/scheduling/clock
uncertainty, not from average localhost timings. No timer/algorithm change is
made based on this single-machine audit.

## Remaining Limits

- Single team only. players != 1 is explicitly refused because opponent movement,
  shared-resource arbitration across teams, and real opponent traffic are not
  fully specified by the available mock. They are NOT VERIFIED.
- Request body contains no day identifier in this protocol. Revision is assigned
  by the server for its current day; the mock does not invent request-side day or
  revision fields. It cannot identify a stale plan that is otherwise valid after
  a caller has already fetched a newer day.
- Store-stock reset and traffic from the preceding two days match the repository
  simulator/benchmark model; this is not proof of official-server equivalence.
- GUI integration tests use the real gui.Handler/Runner HTTP endpoints and actual
  release clients, not a fake subprocess. They do not click a Windows browser or
  execute the .cmd/systemd wrapper interactively.
- Open-HexaUdon-B.cmd targets /home/hexa/release/hexa_udon_B on 8765;
  Open-HexaUdon-H2.cmd targets /home/hexa/release/hexa_udon_H2 on 8766. The original
  launcher also uses 8765, so check that port before opening B. Do not use the
  original Stop-HexaUdon.cmd for independent shutdown: it terminates all HexaUdon
  WSL processes. Use the individual GUI Stop control instead.
- No requests are sent to an actual competition server. HAUI endpoints, TLS,
  real authentication/rate limits/opponents and remote latency remain NOT VERIFIED.

## Recorded Results

See the final evidence summary and status table appended after all runs complete.
Interrupted and superseded exploratory runs are retained, not counted as passes.

## Verified Outcomes So Far

- Final GUI HTTP full match B: results/mock-audit-gui-4b73hwkc/B-0ms-12s-gui.
- Final GUI HTTP full match H2: results/mock-audit-032f0w5t/H2-0ms-12s-gui.
  Both pass, four naturally completed days, score [10,22,22]. Fresh accepted
  day/revision/action/state and acknowledgment-deadline checks also pass offline.
- Recovery: results/mock-audit-r6gzwk2a/recovery-B and recovery-H2, both PASS.
- Negative/reference/actual GUI Start/Stop controls:
  results/mock-audit-7zbglhe6 (21 HTTP test events, 78 reference days, supply/shared
  stock assertions and /proc/PID/exe validation of the real application clients).
- Stress: results/mock-audit-kotnty0l. 20/50/100ms cases PASS. The 1500ms match
  completes, but timing validation FAILS and is not counted as PASS: server
  monotonic duration 1500.7ms vs server wall delta 982.5ms, while the corresponding
  client persisted round trip is 997ms. This demonstrates an approximately 518ms
  backward wall-clock discontinuity. The exact synchronization source is unknown.
  The 4000ms case FAILS the match at vehicle registration (result=Failed), and is
  correctly not reported as a successful match.
- Daily-budget B: results/mock-audit-0hmuguvm/B-100ms-60s PASS, score [8,18,20].
  H2 in that same run finished its client successfully but the test sampled the
  lazy server finalization just before its wall deadline (only three history days
  materialized). That run is FAIL, not PASS. The final test now polls the actual
  final deadline for up to three seconds without changing it. H2 is rerun with
  this corrected completion check; its final evidence is recorded separately.
- Earlier short 6s GUI B failures and interrupted WSL runs are retained under
  results/mock-audit-rgb7kkxq, mock-audit-nbacv3se and mock-audit-iln0w4cm. A 6s day
  leaves only 3s after GUI safety reserve and can be consumed by polling backoff.
  Moving the functional GUI suite to 12s does not establish that 6s is safe.

The Windows launcher/systemd/browser wrapper has only been inspected, not opened
interactively in this audit. Its binary paths and ports match the real GUI HTTP
instances used by the tests. A port collision with the original GUI remains an
operational hazard; do not interpret a successful GET / on 8765 as binary identity.

## Release Integrity

Verified against the prior report; no release binaries were rebuilt or replaced:

| Artifact | SHA256 |
| --- | --- |
| /home/hexa/build-release/hexa_udon | d864d3fd2f325773cbcd594dc93063b63882ca07fa5947365944fa0e8ec7b903 |
| /home/hexa/release/hexa_udon_B | feaa67c74d8b3f21ebf3ee2797d4de765924cbeb97b8d2d1bf496aed727399d1 |
| /home/hexa/release/hexa_udon_H2 | 6ac30c33292aa33234c84bea757376b7b30f8cf05432d8b91e3f332464331c04 |

python tests/benchmark/round8_check.py and python3 tests/gui_check.py also pass.
These are historical-fixture/hash and GUI regression checks, not new live-server
benchmarks or evidence that H2 wins every full HTTP match.

## Final Status

Final machine-readable evidence: results/mock-audit-final.json. It includes source
hashes, Git revision, all three binary hashes, fresh strict offline revalidation,
request/ack times, server durations, scores and failure traces. Final negative,
reference and actual GUI controls: results/mock-audit-w9d6l0hh.

| Category | Status | Scope |
| --- | --- | --- |
| HTTP protocol compatibility | PASS | Repository Procon client/codec and local HTTP mock |
| Valid action submission | PASS | Server validates before storing any accepted revision |
| Invalid action rejection | PASS | Negative requests do not alter accepted revisions or crash handlers |
| Complete full-match simulation | PASS | Both actual GUI clients, 4/4 natural days, [10,22,22] each |
| State consistency | PASS | Fresh persisted C++ client summaries vs Python server; 78 historical reference days |
| Deadline stress test | FAIL | 1500ms timing trace inconsistent; 4000ms registration fails; neither counted PASS |
| Competition-budget test | PASS | Both clients, 60s/day, injected 100ms request delay, local-only |
| GUI integration | PASS | Actual Handler/Runner HTTP Start/Stop, release client identity and full match |
| Windows .cmd/browser/systemd launch | NOT VERIFIED | Paths/ports inspected, wrapper not interactively opened |
| Graceful session recovery | PASS | Both clients, same session, no duplicate vehicle POST |
| Production binary integrity | PASS | All three SHA256 values match prior report |
| Opponent traffic/resource arbitration | NOT VERIFIED | Single-team model only |
| Actual competition-server compatibility | NOT VERIFIED | No real server accessed; HAUI not tested |

Final H2 daily-budget run:
results/mock-audit-competition-9z56wt6o/H2-100ms-60s, PASS, score [9,16,16],
244747ms whole-match duration measured with monotonic time. Both 60s/day runs also
pass the latest strict day/revision/action/state checks and server receipt,
validation, response and client acknowledgment deadline checks. Minimum observed
acknowledgment margins: B 58002ms, H2 9642ms. These are margins of the plans actually
submitted (including earlier interim improvements), not proof of every search
iteration's runtime or a universal planner reserve.

| Scenario | Result | Maximum persisted client POST round trip |
| --- | --- | --- |
| GUI B, 12s days, 0ms injected delay | PASS | 272ms |
| GUI H2, 12s days, 0ms injected delay | PASS | 316ms |
| H2, 6s days, 20ms delay | PASS | 282ms |
| H2, 6s days, 50ms delay | PASS | 287ms |
| H2, 6s days, 100ms delay | PASS | 262ms |
| H2, 6s days, 1500ms delay | FAIL timing validation | Not trustworthy as a single clock-based duration |
| H2, 6s days, 4000ms delay | FAIL match | Registration window expired |
| B, 60s days, 100ms delay | PASS | 276ms |
| H2, 60s days, 100ms delay | PASS | 278ms |

Round-trip values include client-side request throttling, so they are not expected
to equal the injected delay. Both GUI matches pass revised strict offline checks,
including matching final accepted actions and revisions, and server/client ACK
cutoffs. No score superiority claim is made: auto lineups and time-bounded threaded
search are not identical controlled benchmark conditions across these runs.

## Decision

H2 remains a viable main-solver candidate and B an independent fallback for local
integration trials. No solver algorithm defect was demonstrated by this audit.
Do not call the release absolutely safe or proven deployment-ready for the real
competition server. The 1500ms trace is explicitly a measurement failure even
though all four days completed. Resolve/monitor WSL wall-clock discontinuities,
obtain monotonic client-side phase/receive/ACK instrumentation if exact attribution
is required, and manually verify the Windows launcher and intended server protocol
before competition. Preserve the existing 3s GUI safety reserve; these data do not
justify reducing it to 50ms or relying solely on a percentage. Remote RTT-tail and
clock-skew measurements are still needed to size any competition reserve.

No deployment, production replacement, commit, push, or actual competition POST
was performed. Use the separate GUI Stop controls, keep B/H2 on different local
ports, and never attach both to the same real match session during trials.
