#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Batch-upgrade public bandwidth for all cloud servers on a ProKvm panel.

Usage:
    PROKVM_HOST=https://<ip> PROKVM_USER=... PROKVM_PASS=... \
        python3 upgrade_bandwidth.py [TARGET_MBPS]

TARGET_MBPS defaults to 200. Servers already at or above the target are
skipped; servers whose node ceiling is below the target are reported.

Credentials are read from env vars only — never hardcoded.
"""
import os
import re
import sys
import time
import json
import urllib3
import requests

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

HOST = os.environ.get("PROKVM_HOST", "").rstrip("/")
USERNAME = os.environ.get("PROKVM_USER", "")
PASSWORD = os.environ.get("PROKVM_PASS", "")
TARGET_NET = int(sys.argv[1]) if len(sys.argv) > 1 else 200

S = requests.Session()
S.verify = False
S.headers.update({
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/124.0 Safari/537.36",
    "X-Requested-With": "XMLHttpRequest",
})


def post(url, data, referer=None, pjax=False):
    h = {}
    if referer:
        h["Referer"] = referer
    if pjax:
        h["X-PJAX"] = "true"
    r = S.post(url, data=data, headers=h, timeout=40)
    return r.status_code, r.text


def get(url):
    r = S.get(url, timeout=40)
    return r.status_code, r.text


def login():
    if not (HOST and USERNAME and PASSWORD):
        print("missing PROKVM_HOST / PROKVM_USER / PROKVM_PASS env var")
        sys.exit(2)
    get(HOST + "/login")
    data = {
        "username": USERNAME,
        "password": PASSWORD,
        "login_type": "PASS",
        "submit": "1",
    }
    status, body = post(HOST + "/login", data, referer=HOST + "/login")
    ok = "member/index" in body or "setTimeout" in body
    print(f"[login] status={status} ok={ok}")
    return ok


def fetch_list():
    items = []
    for page in [None, 10]:
        url = HOST + "/server/index?size=1000" if page is None else HOST + f"/server/index?page={page}"
        _, html = get(url)
        m = re.search(r"var list\s*=\s*(\{.*?\})\s*;", html, re.S)
        if not m:
            continue
        data = json.loads(m.group(1))
        for k, v in data.items():
            items.append({
                "id_sn": v.get("id_sn"),
                "net": int(v.get("net") or 0),
                "server_name": v.get("server_name"),
                "node": v.get("node"),
            })
    seen = set()
    out = []
    for it in items:
        if it["id_sn"] in seen:
            continue
        seen.add(it["id_sn"])
        out.append(it)
    return out


def parse_upgrade_page(id_sn):
    url = f"{HOST}/server/detail/{id_sn}/upgrade?type=list"
    _, html = get(url)
    m = re.search(r'name="spec_id"[^>]*>.*?<option value="(\d+)"', html, re.S)
    spec_id = m.group(1) if m else None
    mn = re.search(r'net:\s*"(\d+)"', html)
    md = re.search(r'form_data:\s*\{[^}]*net:\s*"(\d+)"', html, re.S)
    mx = re.search(r":max=\"parseFloat\('(\d+)'\)\"", html)
    return {
        "spec_id": spec_id,
        "net_min": mn.group(1) if mn else None,
        "net_cur": md.group(1) if md else None,
        "net_max": mx.group(1) if mx else None,
    }


def do_upgrade(id_sn, spec_id, def_val):
    url = f"{HOST}/server/detail/{id_sn}/upgrade"
    referer = f"{HOST}/server/detail/{id_sn}/upgrade?type=list"
    data = {
        "spec_id": spec_id,
        "net": str(TARGET_NET),
        "def": str(def_val),
        "coupon_id": "0",
        "action": "1",
        "type": "server",
        "scene": "server_upgrade",
    }
    status, body = post(url, data, referer=referer, pjax=True)
    return status, body


def upgrade_one(id_sn, info):
    """Submit one upgrade; retry once on transient node-side failure."""
    for attempt in (1, 2):
        status, body = do_upgrade(id_sn, info["spec_id"], 0)
        try:
            j = json.loads(body)
            code = j.get("code")
            msg = j.get("msg", body)
        except Exception:
            code = None
            msg = body[:120]
        if code == 0:
            return True, msg
        # code != 0: retry once; PVE node SSL hiccups usually clear immediately.
        if attempt == 1:
            time.sleep(2)
            continue
    return False, msg


def main():
    if not login():
        print("登录失败")
        sys.exit(1)

    servers = fetch_list()
    print(f"\n共 {len(servers)} 台服务器:")
    for s in servers:
        print(f"  id_sn={s['id_sn']} net={s['net']}Mbps name={s['server_name']} node={s['node']}")

    todo = [s for s in servers if s["net"] < TARGET_NET]
    skip = [s for s in servers if s["net"] >= TARGET_NET]
    print(f"\n已是 {TARGET_NET}Mbps 跳过: {[s['id_sn'] for s in skip]}")
    print(f"待升级: {[s['id_sn'] for s in todo]}\n")

    ok = 0
    fail = 0
    for s in todo:
        id_sn = s["id_sn"]
        info = parse_upgrade_page(id_sn)
        if not info["spec_id"]:
            print(f"[{id_sn}] 无法解析 spec_id，跳过")
            fail += 1
            continue
        max_net = info["net_max"]
        if max_net and int(max_net) < TARGET_NET:
            print(f"[{id_sn}] 该节点最大带宽 {max_net}Mbps < {TARGET_NET}，跳过")
            fail += 1
            continue
        print(f"[{id_sn}] spec_id={info['spec_id']} cur={info['net_cur']} "
              f"min={info['net_min']} max={info['net_max']} -> 升级到 {TARGET_NET}Mbps ...", end=" ")
        success, msg = upgrade_one(id_sn, info)
        if success:
            print(f"成功: {msg}")
            ok += 1
        else:
            print(f"失败: {msg}")
            fail += 1
        time.sleep(1)

    print(f"\n完成: 成功 {ok}，失败 {fail}")


if __name__ == "__main__":
    main()
