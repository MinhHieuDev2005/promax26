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
import math
import os
import queue
import re
import ssl
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request
from urllib.parse import urlsplit
import webbrowser
import http.cookiejar
from http.client import HTTPException
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext, filedialog, simpledialog
from http_bot_proxy import BotProxy

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

ROOT = Path(__file__).resolve().parent
RUNNER_REGISTRY = ROOT / "solvers" / "registered.json"
CUSTOM_RUNNERS = {}
PROCON37_RUNNER = ROOT / "solvers" / "procon37kyogi_runner.py"
HYBRID_MASTER_RUNNER = ROOT / "build-hybrid-master" / "hybrid_master_runner.exe"
TARGET503_RUNNER = ROOT / "build-boundary-target503" / "boundary_joint_runner.exe"
HIEU_521_RUNNER = ROOT / "build-pro26-hieu" / "hexa_udon_hieu_runner_v2.exe"
BUILTIN_RUNNERS = {"procon37": PROCON37_RUNNER,
                   "hybrid_master": HYBRID_MASTER_RUNNER,
                   "target503": TARGET503_RUNNER,
                   "hieu_521": HIEU_521_RUNNER}

# Tự động tìm HEX_BINARY (ưu tiên bin/, sau đó build/)
if (ROOT / "bin" / "hexudon.exe").exists():
    HEX_BINARY = ROOT / "bin" / "hexudon.exe"
elif (ROOT / "build" / "hexudon.exe").exists():
    HEX_BINARY = ROOT / "build" / "hexudon.exe"
else:
    HEX_BINARY = ROOT / "bin" / "hexudon.exe"

if (ROOT / "solvers" / "runner.exe").is_file():
    PROCON26_RUNNER = ROOT / "solvers" / "runner.exe"
elif (ROOT / "bin" / "hexudon_runner.exe").exists():
    PROCON26_RUNNER = ROOT / "bin" / "hexudon_runner.exe"
elif (ROOT / "build" / "hexudon_runner.exe").exists():
    PROCON26_RUNNER = ROOT / "build" / "hexudon_runner.exe"
else:
    PROCON26_RUNNER = ROOT / "bin" / "hexudon_runner.exe"

DEFAULT_HOST = "procon26.haui.ac.vn"
DEFAULT_USER = "mhieu"
DEFAULT_PASS = "Hieu123456@@@"

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

