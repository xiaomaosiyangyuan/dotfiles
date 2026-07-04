# dotfiles

一键恢复 opencode + 9router + MCP 浏览器工具 配置到新电脑。

## 在新电脑上恢复

```powershell
# 1. 安装依赖
winget install Git.Git
winget install OpenJS.NodeJS

# 2. 运行一键恢复脚本
powershell -NoProfile -ExecutionPolicy Bypass -Command "iex ((New-Object Net.WebClient).DownloadString('https://raw.githubusercontent.com/xiaomaosiyangyuan/dotfiles/main/setup.ps1'))"

# 3. 设置环境变量（API Keys）
setx AGNES_API_KEY     <你的 Agnes Key>
setx MODELSCOPE_API_KEY <你的 ModelScope Key>
setx SENSENOVA_API_KEY  <你的 SenseNova Key>
setx 9ROUTER_API_KEY    sk_9router_admin_72359940ae41489e
```

## 包含的配置

| 项目 | 位置 |
|------|------|
| opencode 主配置 | `~/.config/opencode/opencode.json` |
| opencode 9router 配置 | `~/.opencode/opencode.json` |
| AGENTS.md | `~/AGENTS.md` |
| DNS 修复脚本 | `~/.dns-fix.ps1` |
| Playwright MCP 服务 | `~/.config/opencode/mcp/playwright_mcp_server.py` |
| 9router 别名配置 | `%APPDATA%/9router/mitm/aliases.json` |

## 开机自动行为

- `Dotfiles-AutoPull` — 开机自动 `git pull` 获取最新配置
- `Dotfiles-AutoWatch` — 登录后后台监听文件变化，5分钟内自动 `commit + push`
- `ClashVerge-DNSFix` — 开机修复 IPv6 DNS 被路由器 `fe80::1` 拒绝查询的问题