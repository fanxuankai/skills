#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Run a shell command on every ProKvm server, serially.

Usage:
    PROKVM_HOST=https://<ip> PROKVM_USER=... PROKVM_PASS=... \
        python3 provision_servers.py "<remote shell command>"

The remote command runs via SSH (sshpass). Output per host is printed
prefixed with the host IP. Failures (non-zero exit or timeout) do not
halt the loop — every host is attempted.

Credentials are read from env vars only — never hardcoded.

Requires: sshpass on $PATH (brew install sshpass / apt install sshpass).
"""
import os
import re
import sys
import json
import time
import subprocess
import urllib3
import requests

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

HOST = os.environ.get("PROKVM_HOST", "").rstrip("/")
USERNAME = os.environ.get("PROKVM_USER", "")
PASSWORD = os.environ.get("PROKVM_PASS", "")

if len(sys.argv) < 2:
    print("usage: provision_servers.py \"<remote shell command>\"")
    sys.exit(2)
REMOTE_CMD = sys.argv[1]

S = requests.Session()
S.verify = False
S.headers.update({
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/124.0 Safari/537.36",
    "X-Requested-With": "XMLHttpRequest",
})


def login():
    if not (HOST and USERNAME and PASSWORD):
        print("missing PROKVM_HOST / PROKVM_USER / PROKVM_PASS env var")
        sys.exit(2)
    S.get(HOST + "/login", timeout=20)
    data = {"username": USERNAME, "password": PASSWORD,
            "login_type": "PASS", "submit": "1"}
    r = S.post(HOST + "/login", data=data,
               headers={"Referer": HOST + "/login"}, timeout=20)
    ok = "member/index" in r.text or "setTimeout" in r.text
    print(f"[login] ok={ok}")
    return ok


def fetch_list():
    items = []
    for page in [0, 10]:
        r = S.get(HOST + f"/server/index?page={page}", timeout=30)
        m = re.search(r"var list\s*=\s*(\{.*?\})\s*;", r.text, re.S)
        if not m:
            continue
        data = json.loads(m.group(1))
        for k, v in data.items():
            items.append(v)
    seen = set()
    out = []
    for it in items:
        if it["id_sn"] in seen:
            continue
        seen.add(it["id_sn"])
        out.append(it)
    return out


def run_on_host(ip, ssh_user, ssh_pass, ssh_port, cmd, timeout=120):
    """Run cmd on host, return (stdout, stderr, returncode)."""
    try:
        r = subprocess.run(
            ["sshpass", "-p", ssh_pass, "ssh",
             "-o", "StrictHostKeyChecking=no",
             "-o", "ConnectTimeout=12",
             "-o", "UserKnownHostsFile=/dev/null",
             f"{ssh_user}@{ip}", "-p", str(ssh_port), cmd],
            capture_output=True, text=True, timeout=timeout,
        )
        return r.stdout, r.stderr, r.returncode
    except subprocess.TimeoutExpired:
        return "", "TIMEOUT", -1


def main():
    if not login():
        print("登录失败")
        sys.exit(1)

    servers = fetch_list()
    print(f"\n共 {len(servers)} 台服务器，执行: {REMOTE_CMD}\n")

    ok = 0
    fail = 0
    for i, s in enumerate(servers, 1):
        ip = s.get("ip", "")
        user = s.get("ssh_user", "root")
        pw = s.get("ssh_pass", "")
        port = s.get("ssh_port", "22")
        name = s.get("server_name", "?")
        print(f"=== [{i}/{len(servers)}] {ip} ({name}) ===")
        if not (ip and pw):
            print("  跳过：缺 ip 或 ssh_pass")
            fail += 1
            continue
        out, err, rc = run_on_host(ip, user, pw, port, REMOTE_CMD)
        if out:
            print(out.rstrip())
        if err:
            print(f"[stderr] {err.rstrip()}", file=sys.stderr)
        if rc == 0:
            ok += 1
        else:
            fail += 1
            print(f"  rc={rc}")
        time.sleep(0.5)

    print(f"\n完成: 成功 {ok}，失败 {fail}")


if __name__ == "__main__":
    main()
