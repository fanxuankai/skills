---
name: oci
description: Manage Oracle Cloud Infrastructure (OCI) compute instances, networking (VCN/security lists/NSGs), and SSH access via the OCI CLI. Use whenever the user mentions Oracle Cloud, OCI, OCI instances, Oracle Cloud security lists or port forwarding, or wants to manage/SSH into an Oracle Cloud server — even if they don't explicitly say "OCI".
---

# Oracle Cloud Infrastructure (OCI) Management

Manage OCI compute instances, networking rules, and SSH access through the OCI CLI. All operations use the local OCI CLI configured with API key authentication.

## Prerequisites

### OCI CLI installation

```bash
which oci && oci --version
# If not installed:
# brew install oci-cli  (macOS)
```

### Config file

OCI CLI reads `~/.oci/config` by default. A typical config:

```ini
[DEFAULT]
user=ocid1.user.oc1..aaaaaaaa...
fingerprint=xx:xx:xx:xx:xx:xx:xx:xx:xx:xx:xx:xx:xx:xx:xx:xx
key_file=/Users/<user>/.oci/oci_api_key.pem
tenancy=ocid1.tenancy.oc1..aaaaaaaa...
region=us-phoenix-1
```

Verify auth:

```bash
oci iam region list
# Should return a JSON array of regions
```

### Key identifiers

Most OCI CLI commands require a **Compartment ID**. The tenancy OCID itself acts as the root compartment.

```bash
TENANCY="ocid1.tenancy.oc1..aaaaaaaa..."  # from ~/.oci/config
```

## Compute instances

### List all instances

```bash
oci compute instance list \
  --compartment-id "$TENANCY" \
  --query "data [*].{name:\"display-name\", state:\"lifecycle-state\", id:id, ip:\"primary-public-ip\"}" \
  --output table
```

If the table output is empty, try the root compartment (tenancy OCID) or check if instances are in a subcompartment. Use `--all` to search all compartments:

```bash
oci search resource structured-search \
  --search-query "query instance resources" \
  --output table
```

### Get instance details

```bash
oci compute instance get --instance-id "ocid1.instance.oc1.phx.aaaaaaaa..." | python3 -m json.tool
```

### List VNICs (to get public/private IPs)

```bash
oci compute instance list-vnics --instance-id "$INSTANCE_ID" \
  --query "data [*].{public:\"public-ip\", private:\"private-ip\", name:\"display-name\"}" \
  --output table
```

### Start / stop / reboot

```bash
oci compute instance action --instance-id "$INSTANCE_ID" --action START
oci compute instance action --instance-id "$INSTANCE_ID" --action STOP
oci compute instance action --instance-id "$INSTANCE_ID" --action RESET
```

### Get instance console connection

```bash
# Create console connection (for debugging boot issues)
oci compute instance-console-connection create --instance-id "$INSTANCE_ID"

# Get SSH console connection string
oci compute instance-console-connection list --instance-id "$INSTANCE_ID"
```

## Networking

### List VCNs

```bash
oci network vcn list --compartment-id "$TENANCY" --output table
```

### List security lists

```bash
oci network security-list list --compartment-id "$TENANCY" --vcn-id "$VCN_ID" --output table
```

### View ingress rules

```bash
oci network security-list get --security-list-id "$SL_ID" \
  --query "data.\"ingress-security-rules\"" \
  | python3 -m json.tool
```

### Add an ingress rule to a security list

OCI security list rules are append-only — you must include all existing rules plus the new one. Use a JSON file:

```bash
# Fetch existing rules, add your new rule, then update
oci network security-list get --security-list-id "$SL_ID" > /tmp/sl.json

# Build the update payload with all existing ingress rules + new rule
python3 -c "
import json
sl = json.load(open('/tmp/sl.json'))['data']
rules = sl['ingress-security-rules']
rules.append({
    'source': '0.0.0.0/0',
    'protocol': '6',           # TCP
    'destination-type': 'CIDR_BLOCK',
    'is-stateless': False,
    'tcp-options': {'destination-port-range': {'min': 443, 'max': 443}}
})
print(json.dumps(rules))
" > /tmp/ingress.json

oci network security-list update \
  --security-list-id "$SL_ID" \
  --ingress-security-rules file:///tmp/ingress.json
```

For **Network Security Groups (NSGs)**, the flow is simpler — each rule is added individually:

```bash
oci network security-group-rule add \
  --security-group-id "$NSG_ID" \
  --direction INGRESS \
  --protocol 6 \
  --source 0.0.0.0/0 \
  --source-type CIDR_BLOCK \
  --tcp-destination-port-range '{"min":443,"max":443}'
```

### List / add / remove port forwarding (NAT)

OCI does not have a direct "port forwarding" CLI command. Port forwarding to custom ports on an instance is typically done by:

1. **Security list / NSG ingress rule** — open the external port to 0.0.0.0/0 (or a specific CIDR)
2. **iptables on the instance** — forward external port to the actual service port

```bash
# On the instance (requires SSH access):
sudo iptables -t nat -A PREROUTING -p tcp --dport 38317 -j REDIRECT --to-port 8317
# Persist:
sudo apt install iptables-persistent -y
sudo netfilter-persistent save
```

If the instance has a cloud NAT or Load Balancer in front, use those services instead. For simple port remapping, iptables on the instance is the standard approach.

## SSH access

### SSH config pattern

OCI instances are typically accessed via SSH with a key pair. The user's `~/.ssh/config` usually has entries like:

```
Host oracle-server
    HostName 129.146.x.x
    User ubuntu
    IdentityFile /Users/<user>/.ssh/oci-arm-phx.key
    StrictHostKeyChecking no
```

### Find SSH key for an instance

OCI injects the public key from the instance's metadata. To check which key was used:

```bash
oci compute instance get --instance-id "$INSTANCE_ID" \
  --query "data.metadata.\"ssh_authorized_keys\""
```

### Connect via SSH

If the SSH config already has a Host alias, use it directly:

```bash
ssh oracle-server
```

Otherwise connect with explicit parameters:

```bash
ssh -i ~/.ssh/oci-key.pem ubuntu@<public-ip>
```

### Handle host key mismatch

If the instance was recreated (common with Always Free tier reclamation), the known_hosts entry will conflict:

```bash
ssh-keygen -R "<ip>"
# For custom ports:
ssh-keygen -R "[<ip>]:<port>"
```

## Common workflows

For detailed workflows, read the relevant reference file:

- **references/instance-networking.md** — opening ports on an OCI instance (security list + iptables), finding instance IPs, troubleshooting connectivity
- **references/always-free.md** — managing Always Free tier instances, preventing reclaim, and recovery

## Tips

- OCI CLI JSON output can be filtered with `--query` (JMESPath) and formatted with `--output table|json|text`.
- If a command returns empty output, check: (1) correct compartment ID, (2) the instance's region matches the config profile's region, (3) the user has permission for that resource type.
- The tenancy OCID (from `~/.oci/config`) is the root compartment ID — use it when you don't know the subcompartment.
- Instance public IPs are not in the `instance get` output; use `instance list-vnics` to get them.
- Always verify security list changes by testing connectivity with `curl` or `nc` from an external machine.