# Danh sách solver hỗ trợ
SOLVERS = {
    "Auto-Race (Chạy đua ACO & ALNS - Khuyên dùng tối ưu)": "auto_race",
    "Auto-Race ALL (Chạy đua TẤT CẢ các Solver cùng lúc)": "auto_race_all",
    "ACO (Bầy kiến + LS - Tốc độ chớp nhoáng)": "aco_ls",
    
    "MLNS (Multi-Day LNS + DP Lookahead)": "mlns",
    "Runner EXE (Procon26 / solver thay thế)": "procon26",
    "Hybrid Japan LNS (Procon37 + SA/LNS)": "procon37",
    
    "Target 503+ C++20 (Boundary + Adaptive ALNS)": "target503",
    "Hieu 521 C++20 (Full 26/156 + LNS/SA)": "hieu_521",
    "LocalSearch (2-Opt / Relocate)": "local_search",
    
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

    def submit_roles(self, match_id, token, roles, log_fn=None):
        url = f"{self.base_url}/api/game/matches/{match_id}/agents"
        payload = json.dumps(roles).encode("utf-8")
        headers = {"Content-Type": "application/json", "x-api-token": token, "User-Agent": "hexudon-gui/1.0", "ngrok-skip-browser-warning": "true"}
        req = urllib.request.Request(url, data=payload, headers=headers)
        with urllib.request.urlopen(req, context=ctx, timeout=15) as resp:
            payload = resp.read().decode("utf-8")
            result = json.loads(payload) if payload.strip() else {}
            if log_fn:
                log_fn(f"[Xe] API nộp trả HTTP {resp.status}; đang kiểm tra vai trò thực tế.", "INFO")
            if isinstance(result, dict) and (result.get("ok") is False or result.get("success") is False):
                raise RuntimeError("API trả kết quả nộp vai trò không thành công.")
            return result

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

    # 1. Map cells 2D
    m = map_config.get("map", {})
    if isinstance(m, dict):
        W = m.get("width", 0)
        H = m.get("height", 0)
        cells = m.get("cells", [])
        if cells and not isinstance(cells[0], (list, tuple)) and W > 0 and H > 0:
            m["cells"] = [cells[row * W : (row + 1) * W] for row in range(H)]

    # 2. startsAt, daySeconds, daySteps
    if "startsAt" not in map_config or map_config["startsAt"] is None:
        map_config["startsAt"] = int(time.time())
    if "daySteps" not in map_config or not map_config["daySteps"]:
        map_config["daySteps"] = [100]
    num_days = len(map_config["daySteps"])
    if "daySeconds" not in map_config or not map_config["daySeconds"]:
        map_config["daySeconds"] = [45.0] * num_days
    elif len(map_config["daySeconds"]) < num_days:
        map_config["daySeconds"] = list(map_config["daySeconds"]) + [45.0] * (num_days - len(map_config["daySeconds"]))

    # 3. agents list of ints
    raw_agents = map_config.get("agents", [])
    clean_agents = []
    for a in raw_agents:
        if isinstance(a, dict):
            clean_agents.append(int(a.get("pos", 0)))
        elif isinstance(a, (int, float)):
            clean_agents.append(int(a))
    if not clean_agents:
        clean_agents = [0, 1, 2, 3]
    map_config["agents"] = clean_agents

    # 4. spots
    raw_spots = map_config.get("spots", [])
    clean_spots = []
    for idx, s in enumerate(raw_spots):
        if isinstance(s, dict):
            brand = int(s.get("brand", 0))
            pos = int(s.get("pos", 0))
            stocks = int(s.get("stocks", s.get("stock", 1)))
            clean_spots.append({"brand": brand, "pos": pos, "stocks": stocks})
        elif isinstance(s, (int, float)):
            clean_spots.append({"brand": 0, "pos": int(s), "stocks": 1})
    map_config["spots"] = clean_spots

    # 5. fuelLimits, players, busyThreshold, jammedThreshold
    if "fuelLimits" not in map_config:
        map_config["fuelLimits"] = int(map_config.get("fuel_limit", map_config.get("fuelLimit", 200)))
    if "players" not in map_config:
        map_config["players"] = 2
    if "busyThreshold" not in map_config:
        map_config["busyThreshold"] = 4
    if "jammedThreshold" not in map_config:
        map_config["jammedThreshold"] = 10

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


def build_procon26_payload(map_config, day_info, day_num, raw_status=None,
                           runner_context=None, time_limit_ms=None):
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
            
    payload = {
        "op": "plan",
        "config": map_config,
        "state": state,
        "stock": stock_list
    }
    if runner_context is not None:
        payload["history"] = runner_context.get("history", {
            "distinct_brands": [], "submitted_actions": [],
            "cumulative_daily_types": 0, "total_servings": 0,
        })
        planner_state = runner_context.get("planner_state")
        if planner_state is not None:
            payload["planner_state"] = planner_state
    if time_limit_ms is not None:
        requested = max(1, min(60000, int(time_limit_ms)))
        payload["search"] = {
            "timeLimitMs": requested,
            "randomSeed": 1,
            "sliceMs": 1000 if requested >= 20000 else 250,
            "attempts": 32 if requested >= 20000 else 6,
            "exhaustBudget": requested >= 20000,
        }
    return payload


def new_runner_context():
    return {
        "history": {
            "distinct_brands": [], "submitted_actions": [],
            "cumulative_daily_types": 0, "total_servings": 0,
        },
        "planner_state": None,
        "servings_by_day": [],
        "pending": None,
    }


def policy_uses_runner_context(policy):
    return policy == "procon26" or policy == "auto_race_all" or policy in BUILTIN_RUNNERS or policy in CUSTOM_RUNNERS


def read_server_day(status, default=None):
    """Read the one-based live day across API response naming variants."""
    if not isinstance(status, dict):
        return default
    for field in ("currentDay", "current_day", "current-day"):
        value = status.get(field)
        if type(value) is int and value >= 1:
            return value
        if isinstance(value, str) and value.isdigit() and int(value) >= 1:
            return int(value)
    return default


def infer_server_day(status, map_config, default=None):
    """Use cumulative daily-type score when the day field is missing/stale."""
    reported = read_server_day(status)
    brand_count = len({spot.get("brand") for spot in map_config.get("spots", [])
                       if isinstance(spot, dict) and "brand" in spot})
    total_days = len(map_config.get("daySteps", []))
    candidates = []
    stack = [status] if isinstance(status, dict) else []
    score_fields = {
        "cumulative_daily_types", "cumulativeDailyTypes",
        "total_udon_daily_types", "totalUdonDailyTypes",
    }
    while stack:
        item = stack.pop()
        for key, value in item.items():
            if key in score_fields and type(value) is int:
                candidates.append(value)
            elif isinstance(value, dict):
                stack.append(value)
    inferred = None
    for score in candidates:
        if brand_count and score >= 0 and score % brand_count == 0:
            day = score // brand_count + 1
            if not total_days or day <= total_days:
                inferred = max(inferred or 1, day)
    values = [value for value in (reported, inferred, default) if value is not None]
    return max(values) if values else None


def resume_runner_day(status, runner_context=None):
    # Server day is authoritative. Runner history must be reconciled to it,
    # never used to advance it: /answer revision is not a day counter.
    return read_server_day(status, 1)


def recover_runner_context(map_config, server_day):
    """Create neutral past entries when GUI restarts during an active match.

    The v2 runner treats these deliberately over-horizon entries as unavailable
    traffic history and continues from the authoritative current server state.
    """
    context = new_runner_context()
    past_days = max(0, int(server_day) - 1)
    agent_count = len(map_config.get("agents", []))
    day_steps = map_config.get("daySteps", [])
    placeholders = []
    for day in range(past_days):
        steps = int(day_steps[day]) if day < len(day_steps) else 1
        placeholders.append([[-(max(1, steps) + 1)] for _ in range(agent_count)])
    brands = sorted({int(spot["brand"]) for spot in map_config.get("spots", [])
                     if isinstance(spot, dict) and "brand" in spot})
    context["history"] = {
        "distinct_brands": brands if past_days else [],
        "submitted_actions": placeholders,
        "cumulative_daily_types": len(brands) * past_days,
        "total_servings": 0,
    }
    context["servings_by_day"] = [0] * past_days
    context["recovered"] = bool(past_days)
    return context


def commit_runner_day(runner_context, map_config, plan, planner_state, servings):
    """Commit a day only after /status advances beyond that day."""
    history = runner_context.setdefault("history", new_runner_context()["history"])
    history.setdefault("submitted_actions", []).append(plan)
    brands = sorted({int(spot["brand"]) for spot in map_config.get("spots", [])
                     if isinstance(spot, dict) and "brand" in spot})
    history["distinct_brands"] = brands
    history["cumulative_daily_types"] = len(brands) * len(history["submitted_actions"])
    history["total_servings"] = int(history.get("total_servings", 0)) + max(0, int(servings or 0))
    runner_context.setdefault("servings_by_day", []).append(max(0, int(servings or 0)))
    runner_context["planner_state"] = planner_state


def stage_runner_day(runner_context, day, plan, planner_state, servings):
    """Store/replace the accepted answer for the still-current server day."""
    runner_context["pending"] = {
        "day": int(day), "plan": plan, "planner_state": planner_state,
        "servings": max(0, int(servings or 0)),
    }


def reconcile_runner_context(runner_context, map_config, server_day):
    """Align history to authoritative one-based server day."""
    expected = max(0, int(server_day) - 1)
    history = runner_context.setdefault("history", new_runner_context()["history"])
    actions = history.setdefault("submitted_actions", [])
    servings = runner_context.setdefault("servings_by_day", [])
    pending = runner_context.get("pending")
    events = []
    if isinstance(pending, dict) and pending.get("day", 0) < server_day:
        if len(actions) == pending["day"] - 1:
            commit_runner_day(runner_context, map_config, pending["plan"],
                              pending.get("planner_state"), pending.get("servings", 0))
            actions = history["submitted_actions"]
            servings = runner_context["servings_by_day"]
            events.append(f"committed pending day {pending['day']}")
        runner_context["pending"] = None
    elif isinstance(pending, dict) and pending.get("day", 0) > server_day:
        runner_context["pending"] = None
        events.append("discarded future pending answer")
    if len(actions) > expected:
        del actions[expected:]
        del servings[expected:]
        runner_context["planner_state"] = None
        runner_context["pending"] = None
        events.append(f"trimmed polluted history to {expected} completed days")
    if len(actions) < expected:
        missing = expected - len(actions)
        agent_count = len(map_config.get("agents", []))
        day_steps = map_config.get("daySteps", [])
        for day in range(len(actions), expected):
            steps = int(day_steps[day]) if day < len(day_steps) else 1
            actions.append([[-(max(1, steps) + 1)] for _ in range(agent_count)])
            servings.append(0)
        runner_context["planner_state"] = None
        events.append(f"recovered {missing} past days with neutral traffic")
    brands = sorted({int(spot["brand"]) for spot in map_config.get("spots", [])
                     if isinstance(spot, dict) and "brand" in spot})
    history["distinct_brands"] = brands if expected else []
    history["cumulative_daily_types"] = len(brands) * expected
    history["total_servings"] = sum(servings[:expected])
    runner_context["servings_by_day"] = servings[:expected]
    return events


def read_custom_runners():
    if not RUNNER_REGISTRY.exists():
        return {}
    entries = json.loads(RUNNER_REGISTRY.read_text(encoding="utf-8"))
    if not isinstance(entries, dict) or any(
        not name.startswith(("EXE: ", "HTTP: ")) or not name.partition(": ")[2].strip()
        or not isinstance(filename, str) or "\x00" in filename
        or Path(filename).suffix.lower() not in (".exe", ".py")
        for name, filename in entries.items()
    ):
        raise ValueError("Danh sách solver phải chứa tên EXE: <tên> hoặc HTTP: <tên> và đường dẫn .exe/.py.")
    return {name: (ROOT / filename).resolve() for name, filename in entries.items()}


def register_runner(name, filename, transport="json"):
    if transport not in ("json", "http"):
        raise ValueError("Kiểu EXE phải là json hoặc http.")
    name = name.strip()
    if not name or len(name) > 100 or any(ord(character) < 32 for character in name):
        raise ValueError("Tên solver cần có 1–100 ký tự, không chứa ký tự điều khiển.")
    executable = Path(filename).resolve()
    suffix = executable.suffix.lower()
    if not executable.is_file() or suffix not in (".exe", ".py"):
        raise ValueError("Hãy chọn một file .exe hoặc .py tồn tại.")
    if transport == "http" and suffix != ".exe":
        raise ValueError("Bot HTTP phải là file .exe; file .py chỉ hỗ trợ Runner JSON.")
    label = f"{'HTTP' if transport == 'http' else 'EXE'}: {name}"
    previous_label = f"{'EXE' if transport == 'http' else 'HTTP'}: {name}"
    entries = read_custom_runners()
    entries.pop(previous_label, None)
    entries[label] = executable
    write_custom_runners(entries)
    CUSTOM_RUNNERS.pop(previous_label, None)
    SOLVERS.pop(previous_label, None)
    CUSTOM_RUNNERS.update(entries)
    SOLVERS.update({key: key for key in entries})
    return label

def write_custom_runners(entries):
    RUNNER_REGISTRY.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=RUNNER_REGISTRY.parent, delete=False) as stream:
            temporary = Path(stream.name)
            json.dump({key: str(value) for key, value in entries.items()}, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
        temporary.replace(RUNNER_REGISTRY)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)

def unregister_runner(label):
    if label not in CUSTOM_RUNNERS:
        raise ValueError("Chỉ có thể xóa solver EXE tự thêm, không xóa solver có sẵn.")
    entries = read_custom_runners()
    entries.pop(label, None)
    write_custom_runners(entries)
    CUSTOM_RUNNERS.pop(label)
    SOLVERS.pop(label, None)


def start_http_bot(executable, url, match_id, token):
    executable = executable.resolve()
    if not executable.is_file() or executable.suffix.lower() != ".exe":
        raise ValueError(f"Không tìm thấy bot .exe: {executable}")
    parsed = urlsplit(url)
    if parsed.scheme not in ("http", "https") or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("URL bot phải là địa chỉ HTTP/HTTPS, không chứa tài khoản/mật khẩu.")
    if any(not value.strip() or any(character in value for character in "\x00\r\n") for value in (url, match_id, token)):
        raise ValueError("URL, Match ID và Token phải có giá trị hợp lệ.")
    return subprocess.Popen(
        [str(executable), "-transport", "http", "-url", url, "-match", match_id, "-token", token],
        stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True, encoding="utf-8", errors="replace", bufsize=1, cwd=executable.parent,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )


def stop_http_bot(process):
    if process is None or process.poll() is not None:
        return
    if os.name == "nt":
        result = subprocess.run(
            ["taskkill", "/PID", str(process.pid), "/T", "/F"],
            capture_output=True, timeout=10, creationflags=subprocess.CREATE_NO_WINDOW,
        )
        if result.returncode != 0 and process.poll() is None:
            raise RuntimeError("Không dừng được cây tiến trình bot HTTP; hãy kiểm tra Task Manager.")
    else:
        process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)


