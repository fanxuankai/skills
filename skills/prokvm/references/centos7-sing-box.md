# Provisioning sing-box (233boy) on CentOS 7 ProKvm hosts

A worked example of installing [sing-box](https://github.com/SagerNet/sing-box) via the [233boy script](https://github.com/233boy/sing-box) on a fleet of ProKvm servers, then extracting the generated VLESS+Reality node links. Use this as a template for any "install software + collect a generated artifact" provisioning job.

## Why this needed a reference doc

Three things here aren't obvious and each cost a failed attempt to discover:

1. CentOS 7's yum mirrors are dead (EOL 2024). The 233boy script `yum install`s `wget` and fails before it even starts.
2. The 233boy CLI subcommand to get a node link is `sing-box info <name>` — *not* `sing-box link`, `sing-box url` (no arg), or `sing-box show`.
3. The CLI output is ANSI-colored; you must strip `ESC [ ... m` sequences before grepping, or your parser silently misses lines.

## Prerequisites

- `sshpass` locally (`brew install sshpass` / `apt install sshpass`).
- `provision_servers.py` from this skill, or your own loop that reads the server list and SSHes each host. The script in this skill already exposes `ip` / `ssh_user` / `ssh_pass` / `ssh_port` from the panel.
- All hosts must be `running` (check `status_power` in the list).

## Step 1 — Fix yum, install wget

Run this on each host (idempotent — it no-ops if wget already exists):

```bash
if command -v wget >/dev/null 2>&1; then echo WGET_OK; exit 0; fi
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
yum clean all >/dev/null 2>&1
yum install -y wget >/dev/null 2>&1
command -v wget >/dev/null 2>&1 && echo WGET_OK || echo WGET_FAIL
```

If a host prints `WGET_FAIL`, stop — the vault mirror is unreachable or the host isn't actually CentOS 7. Diagnose with `cat /etc/redhat-release` and `curl -sI https://vault.centos.org/7.9.2009/os/x86_64/repodata/repomd.xml`.

## Step 2 — Install sing-box

The 233boy installer is a one-liner that pipes its own tarball to bash:

```bash
bash <(wget -qO- -o- https://github.com/233boy/sing-box/raw/main/install.sh)
```

It downloads `jq`, the script, and the sing-box binary; generates a random UUID + Reality keypair; writes `/etc/sing-box/conf/<NAME>.json`; and enables the systemd service. Takes ~5 seconds per host on a 200Mbps node.

Check for an existing install first so re-runs are safe:

```bash
command -v sing-box >/dev/null 2>&1 && echo YES || echo NO
```

If `YES`, skip the install step — the script is not re-entrant and re-running it can clobber configs.

## Step 3 — Extract the node link

The 233boy CLI wraps sing-box with a management interface:

```bash
# list configured inbound names
ls /etc/sing-box/conf/
# -> VLESS-REALITY-55726.json   (name is VLESS-REALITY-<port>)

# get the full info block (includes a vless:// URL)
sing-box info VLESS-REALITY-55726
```

The info output looks like:

```
-------------- VLESS-REALITY-55726.json -------------
协议 (protocol)  = vless
地址 (address)   = <server-ip>
端口 (port)      = 55726
用户ID (id)      = <generated-uuid>
...
------------- 链接 (URL) -------------
vless://<uuid>@<server-ip>:<port>?...&pbk=...&fp=chrome#233boy-reality-<server-ip>
------------- END -------------
```

To get just the clean URL (strip ANSI colors, grep the line):

```bash
f=$(ls /etc/sing-box/conf/ | head -1)
n=${f%.json}
sing-box info $n 2>&1 | sed 's/\x1b\[[0-9;]*m//g' | grep -E '^vless://'
```

The `sed` substitution `\x1b\[[0-9;]*m` is essential — the info output is color-coded and a plain `grep` on the raw stream returns nothing because the leading `ESC[41m` makes the line not start with `vless://`.

## Step 4 — Rename the node

The 233boy default name is `233boy-reality-<ip>`. To rename, just rewrite the `#fragment` at the end of the URL:

```python
link = link.rsplit("#", 1)[0] + "#MNL-01"
```

There's no need to call `sing-box` to rename on the host — the `#name` is a client-side label only and doesn't affect the server config.

## Putting it together

A full batch loop reads the server list, runs steps 1–3 on each host serially, collects the extracted link, applies step 4, and writes all links to a file. The file can then be fed into a subscription generator (e.g. a Cloudflare Worker that base64-encodes the list).

Key invariants to assert after the run:
- Link count == server count (no host returned an empty or unparseable `sing-box info`).
- Every link contains `security=reality` and `pbk=` (the Reality public key). A link missing `pbk` means the install silently fell back to plain TLS — re-run step 2 on that host.
- Each link's host:port is unique across the fleet. Duplicates mean two hosts wrote the same default port — rare, but possible if `sing-box` picked the same random port twice.
