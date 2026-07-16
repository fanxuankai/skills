---
name: cloudflare
description: Manage Cloudflare DNS records, tunnels (cloudflared), and zone settings via the Cloudflare API. Use whenever the user mentions Cloudflare, CF tunnels, cloudflared, DNS records on CF, CF API tokens, proxied/grey-cloud records, or wants to route traffic through Cloudflare to an origin server — even if they don't explicitly say "Cloudflare".
---

# Cloudflare Management

Manage Cloudflare DNS, Tunnels, and zone settings through the Cloudflare REST API. All operations use an API token — never the Global API Key.

## Prerequisites

### API Token

The token must be available as an environment variable or in the user's shell config:

```bash
# Check common locations
env | grep -i CLOUDFLARE_API_TOKEN
grep -i cloudflare ~/.zshrc ~/.bash_profile ~/.profile 2>/dev/null
```

If no token exists, guide the user to create one at **My Profile → API Tokens** in the Cloudflare dashboard. For tunnel operations the token needs these permissions at minimum:

- **Zone → DNS → Edit** (manage DNS records)
- **Cloudflare Tunnel → Edit** (create/manage tunnels)
- **Account Settings → Read** (account-level queries)

Account Resources: `Include → All accounts`. Zone Resources: `Include → All zones from an account → <account>`.

### Required IDs

Most API calls need the **Zone ID** and **Account ID**. Fetch them once:

```bash
# Zone ID (by domain name)
curl -s -H "Authorization: Bearer $CF_TOKEN" \
  "https://api.cloudflare.com/client/v4/zones?name=example.com" \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['result'][0]['id'])"

# Account ID (from the same zone query)
curl -s -H "Authorization: Bearer $CF_TOKEN" \
  "https://api.cloudflare.com/client/v4/zones?name=example.com" \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['result'][0]['account']['id'])"
```

## DNS Record Management

### List records for a name

```bash
curl -s -H "Authorization: Bearer $CF_TOKEN" \
  "https://api.cloudflare.com/client/v4/zones/$ZONE_ID/dns_records?name=app.example.com"
```

### Update an existing record (e.g. change A → CNAME)

Fetch the record ID from the list call, then PUT:

```bash
curl -s -X PUT "https://api.cloudflare.com/client/v4/zones/$ZONE_ID/dns_records/$RECORD_ID" \
  -H "Authorization: Bearer $CF_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"type":"CNAME","name":"app.example.com","content":"tunnel-id.cfargotunnel.com","proxied":true}'
```

### Create a new record

```bash
curl -s -X POST "https://api.cloudflare.com/client/v4/zones/$ZONE_ID/dns_records" \
  -H "Authorization: Bearer $CF_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"type":"A","name":"app.example.com","content":"1.2.3.4","proxied":true}'
```

### proxied (orange cloud) vs DNS-only (grey cloud)

- `proxied: true` — traffic goes through CF edge (DDoS protection, CDN, SSL). CF connects to origin on port 443 (HTTPS) or 80 (HTTP) by default. Free plan does not support custom origin ports through the proxy.
- `proxied: false` — DNS resolves directly to the origin IP. No CF features, but works with any port.

## Cloudflare Tunnel

Tunnels let cloudflared on an origin server establish an outbound connection to Cloudflare, so the origin doesn't need open inbound ports, a public IP, or its own SSL certificate. This is the recommended way to expose services behind NAT or firewalls.

### When to use a tunnel

