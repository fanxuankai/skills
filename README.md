# skills

Agent skills for managing real infrastructure — Cloudflare and Oracle Cloud — from any Agent-Skills-compatible harness (ZCode, Claude Code, Codex).

These skills exist so you don't have to paste API docs into a chat every time you want to move a DNS record, stand up a Cloudflare Tunnel, or open a port on an OCI instance. Each skill is a self-contained `SKILL.md` plus reference workflows that an agent loads on demand and acts on directly.

## Skills

### cloudflare

Manage Cloudflare DNS records, Tunnels (`cloudflared`), and zone settings through the Cloudflare REST API.

Use it when you want to:

- Create, list, or update DNS records (A / CNAME, proxied vs. grey-cloud)
- Stand up a Cloudflare Tunnel so an origin behind NAT/firewall can serve HTTPS without a public IP or its own SSL cert
- Replace a reverse-proxy middleman (e.g. an nginx box doing SSL termination) with a tunnel
- Rename a tunnel, verify ingress, or debug a 502

It always authenticates with a scoped **API token** — never the Global API Key — and walks the agent through fetching the Zone/Account IDs it needs. Detailed end-to-end workflows live in `references/dns-migration.md` and `references/tunnel-setup.md`.

### oci

Manage Oracle Cloud Infrastructure compute instances, networking (VCN, security lists, NSGs), and SSH access through the OCI CLI.

Use it when you want to:

- List instances, find their public/private IPs, or start/stop/reboot them
- Open a port on an instance (security-list or NSG ingress rule, plus iptables on the box for remapping)
- Get a console connection for boot debugging
- SSH into an instance, including recovering from a host-key mismatch after an Always Free reclamation

It assumes the OCI CLI is installed and `~/.oci/config` is set up with API-key auth. It leans on the tenancy OCID as the root compartment when you don't know the subcompartment, and reminds the agent that public IPs come from `instance list-vnics`, not `instance get`. Reference workflows: `references/instance-networking.md`, `references/always-free.md`.

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

Each skill follows the Agent-Skills standard: a `SKILL.md` with a YAML front matter (`name`, `description`) that the harness matches against, plus optional `references/` files the agent reads only when a workflow needs them.

## Installation

### Clone into your agents directory

```bash
git clone https://github.com/fanxuankai/skills.git ~/.agents/skills
```

This drops the skills where ZCode, Claude Code, and Codex already look. Restart your agent (or start a new session) and the `cloudflare` and `oci` skills become model-invocable.

### Via skills.sh

```bash
npx skills@latest add fanxuankai/skills
```

Pick the skills you want and the harness you use; skills.sh copies editable files into your project.

### Prerequisites per skill

The skills don't install the underlying tooling for you — they expect it to be present:

- **cloudflare** — a Cloudflare API token in `$CLOUDFLARE_API_TOKEN` (or your shell config) with at minimum Zone → DNS → Edit and Cloudflare Tunnel → Edit. `cloudflared` needs to be installed on any origin you point a tunnel at.
- **oci** — the OCI CLI (`brew install oci-cli` on macOS) and a valid `~/.oci/config` with API-key auth. Verify with `oci iam region list`.

## License

MIT
