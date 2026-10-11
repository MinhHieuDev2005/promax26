import http.client
import io
import json
from pathlib import Path
import sys
import tempfile
import threading
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from gui import Handler, Runner, ThreadingHTTPServer, validate_request


def rejected(data):
    try:
        validate_request(data)
    except ValueError:
        return
    raise AssertionError('Unsafe input was accepted')


request = {'mode': 'dry', 'url': 'https://example.invalid', 'token': 'secret/value', 'backend': 'procon'}
assert validate_request(request) == ('https://example.invalid', 'secret/value')
haui_request = {'mode': 'dry', 'backend': 'haui', 'url': 'https://example.invalid', 'token': 'token123', 'match_id': 'match-1'}
assert validate_request(haui_request) == ('https://example.invalid', 'token123')
for invalid in (None, [], {}, dict(request, mode='shell'), dict(request, token=''),
                dict(request, backend='bad'), dict(haui_request, match_id='../bad'),
                dict(haui_request, token='bad token\n'), dict(haui_request, match_id=''),
                dict(request, token='secret\nvalue'), dict(request, mode='execute'),
                dict(request, mode='execute', confirmed='yes')):
    rejected(invalid)
for url in ('file:///etc/passwd', 'https://user:pass@example.invalid',
            'https://example.invalid?token=secret', 'http://example.invalid:bad',
            'http://example.invalid/#fragment', 'http://example.invalid/\npath'):
    rejected(dict(request, url=url))

with tempfile.TemporaryDirectory() as temporary:
    binary = Path(temporary) / 'client'
    binary.touch()
    runner = Runner(binary, Path(temporary) / 'runtime')
    process = Mock()
    process.poll.return_value = None
    process.wait.return_value = 0
    process.stdout = io.StringIO('secret/value secret%2Fvalue\n' + 'x' * 8190 + 'secret/value\nOK\n')
    with patch('gui.subprocess.Popen', return_value=process) as launch, patch('gui.threading.Thread'):
        runner.start(request)
        command = launch.call_args.args[0]
        assert '--execute' not in command and command[1] == 'auto'
        assert command[command.index('--threads') + 1] == '8'
        assert 'secret/value' not in command
        assert launch.call_args.kwargs['env']['PROCON_TOKEN'] == 'secret/value'
        assert not launch.call_args.kwargs.get('shell', False)
        first_session = runner.session
        try:
            runner.start(request)
        except ValueError:
            pass
        else:
            raise AssertionError('Concurrent start was accepted')
        assert launch.call_count == 1
        runner.stop()
        process.terminate.assert_called_once()
    runner.collect(process, request['token'])
    assert runner.log == '[TOKEN HIDDEN] [TOKEN HIDDEN]\nOK\n'
    assert not runner.running and runner.exit_code == 0
    with patch('gui.subprocess.Popen', return_value=process) as launch, patch('gui.threading.Thread'):
        runner.start(dict(request, mode='execute', confirmed=True))
        assert '--execute' in launch.call_args.args[0]
        assert runner.session != first_session
        runner.running = False
        runner.start({'mode': 'state'})
        assert launch.call_args.args[0][1:] == ['show-state', '--session-dir', runner.session]
        assert 'PROCON_TOKEN' not in launch.call_args.kwargs['env']
        runner.running = False
        runner.start(dict(request, mode='check'))
        assert launch.call_args.args[0][1] == 'check'
        assert '--execute' not in launch.call_args.args[0]
        runner.running = False
        runner.start(dict(haui_request, mode='check'))
        assert '--haui-match' in launch.call_args.args[0]
        assert launch.call_args.args[0][launch.call_args.args[0].index('--haui-match') + 1] == 'match-1'
    with patch('gui.subprocess.Popen', side_effect=OSError):
        runner.running = False
        try:
            runner.start(request)
        except ValueError:
            pass
        else:
            raise AssertionError('Launch failure was ignored')
        assert not runner.running

with ThreadingHTTPServer(('127.0.0.1', 0), Handler) as server:
    server.host = '127.0.0.1:' + str(server.server_port)
    server.key = 'a' * 64
    server.runner = Mock()
    server.runner.snapshot.return_value = {'running': False}
    thread = threading.Thread(target=server.serve_forever)
    thread.start()

    def send(method, path, data=None, **changes):
        headers = {'Host': server.host, 'X-GUI-Key': server.key,
                   'Origin': 'http://' + server.host, 'Content-Type': 'application/json'}
        headers.update(changes)
        connection = http.client.HTTPConnection('127.0.0.1', server.server_port, timeout=3)
        try:
            connection.request(method, path, body=json.dumps(data) if data is not None else None, headers=headers)
            response = connection.getresponse()
            return response.status, response.read(), dict(response.getheaders())
        finally:
            connection.close()

    try:
        status, body, headers = send('GET', '/')
        assert status == 200 and b'NONCE' not in body
        assert headers['Cache-Control'] == 'no-store'
        assert "frame-ancestors 'none'" in headers['Content-Security-Policy']
        assert send('GET', '/', Host='attacker.invalid')[0] == 403
        assert send('GET', '/status', **{'X-GUI-Key': ''})[0] == 403
        assert send('POST', '/start', request, Origin='http://attacker.invalid')[0] == 403
        assert send('POST', '/start', request, **{'X-GUI-Key': 'wrong'})[0] == 403
        server.runner.start.assert_not_called()
        assert send('POST', '/start', request)[0] == 200
        server.runner.start.assert_called_once_with(request)
        assert send('POST', '/stop', {'confirmed': False})[0] == 400
        server.runner.stop.assert_not_called()
        assert send('POST', '/stop', {'confirmed': True})[0] == 200
        server.runner.stop.assert_called_once()
        assert send('GET', '/../../README.md')[0] == 404
        assert send('POST', '/start', request, **{'Content-Length': '20000'})[0] == 400
    finally:
        server.shutdown()
        thread.join()

print('GUI checks passed: validation, subprocess arguments, redaction, sessions, HTTP protection.')
