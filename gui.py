import argparse
import json
import os
import re
from pathlib import Path
import secrets
import subprocess
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import quote, urlsplit
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, Request, build_opener


ROOT = Path(__file__).resolve().parent


def validate_request(data):
    if not isinstance(data, dict) or data.get('mode') not in ('check', 'dry', 'execute', 'state', 'matches'):
        raise ValueError('Invalid mode.')
    if data['mode'] == 'state':
        return '', ''
    backend = data.get('backend', 'procon')
    if backend not in ('procon', 'haui'):
        raise ValueError('Invalid backend.')
    if data['mode'] == 'matches' and backend != 'haui':
        raise ValueError('Match listing requires HAUI.')
    if backend == 'haui' and data['mode'] != 'matches':
        match_id = data.get('match_id')
        if not isinstance(match_id, str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,128}', match_id):
            raise ValueError('Select a HAUI match first.')
    url, token = data.get('url'), data.get('token')
    if not isinstance(url, str) or not isinstance(token, str):
        raise ValueError('Server URL and token are required.')
    url = url.strip()
    parsed = urlsplit(url)
    if (len(url) > 2048 or parsed.scheme not in ('http', 'https') or not parsed.hostname
            or parsed.username is not None or parsed.password is not None or parsed.query or parsed.fragment
            or any(character.isspace() or ord(character) < 32 for character in url)):
        raise ValueError('Use HTTP/HTTPS without credentials, query or fragment.')
    parsed.port
    if not token or len(token) > 2048 or any(ord(character) < 32 for character in token):
        raise ValueError('Invalid token.')
    if backend == 'haui' and any(not 33 <= ord(character) <= 126 for character in token):
        raise ValueError('Invalid header token.')
    if data['mode'] == 'execute' and data.get('confirmed') is not True:
        raise ValueError('Live execution requires confirmation.')
    return url, token


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, request, response, code, message, headers, new_url):
        return None


def list_matches(data):
    url, token = validate_request(data)
    if data['mode'] != 'matches':
        raise ValueError('Invalid match-list request.')
    request = Request(url.rstrip('/') + '/api/game/matches',
                      headers={'Accept': 'application/json', 'x-api-token': token})
    with build_opener(NoRedirect()).open(request, timeout=10) as response:
        body = response.read(1024 * 1024 + 1)
    if len(body) > 1024 * 1024:
        raise ValueError('Match list too large.')
    payload = json.loads(body)
    matches = payload.get('matches') if isinstance(payload, dict) else payload
    if not isinstance(matches, list) or len(matches) > 1000:
        raise ValueError('Invalid match list.')
    result = []
    for match in matches:
        if not isinstance(match, dict) or type(match.get('id')) not in (str, int):
            raise ValueError('Invalid match ID.')
        match_id = str(match['id'])
        if not re.fullmatch(r'[A-Za-z0-9_-]{1,128}', match_id):
            raise ValueError('Invalid match ID.')
        name, status = match.get('name', match_id), match.get('status', '')
        if not isinstance(name, str) or not isinstance(status, str):
            raise ValueError('Invalid match metadata.')
        result.append({'id': match_id, 'name': name.replace(token, '[TOKEN HIDDEN]')[:160],
                       'status': status.replace(token, '[TOKEN HIDDEN]')[:40]})
    return result


