"""Local-only HTTP audit. Run inside WSL from repository root."""
import argparse
import hashlib
import http.client
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import traceback
import threading
import time

sys.path.insert(0, str(Path(__file__).resolve().parent))
from procon_mock_server import run_mock_server, ProconMockServer
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from gui import Handler, Runner, ThreadingHTTPServer

FIXTURE = 'results/solver-round7/dev-fixed/bridge-12100-s201.fixture.json'


def request(port, method, path, data=None, raw=None, key=None):
    headers = {'Content-Type': 'application/json'}
    if key:
        headers.update({'X-GUI-Key': key, 'Origin': f'http://127.0.0.1:{port}'})
    connection = http.client.HTTPConnection('127.0.0.1', port, timeout=20)
    started = time.time_ns()
    connection.request(method, path, raw if raw is not None else json.dumps(data) if data is not None else None, headers)
    response = connection.getresponse()
    body = response.read()
    acknowledged = time.time_ns()
    connection.close()
    return dict(status=response.status, body=json.loads(body), started_ns=started, acknowledged_ns=acknowledged)


def negative_checks():
    server, app = run_mock_server(0, FIXTURE, 5, 6)
    port = server.server_port
    suffix = '?token=' + app.token
    events = []
    def send(method, path, data=None, raw=None):
        event = request(port, method, path + suffix, data, raw)
        events.append(event)
        return event
    try:
        assert send('GET', '/setting')['status'] == 200
        for lineup in ([0], [0, 0, 2], [False, 0, 0], {}):
            assert send('POST', '/agent', lineup)['status'] == 400
        assert send('POST', '/agent', raw='{')['status'] == 400
        assert send('POST', '/agent', [0, 0, 1])['status'] == 200
        with app.lock:
            app.starts_at = int(time.time()) - 1
            app.current_ends_at = int(time.time()) + 6
        wait = [[-12], [-12], [-12]]
        for bad in ([], wait[:2], [[6], [-12], [-12]], [[True], [-12], [-12]],
                    [[-13], [-12], [-12]], [[1.5], [-12], [-12]]):
            result = send('POST', '/', bad)
            assert result['body']['valid'] is False
            assert not app.day_revisions
        with app.lock:
            original = [dict(agent) for agent in app.agents]
            app.agents[0].update(pos=0, fuel=0)
        assert send('POST', '/', [[0] * 12, [-12], [-12]])['body']['valid'] is False
        with app.lock:
            app.agents[0]['pos'] = 66
        row = json.loads(Path('results/solver-round7/dev-fixed/bridge-12100-s201-B.json').read_text())['days'][0]['plan'][0]
        assert send('POST', '/', [row, [-12], [-12]])['body']['error'] == 'Insufficient fuel'
        with app.lock:
            app.agents = original
        assert send('POST', '/', wait)['body']['revision'] == 1
        assert send('POST', '/', wait)['body']['revision'] == 2
        with app.lock:
            app.current_ends_at = int(time.time()) - 1
        assert send('POST', '/', wait)['status'] == 403
        with app.lock:
            app.current_ends_at = int(time.time()) - 100
            app.step_day_if_needed()
            assert app.match_completed and len(app.history) == app.total_days
            assert all(len(day['plan']) == 3 for day in app.history)
        assert send('POST', '/', wait)['status'] == 403
        bad_auth = request(port, 'GET', '/setting?token=wrong')
        assert bad_auth['status'] == 401
        app.artificial_delay_sec = .1
        delayed = send('GET', '/setting')
        assert (delayed['acknowledged_ns'] - delayed['started_ns']) / 1e6 >= 100
        app.artificial_delay_sec = .2
        with app.lock:
            app.match_completed = False
            app.current_day = 0
            app.current_ends_at = time.time() + .05
        late = send('POST', '/', wait)
        assert late['status'] == 403
        return dict(client=events, server=app.request_log)
    finally:
        server.shutdown()
        server.server_close()


