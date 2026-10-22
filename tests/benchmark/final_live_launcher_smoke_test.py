"""Final Live-Launcher Smoke Test: Production A (8765), H2 (8766), B (8767).
Local mock only. Verifies binaries, process cmdlines, SHA256, match run,
stop isolation, and session preservation.
"""
import hashlib
import http.client
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import time

ROOT = Path('/mnt/d/30013-o-udon')
sys.path.insert(0, str(ROOT / 'tests/benchmark'))
from procon_mock_server import run_mock_server
from deadline_stress_test import FIXTURE, audit_evidence, request

EXPECTED = {
    'production': {
        'unit': 'hexa-udon-gui',
        'port': 8765,
        'binary': '/home/hexa/release/http-fix-20261016/hexa_udon_production_httpfix',
        'sha256': '662d98b1aff91a09ca06c72c05ff68797d3e5a04f53d2704f76030e422f80521',
    },
    'H2': {
        'unit': 'hexa-udon-gui-h2',
        'port': 8766,
        'binary': '/home/hexa/release/http-fix-20261016/hexa_udon_H2_httpfix',
        'sha256': 'b64477871b6a6f2199f46a1a3e5d8c613f30ba0ae6e70435ca4388d92264df55',
    },
    'B': {
        'unit': 'hexa-udon-gui-b',
        'port': 8767,
        'binary': '/home/hexa/release/http-fix-20261016/hexa_udon_B_httpfix',
        'sha256': '45ae08ed0df4d11fbe37aebb1c53298ef79d1ad9d455e00e9636b1d186d5bacc',
    },
}

def get_nonce(port):
    conn = http.client.HTTPConnection('127.0.0.1', port, timeout=5)
    conn.request('GET', '/')
    page = conn.getresponse().read().decode()
    conn.close()
    return re.search(r'nonce="([a-f0-9]{64})"', page).group(1)

def is_active(unit):
    res = subprocess.run(['systemctl', 'is-active', f'{unit}.service'], capture_output=True, text=True)
    return res.stdout.strip() == 'active'

def start_gui(variant):
    spec = EXPECTED[variant]
    unit, port, binary = spec['unit'], spec['port'], spec['binary']
    args = [
        'systemd-run', f'--unit={unit}', '--collect', '--uid=hexa', '--setenv=HOME=/home/hexa',
        '--property=MemoryMax=3G', '--property=MemorySwapMax=512M', '--property=CPUAffinity=0-7', '--property=Nice=10',
        '--working-directory=' + str(ROOT),
        '/usr/bin/python3', '-B', str(ROOT / 'gui.py'), '--binary', binary, '--port', str(port)
    ]
    subprocess.check_output(args)
    for _ in range(50):
        try:
            return get_nonce(port)
        except OSError:
            time.sleep(0.1)
    raise RuntimeError(f'GUI {unit} failed to start on port {port}')

def stop_gui(unit):
    subprocess.check_output(['systemctl', 'stop', f'{unit}.service'])
    for _ in range(30):
        if not is_active(unit):
            return
        time.sleep(0.1)
    raise RuntimeError(f'GUI {unit} failed to stop')

def run_match_test(variant, nonce, output_dir):
    spec = EXPECTED[variant]
    port, expected_bin, expected_hash = spec['port'], spec['binary'], spec['sha256']
    variant_dir = output_dir / variant
    variant_dir.mkdir(parents=True, exist_ok=True)

    # 1. Inspect unit ExecStart
    exec_start = subprocess.check_output(['systemctl', 'show', spec['unit'], '-p', 'ExecStart', '--value'], text=True)
    assert expected_bin in exec_start, f'ExecStart does not contain {expected_bin}: {exec_start}'

    # 2. Start loopback mock server (2 days, 10s delay, 12s per day)
    fixture = json.loads((ROOT / FIXTURE).read_text())
    fixture['daySteps'] = fixture['daySteps'][:2]
    fix_path = variant_dir / 'fixture.json'
    fix_path.write_text(json.dumps(fixture))
    server, app = run_mock_server(0, str(fix_path), 10, 12)
    url = f'http://127.0.0.1:{server.server_port}'

    try:
        # Start match via GUI
        start_res = request(port, 'POST', '/start', {
            'mode': 'execute', 'backend': 'procon', 'confirmed': True,
            'url': url, 'token': app.token
        }, key=nonce)
        assert start_res['status'] == 200, start_res

        # Check running child process
        time.sleep(1)
        main_pid = int(subprocess.check_output(['systemctl', 'show', spec['unit'], '-p', 'MainPID', '--value'], text=True).strip())
        children = Path(f'/proc/{main_pid}/task/{main_pid}/children').read_text().split()
        assert len(children) >= 1, f'No child process found for MainPID {main_pid}'
        child_pid = children[0]
        child_exe = str(Path(f'/proc/{child_pid}/exe').resolve())
        child_cmdline = Path(f'/proc/{child_pid}/cmdline').read_bytes().replace(b'\0', b' ').decode()
        child_hash = hashlib.sha256(Path(child_exe).read_bytes()).hexdigest()

        assert child_exe == expected_bin, f'Child exe mismatch: {child_exe} != {expected_bin}'
        assert child_hash == expected_hash, f'Child hash mismatch: {child_hash} != {expected_hash}'
        (variant_dir / 'process.json').write_text(json.dumps({
            'main_pid': main_pid, 'child_pid': child_pid,
            'child_exe': child_exe, 'child_cmdline': child_cmdline,
            'child_hash': child_hash
        }, indent=2))

        # Wait for match to finish
        limit = time.monotonic() + 50
        while time.monotonic() < limit:
            status = request(port, 'GET', '/status', key=nonce)['body']
            if not status['running']:
                break
            time.sleep(0.3)
        assert not status['running'], 'Match did not finish in time'
        assert status['exit_code'] == 0, f'Exit code not 0: {status}'

        # Verify operations and session
        session_path = Path(status['session'])
        session_data = json.loads((session_path / 'session.json').read_text())
        ops_path = session_path.parent / 'log/operations.jsonl'
        operations = [json.loads(l) for l in ops_path.read_text().splitlines()]
        (variant_dir / 'client.log').write_text(status['log'])
        (variant_dir / 'session.json').write_text(json.dumps(session_data, indent=2))
        (variant_dir / 'operations.jsonl').write_text(ops_path.read_text())

        # Verify days were accepted
        accepted = session_data.get('acceptedDays', [])
        assert len(accepted) == 2, f'Expected 2 accepted days, got {len(accepted)}'
        # Check HTTP POST entries
        post_events = [op for op in operations if op.get('operation') in ('daily-submit', 'submit-actions')]
        assert len(post_events) >= 2, f'Expected submit operations: {post_events}'
        for ev in post_events:
            assert ev.get('httpStatus') == 200, ev
            assert ev.get('submissionAttempted') is True, ev

        print(f'Match execution for {variant} on port {port}: PASS (scores={session_data.get("scores")})', flush=True)
        return True
    finally:
        server.shutdown()
        server.server_close()

