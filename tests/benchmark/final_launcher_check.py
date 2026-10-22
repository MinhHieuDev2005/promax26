"""Check already-open Windows launchers against loopback mocks; never a real server."""
import hashlib
import http.client
import json
from pathlib import Path
import re
import sys
import tempfile
import time

sys.path.insert(0, str(Path(__file__).resolve().parent))
from deadline_stress_test import FIXTURE, audit_evidence, request
from procon_mock_server import run_mock_server


def main():
    output = Path(tempfile.mkdtemp(prefix='final-launchers-', dir='results')).resolve()
    print(output, flush=True)
    for variant, port in (('B', 8767), ('H2', 8766)):
        directory = output / variant
        directory.mkdir()
        connection = http.client.HTTPConnection('127.0.0.1', port, timeout=10)
        connection.request('GET', '/')
        page = connection.getresponse().read().decode()
        connection.close()
        key = re.search(r'nonce="([a-f0-9]{64})"', page).group(1)
        initial = request(port, 'GET', '/status', key=key)['body']
        assert not initial['running'], 'Do not interrupt an existing client'
        server, app = run_mock_server(0, FIXTURE, 18, 12)
        try:
            assert request(port, 'POST', '/start', dict(mode='execute', confirmed=True,
                backend='procon', url=f'http://127.0.0.1:{server.server_port}', token=app.token), key=key)['status'] == 200
            limit = time.monotonic() + 100
            while time.monotonic() < limit:
                status = request(port, 'GET', '/status', key=key)['body']
                if not status['running']:
                    break
                time.sleep(.2)
            assert not status['running'] and status['exit_code'] == 0, status
            while not app.match_completed and time.monotonic() < limit:
                with app.lock:
                    app.step_day_if_needed()
                time.sleep(.02)
            state = json.loads((Path(status['session']) / 'session.json').read_text())
            timings = audit_evidence(state, app.history, app.request_log, app.total_days, 0)
            result = dict(status='PASS', variant=variant, port=port, session=status['session'], timings=timings)
            (directory / 'session.json').write_text(json.dumps(state, indent=2))
            (directory / 'client.log').write_text(status['log'])
        except Exception as error:
            result = dict(status='FAIL', variant=variant, error=repr(error))
            raise
        finally:
            server.shutdown()
            server.server_close()
            (directory / 'http.json').write_text(json.dumps(app.request_log, indent=2))
            (directory / 'history.json').write_text(json.dumps(app.history, indent=2))
            (directory / 'result.json').write_text(json.dumps(result, indent=2))
        print(variant + ' launcher HTTP full match PASS', flush=True)
    paths = ('/home/hexa/build-release/hexa_udon', '/home/hexa/release/hexa_udon_B', '/home/hexa/release/hexa_udon_H2')
    (output / 'hashes.json').write_text(json.dumps({path: hashlib.sha256(Path(path).read_bytes()).hexdigest() for path in paths}, indent=2))


if __name__ == '__main__':
    main()