def run_runner(payload, timeout, executable=None, return_response=False):
    executable = (executable if executable is not None else PROCON26_RUNNER).resolve()
    if not executable.is_file() or executable.suffix.lower() not in (".exe", ".py"):
        raise RuntimeError(f"Runner .exe/.py not found: {executable}. Select one in Kho Solver.")
    command = [sys.executable, str(executable)] if executable.suffix.lower() == ".py" else [str(executable)]
    try:
        result = subprocess.run(
            command, input=json.dumps(payload), text=True,
            encoding="utf-8", capture_output=True, timeout=timeout, cwd=executable.parent,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise RuntimeError(f"Cannot run {executable}: {exc}") from exc
    if result.returncode != 0:
        detail = result.stderr.strip()
        try:
            failed = json.loads(result.stdout)
            if isinstance(failed, dict) and failed.get("error"):
                detail = str(failed["error"])
        except (TypeError, ValueError):
            if not detail:
                detail = result.stdout.strip()
        raise RuntimeError(f"Runner exit code {result.returncode}: {detail[:1000] or 'no error detail'}")
    try:
        response = json.loads(result.stdout)
    except ValueError as exc:
        raise RuntimeError("Runner must output one JSON object on stdout; log to stderr.") from exc
    if not isinstance(response, dict) or response.get("ok") is not True:
        detail = response.get("error", "missing ok=true") if isinstance(response, dict) else "not an object"
        raise RuntimeError(f"Runner error: {detail}")
    field = "roles" if payload["op"] == "roles" else "plan"
    value = response.get(field)
    agents = payload["config"].get("agents", []) if field == "roles" else payload["state"]["agents"]
    if not isinstance(value, list) or len(value) != len(agents):
        raise RuntimeError(f"Runner {field} must contain {len(agents)} entries.")
    if field == "roles":
        if not value or any(type(role) is not int or role not in (0, 1) for role in value):
            raise RuntimeError("Runner roles must be integer 0/1.")
    elif any(not isinstance(route, list) or any(type(action) is not int for action in route) for route in value):
        raise RuntimeError("Runner plan must be an array of integer arrays.")
    return response if return_response else value


def validate_roles(roles, count):
    if not isinstance(roles, list) or len(roles) != count or not roles or any(type(role) is not int or role not in (0, 1) for role in roles):
        raise ValueError(f"Expected {count} agent roles containing only integer 0/1.")
    return list(roles)


def solve_roles(policy, map_config, cancelled=None, log_fn=None):
    if policy.startswith("HTTP: "):
        raise ValueError("HTTP Auto delegates role selection to the bot.")
    agents = map_config.get("agents")
    if not isinstance(agents, list) or not agents:
        raise ValueError("Role selection requires the actual match agents.")
    # ponytail: cap unknown selection windows at 5s; extend only with measured deadline-safe budgets.
    budget = 5.0
    advertised = map_config.get("agent_selection_time_limit")
    if advertised is not None:
        if isinstance(advertised, bool) or not math.isfinite(float(advertised)) or float(advertised) <= 0:
            raise ValueError("Invalid agent selection time limit.")
        budget = min(budget, float(advertised))
    starts_at = float(map_config.get("startsAt", 0))
    if not math.isfinite(starts_at):
        raise ValueError("Invalid match start time.")
    if starts_at > time.time():
        budget = min(budget, starts_at - time.time())
    budget = max(0.0, budget - 0.5)
    if budget < 0.1:
        raise RuntimeError("Not enough time to select and submit agent roles safely.")
    if cancelled and cancelled():
        raise RuntimeError("Role selection cancelled.")
    if policy == "procon26" or policy in BUILTIN_RUNNERS or policy in CUSTOM_RUNNERS:
        if log_fn:
            log_fn(f"JSON runner role selector: {policy}; timeout={budget:.2f}s.", "INFO")
        roles = run_runner({"op": "roles", "config": map_config,
                            "search": {"timeLimitMs": int(budget * 900)}}, timeout=budget,
                           executable=BUILTIN_RUNNERS.get(policy, CUSTOM_RUNNERS.get(policy)))
        return validate_roles(roles, len(agents))
    if policy.startswith("auto"):
        policy = "alns"
    if log_fn:
        log_fn(f"Native role selector: {policy}; budget={budget:.2f}s (independent of day budget).", "INFO")
    payload = {"config": map_config, "search": {"timeLimitMs": int(budget * 900)}}
    with subprocess.Popen([str(HEX_BINARY), "select", policy], stdin=subprocess.PIPE,
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                          encoding="utf-8", cwd=ROOT) as process:
        deadline = time.monotonic() + budget
        pending = json.dumps(payload)
        timed_out = False
        while True:
            try:
                output, errors = process.communicate(pending, timeout=0.05)
                break
            except subprocess.TimeoutExpired:
                pending = None
                if (cancelled and cancelled()) or time.monotonic() >= deadline:
                    timed_out = True
                    process.kill()
                    output, errors = process.communicate()
                    if cancelled and cancelled():
                        raise RuntimeError("Role selection cancelled.")
                    break
        if process.returncode != 0 and not timed_out:
            raise RuntimeError(f"Selector exited {process.returncode}: {errors[:500]}")
        incumbent = None
        for line in output.splitlines():
            try:
                result = json.loads(line)
                incumbent = validate_roles(result.get("types"), len(agents))
                if log_fn:
                    log_fn(f"Role candidate: {incumbent}; phase={result.get('phase')}; score={result.get('score')}", "INFO")
            except (ValueError, AttributeError):
                continue
        if incumbent is None:
            raise RuntimeError(f"Selector returned no valid roles: {errors[:500]}")
        return incumbent


def confirmed_roles(status, count):
    agents = status.get("agents", [])
    if not agents:
        return None
    return validate_roles([agent.get("kind") for agent in agents], count)


def reconcile_roles(api, match_id, token, config, policy, proposed, cancelled, log, confirmation_timeout=30):
    count = len(config.get("agents", []))
    status = api.get_game_status(match_id, token)
    if status.get("finished") or status.get("status") == "finished":
        raise RuntimeError("Match is finished; refusing role submission.")
    existing = confirmed_roles(status, count)
    if existing is not None:
        log(f"[Xe] SERVER ĐÃ XÁC NHẬN: {existing}; giữ vai trò đã có trên server.", "SUCCESS")
        return existing
    roles = solve_roles(policy, config, cancelled, log) if proposed is None else validate_roles(proposed, count)
    log(f"[Xe] ĐÃ CHỌN ({'solver' if proposed is None else 'thủ công'}): {roles}; chưa nộp.", "INFO")
    if cancelled():
        raise RuntimeError("Role submission cancelled.")
    try:
        api.submit_roles(match_id, token, roles, log_fn=log)
    except Exception:
        existing = confirmed_roles(api.get_game_status(match_id, token), count)
        if existing is None:
            raise
        log(f"[Xe] SERVER ĐÃ XÁC NHẬN sau xung đột: {existing}; dùng vai trò thực tế.", "WARN")
        return existing
    log(f"[Xe] ĐÃ GỬI: {roles} — CHỜ XÁC NHẬN từ /status, tối đa {confirmation_timeout}s; không nộp lại.", "INFO")
    deadline = time.monotonic() + confirmation_timeout
    while True:
        if cancelled():
            raise RuntimeError("Đã dừng chờ xác nhận; yêu cầu đã gửi không bị hủy trên server.")
        try:
            status = api.get_game_status(match_id, token)
        except (OSError, HTTPException):
            log("[Xe] Chưa đọc được /status; tiếp tục chờ, không nộp lại.", "WARN")
        else:
            existing = confirmed_roles(status, count)
            if existing is not None:
                if existing != roles:
                    log(f"[Xe] Vai trò server {existing} khác đề xuất {roles}; dùng vai trò server.", "WARN")
                log(f"[Xe] SERVER ĐÃ XÁC NHẬN: {existing} (Server-confirmed roles).", "SUCCESS")
                return existing
            if status.get("finished") or status.get("status") == "finished":
                raise RuntimeError("Trận đã kết thúc nhưng chưa xác nhận được vai trò xe.")
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError("Đã gửi vai trò nhưng chưa xác nhận được từ /status. Không đồng nghĩa bị từ chối; chưa chạy kế hoạch, không tự nộp lại.")
        time.sleep(min(1.0, remaining))

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


def solve_auto_race(map_config, day_info, roles, time_limit_ms=3000, log_fn=None, include_all=False, day_num=1, raw_status=None, day_budget_sec=None, runner_context=None):
    """Chạy song song các solver, đo điểm số thực tế bằng check và nộp phương án cao điểm nhất."""
    normalize_map_config(map_config)
    brand_count = len({spot.get("brand") for spot in map_config.get("spots", [])
                       if isinstance(spot, dict) and "brand" in spot})
    if day_budget_sec and day_budget_sec > 0:
        cand_timeout = max(2, int(day_budget_sec - 2))
    else:
        cand_timeout = max(15, int(time_limit_ms / 1000) + 8)

    def run_candidate(pol):
        t0 = time.time()
        try:
            if pol == "procon26" or pol in CUSTOM_RUNNERS:
                candidate_context = None
                if runner_context is not None:
                    candidate_context = {"history": runner_context["history"]}
                    saved = runner_context.get("planner_state")
                    if isinstance(saved, dict) and saved.get("candidate") == pol:
                        candidate_context["planner_state"] = saved.get("state")
                payload = build_procon26_payload(
                    map_config, day_info, day_num, raw_status,
                    candidate_context, time_limit_ms,
                )
                for _attempt in range(3):
                    try:
                        response = run_runner(
                            payload, timeout=cand_timeout,
                            executable=CUSTOM_RUNNERS.get(pol), return_response=True,
                        )
                        break
                    except RuntimeError as exc:
                        detail = str(exc)
                        limit = re.search(r"timeLimitMs must be 1\.\.(\d+)", detail)
                        if limit and payload.get("search", {}).get("timeLimitMs", 0) > int(limit.group(1)):
                            payload["search"]["timeLimitMs"] = int(limit.group(1))
                            if log_fn:
                                log_fn(f"  {pol}: giới hạn nội bộ {limit.group(1)}ms; tự giảm riêng runner này.", "WARN")
                            continue
                        if "history cannot replay" in detail and "history" in payload:
                            payload.pop("history", None)
                            payload.pop("planner_state", None)
                            if log_fn:
                                log_fn(f"  {pol}: artifact cũ không replay được lịch sử; chạy lại từ state hiện tại.", "WARN")
                            continue
                        raise
                else:
                    raise RuntimeError("Runner compatibility retry exhausted")
                plan = response["plan"]
            else:
                search_cfg = {"timeLimitMs": time_limit_ms, "time_limit_ms": time_limit_ms}
                if pol == "mlns":
                    search_cfg["mlnsLookaheadDays"] = 2
                p = subprocess.run(
                    [str(HEX_BINARY), "plan", pol],
                    input=json.dumps({"config": map_config, "day_info": day_info, "types": roles, "search": search_cfg}),
                    text=True,
                    capture_output=True,
                    timeout=cand_timeout,
                    cwd=ROOT
                )
                if p.returncode != 0:
                    return pol, None, {"valid": False, "servings": -1, "error": p.stderr.strip()}, time.time() - t0, None
                plan = json.loads(p.stdout)

            el = time.time() - t0
            score = check_plan_score(map_config, day_info, plan)
            planner_state = response.get("planner_state") if pol == "procon26" or pol in CUSTOM_RUNNERS else None
            return pol, plan, score, el, planner_state
        except Exception as exc:
            return pol, None, {"valid": False, "servings": -1, "error": str(exc)}, time.time() - t0, None

    if include_all:
        candidates = ["aco_ls", "alns", "procon26", "local_search", "greedy", *(name for name in CUSTOM_RUNNERS if not name.startswith("HTTP: "))]
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

    for pol, plan, sc, el, _planner_state in results:
        pol_name = name_map.get(pol, pol)
        if sc.get("valid"):
            if log_fn:
                log_fn(f"  🏎️ {pol_name:<11}: {sc.get('servings', 0)} bát mì | {sc.get('distinct_types', 0)}/{brand_count} loại ({el:.2f}s)", "INFO")
        else:
            if log_fn:
                detail = sc.get("error") or "Kế hoạch không hợp lệ"
                log_fn(f"  ❌ {pol_name:<11}: {detail} ({el:.2f}s)", "WARN")

    valid_results = [r for r in results if r[1] is not None and r[2].get("valid", False)]
    if valid_results:
        winner = max(valid_results, key=lambda x: (x[2].get("daily_types", 0), x[2].get("servings", 0), -x[3]))
        if runner_context is not None:
            runner_context["pending_planner_state"] = {
                "candidate": winner[0], "state": winner[4],
            }
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


def solve_plan(policy, map_config, day_info, roles, day_num=1, raw_status=None,
               time_limit_ms=3000, log_fn=None, day_budget_sec=None,
               runner_context=None):
    if policy.startswith("HTTP: "):
        raise ValueError("Bot HTTP tự giải và nộp bài; không dùng được như runner JSON.")
    normalize_map_config(map_config)
    if policy == "procon26" or policy in BUILTIN_RUNNERS or policy in CUSTOM_RUNNERS:
        payload = build_procon26_payload(map_config, day_info, day_num, raw_status,
                                         runner_context, time_limit_ms)
        pr_timeout = max(2, int(day_budget_sec - 2)) if (day_budget_sec and day_budget_sec > 0) else 30
        response = run_runner(payload, timeout=pr_timeout,
                              executable=BUILTIN_RUNNERS.get(policy, CUSTOM_RUNNERS.get(policy)),
                              return_response=True)
        diagnostics = response.get("diagnostics")
        if log_fn and isinstance(diagnostics, dict):
            projected = diagnostics.get("projected_final")
            log_fn(
                "Runner diagnostics: "
                f"elapsed={diagnostics.get('elapsed_ms', '?')}ms, "
                f"expansions={diagnostics.get('expansions', '?')}, "
                f"evaluated={diagnostics.get('evaluated', '?')}, "
                f"bound_prunes={diagnostics.get('safe_bound_prunes', '?')}, "
                f"projected={projected}.",
                "INFO",
            )
        if runner_context is not None:
            runner_context["pending_planner_state"] = response.get("planner_state")
        return response["plan"]

    if policy == "auto_race":
        return solve_auto_race(map_config, day_info, roles, time_limit_ms=time_limit_ms, log_fn=log_fn, include_all=False, day_num=day_num, raw_status=raw_status, day_budget_sec=day_budget_sec)

    if policy == "auto_race_all":
        return solve_auto_race(map_config, day_info, roles, time_limit_ms=time_limit_ms, log_fn=log_fn, include_all=True, day_num=day_num, raw_status=raw_status, day_budget_sec=day_budget_sec, runner_context=runner_context)

    # Standard hex policy
    if day_budget_sec and day_budget_sec > 0:
        sub_timeout = max(2, int(day_budget_sec - 2))
    else:
        sub_timeout = max(35, int(time_limit_ms / 1000) + 25)

    search_cfg = {"timeLimitMs": time_limit_ms, "time_limit_ms": time_limit_ms}
    if policy == "mlns":
        search_cfg["mlnsLookaheadDays"] = 2
    try:
        p = subprocess.run(
            [str(HEX_BINARY), "plan", policy],
            input=json.dumps({"config": map_config, "day_info": day_info, "types": roles, "search": search_cfg}),
            text=True,
            capture_output=True,
            timeout=sub_timeout,
            cwd=ROOT
        )
        if p.returncode == 0 and p.stdout.strip():
            plan = json.loads(p.stdout)
            sc = check_plan_score(map_config, day_info, plan)
            if sc.get("valid") and log_fn:
                log_fn(f"  📊 Kế hoạch: {sc.get('servings', 0)} bát mì | {sc.get('distinct_types', 0)}/4 loại mì", "INFO")
            return plan
        else:
            if log_fn:
                log_fn(f"Solver {policy} kết thúc với mã lỗi ({p.returncode}), kích hoạt Greedy cứu nguy khẩn cấp...", "WARN")
    except subprocess.TimeoutExpired:
        if log_fn:
            log_fn(f"⚠️ Solver {policy} chạy quá {sub_timeout}s (Timeout), kích hoạt Greedy cứu nguy khẩn cấp...", "WARN")
    except Exception as e_run:
        if log_fn:
            log_fn(f"⚠️ Solver {policy} gặp lỗi ({e_run}), kích hoạt Greedy cứu nguy khẩn cấp...", "WARN")

    # Greedy Fallback cứu sinh
    try:
        p_fb = subprocess.run(
            [str(HEX_BINARY), "plan", "greedy"],
            input=json.dumps({"config": map_config, "day_info": day_info, "types": roles, "search": {"time_limit_ms": 1000}}),
            text=True,
            capture_output=True,
            timeout=10,
            cwd=ROOT
        )
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


class HexControlCenter(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("HEXUDON PROCON 2026 - Control Center & Strategy Bot")
        self.geometry("1420x820")
        self.minsize(1100, 680)
        
        self.api = HauiAPI()
        self.is_running = False
        self.http_process = None
        self.http_proxy = None
        self.http_ready = threading.Event()
        self.http_results = queue.Queue()
        self.current_match_id = None
        self.current_match_url = None
        self.stop_requested = False
        self.log_queue = queue.Queue()
        self.role_mode = "manual"
        self.role_results = queue.Queue()
        self.cached_map_config = None
        self.current_roles = [1, 0, 0, 0, 0, 0]
        # Continuity for stateless JSON runner processes. Step mode may invoke
        # a fresh process per day, but v2 still needs accepted history/state.
        self.runner_sessions = {}

        try:
            CUSTOM_RUNNERS.update(read_custom_runners())
            SOLVERS.update({name: name for name in CUSTOM_RUNNERS})
        except (OSError, ValueError) as exc:
            messagebox.showerror("Danh sách solver", f"Không đọc được {RUNNER_REGISTRY}: {exc}", parent=self)

        self.setup_styles()
        self.build_ui()
        self.protocol("WM_DELETE_WINDOW", self.close_gui)
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
        solver_buttons = ttk.Frame(row2)
        solver_buttons.grid(row=1, column=4, padx=4, pady=4)
        ttk.Button(solver_buttons, text="+ Thêm solver EXE", command=self.add_runner).pack(side=tk.LEFT)
        ttk.Button(solver_buttons, text="Xóa solver", command=self.delete_runner).pack(side=tk.LEFT, padx=(4, 0))

        ttk.Label(row2, text="Thời gian giải/ngày:").grid(row=2, column=0, sticky=tk.W, padx=4, pady=4)
        self.cbo_timelimit = ttk.Combobox(row2, values=[
            "1500ms (1.5s - Tối ưu tốc độ)",
            "3000ms (3.0s - Tiêu chuẩn)",
            "5000ms (5.0s - Chuyên sâu)",
            "8000ms (8.0s - Cực sâu)",
            "20000ms (20s - Chokudai)",
            "40000ms (40s - Chokudai sâu)",
            "60000ms (60s - Tối đa)",
        ], width=30, state="readonly")
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
                "1 Xe Tiếp Xăng (Xe 1 ⛽) + Còn lại Tuần Tra (🏎️) [Map nhỏ/vừa]",
                "2 Xe Tiếp Xăng (Xe 1, 2 ⛽) + Còn lại Tuần Tra (🏎️) [Khuyên dùng map lớn]",
                "🤖 Tự động tối ưu bằng Solver & Bản đồ",
                "✏️ Tùy chỉnh thủ công từng xe bên dưới"
            ],
            width=50,
            state="readonly"
        )
        self.cbo_role_preset.grid(row=0, column=1, columnspan=4, sticky=tk.W, padx=4, pady=4)
        self.cbo_role_preset.current(0)
        self.cbo_role_preset.bind("<<ComboboxSelected>>", self.on_role_preset_changed)

        btn_send_roles = ttk.Button(row_roles, text="📤 Nộp Vai Trò Xe Ngay", command=self.submit_roles_now)
        btn_send_roles.grid(row=0, column=5, padx=8, pady=4)

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
        if self.is_running:
            return
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
        """Cập nhật giao diện chọn vai trò xe co giãn theo đúng số xe thực tế của map, bảo toàn cấu hình người dùng."""
        if hasattr(self, "agent_role_combos") and len(self.agent_role_combos) == num_agents and hasattr(self, "current_roles") and len(self.current_roles) == num_agents:
            return

        # Giữ lại cấu hình vai trò hiện tại nếu có
        auto_roles = getattr(self, "role_mode", "manual") == "auto"
        old_roles = getattr(self, "current_roles", [1] + [0] * max(0, num_agents - 1))
        if len(old_roles) < num_agents:
            roles = list(old_roles) + [0] * (num_agents - len(old_roles))
        else:
            roles = list(old_roles[:num_agents])
        self.current_roles = roles

        for w in self.frame_agents.winfo_children():
            w.destroy()
        self.agent_role_combos.clear()

        # Cập nhật danh sách preset theo số xe thực tế
        p1 = f"1 Xe Tiếp Xăng (Xe 1 ⛽) + {max(0, num_agents - 1)} Xe Tuần Tra (🏎️) [Map nhỏ/vừa]"
        p2 = f"2 Xe Tiếp Xăng (Xe 1, 2 ⛽) + {max(0, num_agents - 2)} Xe Tuần Tra (🏎️) [Khuyên dùng map lớn]" if num_agents >= 3 else "2 Xe Tiếp Xăng (Xe 1, 2 ⛽)"
        p_auto = f"🤖 Tự động tối ưu bằng Solver ({num_agents} xe)"
        p_custom = "✏️ Tùy chỉnh thủ công từng xe bên dưới"
        self.cbo_role_preset["values"] = [p1, p2, p_auto, p_custom]

        for i in range(num_agents):
            r = i // 4
            c = (i % 4) * 2
            lbl = ttk.Label(self.frame_agents, text=f"Xe {i+1}:", font=("Segoe UI", 9, "bold"))
            lbl.grid(row=r, column=c, sticky=tk.W, padx=(8 if (i % 4) > 0 else 0, 2), pady=3)
            cbo = ttk.Combobox(self.frame_agents, values=["🏎️ Tuần tra (0)", "⛽ Tiếp xăng (1)"], width=13, state="readonly")
            cbo.current(1 if roles[i] == 1 else 0)
            cbo.bind("<<ComboboxSelected>>", self.on_agent_role_changed)
            cbo.grid(row=r, column=c + 1, sticky=tk.W, padx=(0, 6), pady=3)
            self.agent_role_combos.append(cbo)

        # Cập nhật trạng thái hiển thị của preset combobox
        if auto_roles:
            self.cbo_role_preset.current(2)
        elif roles == [1] + [0] * (num_agents - 1):
            self.cbo_role_preset.current(0)
        elif num_agents >= 2 and roles == [1, 1] + [0] * (num_agents - 2):
            self.cbo_role_preset.current(1)
        else:
            self.cbo_role_preset.set(f"✏️ Tùy chỉnh: {roles.count(1)} xe xăng ⛽, {roles.count(0)} xe tuần tra 🏎️")

    def on_role_preset_changed(self, event=None):
        if self.is_running:
            self.log("Bot HTTP đang chạy trong trận; không thể thay đổi vai trò xe lúc này.", "WARN")
            return
        idx = self.cbo_role_preset.current()
        self.role_mode = "auto" if idx == 2 else "manual"
        num_agents = len(self.agent_role_combos)
        if num_agents <= 0:
            return
        if idx == 0:  # 1 Refuel (Xe 1) + còn lại Patrol
            roles = [1] + [0] * (num_agents - 1)
            for i in range(num_agents):
                self.agent_role_combos[i].current(1 if i == 0 else 0)
            self.current_roles = roles
            self.log(f"Đã chọn: 1 xe tiếp xăng ⛽ (Xe 1), {max(0, num_agents - 1)} xe tuần tra 🏎️", "INFO")
        elif idx == 1:  # 2 Refuel (Xe 1, 2) + còn lại Patrol
            roles = [1 if (i in [0, 1] and num_agents > 1) else 0 for i in range(num_agents)]
            for i in range(num_agents):
                self.agent_role_combos[i].current(1 if (i in [0, 1] and num_agents > 1) else 0)
            self.current_roles = roles
            self.log(f"Đã chọn: 2 xe tiếp xăng ⛽ (Xe 1, 2), {max(0, num_agents - 2)} xe tuần tra 🏎️", "INFO")
        elif idx == 2:
            self.log("Auto: roles will be computed from fresh server config when starting/submitting; HTTP delegates to bot.", "INFO")
        elif idx == 3:  # Tùy chỉnh thủ công
            self.log("✏️ Chế độ tùy chỉnh: Hãy chọn vai trò cho từng xe ở các ô bên dưới.", "INFO")

    def on_agent_role_changed(self, event=None):
        if self.is_running:
            return
        self.role_mode = "manual"
        roles = []
        for cbo in self.agent_role_combos:
            val = cbo.get()
            roles.append(1 if "Tiếp xăng" in val or "(1)" in val else 0)
        self.current_roles = roles
        refuels = roles.count(1)
        patrols = roles.count(0)
        self.cbo_role_preset.set(f"✏️ Tùy chỉnh: {refuels} xe xăng ⛽, {patrols} xe tuần tra 🏎️")
        self.log(f"✏️ Đã chỉnh thủ công: {roles} ({refuels} xe tiếp xăng ⛽, {patrols} xe tuần tra 🏎️)", "INFO")

    def get_selected_roles(self, map_config=None, policy=None):
        num_agents = 0
        if map_config and "agents" in map_config:
            num_agents = len(map_config["agents"])
        elif hasattr(self, "agent_role_combos"):
            num_agents = len(self.agent_role_combos)
        if num_agents <= 0:
            num_agents = 4

        roles = []
        if hasattr(self, "agent_role_combos") and self.agent_role_combos:
            for cbo in self.agent_role_combos:
                val = cbo.get()
                roles.append(1 if "Tiếp xăng" in val or "(1)" in val else 0)
        elif hasattr(self, "current_roles") and self.current_roles:
            roles = list(self.current_roles)

        roles = validate_roles(roles, num_agents)

        self.current_roles = roles
        return roles

    def load_match_info(self, match_id=None):
        """Tải thông tin chi tiết của trận đấu từ server và tự động cập nhật GUI động."""
        if self.is_running:
            return None
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
            self.cached_map_config = map_config
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
        if self.is_running:
            return
        policy = SOLVERS[self.cbo_solver.get()]
        auto = getattr(self, "role_mode", "manual") == "auto"
        if auto and policy.startswith("HTTP: "):
            self.log("HTTP Auto: start the bot to let it choose roles; no manual submission.", "WARN")
            return
        token = self.ent_token.get().strip()
        match_id = self.ent_match_id.get().strip()
        if not token or not match_id:
            messagebox.showwarning("Missing credentials", "Match ID and token are required.")
            return
        self.api.set_host(self.ent_host.get().strip())
        roles = None if auto else list(self.get_selected_roles())
        self.is_running = True
        self.stop_requested = False
        def worker():
            try:
                config = self.api.get_game_config(match_id, token)
                actual = reconcile_roles(self.api, match_id, token, config, policy, roles,
                                         lambda: self.stop_requested, self.log)
                self.role_results.put(actual)
            except TimeoutError as exc:
                self.log(f"[Xe] CHƯA XÁC NHẬN: {exc}", "WARN")
            except Exception as exc:
                self.log(f"Role submission failed: {exc}", "ERROR")
            finally:
                self.is_running = False
        threading.Thread(target=worker, daemon=True).start()

    def fetch_latest_match(self):
        if self.is_running:
            return
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
        if self.is_running:
            return
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
        if not self.runner_changes_allowed():
            return
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

        if getattr(self, "role_mode", "manual") == "auto":
            selected_roles = None
        else:
            selected_roles = list(self.get_selected_roles())

        if policy.startswith("HTTP: "):
            if mode != "auto":
                messagebox.showinfo("Bot HTTP", "Bot HTTP chỉ hỗ trợ TỰ ĐỘNG CẢ TRẬN, không hỗ trợ giải riêng một ngày.", parent=self)
                return

        self.is_running = True
        self.stop_requested = False
        self.btn_start.config(state=tk.DISABLED)
        self.btn_step.config(state=tk.DISABLED)
        self.btn_stop.config(state=tk.NORMAL)
        self.btn_replay.config(state=tk.NORMAL)
        self.current_match_id = match_id
        self.current_match_url = f"{self.api.base_url}/matches/{match_id}"

        if policy.startswith("HTTP: "):
            self.lbl_status_day.config(text="Trạng thái: Đang kiểm tra API qua proxy")
            self.http_ready.clear()
            self.lbl_status_score.config(text="Điểm số: xem log bot hoặc replay")
            self.log(f"▶ {policy} | URL: {self.api.base_url} | Match: {match_id}", "INFO")
            if selected_roles:
                self.log(f"Cấu hình vai trò xe áp dụng từ GUI: {selected_roles}", "INFO")
            else:
                self.log("Vai trò xe: Tự động phân tích và chọn bởi Bot", "INFO")
            self.log("Proxy kiểm tra kết nối rồi chuyển API bot sang API HAUI; giới hạn ms/ngày không áp dụng.", "INFO")
            threading.Thread(target=self._run_http_session, args=(CUSTOM_RUNNERS[policy], self.api.base_url, match_id, token, selected_roles), daemon=True).start()
            return

        threading.Thread(target=self._run_live_worker, args=(match_id, token, policy, time_limit_ms, mode, selected_roles), daemon=True).start()

    def stop_match(self):
        self.stop_requested = True
        try:
            stop_http_bot(self.http_process)
            if self.http_proxy is not None:
                self.http_proxy.close()
        except (OSError, RuntimeError, subprocess.TimeoutExpired) as exc:
            self.log(f"Lỗi dừng bot HTTP: {exc}", "ERROR")
            return
        self.log("Đã yêu cầu DỪNG bot thi đấu.", "WARN")

    def _run_http_session(self, executable, url, match_id, token, custom_roles=None):
        proxy = None
        process = None
        returncode = -1
        try:
            ca_file = executable.parent / "windows-roots.pem"
            proxy = BotProxy(url, match_id, token, self.log, ca_file=ca_file if ca_file.is_file() else None, custom_roles=custom_roles)
            self.http_proxy = proxy
            if self.stop_requested:
                return
            proxy.check_connection()
            if self.stop_requested:
                return
            process = start_http_bot(executable, proxy.url, match_id, proxy.local_token)
            self.http_process = process
            self.http_ready.set()
            if self.stop_requested:
                stop_http_bot(self.http_process)
            self.log("Bot đã khởi chạy qua proxy cục bộ; theo dõi các dòng [Proxy] để biết yêu cầu thực tế.", "INFO")
            returncode = self._read_http_output(self.http_process, token, proxy.local_token)
        except (OSError, ValueError, RuntimeError, HTTPException, subprocess.TimeoutExpired) as exc:
            message = f"Không chạy được phiên Bot HTTP: {exc}".replace(token, "[TOKEN]")
            if proxy is not None:
                message = message.replace(proxy.local_token, "[LOCAL TOKEN]")
            self.log(message, "ERROR")
        finally:
            if process is not None and process.poll() is None:
                try:
                    stop_http_bot(process)
                except (OSError, RuntimeError, subprocess.TimeoutExpired) as exc:
                    self.log(f"Chưa dừng được bot HTTP; hãy bấm DỪNG hoặc kiểm tra Task Manager: {exc}", "ERROR")
                returncode = process.wait()
            if proxy is not None:
                proxy.close()
            self.http_results.put(returncode)

    def _read_http_output(self, process, token, local_token=""):
        try:
            with process.stdout:
                for line in process.stdout:
                    message = line.rstrip().replace(token, "[TOKEN]")
                    if local_token:
                        message = message.replace(local_token, "[LOCAL TOKEN]")
                    self.log(message, "INFO")
        except (OSError, ValueError) as exc:
            message = f"Lỗi đọc log bot HTTP: {exc}".replace(token, "[TOKEN]")
            if local_token:
                message = message.replace(local_token, "[LOCAL TOKEN]")
            self.log(message, "ERROR")
        finally:
            returncode = process.wait()
        return returncode

    def close_gui(self):
        self.stop_requested = True
        try:
            stop_http_bot(self.http_process)
            if self.http_proxy is not None:
                self.http_proxy.close()
        except (OSError, RuntimeError, subprocess.TimeoutExpired) as exc:
            messagebox.showerror("Không đóng được bot HTTP", str(exc), parent=self)
            return
        self.destroy()

    def _run_live_worker(self, match_id, token, policy, time_limit_ms, mode="auto", user_roles=None):
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
                    raise RuntimeError("Cannot load actual match config; refusing local-map fallback.")

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
            reported_day = infer_server_day(status, map_config)
            existing_context = None
            if policy_uses_runner_context(policy):
                session_key = (str(match_id), str(policy))
                existing_context = self.runner_sessions.get(session_key)
                if existing_context is None and reported_day and reported_day > 1:
                    existing_context = recover_runner_context(map_config, reported_day)
                    self.runner_sessions[session_key] = existing_context
                    self.log(
                        f"Khôi phục runner ở Ngày {reported_day}: không có action lịch sử sau khi mở lại GUI; "
                        "dùng traffic quá khứ trung tính và trạng thái hiện tại từ server.", "WARN"
                    )
                if existing_context is not None:
                    for event in reconcile_runner_context(existing_context, map_config, reported_day or 1):
                        self.log(f"Runner session: {event}.", "WARN")
            curr_day = reported_day or 1
            if reported_day is None:
                self.log("/status không có trường ngày; dùng Ngày 1 và không tự tăng theo answer revision.", "WARN")

            # Chọn vai trò xe
            self.log("Đang kiểm tra và phân bổ vai trò xe...", "INFO")
            try:
                roles = reconcile_roles(self.api, match_id, token, map_config, policy, user_roles,
                                        lambda: self.stop_requested, self.log)
            except TimeoutError as exc:
                self.log(f"[Xe] CHƯA XÁC NHẬN: {exc}", "WARN")
                self.lbl_status_day.config(text="Trạng thái: Chưa xác nhận vai trò xe; chưa chạy kế hoạch")
                return
            self.role_results.put(roles)

            def solve_and_submit_day(target_day):
                day_idx = target_day - 1
                cfg_day_steps = map_config.get("daySteps", [])
                cfg_day_seconds = map_config.get("daySeconds", [])
                steps = cfg_day_steps[day_idx] if day_idx < len(cfg_day_steps) else 20
                self.lbl_status_day.config(text=f"Trạng thái: Đang chuẩn bị Ngày {target_day}/{total_days}...")
                self.log(f"\n--- NGÀY {target_day}/{total_days} (Dự kiến số bước: {steps}) ---", "INFO")

                # Đồng bộ hóa chính xác nhịp ngày với Server (chờ đến khi server thực sự chuyển sang target_day)
                day_st = None
                poll_count = 0
                # A resumed runner may already have answers queued ahead of the
                # server clock. Wait through every remaining day boundary; do
                # not call the solver with an older state after timeout.
                max_polls = max(120, int(sum(cfg_day_seconds[:max(0, target_day - 1)]) + 30))

                while not self.stop_requested and poll_count < max_polls:
                    try:
                        st = self.api.get_game_status(match_id, token)
                        cur = read_server_day(st)
                        m_status = st.get("status", "")
                        if m_status == "finished":
                            self.log("Server thông báo trận đấu đã hoàn thành!", "SUCCESS")
                            return target_day, True

                        if cur is not None and cur >= target_day:
                            day_st = st
                            if cur > target_day:
                                self.log(f"Server đã nhảy trước đến Ngày {cur} (Target ban đầu: Ngày {target_day})!", "WARN")
                            break
                        else:
                            if poll_count % 5 == 0:
                                self.lbl_status_day.config(text=f"Trạng thái: Đang đợi server mở Ngày {target_day}/{total_days} ({poll_count}s)...")
                                self.log(f"⏳ Đang đợi server xử lý ngày cũ và mở Ngày {target_day} (Server hiện tại: Ngày {cur}, đã đợi {poll_count}s)...", "INFO")
                    except Exception as e_poll:
                        if poll_count % 10 == 0:
                            self.log(f"Đang kết nối lại server: {e_poll}", "WARN")

                    time.sleep(1.0)
                    poll_count += 1

                if self.stop_requested:
                    return target_day, True

                if not day_st:
                    latest = None
                    try:
                        latest = self.api.get_game_status(match_id, token)
                    except Exception as e_st:
                        self.log(f"Lỗi đọc status từ server: {e_st}", "ERROR")
                    latest_day = read_server_day(latest)
                    raise TimeoutError(
                        f"Server chưa mở Ngày {target_day} sau {max_polls}s "
                        f"(ngày server hiện tại: {latest_day or 'không xác định'}). "
                        "GUI không gọi solver và không nộp state sai ngày; hãy bấm chạy lại khi server chuyển ngày."
                    )

                # Lấy số bước chính xác theo ngày hiện tại từ server hoặc map config
                cur_server_day = read_server_day(day_st, target_day)
                cur_day_idx = cur_server_day - 1
                server_steps = day_st.get("stepsCount")
                if server_steps and isinstance(server_steps, int) and server_steps > 0:
                    steps = server_steps
                elif cur_day_idx < len(cfg_day_steps):
                    steps = cfg_day_steps[cur_day_idx]

                # Tự động điều chỉnh thời gian giải an toàn theo cấu hình daySeconds của map
                day_sec = cfg_day_seconds[cur_day_idx] if cur_day_idx < len(cfg_day_seconds) else 45.0
                # Use a stable per-day search allowance. A five-second reserve
                # absorbs process startup, JSON, validation and HTTP submit.
                safe_budget_ms = max(1000, int((day_sec - 5.0) * 1000))
                effective_time_limit_ms = min(time_limit_ms, safe_budget_ms)
                raw_ends_at = day_st.get("endsAt", day_st.get("ends_at"))
                deadline_budget_ms = None
                if isinstance(raw_ends_at, (int, float)) and not isinstance(raw_ends_at, bool):
                    ends_at_seconds = float(raw_ends_at)
                    if ends_at_seconds > 100_000_000_000:
                        ends_at_seconds /= 1000.0
                    deadline_budget_ms = max(1, int((ends_at_seconds - time.time() - 1.0) * 1000))
                    effective_time_limit_ms = min(effective_time_limit_ms, deadline_budget_ms)
                if effective_time_limit_ms < time_limit_ms:
                    reason = f"daySeconds={day_sec}s"
                    if deadline_budget_ms is not None:
                        reason += f", endsAt còn khoảng {max(0, deadline_budget_ms) / 1000:.2f}s"
                    self.log(f"⚡ Ngân sách yêu cầu {time_limit_ms}ms; ngân sách thực tế {effective_time_limit_ms}ms ({reason}) để nộp trước hạn.", "WARN")
                else:
                    self.log(f"Ngân sách runner thực tế: {effective_time_limit_ms}ms.", "INFO")

                self.lbl_status_day.config(text=f"Trạng thái: Đang giải Ngày {cur_server_day}/{total_days} ({steps} bước | Giới hạn: {effective_time_limit_ms}ms)")

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
                    "day": cur_day_idx,
                    "steps": steps,
                    "agents": built_agents,
                    "traffics": norm_traffics
                }

                runner_context = None
                if policy_uses_runner_context(policy):
                    session_key = (str(match_id), str(policy))
                    runner_context = self.runner_sessions.setdefault(session_key, new_runner_context())
                    for event in reconcile_runner_context(runner_context, map_config, cur_server_day):
                        self.log(f"Runner session: {event}.", "WARN")
                    committed_days = len(runner_context["history"]["submitted_actions"])
                    if committed_days != cur_day_idx:
                        raise RuntimeError(
                            f"Runner history has {committed_days} committed days but server is at "
                            f"day {cur_server_day}. Keep this GUI open for the whole match; "
                            "accepted actions cannot be reconstructed from /status."
                        )

                t0 = time.time()
                plan = solve_plan(
                    policy, map_config, day_info, roles, day_num=cur_server_day,
                    raw_status=day_st, time_limit_ms=effective_time_limit_ms,
                    log_fn=self.log, day_budget_sec=day_sec,
                    runner_context=runner_context,
                )
                elapsed = time.time() - t0
                self.log(f"Đã giải xong trong {elapsed:.2f}s! Đang nộp bài...", "SUCCESS")

                local_score = check_plan_score(map_config, day_info, plan)
                ans_res = self.api.submit_actions(match_id, token, plan)
                rejected = isinstance(ans_res, dict) and any(
                    ans_res.get(field) is False for field in ("valid", "ok", "success")
                )
                if rejected:
                    self.log(f"❌ Server phản hồi lỗi: {ans_res.get('error', ans_res)}", "ERROR")
                else:
                    if runner_context is not None:
                        stage_runner_day(
                            runner_context, cur_server_day, plan,
                            runner_context.pop("pending_planner_state", None),
                            local_score.get("servings", 0) if local_score.get("valid") else 0,
                        )
                    self.log(f"✅ Server ghi nhận nộp bài Ngày {cur_server_day} thành công: {ans_res}", "SUCCESS")

                is_match_over = (cur_server_day >= total_days)
                return cur_server_day, is_match_over

            # BƯỚC 2: Tiến hành giải theo chế độ đã chọn
            if mode == "step":
                solve_and_submit_day(curr_day)
                if self.stop_requested:
                    self.lbl_status_day.config(text=f"Trạng thái: Đã dừng trước khi nộp Ngày {curr_day}")
                    self.log(f"Đã dừng; chưa xác nhận nộp bài Ngày {curr_day}.", "WARN")
                else:
                    self.lbl_status_day.config(text=f"Trạng thái: Đã hoàn tất nộp Ngày {curr_day}! Sẵn sàng.")
                    self.log(f"🎯 ĐÃ HOÀN TẤT NỘP BÀI NGÀY {curr_day}!", "SUCCESS")
                    self.log("Bạn có thể mở Replay xem diễn biến, đổi Solver nếu muốn và bấm tiếp cho ngày sau.", "INFO")
            else:
                current_target = curr_day
                while not self.stop_requested and current_target <= total_days:
                    # Kiểm tra tình trạng trận đấu trước khi giải
                    try:
                        st_pre = self.api.get_game_status(match_id, token)
                        if st_pre.get("status") == "finished":
                            self.log("🏁 Trận đấu đã hoàn thành trên server!", "SUCCESS")
                            break
                        live_cur = read_server_day(st_pre)
                        if live_cur and live_cur > current_target:
                            current_target = live_cur
                    except Exception:
                        pass

                    if current_target > total_days:
                        break

                    res_day, is_done = solve_and_submit_day(current_target)
                    if is_done or res_day >= total_days:
                        break

                    # Chuyển ngày nếu là match luyện tập của admin
                    if not self.stop_requested:
                        try:
                            self.api.match_action(match_id, "next_day")
                            self.log(f"Đã gửi tín hiệu next_day sang Ngày {res_day + 1}", "INFO")
                        except Exception:
                            pass

                    current_target = res_day + 1

                # BƯỚC 3: Tổng kết điểm
                final_m = None
                poll_end = 0
                while poll_end < 15 and not self.stop_requested:
                    try:
                        st_end = self.api.get_game_status(match_id, token)
                        if st_end.get("status") == "finished" or st_end.get("finished"):
                            break
                    except Exception:
                        pass
                    time.sleep(1.0)
                    poll_end += 1

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
                        brand_max = len({spot.get("brand") for spot in map_config.get("spots", [])
                                         if isinstance(spot, dict) and "brand" in spot})
                        daily_max = brand_max * total_days
                        self.log(f"🚩 Đội {t_name}: {servings} bát mì | {types}/{brand_max} loại mì | Daily: {daily}/{daily_max}", "SUCCESS")
                        self.lbl_status_score.config(text=f"Điểm số: {servings} bát mì (Loại: {types}/{brand_max}, Daily: {daily}/{daily_max})")
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
        self.cbo_v_policy1 = ttk.Combobox(box_select, values=[name for name in SOLVERS if not name.startswith("HTTP: ")], width=35, state="readonly")
        self.cbo_v_policy1.grid(row=0, column=3, padx=6, pady=6)
        self.cbo_v_policy1.current(0)  # ACO

        # Đội 2
        ttk.Label(box_select, text="ĐỘI 2:", font=("Segoe UI", 10, "bold"), foreground="#C53030").grid(row=1, column=0, padx=6, pady=6, sticky=tk.W)
        self.cbo_v_team2 = ttk.Combobox(box_select, values=[t["name"] for t in PRESET_TEAMS], width=20, state="readonly")
        self.cbo_v_team2.grid(row=1, column=1, padx=6, pady=6)
        self.cbo_v_team2.current(1)  # Team-ALNS

        ttk.Label(box_select, text="Thuật toán:").grid(row=1, column=2, padx=6, pady=6)
        self.cbo_v_policy2 = ttk.Combobox(box_select, values=[name for name in SOLVERS if not name.startswith("HTTP: ")], width=35, state="readonly")
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
        if not self.runner_changes_allowed():
            return
        self.btn_run_4way.config(state=tk.DISABLED)
        self.btn_open_v_replay.config(state=tk.DISABLED)
        threading.Thread(target=self._run_multi_worker, args=(["Team-ACO", "Team-ALNS", "Team-MLNS", "Procon26-Bot"],), daemon=True).start()

    def start_6way_match(self):
        if not self.runner_changes_allowed():
            return
        self.btn_run_6way.config(state=tk.DISABLED)
        self.btn_open_v_replay.config(state=tk.DISABLED)
        threading.Thread(target=self._run_multi_worker, args=(["Team-ACO", "Team-ALNS", "Team-MLNS", "Procon26-Bot", "Team-LocalSearch", "Team-Greedy"],), daemon=True).start()

    def start_championship(self):
        if not self.runner_changes_allowed():
            return
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
        if not self.runner_changes_allowed():
            return
        t1_name = self.cbo_v_team1.get()
        p1 = SOLVERS[self.cbo_v_policy1.get()]
        t2_name = self.cbo_v_team2.get()
        p2 = SOLVERS[self.cbo_v_policy2.get()]
        if p1.startswith("HTTP: ") or p2.startswith("HTTP: "):
            messagebox.showinfo("Bot HTTP", "Bot HTTP chỉ dùng trong tab Thi Đấu Trực Tiếp.", parent=self)
            return

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

        runner_box = ttk.LabelFrame(frame, text="Solver EXE - Runner JSON / Bot HTTP", padding=8)
        runner_box.pack(fill=tk.X, pady=(0, 10))
        ttk.Button(runner_box, text="+ Thêm solver EXE vào danh sách", command=self.add_runner).pack(anchor=tk.W, pady=4)
        ttk.Label(runner_box, text="Chỉ chạy EXE tin cậy. Chọn đúng kiểu: Runner JSON hoặc Bot HTTP. Danh sách tự lưu.\n"
                  "Để thay EXE của solver đã thêm, nhập lại cùng tên và xác nhận.",
                  wraplength=500).pack(anchor=tk.W)

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

    def runner_changes_allowed(self):
        arena_buttons = (self.btn_run_versus, self.btn_run_4way, self.btn_run_6way, self.btn_run_champ)
        if self.is_running or any(str(button.cget("state")) == tk.DISABLED for button in arena_buttons):
            messagebox.showwarning("Runner", "Hãy đợi tác vụ hiện tại kết thúc trước khi đổi runner.")
            return False
        return True

    def add_runner(self):
        if not self.runner_changes_allowed():
            return
        filename = filedialog.askopenfilename(
            parent=self, title="Thêm solver tin cậy",
            filetypes=[("Solver", "*.exe *.py"), ("Executable", "*.exe"), ("Python", "*.py")],
        )
        if not filename:
            return
        name = simpledialog.askstring("Tên solver", "Đặt tên solver mới (nhập tên cũ để thay EXE hoặc đổi kiểu).",
                                      initialvalue=Path(filename).stem, parent=self)
        if name is None:
            return
        http = False if Path(filename).suffix.lower() == ".py" else messagebox.askyesnocancel(
            "Kiểu solver", "EXE này có phải Bot HTTP nhận -url, -match, -token?\n\nCó: Bot HTTP (ví dụ bot_v11.exe).\nKhông: Runner JSON roles / plan (ví dụ Procon26).\nHủy: không thêm.", parent=self)
        if http is None:
            return
        try:
            label = f"{'HTTP' if http else 'EXE'}: {name.strip()}"
            existing = read_custom_runners()
            if any(f"{prefix}: {name.strip()}" in existing for prefix in ("EXE", "HTTP")) and not messagebox.askyesno("Thay solver", f"Thay executable/kiểu của {name.strip()}?", parent=self):
                return
            label = register_runner(name, filename, transport="http" if http else "json")
        except (OSError, ValueError) as exc:
            messagebox.showerror("Không thêm được solver", str(exc), parent=self)
            return
        for combo in (self.cbo_solver, self.cbo_v_policy1, self.cbo_v_policy2):
            choices = [name for name in SOLVERS if combo is self.cbo_solver or not name.startswith("HTTP: ")]
            combo.configure(values=choices)
            if combo.get() not in choices:
                combo.current(0)
        self.cbo_solver.set(label)
        self.notebook.select(self.tab_live)
        self.log(f"Đã lưu {label}: {CUSTOM_RUNNERS[label]}", "SUCCESS")

    def delete_runner(self):
        if not self.runner_changes_allowed():
            return
        label = self.cbo_solver.get()
        if label not in CUSTOM_RUNNERS:
            messagebox.showinfo("Xóa solver", "Hãy chọn solver EXE tự thêm trong danh sách thuật toán. Các solver có sẵn được giữ nguyên.", parent=self)
            return
        if not messagebox.askyesno("Xóa solver", f"Xóa {label} khỏi danh sách?\nFile EXE và DLL trên máy sẽ được giữ nguyên.", parent=self):
            return
        try:
            unregister_runner(label)
        except (OSError, ValueError) as exc:
            messagebox.showerror("Không xóa được solver", str(exc), parent=self)
            return
        for combo in (self.cbo_solver, self.cbo_v_policy1, self.cbo_v_policy2):
            combo.configure(values=[name for name in SOLVERS if combo is self.cbo_solver or not name.startswith("HTTP: ")])
            if combo.get() not in SOLVERS:
                combo.current(0)
        self.log(f"Đã xóa {label} khỏi danh sách; giữ nguyên file EXE.", "INFO")

    def open_current_replay(self):
        if self.current_match_url:
            webbrowser.open(self.current_match_url)
        else:
            messagebox.showinfo("Chưa có trận", "Chưa có trận đấu nào được chọn!")

    def log(self, message: str, tag: str = "INFO"):
        self.log_queue.put((message, tag))

    def check_log_queue(self):
        while not self.role_results.empty():
            roles = self.role_results.get_nowait()
            self.current_roles = roles
            self.update_agent_role_ui(len(roles))
            for combo, role in zip(self.agent_role_combos, roles):
                combo.current(role)
        for widget in [self.cbo_role_preset, self.cbo_solver, *self.agent_role_combos]:
            widget.configure(state="disabled" if self.is_running else "readonly")
        self.btn_stop.configure(state="normal" if self.is_running else "disabled")
        for widget in (self.ent_host, self.ent_match_id, self.ent_token):
            widget.configure(state="disabled" if self.is_running else "normal")

        if self.http_ready.is_set():
            self.http_ready.clear()
            self.lbl_status_day.config(text="Trạng thái: Bot HTTP đang chạy qua proxy")
        while not self.http_results.empty():
            returncode = self.http_results.get_nowait()
            status = "Đã dừng bot HTTP" if self.stop_requested else f"Bot HTTP đã thoát (mã {returncode})"
            self.lbl_status_day.config(text=f"Trạng thái: {status}")
            self.log(status, "INFO" if self.stop_requested or returncode == 0 else "ERROR")
            self.http_process = None
            self.http_proxy = None
            self.is_running = False
            self.btn_start.config(state=tk.NORMAL)
            self.btn_step.config(state=tk.NORMAL)
            self.btn_stop.config(state=tk.DISABLED)
        while not self.log_queue.empty():
            msg, tag = self.log_queue.get_nowait()
            ts = time.strftime("[%H:%M:%S] ")
            self.txt_log.insert(tk.END, ts + msg + "\n", tag)
            self.txt_log.see(tk.END)
        self.after(100, self.check_log_queue)


if __name__ == "__main__":
    app = HexControlCenter()
    app.mainloop()
