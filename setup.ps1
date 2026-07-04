<#
.SYNOPSIS
  一键恢复 dotfiles 配置到新电脑
.DESCRIPTION
  从 GitHub 拉取配置，部署到正确位置，安装依赖
#>

$ErrorActionPreference = "Stop"
$repoUrl = "https://github.com/xiaomaosiyangyuan/dotfiles.git"
$dotfiles = "$env:USERPROFILE\dotfiles"

Write-Host "=== 1/6: 克隆配置仓库 ===" -ForegroundColor Cyan
if (-not (Test-Path $dotfiles)) {
    git clone $repoUrl $dotfiles
} else {
    git -C $dotfiles pull
}

Write-Host "=== 2/6: 部署 opencode 配置 ===" -ForegroundColor Cyan
# 合并 .config/opencode
$configDir = "$env:USERPROFILE\.config\opencode"
if (-not (Test-Path $configDir)) { New-Item -ItemType Directory $configDir -Force | Out-Null }
Copy-Item "$dotfiles\opencode\.config\opencode.json" "$configDir\opencode.json" -Force
Copy-Item "$dotfiles\opencode\.gitignore" "$configDir\.gitignore" -Force

# 部署 MCP 脚本
$mcpDir = "$configDir\mcp"
if (-not (Test-Path $mcpDir)) { New-Item -ItemType Directory $mcpDir -Force | Out-Null }
Copy-Item "$dotfiles\opencode\mcp\playwright_mcp_server.py" "$mcpDir\playwright_mcp_server.py" -Force

# 合并 .opencode
$opencodeDir = "$env:USERPROFILE\.opencode"
if (-not (Test-Path $opencodeDir)) { New-Item -ItemType Directory $opencodeDir -Force | Out-Null }
Copy-Item "$dotfiles\opencode\.opencode\opencode.json" "$opencodeDir\opencode.json" -Force

# 部署 AGENTS.md
Copy-Item "$dotfiles\opencode\AGENTS.md" "$env:USERPROFILE\AGENTS.md" -Force

# 部署 DNS 修复脚本
Copy-Item "$dotfiles\opencode\.dns-fix.ps1" "$env:USERPROFILE\.dns-fix.ps1" -Force

Write-Host "=== 3/6: 安装 9router ===" -ForegroundColor Cyan
npm install -g 9router
New-Item -ItemType Directory "$env:APPDATA\9router\mitm" -Force | Out-Null
Copy-Item "$dotfiles\9router\aliases.json" "$env:APPDATA\9router\mitm\aliases.json" -Force

Write-Host "=== 4/6: 安装 opencode 插件依赖 ===" -ForegroundColor Cyan
if (Test-Path "$configDir\package.json") {
    Set-Location $configDir; npm install
}
if (Test-Path "$opencodeDir\package.json") {
    Set-Location $opencodeDir; npm install
}

Write-Host "=== 5/6: 部署开机自启任务 ===" -ForegroundColor Cyan
# 开机自动拉取最新配置
$pullAction = New-ScheduledTaskAction -Execute "powershell.exe" -Argument "-NoProfile -ExecutionPolicy Bypass -Command `"git -C $dotfiles pull`""
$pullTrigger = New-ScheduledTaskTrigger -AtStartup
$pullSettings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable
$pullPrincipal = New-ScheduledTaskPrincipal -UserId "SYSTEM" -LogonType ServiceAccount -RunLevel Highest
Register-ScheduledTask -TaskName "Dotfiles-AutoPull" -Action $pullAction -Trigger $pullTrigger -Settings $pullSettings -Principal $pullPrincipal -Force

# 部署 DNS 修复计划任务
$dnsAction = New-ScheduledTaskAction -Execute "powershell.exe" -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$env:USERPROFILE\.dns-fix.ps1`""
Register-ScheduledTask -TaskName "ClashVerge-DNSFix" -Action $dnsAction -Trigger $pullTrigger -Settings $pullSettings -Principal $pullPrincipal -Force

Write-Host "=== 6/6: 部署文件改动自动推送 ===" -ForegroundColor Cyan
# 安装 watcher 开机自启
$watchScript = "$dotfiles\git-watch.ps1"
$watchAction = New-ScheduledTaskAction -Execute "powershell.exe" -Argument "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$watchScript`""
$logonTrigger = New-ScheduledTaskTrigger -AtLogOn
Register-ScheduledTask -TaskName "Dotfiles-AutoWatch" -Action $watchAction -Trigger $logonTrigger -Settings $pullSettings -Force

Write-Host "`n=== 全部完成！===" -ForegroundColor Green
Write-Host "请设置环境变量（否则 opencode 会报 API Key 缺失）：" -ForegroundColor Yellow
Write-Host "  setx AGNES_API_KEY     <你的 Agnes Key>" -ForegroundColor Gray
Write-Host "  setx MODELSCOPE_API_KEY <你的 ModelScope Key>" -ForegroundColor Gray
Write-Host "  setx SENSENOVA_API_KEY  <你的 SenseNova Key>" -ForegroundColor Gray
Write-Host "  setx 9ROUTER_API_KEY    sk_9router_admin_72359940ae41489e" -ForegroundColor Gray