def main():
    output_dir = ROOT / 'results/final-live-smoke-test'
    output_dir.mkdir(parents=True, exist_ok=True)

    print('=== STEP 1 & 2: Checking existing units and processes ===')
    for var, spec in EXPECTED.items():
        unit = spec['unit']
        active = is_active(unit)
        print(f'{unit}: active={active}')
        assert not active, f'{unit} is active! Please stop it before testing.'

    # Check for running solver processes
    ps = subprocess.check_output(['ps', '-eo', 'pid,user,args'], text=True)
    for line in ps.splitlines():
        if any(b in line for b in ('hexa_udon_production_httpfix', 'hexa_udon_H2_httpfix', 'hexa_udon_B_httpfix')):
            raise RuntimeError(f'Lingering solver process found: {line}')

    print('=== STEP 3 & 4: Starting all 3 GUIs and verifying ExecStart & hashes ===')
    nonces = {}
    for var in ('production', 'H2', 'B'):
        nonces[var] = start_gui(var)
        print(f'Started {var} GUI on port {EXPECTED[var]["port"]}')

    # Verify all 3 are active simultaneously
    for var, spec in EXPECTED.items():
        assert is_active(spec['unit']), f'{spec["unit"]} is not active'

    print('=== STEP 5: Running mock match through each live GUI ===')
    for var in ('production', 'H2', 'B'):
        run_match_test(var, nonces[var], output_dir)

    print('=== STEP 6: Testing Stop isolation on each GUI ===')
    # Stop B first
    stop_gui(EXPECTED['B']['unit'])
    assert not is_active(EXPECTED['B']['unit']), 'B should be inactive'
    assert is_active(EXPECTED['production']['unit']), 'production should still be active'
    assert is_active(EXPECTED['H2']['unit']), 'H2 should still be active'
    print('Stop B isolation: PASS')

    # Stop H2 next
    stop_gui(EXPECTED['H2']['unit'])
    assert not is_active(EXPECTED['H2']['unit']), 'H2 should be inactive'
    assert is_active(EXPECTED['production']['unit']), 'production should still be active'
    print('Stop H2 isolation: PASS')

    # Stop Production last
    stop_gui(EXPECTED['production']['unit'])
    assert not is_active(EXPECTED['production']['unit']), 'production should be inactive'
    print('Stop Production isolation: PASS')

    # Confirm WSL is alive and normal
    wsl_check = subprocess.check_output(['uptime'], text=True)
    assert 'load average' in wsl_check
    print('WSL host health: PASS')

    print('=== STEP 7: Verifying all pre-existing sessions preserved ===')
    initial_hashes = json.loads(Path('/home/hexa/initial_session_hashes.json').read_text())
    preserved_count = 0
    for path_str, expected_hash in initial_hashes.items():
        p = Path(path_str)
        assert p.is_file(), f'Session file missing: {path_str}'
        actual_hash = hashlib.sha256(p.read_bytes()).hexdigest()
        assert actual_hash == expected_hash, f'Session file modified: {path_str}'
        preserved_count += 1
    print(f'Preserved session files verified: {preserved_count}/{len(initial_hashes)} PASS')

    print('=== ALL CRITERIA PASSED: FINAL LOCAL RELEASE READY ===')

if __name__ == '__main__':
    main()