def reference_checks():
    comparisons = 0
    for variant in ('B', 'H2'):
        for fixture in sorted(Path('results/solver-round7/dev-fixed').glob('*.fixture.json')):
            app = ProconMockServer(fixture)
            recorded = json.loads(Path(str(fixture).replace('.fixture.json', f'-{variant}.json')).read_text())
            app.agents = [dict(kind=kind, pos=position, fuel=app.fuel_limit)
                          for kind, position in zip(recorded['kinds'], app.fixture['agents'])]
            for day in recorded['days']:
                app.current_day = day['day']
                status = app.current_traffic_status()
                assert status == day['status']
                agents, stay, hits, balls = app.validate_plan(day['plan'])
                assert [agent['pos'] for agent in agents] == day['positions']
                assert [agent['fuel'] for agent in agents] == day['fuel']
                assert hits == day['hits'] and balls == day['bowls'] and stay == day['stay']
                app.agents = agents
                app.stays.append(stay)
                comparisons += 1
    app = ProconMockServer(FIXTURE)
    position = app.spots[0]['pos']
    app.agents = [dict(kind=0, pos=position, fuel=0), dict(kind=0, pos=position, fuel=0), dict(kind=1, pos=position, fuel=0)]
    agents, stay, hits, bowls = app.validate_plan([[-12], [-12], [-12]])
    assert bowls == min(2, app.spots[0]['stocks'])
    assert agents[0]['fuel'] == agents[1]['fuel'] == app.fuel_limit
    assert agents[2]['fuel'] == 0
    assert app.last_stock[0] == app.spots[0]['stocks'] - bowls
    return comparisons


def match(output, variant, delay, day_seconds, gui=False, binary=None):
    label = f'{variant}-{delay}ms-{day_seconds}s' + ('-gui' if gui else '')
    directory = output / label
    directory.mkdir()
    server, app = run_mock_server(0, FIXTURE, 18 if gui else 4, day_seconds, delay)
    binary = binary or f'/home/hexa/release/hexa_udon_{variant}'
    process = None
    gui_server = None
    started = time.monotonic_ns()
    try:
        if gui:
            runner = Runner(binary, directory / 'runtime')
            gui_server = ThreadingHTTPServer(('127.0.0.1', 8767 if variant == 'B' else 8766), Handler)
            gui_server.host = f'127.0.0.1:{gui_server.server_port}'
            gui_server.key, gui_server.runner = 'a' * 64, runner
            threading.Thread(target=gui_server.serve_forever, daemon=True).start()
            response = request(gui_server.server_port, 'POST', '/start', dict(mode='execute', confirmed=True,
                backend='procon', url=f'http://127.0.0.1:{server.server_port}', token=app.token), key=gui_server.key)
            assert response['status'] == 200
            process = runner.process
        else:
            environment = dict(os.environ, PROCON_TOKEN=app.token)
            log_handle = (directory / 'client.log').open('w')
            process = subprocess.Popen([binary, 'auto', '--base-url', f'http://127.0.0.1:{server.server_port}',
                '--execute', '--session-dir', str(directory / 'session'), '--log-dir', str(directory / 'log'),
                '--kind-ms', '500', '--safety-seconds', '1', '--poll-ms', '500', '--threads', '4'],
                env=environment, stdout=log_handle, stderr=subprocess.STDOUT)
        process.wait(timeout=day_seconds * app.total_days + 90)
        if gui:
            while runner.running:
                time.sleep(.05)
            (directory / 'client.log').write_text(runner.log)
            session = Path(runner.session)
        else:
            log_handle.close()
            session = directory / 'session'
        finalization_limit = time.monotonic() + 3
        while not app.match_completed and time.monotonic() < finalization_limit:
            with app.lock:
                app.step_day_if_needed()
            if not app.match_completed:
                time.sleep(.01)
        state = json.loads((session / 'session.json').read_text())
        (directory / 'session.json').write_text(json.dumps(state, indent=2))
        assert app.match_completed and process.returncode == 0
        timings = audit_evidence(state, app.history, app.request_log, app.total_days, delay)
        result = dict(label=label, status='PASS', score=[len(app.acquired_brands), sum(app.daily_distinct_brand_counts), app.total_balls],
                      elapsed_ms=(time.monotonic_ns()-started)/1e6, timings=timings)
    except Exception as error:
        result = dict(label=label, status='FAIL', error=repr(error), traceback=traceback.format_exc())
    finally:
        if process and process.poll() is None:
            process.terminate()
            process.wait(timeout=20)
        if gui_server:
            gui_server.shutdown()
            gui_server.server_close()
        server.shutdown()
        server.server_close()
        (directory / 'http.json').write_text(json.dumps(app.request_log, indent=2))
        (directory / 'history.json').write_text(json.dumps(app.history, indent=2))
    (directory / 'result.json').write_text(json.dumps(result, indent=2))
    print(json.dumps({key: value for key, value in result.items() if key != 'timings'}), flush=True)
    return result


