# skills

个人日常使用的 agent skills 沉淀。把反复用到的操作、容易忘的 ID、容易踩的坑、容易拼错的命令固化下来，让 agent 直接照着干。

不追求覆盖面，只放自己用过的。每个 skill 是一个 `SKILL.md` 加若干 `references/` 工作流，agent 按需加载。

## Install

```bash
git clone https://github.com/fanxuankai/skills.git ~/.agents/skills
```

或通过 skills.sh：

```bash
npx skills@latest add fanxuankai/skills
```

## Skills

**cloudflare** — 通过 Cloudflare REST API 管理 DNS 记录、Tunnel（`cloudflared`）和 zone 设置。始终用 scope 受限的 API token，不用 Global API Key。涵盖记录增删改、tunnel 创建与 DNS 接线、`cloudflared` 安装与 systemd、改名、502 排查。

**oci** — 通过 OCI CLI 管理 Oracle Cloud 计算实例、网络（VCN / 安全列表 / NSG）和 SSH 访问。涵盖实例与 VNIC IP 查询、启停重启、开端口（ingress 规则 + iptables）、控制台连接、Always Free 回收后的 host-key 处理。

**prokvm** — 通过逆向出的 web API 操作 ProKvm 会员中心（自签 HTTPS、无官方 API 文档）。涵盖登录、抓取服务器列表（分页 + HTML 内嵌 JSON）、解析升级页、带 PJAX 头的批量带宽升级，以及面板升级后重新逆向的工作流。凭据一律从环境变量读取，不硬编码。

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
└── prokvm/
    ├── SKILL.md
    ├── references/
    │   └── reverse-engineer-panel.md
    └── scripts/
        └── upgrade_bandwidth.py
```

## License

MIT
