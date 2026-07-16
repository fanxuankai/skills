# Always Free Tier Management

Managing OCI Always Free instances: preventing reclaim, recovery, and common pitfalls.

## Always Free limits

Always Free tier includes:
- 2 AMD VM instances (1/8 OCPU, 1GB RAM each)
- 4 ARM (Ampere A1) instances (total 4 OCPU, 24GB RAM)
- 2 Block Volumes (200GB total)
- 10GB Object Storage
- 1 VCN + 2 subnets

Resources exceeding Always Free limits will be billed. Arm Ampere A1 instances can be created as a single 4-core/24GB instance or split into multiple smaller instances.

## Preventing instance reclaim

Oracle reclaims Always Free **idle** instances. An instance is considered idle if, for a 7-day period:
- CPU utilization is below 20%
- Network traffic is below 20%
- Memory utilization is below 20% (always met for 1GB instances)

To prevent reclaim, keep some activity on the instance:

```bash
# Lightweight cron job to generate CPU activity every hour
(crontab -l 2>/dev/null; echo "0 * * * * /usr/bin/dd if=/dev/zero of=/dev/null bs=1M count=100 2>/dev/null") | crontab -
```

Or run a lightweight service that generates periodic traffic.

## Checking instance status

```bash
oci compute instance list --compartment-id "$TENANCY" \
  --query "data [*].{name:\"display-name\", state:\"lifecycle-state\", shape:\"shape\"}" \
  --output table
```

States: `RUNNING`, `STOPPED`, `STOPPING`, `STARTING`, `TERMINATED`.

## Recovering a stopped/terminated instance

If an Always Free instance was reclaimed:
- **Stopped** (not terminated) — restart it:
  ```bash
  oci compute instance action --instance-id "$INSTANCE_ID" --action START
  ```
- **Terminated** — the instance and its boot volume are gone. You must recreate it. Custom block volumes may survive if they were not the boot volume.

## Creating an ARM (Ampere A1) instance

ARM instances are popular because they offer the most resources for free. Shape: `VM.Standard.A1.Flex`.

```bash
oci compute instance launch \
  --compartment-id "$TENANCY" \
  --availability-domain "AD-1" \
  --shape "VM.Standard.A1.Flex" \
  --shape-config '{"ocpus":4,"memory-in-gbs":24}' \
  --image-id "$IMAGE_ID" \
  --subnet-id "$SUBNET_ID" \
  --assign-public-ip true \
  --ssh-authorized-keys file:///tmp/pubkey
```

Finding the latest Ubuntu ARM image:

```bash
oci compute image list \
  --compartment-id "$TENANCY" \
  --operating-system "Canonical Ubuntu" \
  --operating-system-version "22.04" \
  --shape "VM.Standard.A1.Flex" \
  --sort-by TIMECREATED \
  --sort-order DESC \
  --limit 1 \
  --query "data [0].id"
```

## SSH on ARM instances

ARM instances use `ubuntu` as the default user (for Ubuntu images). The SSH key is set at launch time via `--ssh-authorized-keys`.

## Common pitfalls

- **Out of capacity**: ARM shapes sometimes return "Out of host capacity" during creation. Retry — OCI releases capacity periodically. A script that retries every few minutes works.
- **Region**: Always Free resources must be in the region specified in `~/.oci/config`. Resources in other regions may not be free.
- **Boot volume size**: Default boot volume is 47GB. If you have 2 instances, that's 94GB — close to the 200GB block volume limit. Keep boot volumes small unless you need the space.
- **Upgrading to paid**: If you upgrade to a paid account, your Always Free resources keep running for free, but you can also create paid resources. Downgrading back to free is not always possible.
