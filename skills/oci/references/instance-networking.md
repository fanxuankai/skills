# Instance Networking

Opening ports and troubleshooting connectivity on OCI compute instances.

## How OCI networking works

OCI has three layers of network filtering:

1. **Internet Gateway (IGW)** — attached to the VCN, allows internet access. Must exist for public subnets.
2. **Security List** — subnet-level firewall rules (stateful, default allow egress). One subnet can have multiple security lists. Rules are **cumulative** — all rules from all attached lists are merged.
3. **Network Security Group (NSG)** — instance-level firewall rules (stateful). More flexible; rules can be added/removed individually.

Both Security Lists and NSGs must allow the port. If either blocks it, the connection fails.

## Finding the right VCN and Security List

```bash
# Get the instance's VNIC
oci compute instance list-vnics --instance-id "$INSTANCE_ID" \
  --query "data [*].{subnet:\"subnet-id\", public:\"public-ip\", private:\"private-ip\"}" \
  --output table

# From the subnet ID, find the VCN
oci network subnet get --subnet-id "$SUBNET_ID" \
  --query "data.\"vcn-id\""

# List security lists in that VCN
oci network security-list list --compartment-id "$TENANCY" --vcn-id "$VCN_ID" \
  --query "data [*].{name:\"display-name\", id:id}" \
  --output table
```

## Opening a port

### Option A: Security List (subnet-level)

Security list rules are append-only in the OCI API — an update replaces all rules. Fetch existing, add new, update:

```bash
SL_ID="ocid1.securitylist.oc1.phx.aaaaaaaa..."

# Save current state
oci network security-list get --security-list-id "$SL_ID" > /tmp/sl.json

# Build new ingress rules array
python3 << 'PYEOF'
import json
sl = json.load(open('/tmp/sl.json'))['data']
rules = sl['ingress-security-rules']
rules.append({
    "source": "0.0.0.0/0",
    "protocol": "6",
    "is-stateless": False,
    "tcp-options": {"destination-port-range": {"min": 443, "max": 443}}
})
json.dump(rules, open('/tmp/ingress.json', 'w'))
PYEOF

# Apply (include all existing rules + the new one)
oci network security-list update \
  --security-list-id "$SL_ID" \
  --ingress-security-rules file:///tmp/ingress.json \
  --force
```

### Option B: Network Security Group (instance-level, preferred)

NSG rules can be added individually without affecting existing rules:

```bash
# List NSGs
oci network nsg list --compartment-id "$TENANCY" --output table

# Or create a new NSG
oci network nsg create --compartment-id "$TENANCY" --display-name "web-ports" --vcn-id "$VCN_ID"

# Add a rule
oci network nsg-rule add \
  --nsg-id "$NSG_ID" \
  --direction INGRESS \
  --protocol 6 \
  --source 0.0.0.0/0 \
  --source-type CIDR_BLOCK \
  --tcp-destination-port-range '{"min":443,"max":443}'

# Attach the NSG to the instance's VNIC
oci compute vnic update --vnic-id "$VNIC_ID" --nsg-ids '["'$NSG_ID'"]'
```

## Port forwarding with iptables

If a service listens on a non-standard port (e.g. 8317) and you want to expose it on a different external port (e.g. 38317), use iptables on the instance:

```bash
# SSH into the instance first
ssh oracle-server

# Add the NAT rule
sudo iptables -t nat -A PREROUTING -p tcp --dport 38317 -j REDIRECT --to-port 8317

# Allow the forwarded port through the firewall (if ufw/iptables filtering is active)
sudo iptables -I INPUT -p tcp --dport 8317 -j ACCEPT

# Persist rules across reboots
sudo apt install iptables-persistent -y
sudo netfilter-persistent save
```

To list existing NAT rules:

```bash
sudo iptables -t nat -L PREROUTING -n --line-numbers
```

To delete a NAT rule:

```bash
sudo iptables -t nat -D PREROUTING <line-number>
```

## Troubleshooting connectivity

1. **Check the instance is running:**
   ```bash
   oci compute instance get --instance-id "$INSTANCE_ID" --query "data.\"lifecycle-state\""
   ```

2. **Check the public IP:**
   ```bash
   oci compute instance list-vnics --instance-id "$INSTANCE_ID" --query "data [0].\"public-ip\""
   ```

3. **Check security list ingress rules:**
   ```bash
   oci network security-list get --security-list-id "$SL_ID" --query "data.\"ingress-security-rules\"" | python3 -m json.tool
   ```

4. **Check from an external machine:**
   ```bash
   curl -v --max-time 5 http://<public-ip>:<port>/
   nc -zv <public-ip> <port>
   ```

5. **Check the service is listening on the instance:**
   ```bash
   ssh oracle-server 'ss -tlnp | grep <port>'
   ```

6. **Check iptables on the instance:**
   ```bash
   ssh oracle-server 'sudo iptables -L -n; sudo iptables -t nat -L -n'
   ```

Common issues:
- Security list source is not `0.0.0.0/0` — it might be restricted to a specific CIDR
- Protocol number wrong: TCP=6, UDP=17, ICMP=1
- The instance's subnet has no route table entry to the Internet Gateway
- The service binds to `127.0.0.1` instead of `0.0.0.0`
