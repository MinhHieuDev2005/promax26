#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
HEXUDON PROCON 2026 - GUI CONTROL CENTER (BẢNG ĐIỀU KHIỂN CHIẾN THUẬT)
Giao diện đồ họa chuyên nghiệp cho phép:
1. Thi đấu chính thức (Live / Practice) bằng Token với các Solver đỉnh cao (ACO, ALNS, MLNS, Auto-Race...)
2. Đấu đối kháng trực tiếp 1v1 hoặc Đấu trường nhiều bot tự động trên server HAUI
3. Tự động chuyển ngày, theo dõi điểm số (Bát mì, Loại mì), và mở Replay trực tiếp trên web
"""

import json
import os
import queue
import ssl
import subprocess
import sys
import threading
import time
import urllib.request
import webbrowser
import http.cookiejar
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

ROOT = Path(__file__).resolve().parent

# Tự động tìm HEX_BINARY (ưu tiên bin/, sau đó build/)
if (ROOT / "bin" / "hexudon.exe").exists():
    HEX_BINARY = ROOT / "bin" / "hexudon.exe"
elif (ROOT / "build" / "hexudon.exe").exists():
    HEX_BINARY = ROOT / "build" / "hexudon.exe"
else:
    HEX_BINARY = ROOT / "bin" / "hexudon.exe"

# Tự động tìm PROCON26_RUNNER (ưu tiên bin/, sau đó build/, sau đó fallback D:/Procon26)
if (ROOT / "bin" / "hexudon_runner.exe").exists():
    PROCON26_RUNNER = ROOT / "bin" / "hexudon_runner.exe"
    ROOT_PROCON26 = ROOT
elif (ROOT / "build" / "hexudon_runner.exe").exists():
    PROCON26_RUNNER = ROOT / "build" / "hexudon_runner.exe"
    ROOT_PROCON26 = ROOT
elif Path("D:/Procon26/out/build/haui-practice-release/hexudon_runner.exe").exists():
    PROCON26_RUNNER = Path("D:/Procon26/out/build/haui-practice-release/hexudon_runner.exe")
    ROOT_PROCON26 = Path("D:/Procon26").resolve()
else:
    PROCON26_RUNNER = ROOT / "bin" / "hexudon_runner.exe"
    ROOT_PROCON26 = ROOT

DEFAULT_HOST = "procon26.haui.ac.vn"
DEFAULT_USER = "mhieu"
DEFAULT_PASS = "Hieu123456@"

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

# Danh sách solver hỗ trợ
SOLVERS = {
    "Auto-Race (Chạy đua ACO & ALNS - Khuyên dùng tối ưu)": "auto_race",
    "Auto-Race ALL (Chạy đua TẤT CẢ các Solver cùng lúc)": "auto_race_all",
    "ACO (Bầy kiến + LS - Tốc độ chớp nhoáng)": "aco_ls",
    "ALNS (Adaptive LNS - Ổn định & Sâu)": "alns",
    "MLNS (Multi-Day LNS + DP Lookahead)": "mlns",
    "Procon26-Bot (Solver D:\\Procon26)": "procon26",
    "LocalSearch (2-Opt / Relocate)": "local_search",
    "Greedy (Tham lam cơ bản)": "greedy",
}

# Các đội mẫu trên tài khoản HAUI
PRESET_TEAMS = [
    {"name": "Team-ACO", "token": "procon_5d14071e84b643cfbcf5df1e2ce78561", "policy": "aco_ls"},
    {"name": "Team-ALNS", "token": "procon_0607dbac5aa2487a95b3c1b58e8a5a2e", "policy": "alns"},
    {"name": "Team-MLNS", "token": "procon_0ee95461d7294954b391daeeb7f7f9bd", "policy": "mlns"},
    {"name": "Procon26-Bot", "token": "procon_c15f8ba6cb434e03b6ac4c6c9cdbd9c6", "policy": "procon26"},
    {"name": "Team-LocalSearch", "token": "procon_29a657cb0bd64a4388dee27cca339d3b", "policy": "local_search"},
    {"name": "Team-Greedy", "token": "procon_08099c90bee748a3be2e0c7384a1398e", "policy": "greedy"},
]


class HauiAPI:
    def __init__(self, host=DEFAULT_HOST):
        self.jar = http.cookiejar.CookieJar()
        self.opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(self.jar),
            urllib.request.HTTPSHandler(context=ctx)
        )
        self.set_host(host)

    def set_host(self, host):
        from urllib.parse import urlparse
        host = (host or DEFAULT_HOST).strip()
        if not host.startswith("http://") and not host.startswith("https://"):
            if "localhost" in host or "127.0.0.1" in host or host.startswith("192.168.") or host.startswith("10.") or ":" in host:
                host = f"http://{host}"
            else:
                host = f"https://{host}"
        parsed = urlparse(host)
        self.host = parsed.netloc
        self.base_url = f"{parsed.scheme}://{parsed.netloc}".rstrip("/")

    def _headers(self, token=None):
        h = {
            "User-Agent": "hexudon-gui/1.0",
            "ngrok-skip-browser-warning": "true"
        }
        if token:
            h["x-api-token"] = token
        return h

    def login(self, username, password):
        payload = json.dumps({"username": username, "password": password}).encode("utf-8")
        headers = {"Content-Type": "application/json", "User-Agent": "hexudon-gui/1.0", "ngrok-skip-browser-warning": "true"}
        try:
            url = f"{self.base_url}/api/auth/login"
            req = urllib.request.Request(url, data=payload, headers=headers)
            with self.opener.open(req, timeout=15) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            if e.code in [404, 400]:
                url = f"{self.base_url}/api/admin/login"
                req = urllib.request.Request(url, data=payload, headers=headers)
                with self.opener.open(req, timeout=15) as resp:
                    return json.loads(resp.read().decode("utf-8"))
            raise

    def get_matches(self, token=None):
        headers = self._headers(token)
        # Thử 1: /api/game/matches (chuẩn cho thí sinh có token, không cần admin)
        try:
            url = f"{self.base_url}/api/game/matches"
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, context=ctx, timeout=8) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                return data.get("matches", []) if isinstance(data, dict) else data
        except Exception:
            pass

        # Thử 2: /api/admin/matches (chuẩn admin HAUI)
        try:
            url = f"{self.base_url}/api/admin/matches"
            req = urllib.request.Request(url, headers=headers)
            with self.opener.open(req, timeout=8) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                return data.get("matches", []) if isinstance(data, dict) else data
        except Exception:
            pass

        # Thử 3: /api/matches (chuẩn admin procon26_v3)
        try:
            url = f"{self.base_url}/api/matches"
            req = urllib.request.Request(url, headers=headers)
            with self.opener.open(req, timeout=8) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                return data.get("matches", []) if isinstance(data, dict) else data
        except Exception:
            return []

    def get_match(self, match_id):
        headers = self._headers()
        try:
            url = f"{self.base_url}/api/admin/matches/{match_id}"
            req = urllib.request.Request(url, headers=headers)
            with self.opener.open(req, timeout=15) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            if e.code in [404, 400]:
                url = f"{self.base_url}/api/matches/{match_id}"
                req = urllib.request.Request(url, headers=headers)
                with self.opener.open(req, timeout=15) as resp:
                    return json.loads(resp.read().decode("utf-8"))
            raise

    def create_match(self, name, map_config):
        url = f"{self.base_url}/api/admin/matches"
        payload = json.dumps({"name": name, "mapConfig": map_config}).encode("utf-8")
        req = urllib.request.Request(url, data=payload, method="POST", headers={"Content-Type": "application/json", "User-Agent": "hexudon-gui/1.0", "ngrok-skip-browser-warning": "true"})
        with self.opener.open(req, timeout=15) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def add_team(self, match_id, team_id):
        url = f"{self.base_url}/api/admin/matches/{match_id}/teams"
        payload = json.dumps({"teamId": team_id}).encode("utf-8")
        req = urllib.request.Request(url, data=payload, method="POST", headers={"Content-Type": "application/json", "User-Agent": "hexudon-gui/1.0", "ngrok-skip-browser-warning": "true"})
        with self.opener.open(req, timeout=15) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def match_action(self, match_id, action):
        url = f"{self.base_url}/api/admin/matches/{match_id}"
        payload = json.dumps({"action": action}).encode("utf-8")
        req = urllib.request.Request(url, data=payload, method="PUT", headers={"Content-Type": "application/json", "User-Agent": "hexudon-gui/1.0", "ngrok-skip-browser-warning": "true"})
        with self.opener.open(req, timeout=15) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def get_teams(self):
        headers = self._headers()
        try:
            url = f"{self.base_url}/api/admin/teams"
            req = urllib.request.Request(url, headers=headers)
            with self.opener.open(req, timeout=15) as resp:
                return json.loads(resp.read().decode("utf-8")).get("teams", [])
        except urllib.error.HTTPError as e:
            if e.code in [404, 400]:
                url = f"{self.base_url}/api/teams"
                req = urllib.request.Request(url, headers=headers)
                with self.opener.open(req, timeout=15) as resp:
                    return json.loads(resp.read().decode("utf-8")).get("teams", [])
            raise

    def submit_roles(self, match_id, token, roles):
        url = f"{self.base_url}/api/game/matches/{match_id}/agents"
        payload = json.dumps(roles).encode("utf-8")
        headers = {"Content-Type": "application/json", "x-api-token": token, "User-Agent": "hexudon-gui/1.0", "ngrok-skip-browser-warning": "true"}
        req = urllib.request.Request(url, data=payload, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, context=ctx, timeout=15) as resp:
                body = resp.read().decode("utf-8")
                return json.loads(body) if body.strip() else {"ok": True}
        except urllib.error.HTTPError as error:
            body = error.read().decode("utf-8", errors="replace").strip()
            detail = body or error.reason or "server did not provide details"
            raise RuntimeError(
                f"HTTP {error.code} khi nộp {roles} tới {url}: {detail}"
            ) from None

    def get_game_status(self, match_id, token):
        url = f"{self.base_url}/api/game/matches/{match_id}/status"
        headers = {"x-api-token": token, "User-Agent": "hexudon-gui/1.0", "ngrok-skip-browser-warning": "true"}
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, context=ctx, timeout=15) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def get_game_config(self, match_id, token):
        url = f"{self.base_url}/api/game/matches/{match_id}/config"
        headers = {"x-api-token": token, "User-Agent": "hexudon-gui/1.0", "ngrok-skip-browser-warning": "true"}
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, context=ctx, timeout=15) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def submit_actions(self, match_id, token, actions):
        url = f"{self.base_url}/api/game/matches/{match_id}/answer"
        payload = json.dumps(actions).encode("utf-8")
        headers = {"Content-Type": "application/json", "x-api-token": token, "User-Agent": "hexudon-gui/1.0", "ngrok-skip-browser-warning": "true"}
        req = urllib.request.Request(url, data=payload, headers=headers)
        with urllib.request.urlopen(req, context=ctx, timeout=15) as resp:
            return json.loads(resp.read().decode("utf-8"))


# --- Solver Helpers ---
def normalize_map_config(map_config):
    """Đảm bảo map_config chuẩn 100%, tự chuyển cells 1D sang 2D, đảm bảo spots và agents không lỗi."""
    if not map_config or not isinstance(map_config, dict):
        return map_config
    m = map_config.get("map", {})
    if isinstance(m, dict):
        W = m.get("width", 0)
        H = m.get("height", 0)
        cells = m.get("cells", [])
        if cells and not isinstance(cells[0], (list, tuple)) and W > 0 and H > 0:
            m["cells"] = [cells[row * W : (row + 1) * W] for row in range(H)]
    return map_config


def get_road_cells(map_config):
    """Lấy danh sách tọa độ (pos = y * W + x) của tất cả ô đường (terrain == 1)."""
    m = map_config.get("map", {})
    W = m.get("width", 0)
    H = m.get("height", 0)
    cells = m.get("cells", [])
    if not cells or W <= 0 or H <= 0:
        return []
    road_cells = []
    if isinstance(cells[0], (list, tuple)):
        for y in range(min(H, len(cells))):
            row = cells[y]
            for x in range(min(W, len(row))):
                if row[x] == 1:
                    road_cells.append(y * W + x)
    else:
        for idx, val in enumerate(cells):
            if val == 1:
                road_cells.append(idx)
    return road_cells


def normalize_traffics(raw_traffics, road_cells=None):
    """Chuẩn hóa dữ liệu traffics từ bất kỳ định dạng nào (list dict, list int, dict) về chuẩn."""
    if not raw_traffics:
        return []
    result = []
    if isinstance(raw_traffics, list):
        for idx, item in enumerate(raw_traffics):
            if isinstance(item, dict):
                result.append({"pos": item.get("pos", idx), "status": item.get("status", 0)})
            elif isinstance(item, (int, float)):
                pos = road_cells[idx] if (road_cells and idx < len(road_cells)) else idx
                result.append({"pos": pos, "status": int(item)})
    elif isinstance(raw_traffics, dict):
        for k, v in raw_traffics.items():
            try:
                pos = int(k)
                st = v.get("status", v) if isinstance(v, dict) else int(v)
                result.append({"pos": pos, "status": st})
            except Exception:
                pass
    return result


def normalize_agents(raw_agents, cfg_agents, roles, fuel_limit):
    """Chuẩn hóa danh sách xe, bất kể server trả về list of dict hay list of int."""
    fuel_max = fuel_limit if isinstance(fuel_limit, (int, float)) else 200
    built_agents = []
    for i in range(len(cfg_agents)):
        ca = cfg_agents[i]
        default_pos = ca if isinstance(ca, int) else (ca.get("pos", 0) if isinstance(ca, dict) else 0)
        k = roles[i] if i < len(roles) else 0
        if i < len(raw_agents):
            ag = raw_agents[i]
            if isinstance(ag, dict):
                k = ag.get("kind", k)
                p = ag.get("pos", default_pos)
                f = ag.get("fuel", fuel_max)
            elif isinstance(ag, (int, float)):
                p = int(ag)
                f = fuel_max
            else:
                p = default_pos
                f = fuel_max
        else:
            p = default_pos
            f = fuel_max
        built_agents.append({"kind": k, "pos": p, "fuel": f})
    return built_agents


def build_procon26_payload(map_config, day_info, day_num, raw_status=None):
    """Tạo payload chuẩn 100% cho PROCON26_RUNNER."""
    normalize_map_config(map_config)
    road_cells = get_road_cells(map_config)
    
    traffic_map = {}
    raw_tr = (raw_status or {}).get("traffics", [])
    if isinstance(raw_tr, list):
        for idx, t in enumerate(raw_tr):
            if isinstance(t, dict):
                traffic_map[t.get("pos")] = t.get("status", 0)
            elif isinstance(t, (int, float)):
                pos = road_cells[idx] if idx < len(road_cells) else idx
                traffic_map[pos] = int(t)
    elif isinstance(raw_tr, dict):
        for k, v in raw_tr.items():
            try:
                pos = int(k)
                st = v.get("status", v) if isinstance(v, dict) else int(v)
                traffic_map[pos] = st
            except Exception:
                pass
                
    traffics = [{"pos": pos, "status": traffic_map.get(pos, 0)} for pos in road_cells]
    
    state = {
        "day": day_num,
        "startsAt": (raw_status or {}).get("startsAt", int(time.time())),
        "endsAt": (raw_status or {}).get("endsAt", int(time.time()) + 60),
        "stepsCount": day_info.get("steps", 100),
        "agents": day_info.get("agents", []),
        "others": (raw_status or {}).get("others", []),
        "traffics": traffics
    }
    
    stock_list = []
    for s in map_config.get("spots", []):
        if isinstance(s, dict):
            stock_list.append(s.get("stocks", s.get("stock", 1)))
        elif isinstance(s, (int, float)):
            stock_list.append(1)
        else:
            stock_list.append(1)
            
    return {
        "op": "plan",
        "config": map_config,
        "state": state,
        "stock": stock_list
    }


def solve_roles(policy, map_config):
    normalize_map_config(map_config)
    num_agents = len(map_config.get("agents", [])) if (map_config and "agents" in map_config) else 6
    if policy == "procon26":
        payload = {"op": "roles", "config": map_config}
        p = subprocess.run([str(PROCON26_RUNNER)], input=json.dumps(payload), text=True, capture_output=True, timeout=20, cwd=ROOT_PROCON26)
        res = json.loads(p.stdout)
        roles = res.get("roles", [1] + [0] * (num_agents - 1))
        return roles[:num_agents] if len(roles) >= num_agents else roles + [0] * (num_agents - len(roles))
    
    actual_policy = "aco_ls" if policy in ["auto_race", "auto_race_all"] else policy
    payload = {"config": map_config}
    p = subprocess.run([str(HEX_BINARY), "types", actual_policy], input=json.dumps(payload), text=True, capture_output=True, timeout=20, cwd=ROOT)
    if p.returncode != 0:
        return [1] + [0] * (num_agents - 1)
    roles = json.loads(p.stdout)
    if len(roles) < num_agents:
        roles = roles + [0] * (num_agents - len(roles))
    elif len(roles) > num_agents:
        roles = roles[:num_agents]
    return roles


def check_plan_score(map_config, day_info, actions):
    """Tính toán và kiểm tra điểm của action plan bằng hexudon.exe check."""
    try:
        normalize_map_config(map_config)
        payload = {"config": map_config, "day_info": day_info, "actions": actions}
        p = subprocess.run(
            [str(HEX_BINARY), "check", "aco_ls"],
            input=json.dumps(payload),
            text=True,
            capture_output=True,
            timeout=10,
            cwd=ROOT
        )
        if p.returncode == 0:
            res = json.loads(p.stdout)
            if res.get("valid") and "score" in res:
                s = res["score"]
                return {
                    "valid": True,
                    "servings": s.get("servings", 0),
                    "distinct_types": s.get("distinct_types", 0),
                    "daily_types": s.get("daily_types", 0),
                }
            elif not res.get("valid"):
                return {"valid": False, "servings": -1, "error": res.get("error")}
    except Exception:
        pass
    return {"valid": False, "servings": -1}


def solve_auto_race(map_config, day_info, roles, time_limit_ms=3000, log_fn=None, include_all=False, day_num=1, raw_status=None):
    """Chạy song song các solver, đo điểm số thực tế bằng check và nộp phương án cao điểm nhất."""
    normalize_map_config(map_config)
    def run_candidate(pol):
        t0 = time.time()
        try:
            if pol == "procon26":
                payload = build_procon26_payload(map_config, day_info, day_num, raw_status)
                p = subprocess.run([str(PROCON26_RUNNER)], input=json.dumps(payload), text=True, capture_output=True, timeout=max(15, int(time_limit_ms / 1000) + 5), cwd=ROOT_PROCON26)
                res = json.loads(p.stdout)
                if not res.get("ok"):
                    return pol, None, {"valid": False, "servings": -1}, time.time() - t0
                plan = res["plan"]
                if not res.get("ok"):
                    return pol, None, {"valid": False, "servings": -1}, time.time() - t0
                plan = res["plan"]
            else:
                p = subprocess.run(
                    [str(HEX_BINARY), "plan", pol],
                    input=json.dumps({"config": map_config, "day_info": day_info, "types": roles, "search": {"time_limit_ms": time_limit_ms}}),
                    text=True,
                    capture_output=True,
                    timeout=max(15, int(time_limit_ms / 1000) + 8),
                    cwd=ROOT
                )
                if p.returncode != 0:
                    return pol, None, {"valid": False, "servings": -1}, time.time() - t0
                plan = json.loads(p.stdout)

            el = time.time() - t0
            score = check_plan_score(map_config, day_info, plan)
            return pol, plan, score, el
        except Exception:
            return pol, None, {"valid": False, "servings": -1}, time.time() - t0

    if include_all:
        candidates = ["aco_ls", "alns", "procon26", "local_search", "greedy"]
        race_title = f"[Auto-Race ALL] Khởi tranh đại chiến {len(candidates)} Solver cùng lúc ({time_limit_ms}ms)..."
    else:
        candidates = ["aco_ls", "alns"]
        race_title = f"[Auto-Race] Khởi động đua song song: ACO vs ALNS ({time_limit_ms}ms)..."

    if log_fn:
        log_fn(race_title, "INFO")

    results = []
    with ThreadPoolExecutor(max_workers=len(candidates)) as executor:
        futures = [executor.submit(run_candidate, c) for c in candidates]
        for f in futures:
            results.append(f.result())

    name_map = {
        "aco_ls": "ACO",
        "alns": "ALNS",
        "procon26": "Procon26",
        "local_search": "LocalSearch",
        "greedy": "Greedy",
        "mlns": "MLNS"
    }

    for pol, plan, sc, el in results:
        pol_name = name_map.get(pol, pol)
        if sc.get("valid"):
            if log_fn:
                log_fn(f"  🏎️ {pol_name:<11}: {sc.get('servings', 0)} bát mì | {sc.get('distinct_types', 0)}/4 loại ({el:.2f}s)", "INFO")
        else:
            if log_fn:
                log_fn(f"  ❌ {pol_name:<11}: Kế hoạch không hợp lệ hoặc quá giờ ({el:.2f}s)", "WARN")

    valid_results = [r for r in results if r[1] is not None and r[2].get("valid", False)]
    if valid_results:
        winner = max(valid_results, key=lambda x: (x[2].get("daily_types", 0), x[2].get("servings", 0), -x[3]))
        win_name = name_map.get(winner[0], winner[0])
        if log_fn:
            log_fn(f"  🏆 CHIẾN THẮNG: {win_name} ({winner[2].get('servings', 0)} bát mì) -> ĐÃ CHỌN ĐỂ NỘP LÊN SERVER!", "SUCCESS")
        return winner[1]

    # Cứu sinh nếu tất cả solver đều lỗi
    if log_fn:
        log_fn("[Auto-Race] Tất cả đều gặp lỗi, kích hoạt phương án cứu sinh khẩn cấp...", "WARN")
    try:
        p_fb = subprocess.run([str(HEX_BINARY), "plan", "greedy"], input=json.dumps({"config": map_config, "day_info": day_info, "types": roles, "search": {"time_limit_ms": 1000}}), text=True, capture_output=True, timeout=10, cwd=ROOT)
        if p_fb.returncode == 0 and p_fb.stdout.strip():
            return json.loads(p_fb.stdout)
    except Exception:
        pass
    steps = day_info.get("steps", 20)
    num_agents = len(roles) if roles else (len(day_info.get("agents", [])) or 4)
    return [[-int(steps)] for _ in range(num_agents)]


def solve_plan(policy, map_config, day_info, roles, day_num=1, raw_status=None, time_limit_ms=3000, log_fn=None):
    normalize_map_config(map_config)
    if policy == "procon26":
        payload = build_procon26_payload(map_config, day_info, day_num, raw_status)
        p = subprocess.run([str(PROCON26_RUNNER)], input=json.dumps(payload), text=True, capture_output=True, timeout=30, cwd=ROOT_PROCON26)
        res = json.loads(p.stdout)
        if not res.get("ok"):
            raise RuntimeError(res.get("error"))
        return res["plan"]

    if policy == "auto_race":
        return solve_auto_race(map_config, day_info, roles, time_limit_ms=time_limit_ms, log_fn=log_fn, include_all=False, day_num=day_num, raw_status=raw_status)

    if policy == "auto_race_all":
        return solve_auto_race(map_config, day_info, roles, time_limit_ms=time_limit_ms, log_fn=log_fn, include_all=True, day_num=day_num, raw_status=raw_status)

    # Standard hex policy
    p = subprocess.run([str(HEX_BINARY), "plan", policy], input=json.dumps({"config": map_config, "day_info": day_info, "types": roles, "search": {"time_limit_ms": time_limit_ms}}), text=True, capture_output=True, timeout=max(20, int(time_limit_ms / 1000) + 10), cwd=ROOT)
    if p.returncode != 0 or not p.stdout.strip():
        if log_fn:
            log_fn(f"Solver {policy} lỗi ({p.returncode}), kích hoạt Greedy cứu nguy khẩn cấp...", "WARN")
        try:
            p_fb = subprocess.run([str(HEX_BINARY), "plan", "greedy"], input=json.dumps({"config": map_config, "day_info": day_info, "types": roles, "search": {"time_limit_ms": 1000}}), text=True, capture_output=True, timeout=10, cwd=ROOT)
            if p_fb.returncode == 0 and p_fb.stdout.strip():
                return json.loads(p_fb.stdout)
        except Exception:
            pass
        # Kế hoạch an toàn tuyệt đối bằng Python nếu binary gặp sự cố
        steps = day_info.get("steps", 20)
        num_agents = len(roles) if roles else (len(day_info.get("agents", [])) or 4)
        if log_fn:
            log_fn("Tạo kế hoạch an toàn (Wait) để bảo toàn trận đấu...", "WARN")
        return [[-int(steps)] for _ in range(num_agents)]
    
    plan = json.loads(p.stdout)
    sc = check_plan_score(map_config, day_info, plan)
    if sc.get("valid") and log_fn:
        log_fn(f"  📊 Kế hoạch: {sc.get('servings', 0)} bát mì | {sc.get('distinct_types', 0)}/4 loại mì", "INFO")
    return plan


class HexControlCenter(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("HEXUDON PROCON 2026 - Control Center & Strategy Bot")
        self.geometry("1420x820")
        self.minsize(1100, 680)
        
        self.api = HauiAPI()
        self.is_running = False
        self.current_match_id = None
        self.current_match_url = None
        self.stop_requested = False
        self.log_queue = queue.Queue()

        self.setup_styles()
        self.build_ui()
        self.check_log_queue()

    def setup_styles(self):
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except Exception:
            pass
        style.configure("TNotebook.Tab", font=("Segoe UI", 10, "bold"), padding=[12, 6])
        style.configure("Header.TLabel", font=("Segoe UI", 13, "bold"), foreground="#1A365D")
        style.configure("SubHeader.TLabel", font=("Segoe UI", 9), foreground="#4A5568")
        style.configure("Primary.TButton", font=("Segoe UI", 10, "bold"), background="#2B6CB0", foreground="white")
        style.configure("Success.TButton", font=("Segoe UI", 10, "bold"), background="#2F855A", foreground="white")
        style.configure("Danger.TButton", font=("Segoe UI", 10, "bold"), background="#C53030", foreground="white")

    def build_ui(self):
        # Top banner
        banner = tk.Frame(self, bg="#1A365D", height=50)
        banner.pack(fill=tk.X, side=tk.TOP)
        
        lbl_title = tk.Label(banner, text="🏆 HEXUDON PROCON 2026 - CONTROL CENTER", font=("Segoe UI", 13, "bold"), fg="white", bg="#1A365D")
        lbl_title.pack(side=tk.LEFT, padx=16, pady=8)
        
        lbl_sub = tk.Label(banner, text="Multi-Solver Engine: ACO • ALNS • MLNS • Procon26", font=("Segoe UI", 9), fg="#CBD5E0", bg="#1A365D")
        lbl_sub.pack(side=tk.RIGHT, padx=16, pady=10)

        # MAIN SPLIT CONTAINER (Chia đôi giao diện: Trái = Bảng điều khiển, Phải = Console Log)
        self.paned = ttk.PanedWindow(self, orient=tk.HORIZONTAL)
        self.paned.pack(fill=tk.BOTH, expand=True, padx=8, pady=(4, 8))

        # CỘT TRÁI: Bảng điều khiển (Notebook tabs)
        left_frame = ttk.Frame(self.paned)
        self.paned.add(left_frame, weight=5)

        self.notebook = ttk.Notebook(left_frame)
        self.notebook.pack(fill=tk.BOTH, expand=True)

        # TAB 1: Thi đấu chính thức (Live Match)
        self.tab_live = ttk.Frame(self.notebook)
        self.notebook.add(self.tab_live, text=" 🎯 Thi Đấu Trực Tiếp (Live / Practice) ")
        self.build_tab_live()

        # TAB 2: Đấu đối kháng tự động (Versus Arena)
        self.tab_versus = ttk.Frame(self.notebook)
        self.notebook.add(self.tab_versus, text=" ⚔️ Đấu Trường Đối Kháng (Arena) ")
        self.build_tab_versus()

        # TAB 3: Cài đặt & Kho Solver
        self.tab_info = ttk.Frame(self.notebook)
        self.notebook.add(self.tab_info, text=" ℹ️ Kho Solver & Hướng Dẫn ")
        self.build_tab_info()

        # CỘT PHẢI: Nhật Ký Thi Đấu Thời Gian Thực (Full chiều cao)
        log_frame = ttk.LabelFrame(self.paned, text="📋 Nhật Ký Thi Đấu Thời Gian Thực (Console Logs)", padding=6)
        self.paned.add(log_frame, weight=5)

        # Header bar trên cột phải
        log_top = ttk.Frame(log_frame)
        log_top.pack(fill=tk.X, pady=(0, 4))

        lbl_log_status = ttk.Label(log_top, text="🟢 Trực tiếp (Live Stream)", font=("Segoe UI", 9, "bold"), foreground="#2B6CB0")
        lbl_log_status.pack(side=tk.LEFT, padx=2)

        btn_clear = ttk.Button(log_top, text="🧹 Xóa Log", command=self.clear_log, width=10)
        btn_clear.pack(side=tk.RIGHT, padx=2)

        self.txt_log = scrolledtext.ScrolledText(log_frame, wrap=tk.WORD, font=("Consolas", 10), bg="#1E1E1E", fg="#D4D4D4")
        self.txt_log.pack(fill=tk.BOTH, expand=True, padx=2, pady=2)
        self.txt_log.tag_config("SUCCESS", foreground="#48BB78")
        self.txt_log.tag_config("ERROR", foreground="#F56565")
        self.txt_log.tag_config("INFO", foreground="#63B3ED")
        self.txt_log.tag_config("WARN", foreground="#ECC94B")

    def clear_log(self):
        """Xóa toàn bộ nội dung console log."""
        self.txt_log.delete("1.0", tk.END)

    # ==================== TAB 1 ====================
    def build_tab_live(self):
        frame = ttk.Frame(self.tab_live, padding=12)
        frame.pack(fill=tk.BOTH, expand=True)

        # Row 1: Team Preset, Server Host & Token
        row1 = ttk.LabelFrame(frame, text="1. Chọn Máy Chủ, Đội & Token Thi Đấu", padding=8)
        row1.pack(fill=tk.X, pady=(0, 8))

        ttk.Label(row1, text="Máy chủ (Host/IP):").grid(row=0, column=0, sticky=tk.W, padx=4, pady=4)
        self.ent_host = ttk.Entry(row1, width=38)
        self.ent_host.insert(0, DEFAULT_HOST)
        self.ent_host.grid(row=0, column=1, sticky=tk.W, padx=4, pady=4)

        ttk.Label(row1, text="Đội mẫu:").grid(row=1, column=0, sticky=tk.W, padx=4, pady=4)
        self.cbo_preset = ttk.Combobox(row1, values=[f"{t['name']} ({t['policy'].upper()})" for t in PRESET_TEAMS], width=35, state="readonly")
        self.cbo_preset.grid(row=1, column=1, sticky=tk.W, padx=4, pady=4)
        self.cbo_preset.current(0)
        self.cbo_preset.bind("<<ComboboxSelected>>", self.on_preset_selected)

        ttk.Label(row1, text="Token (X-API-TOKEN):").grid(row=2, column=0, sticky=tk.W, padx=4, pady=4)
        self.ent_token = ttk.Entry(row1, width=50)
        self.ent_token.insert(0, PRESET_TEAMS[0]["token"])
        self.ent_token.grid(row=2, column=1, sticky=tk.W, padx=4, pady=4)

        btn_test_conn = ttk.Button(row1, text="⚡ Kiểm Tra Kết Nối", command=self.test_connection)
        btn_test_conn.grid(row=2, column=2, padx=6, pady=4)

        # Row 2: Match ID & Solver Selection
        row2 = ttk.LabelFrame(frame, text="2. Cấu Hình Trận Đấu & Chọn Solver", padding=8)
        row2.pack(fill=tk.X, pady=(0, 8))

        ttk.Label(row2, text="Match ID:").grid(row=0, column=0, sticky=tk.W, padx=4, pady=4)
        self.ent_match_id = ttk.Entry(row2, width=38)
        self.ent_match_id.grid(row=0, column=1, sticky=tk.W, padx=4, pady=4)
        self.ent_match_id.bind("<Return>", lambda e: self.load_match_info())

        btn_find_match = ttk.Button(row2, text="🔍 Lấy trận mới nhất", command=self.fetch_latest_match)
        btn_find_match.grid(row=0, column=2, padx=4, pady=4)

        btn_load_match = ttk.Button(row2, text="📋 Tải thông số map", command=self.load_match_info)
        btn_load_match.grid(row=0, column=3, padx=4, pady=4)

        ttk.Label(row2, text="Solver Thuật toán:").grid(row=1, column=0, sticky=tk.W, padx=4, pady=4)
        self.cbo_solver = ttk.Combobox(row2, values=list(SOLVERS.keys()), width=45, state="readonly")
        self.cbo_solver.grid(row=1, column=1, columnspan=3, sticky=tk.W, padx=4, pady=4)
        self.cbo_solver.current(3)  # Mặc định Auto-Race

        ttk.Label(row2, text="Thời gian giải/ngày:").grid(row=2, column=0, sticky=tk.W, padx=4, pady=4)
        self.cbo_timelimit = ttk.Combobox(row2, values=["1500ms (1.5s - Tối ưu tốc độ)", "3000ms (3.0s - Tiêu chuẩn)", "5000ms (5.0s - Chuyên sâu)", "8000ms (8.0s - Cực sâu)"], width=30, state="readonly")
        self.cbo_timelimit.grid(row=2, column=1, sticky=tk.W, padx=4, pady=4)
        self.cbo_timelimit.current(1)

        self.lbl_match_details = ttk.Label(row2, text="Thông số trận: Chưa tải thông tin (Nhập Match ID rồi bấm '🔍 Lấy trận mới nhất' hoặc '📋 Tải thông số map')", font=("Segoe UI", 9, "bold"), foreground="#2B6CB0")
        self.lbl_match_details.grid(row=3, column=0, columnspan=4, sticky=tk.W, padx=4, pady=(4, 2))

        # Row 3: Cấu Hình Vai Trò Xe (Patrol vs Refuel Tiếp Xăng)
        row_roles = ttk.LabelFrame(frame, text="3. Phân Bổ Vai Trò Xe (Xe Gom Mì 🏎️ & Xe Tiếp Xăng ⛽)", padding=8)
        row_roles.pack(fill=tk.X, pady=(0, 8))

        ttk.Label(row_roles, text="Cấu hình xe:").grid(row=0, column=0, sticky=tk.W, padx=4, pady=4)
        self.cbo_role_preset = ttk.Combobox(
            row_roles,
            values=[
                "1 Xe Tiếp Xăng (Xe 1 ⛽) + Còn lại Tuần Tra (🏎️) - [Khuyên Dùng Chuẩn]",
                "2 Xe Tiếp Xăng (Xe 1, 2 ⛽) + Còn lại Tuần Tra (🏎️)",
                "Tự động tính toán bằng Solver (Thuật toán tự chọn)",
                "Tùy chỉnh thủ công từng xe bên dưới"
            ],
            width=50,
            state="readonly"
        )
        self.cbo_role_preset.grid(row=0, column=1, columnspan=4, sticky=tk.W, padx=4, pady=4)
        self.cbo_role_preset.current(0)
        self.cbo_role_preset.bind("<<ComboboxSelected>>", self.on_role_preset_changed)

        self.btn_send_roles = ttk.Button(row_roles, text="📤 Nộp Vai Trò Xe Ngay", command=self.submit_roles_now)
        self.btn_send_roles.grid(row=0, column=5, padx=8, pady=4)

        # Selector cho từng xe (động theo số lượng xe của map)
        self.agent_role_combos = []
        self.frame_agents = ttk.Frame(row_roles)
        self.frame_agents.grid(row=1, column=0, columnspan=6, sticky=tk.W, padx=4, pady=4)

        self.update_agent_role_ui(6)  # Khởi tạo mặc định 6 xe, sẽ tự động co giãn theo map

        # Row 4: Action Buttons
        row3 = ttk.Frame(frame)
        row3.pack(fill=tk.X, pady=6)

        self.btn_start = tk.Button(row3, text="▶ TỰ ĐỘNG CẢ TRẬN (AUTO PLAY)", font=("Segoe UI", 10, "bold"), bg="#2B6CB0", fg="white", activebackground="#2C5282", activeforeground="white", padx=12, pady=6, relief=tk.RAISED, command=lambda: self.start_live_match(mode="auto"))
        self.btn_start.pack(side=tk.LEFT, padx=(0, 6))

        self.btn_step = tk.Button(row3, text="🎯 GIẢI & NỘP 1 NGÀY (STEP)", font=("Segoe UI", 10, "bold"), bg="#319795", fg="white", activebackground="#285E61", activeforeground="white", padx=12, pady=6, relief=tk.RAISED, command=lambda: self.start_live_match(mode="step"))
        self.btn_step.pack(side=tk.LEFT, padx=(0, 6))

        self.btn_stop = tk.Button(row3, text="⏹ DỪNG", font=("Segoe UI", 10, "bold"), bg="#C53030", fg="white", activebackground="#9B2C2C", activeforeground="white", padx=12, pady=6, relief=tk.RAISED, state=tk.DISABLED, command=self.stop_match)
        self.btn_stop.pack(side=tk.LEFT, padx=(0, 6))

        self.btn_replay = ttk.Button(row3, text="🌐 Mở Xem Replay Trực Tiếp", state=tk.DISABLED, command=self.open_current_replay)
        self.btn_replay.pack(side=tk.LEFT, padx=6)

        # Status cards
        status_box = ttk.LabelFrame(frame, text="Trạng Thái Thi Đấu", padding=8)
        status_box.pack(fill=tk.X, pady=(6, 0))

        self.lbl_status_day = ttk.Label(status_box, text="Trạng thái: Sẵn sàng", font=("Segoe UI", 10, "bold"), foreground="#2D3748")
        self.lbl_status_day.grid(row=0, column=0, sticky=tk.W, padx=8, pady=2)

        self.lbl_status_score = ttk.Label(status_box, text="Điểm số: Chưa có", font=("Segoe UI", 10), foreground="#4A5568")
        self.lbl_status_score.grid(row=0, column=1, sticky=tk.W, padx=16, pady=2)

    def on_preset_selected(self, event=None):
        idx = self.cbo_preset.current()
        if idx >= 0 and idx < len(PRESET_TEAMS):
            team = PRESET_TEAMS[idx]
            self.ent_token.delete(0, tk.END)
            self.ent_token.insert(0, team["token"])
            # Sync solver
            policy = team["policy"]
            for i, (name, p) in enumerate(SOLVERS.items()):
                if p == policy:
                    self.cbo_solver.current(i)
                    break

    def update_agent_role_ui(self, num_agents):
        """Cập nhật giao diện chọn vai trò xe co giãn theo đúng số xe thực tế của map."""
        # Loading/refreshing the match used to rebuild these widgets and silently
        # reset a manual selection immediately before submit_roles_now() read it.
        # Preserve the current values across a rebuild when the agent count is
        # unchanged (and preserve the overlapping prefix when it changes).
        previous_roles = []
        for cbo in self.agent_role_combos:
            previous_roles.append(1 if "(1)" in cbo.get() else 0)
        preset_index = self.cbo_role_preset.current()

        for w in self.frame_agents.winfo_children():
            w.destroy()
        self.agent_role_combos.clear()

        # Cập nhật danh sách preset theo số xe thực tế
        p1 = f"1 Xe Tiếp Xăng (Xe 1 ⛽) + {max(0, num_agents - 1)} Xe Tuần Tra (🏎️) - [Khuyên Dùng]"
        p2 = f"2 Xe Tiếp Xăng (Xe 1, 2 ⛽) + {max(0, num_agents - 2)} Xe Tuần Tra (🏎️)" if num_agents >= 3 else "2 Xe Tiếp Xăng"
        self.cbo_role_preset["values"] = [
            p1,
            p2,
            f"Tự động tính toán bằng Solver ({num_agents} xe)",
            "Tùy chỉnh thủ công từng xe bên dưới"
        ]
        if self.cbo_role_preset.current() < 0:
            self.cbo_role_preset.current(0)

        for i in range(num_agents):
            r = i // 4
            c = (i % 4) * 2
            lbl = ttk.Label(self.frame_agents, text=f"Xe {i+1}:", font=("Segoe UI", 9, "bold"))
            lbl.grid(row=r, column=c, sticky=tk.W, padx=(8 if (i % 4) > 0 else 0, 2), pady=3)
            cbo = ttk.Combobox(self.frame_agents, values=["🏎️ Tuần tra (0)", "⛽ Tiếp xăng (1)"], width=13, state="readonly")
            if preset_index == 3 and i < len(previous_roles):
                cbo.current(previous_roles[i])
            else:
                cbo.current(1 if i == 0 else 0)
            cbo.grid(row=r, column=c + 1, sticky=tk.W, padx=(0, 6), pady=3)
            self.agent_role_combos.append(cbo)

        # Re-apply the selected preset and the correct editable/disabled state.
        self.on_role_preset_changed()

    def on_role_preset_changed(self, event=None):
        idx = self.cbo_role_preset.current()
        num_agents = len(self.agent_role_combos)
        if idx == 0:  # 1 Refuel (Xe 1) + còn lại Patrol
            for i in range(num_agents):
                self.agent_role_combos[i].current(1 if i == 0 else 0)
        elif idx == 1:  # 2 Refuel (Xe 1, 2) + còn lại Patrol
            for i in range(num_agents):
                self.agent_role_combos[i].current(1 if (i in [0, 1] and num_agents > 1) else 0)
        elif idx == 2:  # Solver auto
            self.log(f"Đã chọn chế độ Tự động: Thuật toán Solver sẽ tự phân tích bản đồ để chọn vai trò tối ưu cho {num_agents} xe.", "INFO")

        # The per-agent controls are meaningful only in manual mode. Showing
        # preset values while disabling edits also makes it clear which list
        # will actually be submitted.
        combo_state = "readonly" if idx == 3 else "disabled"
        for cbo in self.agent_role_combos:
            cbo.configure(state=combo_state)

    def get_selected_roles(self, map_config, policy):
        idx = self.cbo_role_preset.current()
        num_agents = len(map_config.get("agents", [])) if (map_config and "agents" in map_config) else len(self.agent_role_combos)
        if idx == 0:  # Exactly one refuel car.
            return [1 if i == 0 else 0 for i in range(num_agents)]
        if idx == 1:  # Exactly two refuel cars (or all cars when only one exists).
            return [1 if i < min(2, num_agents) else 0 for i in range(num_agents)]
        if idx == 2:  # Solver auto
            roles = solve_roles(policy, map_config)
            if len(roles) < num_agents:
                roles = roles + [0] * (num_agents - len(roles))
            elif len(roles) > num_agents:
                roles = roles[:num_agents]
            return roles
        # Manual mode: use exactly what is visible in the per-agent selectors.
        roles = []
        for cbo in self.agent_role_combos:
            val = cbo.get()
            roles.append(1 if "Tiếp xăng" in val or "(1)" in val else 0)
        if len(roles) < num_agents:
            roles = roles + [0] * (num_agents - len(roles))
        elif len(roles) > num_agents:
            roles = roles[:num_agents]
        return roles

    def load_match_info(self, match_id=None):
        """Tải thông tin chi tiết của trận đấu từ server và tự động cập nhật GUI động."""
        if not match_id:
            match_id = self.ent_match_id.get().strip()
        if not match_id:
            messagebox.showwarning("Thiếu Match ID", "Vui lòng nhập Match ID trước khi tải thông tin map!")
            return None

        host = self.ent_host.get().strip() if hasattr(self, "ent_host") else DEFAULT_HOST
        self.api.set_host(host)
        token = self.ent_token.get().strip()

        map_config = None
        # ƯU TIÊN 1: Dùng token thí sinh gọi thẳng API game chính thức (/api/game/matches/{id}/config)
        if token:
            try:
                map_config = self.api.get_game_config(match_id, token)
            except Exception:
                pass

        # ƯU TIÊN 2: Nếu không có token hoặc chưa được, thử login admin (chỉ áp dụng cho server HAUI)
        if not map_config and "haui.ac.vn" in self.api.base_url.lower():
            try:
                self.api.login(DEFAULT_USER, DEFAULT_PASS)
                match_data = self.api.get_match(match_id)
                map_config = json.loads(match_data["match"]["map_config_json"])
            except Exception:
                pass

        if map_config:
            w = map_config.get("map", {}).get("width", "?")
            h = map_config.get("map", {}).get("height", "?")
            num_agents = len(map_config.get("agents", []))
            total_days = len(map_config.get("daySteps", []))
            num_spots = len(map_config.get("spots", []))
            fuel_limit = map_config.get("fuelLimits", "?")
            day_steps = map_config.get("daySteps", [])

            self.lbl_match_details.config(
                text=f"🗺️ Map {w}x{h} | 🏎️ {num_agents} Xe | 📅 {total_days} Ngày (bước: {day_steps}) | 🍜 {num_spots} Quán | ⛽ Xăng max: {fuel_limit}"
            )
            self.update_agent_role_ui(num_agents)
            self.log(f"✅ ĐÃ NẠP THÔNG SỐ MAP TỪ {self.api.base_url}: {w}x{h} ô, {num_agents} Xe, {total_days} Ngày (bước: {day_steps}), {num_spots} Quán mì, Xăng {fuel_limit}", "SUCCESS")
            return map_config
        else:
            self.log(f"Không thể tải map_config từ {self.api.base_url}. Thử đọc từ game status...", "WARN")
            if token:
                try:
                    st = self.api.get_game_status(match_id, token)
                    raw_agents = st.get("agents", [])
                    num_agents = len(raw_agents) if raw_agents else 6
                    self.update_agent_role_ui(num_agents)
                    self.lbl_match_details.config(text=f"🏎️ {num_agents} Xe (Đọc từ status) | Ngày hiện tại: {st.get('currentDay', 1)}")
                    self.log(f"Đã cập nhật số xe từ status: {num_agents} xe", "INFO")
                except Exception as e2:
                    self.log(f"Lỗi đọc status: {e2}", "ERROR")
            return None

    def submit_roles_now(self):
        token = self.ent_token.get().strip()
        match_id = self.ent_match_id.get().strip()
        policy = SOLVERS[self.cbo_solver.get()]
        if not token:
            messagebox.showwarning("Thiếu Token", "Vui lòng nhập X-API-TOKEN của đội!")
            return
        if not match_id:
            messagebox.showwarning("Thiếu Match ID", "Vui lòng nhập Match ID hoặc bấm nút 'Lấy trận mới nhất'!")
            return

        # Snapshot every Tk value before leaving the UI thread. Network calls,
        # admin fallback, and automatic role solving can each take many seconds;
        # doing them in this callback made Windows report the GUI as hung.
        host = self.ent_host.get().strip() if hasattr(self, "ent_host") else DEFAULT_HOST
        self.api.set_host(host)
        preset_index = self.cbo_role_preset.current()
        manual_roles = [1 if "(1)" in cbo.get() else 0
                        for cbo in self.agent_role_combos]
        self.btn_send_roles.configure(state=tk.DISABLED)
        self.log("Đang tải cấu hình và nộp vai trò xe...", "INFO")
        threading.Thread(
            target=self._submit_roles_worker,
            args=(match_id, token, policy, preset_index, manual_roles),
            daemon=True,
        ).start()

    def _submit_roles_worker(self, match_id, token, policy, preset_index,
                             manual_roles):
        try:
            map_config = None
            try:
                map_config = self.api.get_game_config(match_id, token)
            except Exception:
                pass
            if not map_config:
                if "haui.ac.vn" in self.api.base_url.lower():
                    try:
                        self.api.login(DEFAULT_USER, DEFAULT_PASS)
                        match_data = self.api.get_match(match_id)
                        map_config = json.loads(match_data["match"]["map_config_json"])
                    except Exception:
                        pass
            # Never use a local sample map to construct an official role answer:
            # a different agent count is a guaranteed HTTP 400. Manual presets
            # need only the already rendered selector count; automatic mode
            # genuinely requires the authoritative map.
            if map_config:
                num_agents = len(map_config.get("agents", []))
            else:
                try:
                    status = self.api.get_game_status(match_id, token)
                    status_agents = status.get("agents", [])
                    num_agents = len(status_agents) or len(manual_roles)
                except Exception:
                    num_agents = len(manual_roles)
            if num_agents <= 0:
                raise RuntimeError("Không xác định được số xe của trận đấu")
            if preset_index == 0:
                roles = [1 if i == 0 else 0 for i in range(num_agents)]
            elif preset_index == 1:
                roles = [1 if i < min(2, num_agents) else 0
                         for i in range(num_agents)]
            elif preset_index == 2:
                if not map_config:
                    raise RuntimeError(
                        "Không tải được map thật từ server nên không thể tự động chọn xe"
                    )
                roles = solve_roles(policy, map_config)
                roles = (roles + [0] * num_agents)[:num_agents]
            else:
                roles = (manual_roles + [0] * num_agents)[:num_agents]

            if len(roles) != num_agents or any(role not in (0, 1) for role in roles):
                raise RuntimeError(
                    f"Danh sách vai trò không hợp lệ: {roles} (cần {num_agents} xe)"
                )
            self.api.submit_roles(match_id, token, roles)
            self.after(0, self._finish_submit_roles, roles, num_agents, None)
        except Exception as e:
            self.after(0, self._finish_submit_roles, None, 0, str(e))

    def _finish_submit_roles(self, roles, num_agents, error):
        self.btn_send_roles.configure(state=tk.NORMAL)
        if error:
            self.log(f"❌ Lỗi khi nộp vai trò xe: {error}", "ERROR")
            messagebox.showerror("Lỗi nộp xe", f"Không thể nộp vai trò xe: {error}")
            return
        refuels = roles.count(1)
        patrols = roles.count(0)
        self.log(f"✅ ĐÃ NỘP VAI TRÒ XE THÀNH CÔNG: {roles}", "SUCCESS")
        self.log(f"   📊 Cấu hình: {refuels} xe tiếp xăng ⛽ | {patrols} xe tuần tra 🏎️ (Tổng: {num_agents} xe)", "SUCCESS")
        messagebox.showinfo(
            "Nộp thành công",
            f"Đã nộp cấu hình xe lên Server:\n{roles}\n"
            f"({refuels} xe tiếp xăng ⛽, {patrols} xe tuần tra 🏎️ / Tổng {num_agents} xe)",
        )

    def fetch_latest_match(self):
        host = self.ent_host.get().strip() if hasattr(self, "ent_host") else DEFAULT_HOST
        self.api.set_host(host)
        token = self.ent_token.get().strip()

        try:
            self.log(f"🔍 Đang tìm danh sách trận đấu trên {self.api.base_url}...", "INFO")
            matches = []

            # 1. Ưu tiên: Lấy danh sách trận bằng Token thí sinh (/api/game/matches)
            if token:
                try:
                    matches = self.api.get_matches(token=token)
                except Exception as e_tok:
                    self.log(f"  (Lấy danh sách qua Token: {e_tok})", "WARN")

            # 2. Nếu không có token hoặc chưa được và là server HAUI, thử login admin dự phòng
            if not matches and "haui.ac.vn" in self.api.base_url.lower():
                try:
                    self.api.login(DEFAULT_USER, DEFAULT_PASS)
                    matches = self.api.get_matches()
                except Exception:
                    pass

            if matches:
                latest = matches[0]
                m_id = str(latest.get("id", ""))
                m_name = latest.get("name", f"Trận #{m_id}")
                self.ent_match_id.delete(0, tk.END)
                self.ent_match_id.insert(0, m_id)
                self.log(f"✅ Đã tìm thấy trận: {m_name} (ID: {m_id})", "SUCCESS")
                self.load_match_info(m_id)
            else:
                self.log("⚠️ Danh sách trận trên server hiện đang TRỐNG (0 trận).", "WARN")
                self.log("👉 Giải thích: Server hiện chưa có phòng/trận đấu nào được tạo.", "INFO")
                self.log("👉 Nếu BTC đã cấp Match ID: Bạn chỉ cần dán Match ID vào ô rồi bấm '📋 Tải thông số map'!", "INFO")
                self.log("👉 Nếu bạn quản trị server: Hãy vào trang Admin (web) để tạo trận đấu mới.", "INFO")
        except urllib.error.HTTPError as he:
            if he.code == 401:
                self.log("❌ Lỗi 401 Unauthorized: Server từ chối quyền truy cập. Vui lòng kiểm tra lại Token!", "ERROR")
            else:
                self.log(f"❌ Lỗi máy chủ ({he.code}): {he}", "ERROR")
        except Exception as e:
            self.log(f"❌ Lỗi khi tìm trận: {e}", "ERROR")

    def test_connection(self):
        token = self.ent_token.get().strip()
        match_id = self.ent_match_id.get().strip()
        host = self.ent_host.get().strip() if hasattr(self, "ent_host") else DEFAULT_HOST
        self.api.set_host(host)

        self.log("=" * 65, "INFO")
        self.log(f"🔍 ĐANG KIỂM TRA KẾT NỐI TỚI: {self.api.base_url} ...", "INFO")
        
        try:
            # Kiểm tra kết nối mạng tới server
            ping_url = f"{self.api.base_url}/setup"
            req = urllib.request.Request(ping_url, headers=self.api._headers())
            try:
                with urllib.request.urlopen(req, context=ctx, timeout=6) as resp:
                    self.log(f"  ✅ Kết nối mạng tới máy chủ {self.api.base_url}: HOÀN HẢO! (HTTP {resp.status})", "SUCCESS")
            except urllib.error.HTTPError as he:
                if he.code in [200, 401, 403, 404]:
                    self.log(f"  ✅ Kết nối mạng tới máy chủ {self.api.base_url}: TỐT (HTTP {he.code})!", "SUCCESS")
                else:
                    self.log(f"  ⚠️ Máy chủ phản hồi mã HTTP: {he.code}", "WARN")
        except Exception as e:
            try:
                req_root = urllib.request.Request(self.api.base_url, headers=self.api._headers())
                with urllib.request.urlopen(req_root, context=ctx, timeout=6) as resp:
                    self.log(f"  ✅ Kết nối mạng tới máy chủ {self.api.base_url}: HOÀN HẢO! (HTTP {resp.status})", "SUCCESS")
            except Exception as e2:
                self.log(f"  ❌ Không thể kết nối tới {self.api.base_url}: {e2}", "ERROR")
                self.log("=" * 65, "INFO")
                return

        if not token:
            self.log("  ⚠️ Chưa nhập Token. Vui lòng dán X-API-TOKEN để kiểm tra quyền dự thi!", "WARN")
            self.log("=" * 65, "INFO")
            return

        if match_id:
            try:
                st = self.api.get_game_status(match_id, token)
                curr_day = st.get("currentDay", "N/A")
                agents_cnt = len(st.get("agents", []))
                self.log(f"  ✅ X-API-TOKEN HỢP LỆ!", "SUCCESS")
                self.log(f"  📊 Trận đấu {match_id}: Đang ở Ngày {curr_day} | Số xe: {agents_cnt}", "SUCCESS")
            except Exception as e_tok:
                self.log(f"  ❌ Lỗi xác thực token trên trận {match_id}: {e_tok}", "ERROR")
        else:
            self.log(f"  ✅ Đã nhận diện Token ({token[:15]}...). Bạn có thể bấm 'Lấy trận mới nhất' để thi đấu!", "SUCCESS")
        self.log("=" * 65, "INFO")

    def start_live_match(self, mode="auto"):
        token = self.ent_token.get().strip()
        match_id = self.ent_match_id.get().strip()
        host = self.ent_host.get().strip() if hasattr(self, "ent_host") else DEFAULT_HOST
        self.api.set_host(host)

        solver_name = self.cbo_solver.get()
        policy = SOLVERS[solver_name]

        time_limit_str = self.cbo_timelimit.get()
        try:
            time_limit_ms = int(time_limit_str.split("ms")[0])
        except Exception:
            time_limit_ms = 3000

        if not token:
            messagebox.showwarning("Thiếu Token", "Vui lòng nhập X-API-TOKEN của đội!")
            return
        if not match_id:
            messagebox.showwarning("Thiếu Match ID", "Vui lòng nhập Match ID hoặc bấm nút 'Lấy trận mới nhất'!")
            return

        self.is_running = True
        self.stop_requested = False
        self.btn_start.config(state=tk.DISABLED)
        self.btn_step.config(state=tk.DISABLED)
        self.btn_stop.config(state=tk.NORMAL)
        self.btn_replay.config(state=tk.NORMAL)
        self.current_match_id = match_id
        self.current_match_url = f"{self.api.base_url}/matches/{match_id}"

        threading.Thread(target=self._run_live_worker, args=(match_id, token, policy, time_limit_ms, mode), daemon=True).start()

    def stop_match(self):
        self.stop_requested = True
        self.log("Đã yêu cầu DỪNG bot thi đấu.", "WARN")

    def _run_live_worker(self, match_id, token, policy, time_limit_ms, mode="auto"):
        try:
            self.log("=" * 70, "INFO")
            mode_text = "TỰ ĐỘNG CHẠY CẢ TRẬN (AUTO PLAY)" if mode == "auto" else "GIẢI & NỘP 1 NGÀY (STEP)"
            self.log(f"▶ CHẾ ĐỘ: {mode_text}", "INFO")
            self.log(f"Trận đấu ID: {match_id}", "INFO")
            self.log(f"Thuật toán: {policy.upper()} | Hạn mức thời gian: {time_limit_ms}ms", "INFO")
            
            # Lấy map config (Ưu tiên dùng token gọi /api/game/matches/{id}/config)
            map_config = None
            if token:
                try:
                    map_config = self.api.get_game_config(match_id, token)
                except Exception:
                    pass
            if not map_config:
                if "haui.ac.vn" in self.api.base_url.lower():
                    try:
                        self.api.login(DEFAULT_USER, DEFAULT_PASS)
                        match_data = self.api.get_match(match_id)
                        map_config = json.loads(match_data["match"]["map_config_json"])
                    except Exception:
                        pass
                if not map_config:
                    self.log("Không lấy được map từ server, chuyển sang nạp bản đồ map_22x22.json...", "WARN")
                    with open(ROOT / "map_22x22.json", "r", encoding="utf-8") as f:
                        map_config = json.load(f)

            w = map_config.get("map", {}).get("width", "?")
            h = map_config.get("map", {}).get("height", "?")
            num_agents = len(map_config.get("agents", []))
            total_days = len(map_config.get("daySteps", []))
            num_spots = len(map_config.get("spots", []))
            fuel_limit = map_config.get("fuelLimits", "?")
            day_steps = map_config.get("daySteps", [])
            self.log(f"🗺️ Bản đồ trận đấu: {w}x{h} ô | 🏎️ {num_agents} Xe | 📅 {total_days} Ngày (bước: {day_steps}) | 🍜 {num_spots} Quán mì | ⛽ Xăng max: {fuel_limit}", "INFO")

            # BƯỚC 1: Lấy status ban đầu để xác định ngày hiện tại
            status = self.api.get_game_status(match_id, token)
            curr_day = status.get("currentDay", 1)

            # Chọn vai trò xe
            self.log("Đang kiểm tra và phân bổ vai trò xe...", "INFO")
            roles = self.get_selected_roles(map_config, policy)
            if len(roles) < num_agents:
                roles = roles + [0] * (num_agents - len(roles))
            elif len(roles) > num_agents:
                roles = roles[:num_agents]
            refuels = roles.count(1)
            patrols = roles.count(0)
            self.log(f"Cấu hình vai trò xe: {roles} ({refuels} xe tiếp xăng ⛽, {patrols} xe tuần tra 🏎️ / Tổng {num_agents} xe)", "INFO")
            try:
                self.api.submit_roles(match_id, token, roles)
                self.log(f"Nộp cấu hình xe lên server thành công: {roles}", "SUCCESS")
            except Exception as e:
                self.log(f"Nộp vai trò xe (có thể đã nộp trước đó): {e}", "INFO")

            def solve_and_submit_day(target_day):
                day_idx = target_day - 1
                steps = map_config["daySteps"][day_idx]
                self.lbl_status_day.config(text=f"Trạng thái: Đang giải Ngày {target_day}/{total_days} ({steps} bước)")
                self.log(f"\n--- NGÀY {target_day}/{total_days} (Số bước: {steps}) ---", "INFO")

                # Đợi server đồng bộ ngày (linh hoạt 0-indexed và 1-indexed)
                day_st = None
                for _ in range(25):
                    if self.stop_requested:
                        break
                    try:
                        st = self.api.get_game_status(match_id, token)
                        cur = st.get("currentDay")
                        cur_alt = st.get("current_day")
                        if cur == target_day or cur == (target_day - 1) or cur_alt == target_day or cur_alt == (target_day - 1):
                            day_st = st
                            break
                    except Exception:
                        pass
                    time.sleep(0.5)

                if not day_st:
                    try:
                        day_st = self.api.get_game_status(match_id, token)
                    except Exception as e_st:
                        self.log(f"Lỗi đọc status từ server: {e_st}", "ERROR")
                        day_st = {}

                # Chuẩn hóa an toàn dữ liệu bản đồ, xe và giao thông
                normalize_map_config(map_config)
                road_cells = get_road_cells(map_config)
                norm_traffics = normalize_traffics(day_st.get("traffics", []), road_cells)
                built_agents = normalize_agents(
                    day_st.get("agents", []),
                    map_config.get("agents", []),
                    roles,
                    map_config.get("fuelLimits", 200)
                )

                day_info = {
                    "day": day_idx,
                    "steps": steps,
                    "agents": built_agents,
                    "traffics": norm_traffics
                }

                t0 = time.time()
                plan = solve_plan(policy, map_config, day_info, roles, day_num=target_day, raw_status=day_st, time_limit_ms=time_limit_ms, log_fn=self.log)
                elapsed = time.time() - t0
                self.log(f"Đã giải xong trong {elapsed:.2f}s! Đang nộp bài...", "SUCCESS")

                ans_res = self.api.submit_actions(match_id, token, plan)
                self.log(f"Server phản hồi: {ans_res}", "INFO")

            # BƯỚC 2: Tiến hành giải theo chế độ đã chọn
            if mode == "step":
                solve_and_submit_day(curr_day)
                self.lbl_status_day.config(text=f"Trạng thái: Đã hoàn tất nộp Ngày {curr_day}! Sẵn sàng.")
                self.log(f"🎯 ĐÃ HOÀN TẤT NỘP BÀI NGÀY {curr_day}!", "SUCCESS")
                self.log("Bạn có thể mở Replay xem diễn biến, đổi Solver nếu muốn và bấm tiếp cho ngày sau.", "INFO")
            else:
                for day_num in range(curr_day, total_days + 1):
                    if self.stop_requested:
                        self.log("Đã dừng theo yêu cầu của bạn.", "WARN")
                        break

                    solve_and_submit_day(day_num)

                    # Chuyển ngày nếu là match luyện tập của admin
                    if day_num < total_days:
                        time.sleep(0.5)
                        try:
                            self.api.match_action(match_id, "next_day")
                            self.log(f"Đã kích hoạt next_day sang Ngày {day_num + 1}", "INFO")
                        except Exception:
                            pass

                # BƯỚC 3: Tổng kết điểm
                time.sleep(2.0)
                final_m = None
                try:
                    final_m = self.api.get_match(match_id)
                except Exception:
                    pass

                self.log(f"\n===========================================================", "SUCCESS")
                self.log(f"🏁 TRẬN ĐẤU HOÀN THÀNH!", "SUCCESS")
                if final_m and "teams" in final_m:
                    for t in final_m.get("teams", []):
                        t_name = t.get("team_name")
                        servings = t.get("total_udon_servings", 0)
                        types = t.get("total_udon_types", 0)
                        daily = t.get("total_udon_daily_types", 0)
                        self.log(f"🚩 Đội {t_name}: {servings} bát mì | {types}/4 loại mì | {daily} loại/ngày", "SUCCESS")
                        self.lbl_status_score.config(text=f"Điểm số: {servings} bát mì (Loại: {types}/4, Daily: {daily})")
                self.lbl_status_day.config(text="Trạng thái: Trận đấu đã hoàn thành")
                self.log(f"Xem replay: {self.current_match_url}", "INFO")
                self.log(f"===========================================================", "SUCCESS")

        except Exception as e:
            import traceback
            tb = traceback.format_exc()
            self.log(f"Lỗi trận đấu: {e}", "ERROR")
            self.log(f"Chi tiết kỹ thuật:\n{tb}", "ERROR")
            self.lbl_status_day.config(text="Trạng thái: Gặp sự cố")
        finally:
            self.is_running = False
            self.btn_start.config(state=tk.NORMAL)
            self.btn_step.config(state=tk.NORMAL)
            self.btn_stop.config(state=tk.DISABLED)

    # ==================== TAB 2 ====================
    def build_tab_versus(self):
        frame = ttk.Frame(self.tab_versus, padding=12)
        frame.pack(fill=tk.BOTH, expand=True)

        box_select = ttk.LabelFrame(frame, text="1. Chọn 2 Đội So Tài 1v1", padding=10)
        box_select.pack(fill=tk.X, pady=(0, 8))

        # Đội 1
        ttk.Label(box_select, text="ĐỘI 1:", font=("Segoe UI", 10, "bold"), foreground="#2B6CB0").grid(row=0, column=0, padx=6, pady=6, sticky=tk.W)
        self.cbo_v_team1 = ttk.Combobox(box_select, values=[t["name"] for t in PRESET_TEAMS], width=20, state="readonly")
        self.cbo_v_team1.grid(row=0, column=1, padx=6, pady=6)
        self.cbo_v_team1.current(0)  # Team-ACO

        ttk.Label(box_select, text="Thuật toán:").grid(row=0, column=2, padx=6, pady=6)
        self.cbo_v_policy1 = ttk.Combobox(box_select, values=list(SOLVERS.keys()), width=35, state="readonly")
        self.cbo_v_policy1.grid(row=0, column=3, padx=6, pady=6)
        self.cbo_v_policy1.current(0)  # ACO

        # Đội 2
        ttk.Label(box_select, text="ĐỘI 2:", font=("Segoe UI", 10, "bold"), foreground="#C53030").grid(row=1, column=0, padx=6, pady=6, sticky=tk.W)
        self.cbo_v_team2 = ttk.Combobox(box_select, values=[t["name"] for t in PRESET_TEAMS], width=20, state="readonly")
        self.cbo_v_team2.grid(row=1, column=1, padx=6, pady=6)
        self.cbo_v_team2.current(1)  # Team-ALNS

        ttk.Label(box_select, text="Thuật toán:").grid(row=1, column=2, padx=6, pady=6)
        self.cbo_v_policy2 = ttk.Combobox(box_select, values=list(SOLVERS.keys()), width=35, state="readonly")
        self.cbo_v_policy2.grid(row=1, column=3, padx=6, pady=6)
        self.cbo_v_policy2.current(1)  # ALNS

        # Mode 1: 1v1
        row_btn = ttk.Frame(frame)
        row_btn.pack(fill=tk.X, pady=(4, 10))

        self.btn_run_versus = tk.Button(row_btn, text="⚔️ ĐẤU ĐỐI KHÁNG 1V1", font=("Segoe UI", 10, "bold"), bg="#D69E2E", fg="black", activebackground="#B7791F", activeforeground="white", padx=12, pady=5, relief=tk.RAISED, command=self.start_versus_match)
        self.btn_run_versus.pack(side=tk.LEFT, padx=(0, 6))

        self.btn_open_v_replay = ttk.Button(row_btn, text="🌐 Mở Xem Replay Trực Tiếp", state=tk.DISABLED, command=self.open_current_replay)
        self.btn_open_v_replay.pack(side=tk.LEFT, padx=6)

        # Mode 2: Multi-Solver Arenas (Nhiều Solver cùng chơi 1 trận)
        box_multi = ttk.LabelFrame(frame, text="2. Chế Độ Nhiều Solver Cùng Chơi Một Trận (Multi-Solver Arena)", padding=10)
        box_multi.pack(fill=tk.X, pady=(0, 8))

        lbl_desc = ttk.Label(box_multi, text="Cho phép 4 hoặc toàn bộ 6 solver cùng lao vào 1 bản đồ tranh giành mì và gây tắc đường lẫn nhau:", font=("Segoe UI", 9))
        lbl_desc.pack(anchor=tk.W, pady=(0, 6))

        row_multi_btn = ttk.Frame(box_multi)
        row_multi_btn.pack(fill=tk.X)

        self.btn_run_4way = tk.Button(row_multi_btn, text="🥊 ĐẠI CHIẾN 4 SOLVER (ACO • ALNS • MLNS • Procon26)", font=("Segoe UI", 9, "bold"), bg="#805AD5", fg="white", activebackground="#6B46C1", activeforeground="white", padx=10, pady=5, relief=tk.RAISED, command=self.start_4way_match)
        self.btn_run_4way.pack(side=tk.LEFT, padx=(0, 6))

        self.btn_run_6way = tk.Button(row_multi_btn, text="🔥 BATTLE ROYALE 6 SOLVER (Tất cả solver)", font=("Segoe UI", 9, "bold"), bg="#DD6B20", fg="white", activebackground="#C05621", activeforeground="white", padx=10, pady=5, relief=tk.RAISED, command=self.start_6way_match)
        self.btn_run_6way.pack(side=tk.LEFT, padx=(0, 6))

        self.btn_run_champ = tk.Button(row_multi_btn, text="🏆 GIẢI ĐẤU VÒNG TRÒN (5 trận so găng)", font=("Segoe UI", 9, "bold"), bg="#319795", fg="white", activebackground="#285E61", activeforeground="white", padx=10, pady=5, relief=tk.RAISED, command=self.start_championship)
        self.btn_run_champ.pack(side=tk.LEFT, padx=(0, 6))

    def start_4way_match(self):
        self.btn_run_4way.config(state=tk.DISABLED)
        self.btn_open_v_replay.config(state=tk.DISABLED)
        threading.Thread(target=self._run_multi_worker, args=(["Team-ACO", "Team-ALNS", "Team-MLNS", "Procon26-Bot"],), daemon=True).start()

    def start_6way_match(self):
        self.btn_run_6way.config(state=tk.DISABLED)
        self.btn_open_v_replay.config(state=tk.DISABLED)
        threading.Thread(target=self._run_multi_worker, args=(["Team-ACO", "Team-ALNS", "Team-MLNS", "Procon26-Bot", "Team-LocalSearch", "Team-Greedy"],), daemon=True).start()

    def start_championship(self):
        self.btn_run_champ.config(state=tk.DISABLED)
        threading.Thread(target=self._run_champ_worker, daemon=True).start()

    def _run_multi_worker(self, team_names):
        try:
            self.log("=" * 75, "INFO")
            self.log(f"🔥 KHỞI TRANH ĐẠI CHIẾN {len(team_names)} SOLVER TRÊN CÙNG MỘT BẢN ĐỒ:", "INFO")
            for t in team_names:
                self.log(f"   🚩 {t}", "INFO")
            self.log("=" * 75, "INFO")

            self.api.login(DEFAULT_USER, DEFAULT_PASS)
            all_teams = self.api.get_teams()
            teams_map = {t["name"]: t for t in all_teams}

            with open(ROOT / "map_22x22.json", "r", encoding="utf-8") as f:
                map_config = json.load(f)

            map_config["players"] = len(team_names)
            map_config["startsAt"] = int(time.time()) + 90
            map_config["daySeconds"] = [60, 60, 60, 60]

            match_name = f"GUI-Multi-{len(team_names)}P-{int(time.time())}"
            new_m = self.api.create_match(match_name, map_config)
            m_id = new_m["match"]["id"]
            self.current_match_id = m_id
            self.current_match_url = f"https://{DEFAULT_HOST}/matches/{m_id}"
            self.log(f"Đã tạo trận đấu: {self.current_match_url}", "SUCCESS")
            self.btn_open_v_replay.config(state=tk.NORMAL)

            for tname in team_names:
                self.api.add_team(m_id, teams_map[tname]["id"])

            self.api.match_action(m_id, "start_agent_select")

            # Roles
            team_roles = {}
            for tname in team_names:
                pol = "aco_ls" if "ACO" in tname else ("alns" if "ALNS" in tname else ("mlns" if "MLNS" in tname else ("procon26" if "Procon26" in tname else ("local_search" if "Local" in tname else "greedy"))))
                roles = solve_roles(pol, map_config)
                team_roles[tname] = (roles, pol)
                self.api.submit_roles(m_id, teams_map[tname]["token"], roles)
                self.log(f"[{tname}]: Chọn vai trò {roles}", "INFO")

            self.api.match_action(m_id, "start")
            self.log("Trận đấu chính thức BẮT ĐẦU!", "SUCCESS")

            total_days = len(map_config.get("daySteps", []))
            for day_num in range(1, total_days + 1):
                day_idx = day_num - 1
                steps = map_config["daySteps"][day_idx]
                self.log(f"\n--- NGÀY {day_num}/{total_days} (Số bước: {steps}) ---", "INFO")

                statuses = {}
                for _ in range(25):
                    for tname in team_names:
                        try:
                            st = self.api.get_game_status(m_id, teams_map[tname]["token"])
                            if st.get("currentDay") == day_num:
                                statuses[tname] = st
                        except Exception:
                            pass
                    if len(statuses) == len(team_names):
                        break
                    time.sleep(0.5)

                first_st = list(statuses.values())[0] if statuses else {}
                traffics = first_st.get("traffics", [])

                for tname in team_names:
                    st = statuses.get(tname, {})
                    roles, pol = team_roles[tname]
                    raw_agents = st.get("agents", [])
                    built_agents = normalize_agents(st.get("agents", []), map_config.get("agents", []), roles, map_config.get("fuelLimits", 200))
                    road_cells = get_road_cells(map_config)
                    d_info = {"day": day_idx, "steps": steps, "agents": built_agents, "traffics": normalize_traffics(traffics, road_cells)}
                    t0 = time.time()
                    plan = solve_plan(pol, map_config, d_info, roles, day_num=day_num, raw_status=st)
                    elapsed = time.time() - t0
                    self.api.submit_actions(m_id, teams_map[tname]["token"], plan)
                    self.log(f"   + {tname:<16} nộp bài ({elapsed:.2f}s)", "SUCCESS")

                if day_num < total_days:
                    time.sleep(0.5)
                    try:
                        self.api.match_action(m_id, "next_day")
                    except Exception:
                        pass

            time.sleep(2.0)
            final_m = self.api.get_match(m_id)
            self.log("\n" + "=" * 75, "SUCCESS")
            self.log(f"🏁 BẢNG XẾP HẠNG ĐẠI CHIẾN {len(team_names)} SOLVER:", "SUCCESS")
            teams_sorted = sorted(final_m.get("teams", []), key=lambda x: (x.get("total_udon_servings", 0), x.get("total_udon_types", 0)), reverse=True)
            for idx, t in enumerate(teams_sorted, 1):
                self.log(f"   #{idx} {t.get('team_name'):<16}: {t.get('total_udon_servings')} bát mì | {t.get('total_udon_types')}/4 loại | {t.get('total_udon_daily_types')} daily", "SUCCESS")
            self.log(f"Xem Replay trên web: {self.current_match_url}", "INFO")
            self.log("=" * 75, "SUCCESS")

        except Exception as e:
            self.log(f"Lỗi trận đấu: {e}", "ERROR")
        finally:
            self.btn_run_4way.config(state=tk.NORMAL)
            self.btn_run_6way.config(state=tk.NORMAL)

    def _run_champ_worker(self):
        try:
            self.log("=" * 80, "INFO")
            self.log("🏆 BẮT ĐẦU CHẠY GIẢI ĐẤU VÒNG TRÒN ROUND-ROBIN (5 TRẬN 4-BOT)...", "INFO")
            self.log("Vui lòng theo dõi tiến trình trong vài phút...", "INFO")
            self.log("=" * 80, "INFO")
            
            p = subprocess.Popen([sys.executable, str(ROOT / "run_4way_tournament.py")], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, cwd=ROOT)
            for line in p.stdout:
                line_str = line.strip()
                if line_str:
                    if "QUÁN QUÂN" in line_str or "THẮNG" in line_str or "KẾT QUẢ" in line_str:
                        self.log(line_str, "SUCCESS")
                    elif "TRẬN" in line_str or "BẢNG" in line_str:
                        self.log(line_str, "INFO")
                    else:
                        self.log(line_str, "INFO")
            p.wait()
            self.log("🏆 Giải đấu vòng tròn hoàn tất!", "SUCCESS")
        except Exception as e:
            self.log(f"Lỗi giải đấu: {e}", "ERROR")
        finally:
            self.btn_run_champ.config(state=tk.NORMAL)

    def start_versus_match(self):
        t1_name = self.cbo_v_team1.get()
        p1 = SOLVERS[self.cbo_v_policy1.get()]
        t2_name = self.cbo_v_team2.get()
        p2 = SOLVERS[self.cbo_v_policy2.get()]

        if t1_name == t2_name:
            messagebox.showwarning("Chọn Trùng Đội", "Vui lòng chọn 2 đội khác nhau để đối kháng!")
            return

        self.btn_run_versus.config(state=tk.DISABLED)
        self.btn_open_v_replay.config(state=tk.DISABLED)
        threading.Thread(target=self._run_versus_worker, args=(t1_name, p1, t2_name, p2), daemon=True).start()

    def _run_versus_worker(self, t1_name, p1, t2_name, p2):
        try:
            self.log("=" * 70, "INFO")
            self.log(f"⚔️ KHỞI TRANH TRẬN ĐẤU ĐỐI KHÁNG: {t1_name} ({p1.upper()}) VS {t2_name} ({p2.upper()})", "INFO")
            self.log("=" * 70, "INFO")

            self.api.login(DEFAULT_USER, DEFAULT_PASS)
            teams_all = self.api.get_teams()
            t1_obj = next(t for t in teams_all if t["name"] == t1_name)
            t2_obj = next(t for t in teams_all if t["name"] == t2_name)

            with open(ROOT / "map_22x22.json", "r", encoding="utf-8") as f:
                map_config = json.load(f)

            map_config["players"] = 2
            map_config["startsAt"] = int(time.time()) + 90
            map_config["daySeconds"] = [60, 60, 60, 60]

            match_name = f"GUI-Duel-{p1}-vs-{p2}-{int(time.time())}"
            new_m = self.api.create_match(match_name, map_config)
            m_id = new_m["match"]["id"]
            self.current_match_id = m_id
            self.current_match_url = f"https://{DEFAULT_HOST}/matches/{m_id}"
            self.log(f"Đã tạo trận đấu: {self.current_match_url}", "SUCCESS")
            self.btn_open_v_replay.config(state=tk.NORMAL)

            self.api.add_team(m_id, t1_obj["id"])
            self.api.add_team(m_id, t2_obj["id"])
            self.api.match_action(m_id, "start_agent_select")

            # Chọn vai trò xe
            self.log("Cả 2 đội đang chọn vai trò xe...", "INFO")
            r1 = solve_roles(p1, map_config)
            r2 = solve_roles(p2, map_config)
            self.api.submit_roles(m_id, t1_obj["token"], r1)
            self.api.submit_roles(m_id, t2_obj["token"], r2)
            self.log(f"[{t1_name}]: {r1}  |  [{t2_name}]: {r2}", "INFO")

            self.api.match_action(m_id, "start")
            self.log("Trận đấu chính thức BẮT ĐẦU (start)!", "SUCCESS")

            total_days = len(map_config.get("daySteps", []))
            for day_num in range(1, total_days + 1):
                day_idx = day_num - 1
                steps = map_config["daySteps"][day_idx]
                self.log(f"\n--- NGÀY {day_num}/{total_days} (Số bước: {steps}) ---", "INFO")

                st1, st2 = None, None
                for _ in range(25):
                    try:
                        s1 = self.api.get_game_status(m_id, t1_obj["token"])
                        s2 = self.api.get_game_status(m_id, t2_obj["token"])
                        if s1.get("currentDay") == day_num and s2.get("currentDay") == day_num:
                            st1, st2 = s1, s2
                            break
                    except Exception:
                        pass
                    time.sleep(0.5)

                if not st1: st1 = self.api.get_game_status(m_id, t1_obj["token"])
                if not st2: st2 = self.api.get_game_status(m_id, t2_obj["token"])

                traffics = st1.get("traffics", [])

                road_cells = get_road_cells(map_config)
                norm_tr = normalize_traffics(traffics, road_cells)

                # Giải Đội 1
                d_info1 = {"day": day_idx, "steps": steps, "agents": normalize_agents(st1.get("agents", []), map_config.get("agents", []), r1, map_config.get("fuelLimits", 200)), "traffics": norm_tr}
                t0 = time.time()
                plan1 = solve_plan(p1, map_config, d_info1, r1, day_num=day_num, raw_status=st1)
                t_p1 = time.time() - t0
                self.api.submit_actions(m_id, t1_obj["token"], plan1)

                # Giải Đội 2
                d_info2 = {"day": day_idx, "steps": steps, "agents": normalize_agents(st2.get("agents", []), map_config.get("agents", []), r2, map_config.get("fuelLimits", 200)), "traffics": norm_tr}
                t0 = time.time()
                plan2 = solve_plan(p2, map_config, d_info2, r2, day_num=day_num, raw_status=st2)
                t_p2 = time.time() - t0
                self.api.submit_actions(m_id, t2_obj["token"], plan2)

                self.log(f"Nộp bài: {t1_name} ({t_p1:.2f}s) | {t2_name} ({t_p2:.2f}s)", "SUCCESS")

                if day_num < total_days:
                    time.sleep(0.5)
                    try:
                        self.api.match_action(m_id, "next_day")
                    except Exception:
                        pass

            # Kết quả chung cuộc
            time.sleep(2.0)
            final_m = self.api.get_match(m_id)
            self.log("\n" + "=" * 70, "SUCCESS")
            self.log("🏁 KẾT QUẢ TRẬN ĐẤU:", "SUCCESS")
            for t in final_m.get("teams", []):
                self.log(f"   🚩 {t.get('team_name'):<16}: {t.get('total_udon_servings')} bát mì | {t.get('total_udon_types')}/4 loại | {t.get('total_udon_daily_types')} daily", "SUCCESS")
            self.log(f"Xem replay: {self.current_match_url}", "INFO")
            self.log("=" * 70, "SUCCESS")

        except Exception as e:
            self.log(f"Lỗi đối kháng: {e}", "ERROR")
        finally:
            self.btn_run_versus.config(state=tk.NORMAL)

    # ==================== TAB 3 ====================
    def build_tab_info(self):
        frame = ttk.Frame(self.tab_info, padding=14)
        frame.pack(fill=tk.BOTH, expand=True)

        info_text = (
            "📌 BẢNG XẾP HẠNG & CHIẾN LƯỢC CÁC THUẬT TOÁN:\n\n"
            "1. 🚀 Auto-Race (Chạy đua ACO & ALNS song song) - [KHUYÊN DÙNG SỐ 1 CHO THI ĐẤU THẬT]\n"
            "   - Cơ chế: Đồng thời kích hoạt cả ACO và ALNS trong 2 luồng độc lập.\n"
            "   - Hệ thống tự động chấm điểm độc lập (check), so sánh số bát mì và loại mì, chọn ra phương án vượt trội để nộp lên Server.\n\n"
            "2. 🐜 ACO (Ant Colony Optimization + Local Search) - [VÔ ĐỊCH BẢN ĐỒ ĐÔNG XE]\n"
            "   - Cơ chế bầy kiến rải pheromone tìm đường phân tán, cực kỳ hiệu quả khi có nhiều bot cạnh tranh.\n"
            "   - Tốc độ siêu nhanh (~0.1s/ngày), năng suất kỷ lục 70 – 96 bát mì.\n\n"
            "3. ⚡ ALNS (Adaptive Large Neighborhood Search) - [VUA ỔN ĐỊNH BẢN ĐỒ VẮNG]\n"
            "   - Phá hủy và tái tạo chuỗi tuyến đường thích ứng, tối ưu hóa cung đường dài.\n"
            "   - Năng suất ổn định 62 – 90 bát mì, thời gian giải ~3-5s/ngày.\n\n"
            "----------------------------------------------------------------------------------------------------\n"
            "👥 CẨM NANG PHỐI HỢP CHIẾN THUẬT TEAM 2 NGƯỜI - 2 THIẾT BỊ TẠI PHÒNG THI:\n\n"
            "💻 THIẾT BỊ 1 (Laptop Trưởng Nhóm - MASTER):\n"
            "   • Cắm cáp mạng/wifi thi đấu, chạy file Chay_GUI.bat.\n"
            "   • Dán Token chính thức của đội, bấm '⚡ Kiểm Tra Kết Nối' trước giờ thi đấu 5 phút.\n"
            "   • Chọn Solver: 'Auto-Race' (hoặc ACO nếu phòng thi đông đội).\n"
            "   • Bấm '▶ TỰ ĐỘNG CẢ TRẬN' hoặc '🎯 GIẢI & NỘP 1 NGÀY' tùy theo hiệu lệnh trọng tài.\n\n"
            "💻 THIẾT BỊ 2 (Laptop Phân Tích & Dự Phòng - SHADOW / BACKUP):\n"
            "   • Cùng bật Chay_GUI.bat và nhập sẵn Token thi đấu.\n"
            "   • Bấm '🌐 Mở Xem Replay Trực Tiếp' để quan sát trực quan trên bản đồ web.\n"
            "   • Phân tích hướng di chuyển của xe đối thủ, phát hiện các nút giao tắc đường (traffics).\n"
            "   • Trường hợp khẩn cấp (Laptop 1 mất mạng, sập nguồn, treo máy): Laptop 2 lập tức bấm 'GIẢI & NỘP' để cứu điểm ngay tức khắc!\n\n"
            "🛡️ ĐẶC TÍNH SẴN SÀNG 100% OFFLINE:\n"
            "   • Toàn bộ GUI và bộ giải đều sử dụng thư viện chuẩn Python (không cần pip install, không cần internet ngoài).\n"
            "   • Hoàn toàn an toàn và hoạt động hoàn hảo trong phòng thi cách ly internet của ban tổ chức!"
        )
        lbl_info = scrolledtext.ScrolledText(frame, font=("Segoe UI", 10), wrap=tk.WORD, bg="#F7FAFC", relief=tk.SOLID, bd=1, padx=12, pady=12)
        lbl_info.insert(tk.END, info_text)
        lbl_info.config(state=tk.DISABLED)
        lbl_info.pack(fill=tk.BOTH, expand=True)

    def open_current_replay(self):
        if self.current_match_url:
            webbrowser.open(self.current_match_url)
        else:
            messagebox.showinfo("Chưa có trận", "Chưa có trận đấu nào được chọn!")

    def log(self, message: str, tag: str = "INFO"):
        self.log_queue.put((message, tag))

    def check_log_queue(self):
        while not self.log_queue.empty():
            msg, tag = self.log_queue.get_nowait()
            ts = time.strftime("[%H:%M:%S] ")
            self.txt_log.insert(tk.END, ts + msg + "\n", tag)
            self.txt_log.see(tk.END)
        self.after(100, self.check_log_queue)


if __name__ == "__main__":
    app = HexControlCenter()
    app.mainloop()