def audit_evidence(state, history, events, total_days, delay):
    assert len(state['acceptedDays']) == len(history) == total_days
    for accepted, day_history in zip(state['acceptedDays'], history):
        assert accepted['day'] == day_history['day']
        assert accepted['revision'] == day_history['revision']
        assert json.loads(accepted['actions']) == day_history['plan']
        simulation = accepted['simulation']
        assert simulation['totalBalls'] == day_history['balls']
        assert set(simulation['brands']) == {brand for brand, hit in enumerate(day_history['hits']) if hit}
        assert simulation['endAgents'] == [dict(kind=agent['kind'], position=agent['pos'], fuel=agent['fuel']) for agent in day_history['agents']]
    timings = []
    for submission in state['submissions']:
        if submission.get('revision') is None:
            continue
        candidates = [event for event in events if event['method'] == 'POST' and event['path'] == '/'
                      and event['day'] == submission['day'] and event['response'].get('revision') == submission['revision']]
        assert len(candidates) == 1
        event = candidates[0]
        elapsed = submission['finishedAtMs'] - submission['startedAtMs']
        assert elapsed >= delay - 2 and event['elapsed_ms'] >= delay - 2, (
            f"Invalid timing day={submission['day']} revision={submission['revision']}: "
            f"client_wall_ms={elapsed}, server_monotonic_ms={event['elapsed_ms']}, delay_ms={delay}")
        assert abs((event['response_ns'] - event['receipt_ns']) / 1e6 - event['elapsed_ms']) < 50, 'Wall-clock discontinuity during HTTP request'
        assert event['receipt_ns'] < event['deadline'] * 1e9
        assert event['validation_ns'] < event['deadline'] * 1e9
        assert event['response_ns'] < event['deadline'] * 1e9
        assert submission['finishedAtMs'] <= event['deadline'] * 1000
        states = [entry for entry in events if entry['method'] == 'GET' and entry['path'] == '/'
                  and entry['status'] == 200 and entry['response'].get('day') == submission['day']
                  and entry['validation_ns'] <= event['receipt_ns']]
        assert states
        timings.append(dict(day=submission['day'], revision=submission['revision'],
            client_request_start_ms=submission['startedAtMs'], client_ack_ms=submission['finishedAtMs'],
            server_receipt_ns=event['receipt_ns'], validation_ns=event['validation_ns'],
            response_ns=event['response_ns'], deadline=event['deadline'], client_roundtrip_ms=elapsed,
            server_elapsed_monotonic_ms=event['elapsed_ms'],
            server_wall_minus_monotonic_ms=(event['response_ns']-event['receipt_ns'])/1e6-event['elapsed_ms'],
            receipt_margin_ms=event['deadline']*1000-event['receipt_ns']/1e6,
            validation_margin_ms=event['deadline']*1000-event['validation_ns']/1e6,
            state_ready_to_receipt_upper_ms=(event['receipt_ns']-states[0]['validation_ns'])/1e6,
                state_response_to_receipt_lower_ms=max(0, (event['receipt_ns']-states[0]['response_ns'])/1e6)))
    assert timings
    return timings


def recovery_check(output, variant):
    directory = output / ('recovery-' + variant)
    directory.mkdir()
    server, app = run_mock_server(0, FIXTURE, 4, 8)
    binary = f'/home/hexa/release/hexa_udon_{variant}'
    command = [binary, 'auto', '--base-url', f'http://127.0.0.1:{server.server_port}',
        '--execute', '--session-dir', str(directory / 'session'), '--log-dir', str(directory / 'log'),
        '--kind-ms', '500', '--safety-seconds', '1', '--poll-ms', '500', '--threads', '4']
    environment = dict(os.environ, PROCON_TOKEN=app.token)
    process = None
    try:
        with (directory / 'before-stop.log').open('w') as log:
            process = subprocess.Popen(command, env=environment, stdout=log, stderr=subprocess.STDOUT)
            limit = time.monotonic() + 30
            while time.monotonic() < limit:
                state_path = directory / 'session/session.json'
                if state_path.exists():
                    state = json.loads(state_path.read_text())
                    if state.get('dailyPlanningDiagnostics'):
                        break
                time.sleep(.05)
            else:
                raise AssertionError('No completed planning before stop')
            process.terminate()
            assert process.wait(timeout=15) == 130
        state = json.loads(state_path.read_text())
        (directory / 'stopped-session.json').write_text(json.dumps(state, indent=2))
        assert state['submittedAgentKinds'] == app.submitted_kinds
        assert all(record['submissionAttempted'] is not None for record in state['submissions'])
        command[1] = 'recover'
        with (directory / 'after-recover.log').open('w') as log:
            process = subprocess.Popen(command, env=environment, stdout=log, stderr=subprocess.STDOUT)
            assert process.wait(timeout=70) == 0
        finalization_limit = time.monotonic() + 3
        while not app.match_completed and time.monotonic() < finalization_limit:
            with app.lock:
                app.step_day_if_needed()
            if not app.match_completed:
                time.sleep(.01)
        state = json.loads(state_path.read_text())
        (directory / 'session.json').write_text(json.dumps(state, indent=2))
        assert app.match_completed
        timings = audit_evidence(state, app.history, app.request_log, app.total_days, 0)
        assert sum(event['path'] == '/agent' for event in app.request_log) == 1
        result = dict(status='PASS', variant=variant, submissions=len(timings))
    except Exception as error:
        result = dict(status='FAIL', variant=variant, error=repr(error), traceback=traceback.format_exc())
    finally:
        if process and process.poll() is None:
            process.terminate()
            process.wait(timeout=20)
        server.shutdown()
        server.server_close()
        (directory / 'http.json').write_text(json.dumps(app.request_log, indent=2))
        (directory / 'history.json').write_text(json.dumps(app.history, indent=2))
    (directory / 'result.json').write_text(json.dumps(result, indent=2))
    print(result, flush=True)
    return result


