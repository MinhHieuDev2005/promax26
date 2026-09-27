import json
import re
import secrets
import ssl
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from http.client import HTTPException
from urllib.error import HTTPError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, HTTPSHandler, Request, build_opener


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, request, response, code, message, headers, new_url):
        return None


class BotProxy(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, upstream_url, match_id, token, log, ca_file=None, custom_roles=None):
        parsed = urlsplit(upstream_url)
        if parsed.scheme not in ("http", "https") or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise ValueError("Proxy yêu cầu URL HTTP/HTTPS hợp lệ, không chứa tài khoản, query hoặc fragment.")
        if not re.fullmatch(r"[A-Za-z0-9_-]+", match_id):
            raise ValueError("Match ID không hợp lệ.")
        if not token or not token.isascii() or any(ord(character) < 33 or ord(character) == 127 for character in token):
            raise ValueError("Token không hợp lệ.")
        self.upstream_url = upstream_url.rstrip("/")
        self.match_id = match_id
        self.token = token
        self.local_token = secrets.token_urlsafe(32)
        self.logger = log
        self.stopping = threading.Event()
        self.close_lock = threading.Lock()
        self.last_state = None
        if custom_roles is not None and (not isinstance(custom_roles, list) or not custom_roles or any(type(role) is not int or role not in (0, 1) for role in custom_roles)):
            raise ValueError("Custom roles must be a nonempty array of integer 0/1.")
        self.custom_roles = list(custom_roles) if custom_roles is not None else None
        context = ssl.create_default_context()
        if ca_file is not None:
            context.load_verify_locations(cafile=str(ca_file))
        self.opener = build_opener(HTTPSHandler(context=context), NoRedirect())
        super().__init__(("127.0.0.1", 0), ProxyHandler)
        self.url = f"http://127.0.0.1:{self.server_port}"
        self.thread = threading.Thread(target=self.serve_forever, kwargs={"poll_interval": 0.1}, daemon=True)
        self.thread.start()

    def log(self, message, level="INFO"):
        self.logger(message.replace(self.token, "[TOKEN]").replace(self.local_token, "[LOCAL TOKEN]"), level)

    def request(self, endpoint, body=None):
        if self.stopping.is_set():
            raise OSError("Proxy đã dừng.")
        request = Request(
            f"{self.upstream_url}/api/game/matches/{self.match_id}/{endpoint}", data=body,
            headers={"Authorization": f"Bearer {self.token}", "X-API-TOKEN": self.token,
                     "Content-Type": "application/json", "Accept": "application/json",
                     "ngrok-skip-browser-warning": "true"},
        )
        try:
            response = self.opener.open(request, timeout=10)
        except HTTPError as error:
            response = error
        with response:
            payload = response.read(4_000_001)
            if len(payload) > 4_000_000:
                raise ValueError("Phản hồi server vượt 4 MB.")
            try:
                data = json.loads(payload) if payload else {}
            except (ValueError, UnicodeError) as exc:
                raise ValueError(f"Server trả HTTP {response.code}, không phải JSON.") from exc
            if not isinstance(data, (dict, list)):
                raise ValueError("Server trả JSON không đúng cấu trúc object/array.")
            return response.code, data

    def check_connection(self):
        self.log("[Proxy] Đang kiểm tra config/status bằng GET; chưa khởi chạy bot, chưa nộp bài.")
        for endpoint in ("config", "status"):
            code, data = self.request(endpoint)
            if code != 200:
                raise ValueError(f"Không đọc được {endpoint}: HTTP {code}. Kiểm tra URL, Match ID và Token.")
            if not isinstance(data, dict) or (endpoint == "config" and not isinstance(data.get("map"), dict)):
                raise ValueError(f"Server trả {endpoint} không đúng định dạng HAUI.")
            if endpoint == "config" and self.custom_roles is not None and len(self.custom_roles) != len(data.get("agents", [])):
                raise ValueError("Custom role count does not match actual match config.")
            if endpoint == "status" and data.get("agents"):
                actual = [agent.get("kind") for agent in data["agents"]]
                self.log(f"[Proxy] Server-confirmed roles: {actual}; existing assignment takes precedence.")
                if self.custom_roles is not None and actual != self.custom_roles:
                    raise ValueError(f"Server roles {actual} differ from requested roles {self.custom_roles}.")
            if endpoint == "status" and data.get("finished"):
                raise ValueError("Trận đã kết thúc; hãy chọn trận đang hoạt động.")
        self.log("[Proxy] Kết nối API thành công. Bắt đầu cho phép bot tự điều khiển trận.", "SUCCESS")

    def close(self):
        with self.close_lock:
            if self.socket.fileno() == -1:
                return
            self.stopping.set()
            self.shutdown()
            self.server_close()
            self.thread.join(timeout=1)


