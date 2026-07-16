# DNS Migration Workflow

Migrating DNS records between origins, or switching from A records to Cloudflare Tunnel CNAMEs.

## Scenario: Replace a reverse-proxy middleman with a tunnel

Typical setup before: `user → CF edge → Server A (nginx reverse proxy) → Server B (actual service)`

Goal: `user → CF edge → Server B (cloudflared tunnel)` — remove Server A from the path.

### Steps

1. **Identify the actual service ports on the origin (Server B)**

   The existing nginx configs on Server A reveal the `proxy_pass` targets, but those ports may be external NAT ports, not the local ports. Check Server B directly:

   ```bash
   ssh root@<server-b> 'ss -tlnp | grep LISTEN'
   ssh root@<server-b> 'docker ps --format "{{.Names}}\t{{.Ports}}"'
   ```

   Map each subdomain to its actual local port. NAT-forwarded ports (e.g. 38317 → 8317) are NOT what cloudflared uses — it connects to localhost directly.

2. **Create the tunnel** (see SKILL.md "Create a tunnel via API")

3. **Point all subdomain DNS records at the tunnel CNAME**

   For each subdomain, fetch the existing record ID, then PUT with the new CNAME content:

   ```bash
   for sub in app1 app2 app3; do
     RECORD_ID=$(curl -s -H "Authorization: Bearer $CF_TOKEN" \
       "https://api.cloudflare.com/client/v4/zones/$ZONE_ID/dns_records?name=${sub}.example.com" \
       | python3 -c "import sys,json; print(json.load(sys.stdin)['result'][0]['id'])")

     curl -s -X PUT "https://api.cloudflare.com/client/v4/zones/$ZONE_ID/dns_records/$RECORD_ID" \
       -H "Authorization: Bearer $CF_TOKEN" \
       -H "Content-Type: application/json" \
       -d "{\"type\":\"CNAME\",\"name\":\"${sub}.example.com\",\"content\":\"${TUNNEL_ID}.cfargotunnel.com\",\"proxied\":true}"
   done
   ```

4. **Install cloudflared and start the service on Server B**

5. **Verify every subdomain returns 200**

6. **Clean up the old middleman**

   ```bash
   # On Server A: remove the proxy site configs
   cd /etc/nginx/sites-enabled
   rm -f <site-configs-for-migrated-subdomains>
   nginx -t && systemctl reload nginx
   ```

   Keep any site configs for services that still run on Server A (e.g. static sites).

7. **Optionally remove the cloud provider's NAT rules** for the old external ports if nothing else uses them.
