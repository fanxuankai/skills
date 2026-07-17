# Infrastructure Skills For Real Engineers

A small collection of agent skills for managing real infrastructure — Cloudflare and Oracle Cloud. Small, composable, and loaded on demand so the agent acts on working commands instead of hallucinating API shapes.

## Quickstart

```bash
npx skills@latest add fanxuankai/skills
```

Pick the skills you want and the agent you use. Or clone directly:

```bash
git clone https://github.com/fanxuankai/skills.git ~/.agents/skills
```

## Why These Skills Exist

Every time you ask an agent to move a DNS record or open a port, it forgets which ID goes where, reaches for the Global API Key, or invents an endpoint that doesn't exist. These skills encode the exact commands and the gotchas — scoped API tokens, tenancy OCID as the root compartment, public IPs coming from `list-vnics`, the catch-all ingress rule cloudflared refuses to start without — so it gets it right the first time.

Each skill is a `SKILL.md` with YAML front matter the harness matches against, plus `references/` workflows the agent reads only when a task needs them.

## Reference

### cloudflare

Manage Cloudflare DNS records, Tunnels (`cloudflared`), and zone settings through the REST API — always with a scoped API token, never the Global API Key. Covers record CRUD, tunnel creation and DNS wiring, `cloudflared` install + systemd, renaming, and debugging 502s.

### oci

Manage Oracle Cloud compute instances, networking (VCN, security lists, NSGs), and SSH access through the OCI CLI. Covers listing instances and VNIC IPs, start/stop/reboot, opening ports (ingress rule + iptables), console connections, and recovering from host-key mismatches after Always Free reclamation.

## Structure

```
skills/
├── cloudflare/
│   ├── SKILL.md
│   └── references/
│       ├── dns-migration.md
│       └── tunnel-setup.md
└── oci/
    ├── SKILL.md
    └── references/
        ├── instance-networking.md
        └── always-free.md
```

## License

MIT