- Origin server has no open 80/443 (CF proxy can't reach it directly)
- Origin uses non-standard ports (CF free plan can't customize origin port)
- You want to avoid managing SSL certificates on the origin
- You want to remove a reverse-proxy middleman (e.g. an nginx box doing SSL termination + proxy_pass to another server)

### Create a tunnel via API

```bash
TUNNEL_SECRET=$(head -c 32 /dev/urandom | base64)

curl -s -X POST "https://api.cloudflare.com/client/v4/accounts/$ACCOUNT_ID/cfd_tunnel" \
  -H "Authorization: Bearer $CF_TOKEN" \
  -H "Content-Type: application/json" \
  -d "{\"name\":\"my-tunnel\",\"tunnel_secret\":\"$TUNNEL_SECRET\"}"
```

The response includes:
- `result.id` — the Tunnel ID (used in DNS CNAME and cloudflared config)
- `result.credentials_file` — the full credentials JSON to write on the origin server

### Point DNS at the tunnel

Each subdomain becomes a CNAME to `<tunnel-id>.cfargotunnel.com` with `proxied: true`:

```bash
curl -s -X PUT "https://api.cloudflare.com/client/v4/zones/$ZONE_ID/dns_records/$RECORD_ID" \
  -H "Authorization: Bearer $CF_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"type":"CNAME","name":"app.example.com","content":"<tunnel-id>.cfargotunnel.com","proxied":true}'
```

### Install cloudflared on the origin

For Debian/Ubuntu (amd64):

```bash
# If the server can reach GitHub directly:
wget -O /tmp/cloudflared.deb 'https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64.deb'
dpkg -i /tmp/cloudflared.deb

# If GitHub is slow/unreachable from the server, download locally and scp:
# (local machine)
curl -L -o /tmp/cloudflared.deb 'https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64.deb'
scp -P <port> /tmp/cloudflared.deb root@<server>:/tmp/cloudflared.deb
# (on server)
dpkg -i /tmp/cloudflared.deb
```

For other architectures, replace `amd64` with `arm64` etc. Check `uname -m` on the origin first.

### Write credentials and config

```bash
mkdir -p /etc/cloudflared

# Write credentials JSON (from the tunnel creation response)
cat > /etc/cloudflared/credentials.json <<'EOF'
{"AccountTag":"...","TunnelID":"...","TunnelName":"...","TunnelSecret":"..."}
EOF

# Write config
cat > /etc/cloudflared/config.yml <<'EOF'
tunnel: <tunnel-id>
credentials-file: /etc/cloudflared/credentials.json

ingress:
  - hostname: app.example.com
    service: http://localhost:8080
  - hostname: api.example.com
    service: http://localhost:3000
  - service: http_status:404
EOF
```

The last `catch-all` ingress rule (`http_status:404`) is **required** — cloudflared refuses to start without it.

### Install as a systemd service

```bash
cloudflared service install
systemctl enable cloudflared
systemctl start cloudflared
```

This creates `/etc/systemd/system/cloudflared.service` that runs:
`cloudflared --no-autoupdate --config /etc/cloudflared/config.yml tunnel run`

### Port mapping gotcha

cloudflared connects to `localhost:<port>` **inside the origin server**. It does NOT go through the cloud provider's external NAT/port-forwarding rules. Always use the port the service actually listens on locally, not the externally forwarded port.

Check actual listening ports:
```bash
ss -tlnp | grep LISTEN
# or
docker ps --format "{{.Names}}\t{{.Ports}}"
```

### Rename a tunnel

```bash
curl -s -X PATCH "https://api.cloudflare.com/client/v4/accounts/$ACCOUNT_ID/cfd_tunnel/$TUNNEL_ID" \
  -H "Authorization: Bearer $CF_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"name":"new-name"}'
```

Also update `TunnelName` in `/etc/cloudflared/credentials.json` on the origin and restart cloudflared. The DNS CNAME (`<tunnel-id>.cfargotunnel.com`) does **not** change — it uses the Tunnel ID, not the name.

### Verify

```bash
# Check service status
systemctl status cloudflared

# Test each hostname through the tunnel
curl -sk -o /dev/null -w "http=%{http_code} time=%{time_total}s\n" \
  "https://app.example.com/"
```

A 502 from the tunnel means cloudflared is running but can't reach the local service — almost always a wrong port in `config.yml`. Check `ss -tlnp` on the origin.

## Common workflows

For detailed step-by-step workflows, read the relevant reference file:

- **references/dns-migration.md** — migrating DNS records from one origin to another, or switching A records to tunnel CNAMEs
- **references/tunnel-setup.md** — full end-to-end tunnel setup including removing an existing reverse-proxy middleman

## Key things to verify before declaring done

1. Every hostname returns the expected HTTP status (usually 200) via `curl`
2. `systemctl is-active cloudflared` reports `active` on the origin
3. DNS records point to the right target (CNAME for tunnels, A for direct)
4. If a middleman reverse proxy was replaced, its site configs are cleaned up and nginx reloaded
