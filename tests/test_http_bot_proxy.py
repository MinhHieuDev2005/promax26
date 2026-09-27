import json
import ssl
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.error import HTTPError, URLError
from urllib.request import HTTPSHandler, Request, urlopen
from unittest.mock import patch

from http_bot_proxy import BotProxy


class Upstream(BaseHTTPRequestHandler):
    def do_GET(self):
        body = self.rfile.read(int(self.headers.get("Content-Length", 0)))
        self.server.requests.append((self.command, self.path, dict(self.headers), body))
        endpoint = self.path.rsplit("/", 1)[-1]
        code, data = self.server.responses.get((self.command, endpoint), (404, {"error": "missing"}))
        payload = data if isinstance(data, bytes) else json.dumps(data).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        if code == 302:
            self.send_header("Location", "/must-not-follow")
        self.end_headers()
        self.wfile.write(payload)

    do_POST = do_GET

    def log_message(self, *args):
        pass


class ProxyTests(unittest.TestCase):
    def setUp(self):
        self.upstream = ThreadingHTTPServer(("127.0.0.1", 0), Upstream)
        self.upstream.requests = []
        self.upstream.responses = {
            ("GET", "config"): (200, {"map": {"width": 1}}),
            ("GET", "status"): (200, {"day": 1, "agents": [{"kind": 1}], "finished": False}),
            ("POST", "agents"): (200, {"ok": True}),
            ("POST", "answer"): (200, {"ok": True}),
        }
        self.thread = threading.Thread(target=self.upstream.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True)
        self.thread.start()
        self.logs = []
        self.proxy = BotProxy(f"http://127.0.0.1:{self.upstream.server_port}", "test-match", "real-test-token", lambda message, level: self.logs.append((message, level)))

    def tearDown(self):
        self.proxy.close()
        self.upstream.shutdown()
        self.upstream.server_close()
        self.thread.join(timeout=1)

    def request(self, endpoint, body=None, method=None, token=None, headers=None):
        request_headers = {"Authorization": f"Bearer {token if token is not None else self.proxy.local_token}"}
        request_headers.update(headers or {})
        request = Request(f"{self.proxy.url}/api/v1/matches/test-match/{endpoint}", data=body, headers=request_headers, method=method)
        try:
            response = urlopen(request, timeout=3)
        except HTTPError as exc:
            response = exc
        with response:
            return response.code, json.load(response)

    def test_routes_and_payloads(self):
        for endpoint, destination, body in (("setup", "config", None), ("assignment", "agents", b'[1,0]'), ("state", "status", None), ("actions", "answer", b'[[-10],[-10]]'), ("result", "status", None)):
            with self.subTest(endpoint=endpoint):
                self.assertEqual(self.request(endpoint, body)[0], 200)
                method, path, headers, sent = self.upstream.requests[-2 if endpoint == "assignment" else -1]
                self.assertEqual(path, f"/api/game/matches/test-match/{destination}")
                self.assertEqual(method, "POST" if body else "GET")
                self.assertEqual(sent, body or b'')
                self.assertEqual(headers["Authorization"], "Bearer real-test-token")
        self.assertTrue(self.logs)
        self.assertNotIn("real-test-token", str(self.logs))
        self.assertNotIn(self.proxy.local_token, str(self.logs))

    def test_custom_roles_override_assignment_payload(self):
        self.proxy.custom_roles = [1, 0, 0]
        self.upstream.responses[("GET", "status")] = (200, {"agents": [{"kind": 1}, {"kind": 0}, {"kind": 0}]})
        self.assertEqual(self.request("assignment", b'[0,0,0]')[0], 200)
        self.assertEqual(self.upstream.requests[-2][3], b'[1, 0, 0]')

    def test_conflicting_manual_roles_stop_proxy(self):
        self.proxy.custom_roles = [0]
        self.assertEqual(self.request("assignment", b'[0]')[0], 422)
        self.assertTrue(self.proxy.stopping.is_set())
        self.assertEqual(self.request("actions", b'[[]]')[0], 502)

    def test_manual_role_count_checked_before_bot_launch(self):
        self.proxy.custom_roles = [0, 0]
        with self.assertRaises(ValueError):
            self.proxy.check_connection()
        self.assertFalse(any(method == "POST" for method, *_ in self.upstream.requests))

    def test_wait_finished_and_existing_assignment(self):
        self.upstream.responses[("GET", "status")] = (200, {"agents": [], "finished": False})
        self.assertEqual(self.request("state")[1]["day"], -1)
        self.upstream.responses[("GET", "status")] = (200, {"agents": [{}], "finished": False})
        self.upstream.responses[("POST", "agents")] = (400, {"error": "already selected"})
        self.assertEqual(self.request("assignment", b'[1]')[0], 409)
        self.assertEqual(sum(method == "POST" for method, *_ in self.upstream.requests), 1)
        self.upstream.responses[("GET", "status")] = (200, {"finished": True})
        self.assertEqual(self.request("state")[0], 410)
        self.upstream.responses[("POST", "agents")] = (400, {"error": "invalid roles"})
        self.assertEqual(self.request("assignment", b'[9]')[0], 400)

    def test_auth_routes_and_input_validation(self):
        self.assertEqual(self.request("setup", token="wrong")[0], 401)
        self.assertEqual(self.request("unknown")[0], 404)
        self.assertEqual(self.request("setup", b'{}')[0], 405)
        self.assertEqual(self.request("actions", method="GET")[0], 405)
        self.assertEqual(self.request("actions", b'not json')[0], 400)
        self.assertEqual(self.request("actions", b'{}', headers={"Content-Length": "invalid"})[0], 400)
        self.assertEqual(self.request("actions", b'{}', headers={"Content-Length": "1000001"})[0], 413)
        self.assertEqual(self.request("actions", b'{}', headers={"Transfer-Encoding": "chunked"})[0], 400)
        self.assertEqual(self.upstream.requests, [])

    def test_preflight_is_read_only_and_rejects_finished_match(self):
        self.proxy.check_connection()
        self.assertEqual([request[0] for request in self.upstream.requests], ["GET", "GET"])
        self.upstream.responses[("GET", "status")] = (200, {"finished": True})
        with self.assertRaisesRegex(ValueError, "kết thúc"):
            self.proxy.check_connection()

    def test_failures_and_tls_are_visible_without_retry_or_redirect(self):
        self.upstream.responses[("GET", "config")] = (302, {})
        with self.assertRaisesRegex(ValueError, "HTTP 302"):
            self.proxy.check_connection()
        self.assertEqual(len(self.upstream.requests), 1)
        self.upstream.responses[("GET", "config")] = (200, b'<html>not JSON</html>')
        self.assertEqual(self.request("setup")[0], 502)
        handler = next(handler for handler in self.proxy.opener.handlers if isinstance(handler, HTTPSHandler))
        self.assertTrue(handler._context.check_hostname)
        self.assertEqual(handler._context.verify_mode, ssl.CERT_REQUIRED)
        with patch.object(self.proxy.opener, "open", side_effect=URLError(ssl.SSLCertVerificationError("untrusted certificate"))) as send:
            self.assertEqual(self.request("actions", b'[[-1]]')[0], 502)
            send.assert_called_once()
        self.assertTrue(any("TLS" in message and level == "ERROR" for message, level in self.logs))

    def test_close_stops_listener_and_invalid_config_is_rejected(self):
        self.proxy.close()
        self.proxy.close()
        self.assertFalse(self.proxy.thread.is_alive())
        with self.assertRaises(URLError):
            self.request("setup")
        for url, match_id, token in (("file:///tmp", "match", "token"), ("http://user:pass@localhost", "match", "token"), ("http://localhost", "../other", "token"), ("http://localhost", "match", "bad\ntoken")):
            with self.assertRaises(ValueError):
                BotProxy(url, match_id, token, lambda *args: None)


if __name__ == "__main__":
    unittest.main()