# ponytail: one client per GUI process; add cross-process locking before supporting multiple GUI instances.
class Runner:
    def __init__(self, binary, runtime):
        self.binary, self.runtime = Path(binary).resolve(), Path(runtime).resolve()
        self.lock = threading.Lock()
        self.process, self.running = None, False
        self.mode, self.session, self.log = '', '', ''
        self.exit_code = None

    def snapshot(self):
        with self.lock:
            return dict(running=self.running, ready=self.binary.is_file(), mode=self.mode,
                        session=self.session, log=self.log, exit_code=self.exit_code)

    def start(self, data):
        url, token = validate_request(data)
        if data['mode'] == 'matches':
            raise ValueError('Use the match-list endpoint.')
        with self.lock:
            if self.running:
                raise ValueError('A process is already running.')
            if not self.binary.is_file():
                raise ValueError('Build build-release/hexa_udon first.')
            command, mode, session = [str(self.binary)], data['mode'], self.session
            if mode == 'state':
                if not session:
                    raise ValueError('No session to inspect.')
                command += ['show-state', '--session-dir', session]
            else:
                self.runtime.mkdir(parents=True, exist_ok=True, mode=0o700)
                directory = Path(tempfile.mkdtemp(prefix=mode + '-', dir=self.runtime))
                command += ['check' if mode == 'check' else 'auto', '--base-url', url,
                            '--token-env', 'PROCON_TOKEN', '--session-dir', str(directory / 'session'),
                            '--log-dir', str(directory / 'log'), '--max-get-retries', '200', '--threads', '8', '--connect-timeout-ms', '5000', '--total-timeout-ms', '15000']
                if data.get('backend') == 'haui':
                    command += ['--haui-match', data['match_id']]
                if mode != 'check':
                    session = str(directory / 'session')
                if mode == 'execute':
                    command.append('--execute')
            environment = os.environ.copy()
            environment.pop('PROCON_TOKEN', None)
            if token:
                environment['PROCON_TOKEN'] = token
            try:
                process = subprocess.Popen(command, cwd=ROOT, env=environment, stdin=subprocess.DEVNULL,
                                           stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                           text=True, encoding='utf-8', errors='replace')
            except OSError:
                raise ValueError('Cannot start binary. Use Ubuntu/WSL and check the build.') from None
            self.process, self.running, self.mode = process, True, mode
            self.session, self.log, self.exit_code = session, '', None
            threading.Thread(target=self.collect, args=(process, token), daemon=True).start()

    def collect(self, process, token):
        hidden = sorted({token, quote(token, safe='-._~')}, key=len, reverse=True)
        discarding = False
        try:
            with process.stdout:
                while True:
                    line = process.stdout.readline(8193)
                    if not line:
                        break
                    if discarding or len(line) > 8192:
                        discarding = not line.endswith('\n')
                        continue
                    for secret in hidden:
                        if secret:
                            line = line.replace(secret, '[TOKEN HIDDEN]')
                    with self.lock:
                        self.log = (self.log + line)[-65536:]
        finally:
            code = process.wait()
            with self.lock:
                self.exit_code, self.running = code, False

    def stop(self):
        with self.lock:
            if self.process and self.process.poll() is None:
                self.process.terminate()


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def setup(self):
        super().setup()
        self.connection.settimeout(5)

    def reply(self, status, data, html=False):
        body = data.encode('utf-8') if html else json.dumps(data, ensure_ascii=False).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'text/html; charset=utf-8' if html else 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Referrer-Policy', 'no-referrer')
        self.send_header('Content-Security-Policy', "default-src 'none'; script-src 'nonce-" + self.server.key
                         + "'; style-src 'nonce-" + self.server.key + "'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'")
        self.end_headers()
        self.wfile.write(body)

    def authorized(self, api=True):
        if self.headers.get('Host') != self.server.host:
            self.reply(403, {'error': 'Host không hợp lệ.'})
            return False
        supplied = self.headers.get('X-GUI-Key', '').encode('utf-8')
        if api and not secrets.compare_digest(supplied, self.server.key.encode('ascii')):
            self.reply(403, {'error': 'Hãy mở lại trang GUI.'})
            return False
        if self.command == 'POST' and self.headers.get('Origin') != 'http://' + self.server.host:
            self.reply(403, {'error': 'Origin không hợp lệ.'})
            return False
        return True

    def do_GET(self):
        if not self.authorized(api=self.path != '/'):
            return
        if self.path == '/':
            page = (ROOT / 'gui.html').read_text(encoding='utf-8')
            self.reply(200, page.replace('NONCE', self.server.key), html=True)
        elif self.path == '/status':
            self.reply(200, self.server.runner.snapshot())
        else:
            self.reply(404, {'error': 'Không tìm thấy.'})

    def do_POST(self):
        if not self.authorized():
            return
        try:
            length = int(self.headers.get('Content-Length', '0'))
            if not 0 < length <= 16384 or self.headers.get_content_type() != 'application/json':
                raise ValueError('Invalid request body.')
            data = json.loads(self.rfile.read(length))
            if self.path == '/matches':
                self.reply(200, {'matches': list_matches(data)})
                return
            elif self.path == '/start':
                self.server.runner.start(data)
            elif self.path == '/stop':
                if not isinstance(data, dict) or data.get('confirmed') is not True:
                    raise ValueError('Stopping requires confirmation.')
                self.server.runner.stop()
            else:
                self.reply(404, {'error': 'Không tìm thấy.'})
                return
            self.reply(200, {'ok': True})
        except HTTPError as error:
            explanations = {401: 'Token không hợp lệ hoặc không có quyền truy cập.',
                            403: 'Chưa có quyền hoặc trận chưa mở.',
                            404: 'Sai địa chỉ API máy chủ.', 429: 'Quá nhiều yêu cầu; hãy thử lại sau.'}
            self.reply(400, {'error': 'HAUI HTTP ' + str(error.code) + ': '
                            + explanations.get(error.code, 'Máy chủ không chấp nhận yêu cầu; không tự chuyển hướng token.')})
        except URLError:
            self.reply(400, {'error': 'Không kết nối được HAUI. Kiểm tra URL, mạng và chứng chỉ HTTPS.'})
        except (ValueError, UnicodeError):
            self.reply(400, {'error': 'Yêu cầu không hợp lệ, chưa xác nhận, binary chưa sẵn sàng hoặc đang có tiến trình chạy. Kiểm tra thông tin và trạng thái.'})
        except OSError:
            self.reply(500, {'error': 'Không truy cập được thư mục runtime hoặc tiến trình.'})


def main():
    parser = argparse.ArgumentParser(description='Local Hexa Udon GUI. Run inside Ubuntu/WSL.')
    parser.add_argument('--binary', type=Path, default=ROOT / 'build-release' / 'hexa_udon')
    parser.add_argument('--port', type=int, default=8765)
    args = parser.parse_args()
    runner = Runner(args.binary, Path.home() / '.hexa-udon-gui')
    with ThreadingHTTPServer(('127.0.0.1', args.port), Handler) as server:
        server.host, server.key, server.runner = '127.0.0.1:' + str(server.server_port), secrets.token_hex(32), runner
        print('Open http://' + server.host + ' in your browser. Ctrl+C to shut down.', flush=True)
        print('Shutdown stops the client. Verify any pending POST before restarting.', flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
        finally:
            runner.stop()
            if runner.process:
                try:
                    runner.process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    runner.process.kill()
                    runner.process.wait()


if __name__ == '__main__':
    main()
