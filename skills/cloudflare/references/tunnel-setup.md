# Full Tunnel Setup Workflow

End-to-end: from nothing to a running Cloudflare Tunnel exposing one or more services on an origin server.

## 1. Gather prerequisites

```bash
# Find the CF API token
env | grep -i CLOUDFLARE_API_TOKEN
grep -i cloudflare ~/.zshrc 2>/dev/null

# Get Zone ID and Account ID
curl -s -H "Authorization: Bearer $CF_TOKEN" \
  "https://api.cloudflare.com/client/v4/zones?name=example.com" \
  | python3 -c "import sys,json; r=json.load(sys.stdin)['result'][0]; print('ZONE='+r['id']); print('ACCOUNT='+r['account']['id'])"
```

If the token lacks tunnel permissions, the create call returns `{"code":10000,"message":"Authentication error"}` even though `user/tokens/verify` says the token is valid. Guide the user to add **Cloudflare Tunnel → Edit** permission.

## 2. Discover actual service ports on the origin

This is the most common failure point. Do NOT trust external/NAT ports — cloudflared connects to localhost.

```bash
ssh root@<server> 'ss -tlnp | grep LISTEN'
ssh root@<server> 'docker ps --format "{{.Names}}\t{{.Ports}}"'
```

If migrating from an existing nginx reverse proxy, read its configs to understand hostname → port mapping, then verify each port is actually listening on the origin:

```bash
ssh root@<server> 'curl -s -o /dev/null -w "%{http_code}" http://localhost:<port>/'
```

## 3. Create the tunnel

```bash
TUNNEL_SECRET=$(head -c 32 /dev/urandom | base64)

curl -s -X POST "https://api.cloudflare.com/client/v4/accounts/$ACCOUNT_ID/cfd_tunnel" \
  -H "Authorization: Bearer $CF_TOKEN" \
  -H "Content-Type: application/json" \
  -d "{\"name\":\"my-tunnel\",\"tunnel_secret\":\"$TUNNEL_SECRET\"}"
```

Save from the response:
- `result.id` → Tunnel ID
- `result.credentials_file` → credentials JSON (write to origin)

## 4. Install cloudflared on the origin

If the origin can't download from GitHub quickly (common for servers in China), download on the local machine and scp:

```bash
# Local
curl -L -o /tmp/cloudflared.deb 'https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64.deb'
scp -P <port> /tmp/cloudflared.deb root@<server>:/tmp/

# On origin
dpkg -i /tmp/cloudflared.deb
cloudflared --version
```

## 5. Write credentials and config

```bash
mkdir -p /etc/cloudflared

cat > /etc/cloudflared/credentials.json <<'EOF'
{"AccountTag":"<account-id>","TunnelID":"<tunnel-id>","TunnelName":"my-tunnel","TunnelSecret":"<secret>"}
EOF

cat > /etc/cloudflared/config.yml <<EOF
tunnel: <tunnel-id>
credentials-file: /etc/cloudflared/credentials.json

ingress:
  - hostname: app1.example.com
    service: http://localhost:8080
  - hostname: app2.example.com
    service: http://localhost:3000
  - service: http_status:404
EOF
```

The catch-all `http_status:404` rule is mandatory.

## 6. Start the service

```bash
cloudflared service install
systemctl enable cloudflared
systemctl start cloudflared
```

If `systemctl restart` reports a timeout but the journal shows "Registered tunnel connection" for all 4 connections, the service is actually fine — systemd's default start timeout is just too short for cloudflared's precheck. Check with `systemctl is-active cloudflared`.

## 7. Point DNS at the tunnel

For each subdomain, update or create a CNAME record pointing to `<tunnel-id>.cfargotunnel.com` with `proxied: true`.

## 8. Verify

```bash
for sub in app1 app2; do
  curl -sk -o /dev/null -w "$sub: http=%{http_code} time=%{time_total}s\n" \
    "https://${sub}.example.com/"
done
```

- **200** — done
- **502** — cloudflared is running but can't reach the local service. Check the port in config.yml matches `ss -tlnp` output on the origin. Almost always a NAT port vs local port mismatch.
- **530 / DNS error** — DNS CNAME not yet propagated or misconfigured. Verify with the CF API.