def gui_controls(output):
    results = []
    for variant in ('B', 'H2'):
        runner = Runner('/home/hexa/release/hexa_udon_' + variant, output / ('control-' + variant))
        server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        server.host = f'127.0.0.1:{server.server_port}'
        server.key, server.runner = 'b' * 64, runner
        threading.Thread(target=server.serve_forever, daemon=True).start()
        try:
            started = request(server.server_port, 'POST', '/start', dict(mode='dry',
                url='http://127.0.0.1:1', token='local-only'), key=server.key)
            assert started['status'] == 200
            executable = str(Path(f'/proc/{runner.process.pid}/exe').resolve())
            assert executable == str(runner.binary)
            time.sleep(.2)
            assert request(server.server_port, 'POST', '/stop', dict(confirmed=True), key=server.key)['status'] == 200
            limit = time.monotonic() + 15
            while runner.running and time.monotonic() < limit:
                time.sleep(.05)
            assert not runner.running and runner.exit_code in (130, -15)
            results.append(dict(variant=variant, executable=executable, status='PASS', snapshot=runner.snapshot()))
        finally:
            runner.stop()
            server.shutdown()
            server.server_close()
    (output / 'gui-controls.json').write_text(json.dumps(results, indent=2))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--competition', action='store_true')
    parser.add_argument('--recovery-only', action='store_true')
    parser.add_argument('--gui-only', action='store_true')
    parser.add_argument('--checks-only', action='store_true')
    parser.add_argument('--stress-only', action='store_true')
    parser.add_argument('--competition-only', action='store_true')
    args = parser.parse_args()
    output = Path(tempfile.mkdtemp(prefix='mock-audit-', dir='results')).resolve()
    print(output, flush=True)
    if args.competition_only:
        results = [match(output, variant, 100, 60) for variant in ('B', 'H2')]
        return int(any(result['status'] != 'PASS' for result in results))
    if args.stress_only:
        results = [match(output, 'H2', delay, 6) for delay in (0, 20, 50, 100, 1500, 4000)]
        return int(any(result['status'] != 'PASS' for result in results))
    if args.checks_only:
        (output / 'negative.json').write_text(json.dumps(negative_checks(), indent=2))
        (output / 'reference.json').write_text(json.dumps(dict(days=reference_checks())))
        gui_controls(output)
        print('Negative HTTP, GUI controls and simulator parity checks PASS', flush=True)
        return 0
    if args.gui_only:
        results = [match(output, variant, 0, 12, gui=True) for variant in ('B', 'H2')]
        return int(any(result['status'] != 'PASS' for result in results))
    if args.recovery_only:
        results = [recovery_check(output, variant) for variant in ('B', 'H2')]
        return int(any(result['status'] != 'PASS' for result in results))
    (output / 'negative.json').write_text(json.dumps(negative_checks(), indent=2))
    count = reference_checks()
    print(f'Reference day comparisons: {count}', flush=True)
    results = [match(output, variant, 0, 12, gui=True) for variant in ('B', 'H2')]
    results += [match(output, 'H2', delay, 6) for delay in (20, 50, 100, 1500)]
    if args.competition:
        results += [match(output, variant, 100, 60) for variant in ('B', 'H2')]
    hashes = {path: hashlib.sha256(Path(path).read_bytes()).hexdigest() for path in (
        '/home/hexa/build-release/hexa_udon', '/home/hexa/release/hexa_udon_B', '/home/hexa/release/hexa_udon_H2')}
    (output / 'summary.json').write_text(json.dumps(dict(reference_days=count, matches=results, hashes=hashes), indent=2))
    return int(any(result['status'] != 'PASS' for result in results))

if __name__ == '__main__':
    sys.exit(main())