class ProxyHandler(BaseHTTPRequestHandler):
    routes = {"setup": "config", "assignment": "agents", "state": "status", "actions": "answer", "result": "status"}

    def respond(self, code, data):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        try:
            self.send_response(code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        except OSError:
            pass

    def do_GET(self):
        proxy = self.server
        self.connection.settimeout(5)
        endpoint = self.path.rsplit("/", 1)[-1]
        if endpoint not in self.routes or self.path != f"/api/v1/matches/{proxy.match_id}/{endpoint}":
            self.respond(404, {"error": "Unknown match or endpoint"})
            return
        authorization = self.headers.get("Authorization", "").encode("utf-8")
        if not secrets.compare_digest(authorization, f"Bearer {proxy.local_token}".encode("utf-8")):
            self.respond(401, {"error": "Invalid local token"})
            return
        expected_method = "POST" if endpoint in ("assignment", "actions") else "GET"
        if self.command != expected_method:
            self.respond(405, {"error": "Method not allowed"})
            return
        try:
            if self.headers.get("Transfer-Encoding"):
                raise ValueError("Transfer-Encoding is not supported")
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 <= length <= 1_000_000:
                self.respond(413, {"error": "Body exceeds 1 MB"})
                return
            body = self.rfile.read(length) if self.command == "POST" else None
            if body is not None:
                if len(body) != length:
                    raise ValueError("Incomplete body")
                json.loads(body)
        except (OSError, ValueError) as exc:
            self.respond(400, {"error": "Invalid JSON request"})
            proxy.log(f"[Proxy] {endpoint}: yêu cầu không hợp lệ ({type(exc).__name__}).", "ERROR")
            return
        try:
            if endpoint == "assignment" and proxy.custom_roles is not None:
                body = json.dumps(proxy.custom_roles).encode("utf-8")
                proxy.log(f"[Proxy] Đề xuất vai trò xe từ GUI: {proxy.custom_roles}", "INFO")
            code, data = proxy.request(self.routes[endpoint], body)
            if endpoint == "state" and code == 200:
                if not isinstance(data, dict):
                    raise ValueError("Status phải là JSON object.")
                if data.get("finished"):
                    code = 410
                elif not data.get("agents"):
                    data["day"] = -1
            if endpoint == "assignment" and code in (200, 201, 400, 409):
                try:
                    status_code, state = proxy.request("status")
                    if status_code == 200 and isinstance(state, dict) and state.get("agents"):
                        actual = [agent.get("kind") for agent in state["agents"]]
                        proxy.log(f"[Proxy] Server-confirmed roles: {actual}")
                        if proxy.custom_roles is not None and actual != proxy.custom_roles:
                            proxy.stopping.set()
                            code, data = 422, {"error": "Server roles differ from requested roles; restart with server assignment"}
                        elif code == 400:
                            code, data = 409, {"error": "Agents already selected"}
                    elif proxy.custom_roles is not None:
                        proxy.stopping.set()
                        code, data = 502, {"error": "Cannot confirm assigned roles; refusing further actions"}
                except (OSError, ValueError, HTTPException) as exc:
                    proxy.log(f"[Proxy] Không kiểm tra được vai trò hiện có: {exc}", "ERROR")
                    if proxy.custom_roles is not None:
                        proxy.stopping.set()
                        code, data = 502, {"error": "Cannot confirm assigned roles; refusing further actions"}
            detail = f"[Proxy] {endpoint} → {self.routes[endpoint]}: HTTP {code}"
            if endpoint == "state" and isinstance(data, dict):
                detail += f" | day={data.get('day')} | finished={data.get('finished', False)}"
            if endpoint != "state" or detail != proxy.last_state:
                proxy.log(detail, "ERROR" if code >= 400 and code not in (409, 410) else "INFO")
            if endpoint == "state":
                proxy.last_state = detail
            self.respond(code, data)
        except (OSError, ValueError, HTTPException) as exc:
            proxy.log(f"[Proxy] {endpoint}: lỗi kết nối/TLS hoặc dữ liệu: {exc}", "ERROR")
            self.respond(502, {"error": "Upstream connection/TLS or response error; see GUI log"})

    do_POST = do_GET

    def log_message(self, *args):
        pass
