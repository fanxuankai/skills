# skills

Personal AI agent skills for ZCode / Claude Code / Codex and any Agent-Skills-standard harness.

## Skills

### cloudflare

Manage Cloudflare DNS records, tunnels (cloudflared), and zone settings via the Cloudflare API. Use whenever the user mentions Cloudflare, CF tunnels, cloudflared, DNS records on CF, or wants to route traffic through Cloudflare to an origin server.

### oci

Manage Oracle Cloud Infrastructure (OCI) compute instances, networking (VCN/security lists/NSGs), and SSH access via the OCI CLI. Use whenever the user mentions Oracle Cloud, OCI, OCI instances, or wants to manage/SSH into an Oracle Cloud server.

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

## Installation

### Clone into your agents directory

```bash
git clone https://github.com/fanxuankai/skills.git ~/.agents/skills
```

### Via skills.sh

```bash
npx skills@latest add fanxuankai/skills
```

## License

MIT
