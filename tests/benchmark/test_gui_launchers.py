import subprocess, time, http.client, json, re

for unit, port, binary in [
    ("hexa-udon-gui", 8765, "/home/hexa/release/http-fix-20261016/hexa_udon_production_httpfix"),
    ("hexa-udon-gui-h2", 8766, "/home/hexa/release/http-fix-20261016/hexa_udon_H2_httpfix"),
    ("hexa-udon-gui-b", 8767, "/home/hexa/release/http-fix-20261016/hexa_udon_B_httpfix"),
]:
    cmd = [
        "systemd-run", f"--unit={unit}", "--collect", "--uid=hexa", "--setenv=HOME=/home/hexa",
        "--property=MemoryMax=3G", "--property=MemorySwapMax=512M", "--property=CPUAffinity=0-7", "--property=Nice=10",
        "--working-directory=/mnt/d/30013-o-udon",
        "/usr/bin/python3", "-B", "/mnt/d/30013-o-udon/gui.py", "--binary", binary, "--port", str(port)
    ]
    subprocess.check_output(cmd)
    time.sleep(1)
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    conn.request("GET", "/")
    page = conn.getresponse().read().decode()
    key = re.search(r'nonce="([a-f0-9]{64})"', page).group(1)
    conn.request("GET", "/status", headers={"X-GUI-Key": key})
    status = json.loads(conn.getresponse().read().decode())
    conn.close()
    assert status["ready"] is True, status
    assert status["running"] is False, status
    exec_start = subprocess.check_output(["systemctl", "show", unit, "-p", "ExecStart", "--value"], text=True)
    assert binary in exec_start, (binary, exec_start)
    subprocess.check_output(["systemctl", "stop", f"{unit}.service"])
    for _ in range(20):
        res = subprocess.run(["systemctl", "is-active", f"{unit}.service"], capture_output=True, text=True)
        active = res.stdout.strip()
        if active in ("inactive", "failed"):
            break
        time.sleep(0.2)
    assert active in ("inactive", "failed"), active
    print(f"Verified {unit} on port {port} with {binary}: PASS", flush=True)
