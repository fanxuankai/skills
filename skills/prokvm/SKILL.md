---
name: prokvm
description: Manage ProKvm cloud panel — list servers, upgrade public bandwidth, and operate the member center through its (undocumented) web API. Use whenever the user mentions ProKvm, 睿智云, 会员中心, batch-upgrading server bandwidth, 升级公网宽带/带宽, 云服务器升级, or wants to operate a ProKvm panel at a self-signed HTTPS URL — even if they don't explicitly say "ProKvm".
---

# ProKvm Panel Management

Operate a ProKvm member center (self-signed HTTPS, no official API docs) through its web endpoints. Workflows are built by reverse-engineering the panel with `curl -sk`, then automating with `python3` + `requests`.

## Prerequisites

### Identify the panel host

ProKvm panels are user-hosted at self-signed HTTPS URLs (e.g. `https://<panel-ip>`). Ask the user for the host if not given; never assume.

### Credentials

Panel username/password are required. Read them from environment variables rather than hardcoding:

```bash
env | grep -iE 'PROKVM_(HOST|USER|PASS)'
# Expected:
#   PROKVM_HOST=https://<ip>
#   PROKVM_USER=<username>
#   PROKVM_PASS=<password>
```

If absent, ask the user once and export them in the current shell. Do **not** write credentials into committed scripts.

### Python environment

`requests` is required; `urllib3` ships with it.

```bash
python3 -c "import requests" 2>/dev/null || pip3 install requests
```

## Endpoints (reverse-engineered)

All paths are under the panel host. The panel sets a session cookie via `Set-Cookie`, so use a `requests.Session` (or persist `curl`'s cookie jar).

- **Login**: `POST /login`
  - Form: `username`, `password`, `login_type=PASS`, `submit=1`
  - Referer: `HOST/login`. Success heuristic: response body contains `member/index` or `setTimeout`.

- **Server list**: `GET /server/index?page=<n>` (10 per page) or `/server/index?size=1000` for a single page.
  - The HTML embeds `var list = {...};` as JSON. Parse with `re.search(r"var list\s*=\s*(\{.*?\})\s*;", html, re.S)`.
  - Each entry has `id_sn` (server id), `net` (current bandwidth in Mbps), `server_name`, `node`, **plus full SSH credentials**: `ip`, `ssh_user`, `ssh_pass`, `ssh_port`. Grab all of these when provisioning servers — the SSH fields are the entry point for any on-host operation (installing software, reading configs, running health checks).
  - Pagination: page 0 returns the first 10, `page=10` returns the next batch. Deduplicate by `id_sn`.

- **Upgrade page**: `GET /server/detail/{id_sn}/upgrade?type=list`
  - Contains `<select name="spec_id">` with `<option value="...">` — the current `spec_id`.
  - Slider bounds for `net`: read `form_min.net` (or `net:"<n>"` min), `form_max` (via `:max="parseFloat('<n>')"`), and current `form_data.net`.

- **Upgrade submit**: `POST /server/detail/{id_sn}/upgrade`
  - Form: `spec_id`, `net` (target Mbps), `def=0`, `coupon_id=0`, `action=1`, `type=server`, `scene=server_upgrade`
  - Headers required: `X-Requested-With: XMLHttpRequest` and `X-PJAX: true`
  - Referer: `/server/detail/{id_sn}/upgrade?type=list`
  - Success response: `{"code":0,"msg":"云服务器升级成功！"}`

## Self-signed cert handling

`urllib` will reject the panel's self-signed cert. Use `requests` with `verify=False` and disable warnings:

```python
import urllib3, requests
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
S = requests.Session()
S.verify = False
S.headers.update({
    "User-Agent": "Mozilla/5.0 ...",
    "X-Requested-With": "XMLHttpRequest",
})
```

With `curl`, always pass `-sk` (insecure + silent).

## Batch upgrade workflow

For the full end-to-end script (login → fetch list → parse upgrade page → submit upgrades with skip/retry), see **scripts/upgrade_bandwidth.py**. The script reads `PROKVM_HOST`, `PROKVM_USER`, `PROKVM_PASS` and a target Mbps from argv (default 200).

Run it as:

```bash
PROKVM_HOST=https://<panel-ip> \
PROKVM_USER=... \
PROKVM_PASS=... \
python3 scripts/upgrade_bandwidth.py 200
```

Behavior:
- Lists all servers, prints current `net` per server.
- Skips servers already at or above the target.
- Skips servers whose `form_max.net` < target (node ceiling).
- Submits upgrade POST with PJAX headers; parses `code`/`msg` from JSON.
- 1s sleep between submissions to avoid hammering the panel.

## Server provisioning workflow

Once you have the server list with SSH credentials, a common task is to run something on every host — install a package, deploy a service, collect a config. Use **scripts/provision_servers.py** as the base. It:

- Logs into the panel, fetches the full server list (with `ip`/`ssh_user`/`ssh_pass`/`ssh_port`).
- Runs a user-supplied shell command on each host over SSH (via `sshpass` — `brew install sshpass` / `apt install sshpass`).
- Serial by default (parallel SSH from a laptop usually just thrashes the network); edit the loop if you need concurrency.

```bash
PROKVM_HOST=https://<panel-ip> \
PROKVM_USER=... \
PROKVM_PASS=... \
python3 scripts/provision_servers.py "<remote shell command>"
```

For complex multi-step provisioning (install a proxy core, rotate keys, pull a generated node link), don't inline a giant shell string — write the remote steps into a script file, `scp` it up, run it, and pull back the output. `provision_servers.py` shows the SSH helper pattern to copy.

### CentOS 7 caveat

Many ProKvm hosts ship CentOS 7.9, whose official yum mirrors went dark in 2024 (EOL). `yum install` will fail with `Cannot find a valid baseurl for repo: base/7/x86_64`. Before installing anything, repoint yum at the vault mirror:

```bash
mkdir -p /etc/yum.repos.d/bak
mv /etc/yum.repos.d/CentOS-*.repo /etc/yum.repos.d/bak/ 2>/dev/null
for r in os extras updates; do
cat > /etc/yum.repos.d/CentOS-$r.repo << EOF
[$r]
name=CentOS-7 $r
baseurl=https://vault.centos.org/7.9.2009/$r/x86_64/
gpgcheck=0
enabled=1
EOF
done
yum clean all
```

Then `yum install -y wget` (or whatever) works. Always check `command -v <tool>` first and only fix repos when the tool is missing — don't blindly rewrite repos on every host.

For the concrete sing-box (233boy) install + node-link extraction flow that produced this guidance, read **references/centos7-sing-box.md**.

For the manual reverse-engineering steps that produced these endpoints, read **references/reverse-engineer-panel.md** — useful when the panel changes and the script needs updating.

## Retry on transient node-side failures

Upgrade submits can fail even when the request is well-formed, because the panel forwards to a PVE node (`<ip>:8006`) that may have a transient SSL hiccup. The error usually surfaces as a non-zero `code` with a message mentioning the node. A single immediate retry on the same `id_sn` typically succeeds — the bundled script retries once by default. For more than one flaky node, loop the failing `id_sn`s again after the first pass.

## Key things to verify before declaring done

1. The final summary line reports `成功 N` matching the number of servers that were below target.
2. Any server reported as failed should be retried manually (re-run the script, which skips already-at-target servers).
3. Upgrades deduct from the account balance — remind the user to verify billing after a batch run.
4. Credentials are never written into committed files; only read from env vars at runtime.
