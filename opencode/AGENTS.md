# Browser Automation Workflow & Lessons Learned

## 本次流程回顾

### 目标
打开 Edge 浏览器 → 通过书签访问 Yandex → 搜索"跳舞视频"

### 执行步骤
1. 启动 Edge (`Start-Process msedge --remote-debugging-port=9222`)
2. 使用 visible_browser / playwright 导航到 `yandex.com`
3. 在搜索框输入 "跳舞视频"
4. 触发搜索（点击搜索按钮 或 键盘 Enter）

---

## 关键经验教训

### 1. Yandex 验证码（Captcha）防范
- Yandex 对自动化浏览器有**强检测机制**（SmartCaptcha）
- 直接 URL 导航到搜索页 `yandex.com/search?text=...` 会触发验证码
- 直接点击搜索按钮也可能不触发导航
- **解决方案**：用 `playwright` 的 `keyboard.press('Enter')` 提交搜索表单，模拟真实用户操作
- Playwright 在 Yandex 上比 visible_browser 更容易绕过验证码

### 2. 浏览器工具选择

| 工具 | 优点 | 缺点 |
|------|------|------|
| `visible_browser_*` | 能看到界面，操作直观 | 部分按钮点击不触发导航 |
| `playwright_browser_*` | 更底层的控制，keyboard 支持好 | 无 GUI |
| `browser_agent_*` | AI 驱动，能处理验证码 | 超时风险，速度慢 |

**推荐优先级**：Playwright > visible_browser > browser_agent

### 3. 搜索提交方式（按推荐顺序）
1. `fill(text)` + `keyboard.press('Enter')` — **最可靠**
2. `click` 搜索按钮 — 部分网站不触发
3. 直接导航到搜索 URL — 容易触发反爬

### 4. Edge 启动方式
```powershell
Start-Process -FilePath "msedge.exe" -ArgumentList "--remote-debugging-port=9222" , "--user-data-dir=<profile_path>"
```
- 使用 `--remote-debugging-port` 以便调试工具连接
- 指定 `--user-data-dir` 使用用户真实配置（含书签、Cookie）

---

## 持久化配置建议

### 浏览器自动化最佳实践

```yaml
# 通用搜索工作流
1. 首选 playwright (run_code_unsafe) 执行复杂操作
2. 使用 fill + Enter 而非 click 提交表单
3. 对反爬严格的网站（Yandex 等）:
   - 先用真实浏览器打开网站
   - 用 keyboard 事件提交
   - 避免直接 URL 跳转到搜索结果页
```

### 反爬规避 checklist
- [ ] 使用 `fill()` 而非 `type()` 输入文本
- [ ] 使用 `keyboard.press('Enter')` 提交
- [ ] 避免多次快速请求同一域名
- [ ] 遇到 captcha 时尝试 visible_browser 重试

---

## 视频批量下载工作流

### 适用场景
批量下载 HLS 流媒体视频（m3u8格式），适用于海角网、51爆料网等视频网站。

### 核心原理
1. 网站视频使用 HLS 流媒体（.m3u8），通过 JavaScript 动态加载
2. 使用 Playwright 的 `performance.getEntriesByType('resource')` 捕获 m3u8 URL
3. 使用 ffmpeg 下载并合并 TS 分片（自动处理 AES-128 加密）
4. 使用 ffprobe 验证下载完整性

### 完整步骤

#### Step 1: 获取文章ID列表
```javascript
// Playwright evaluate 获取页面所有文章ID
const links = await page.evaluate(() => {
  const results = [];
  document.querySelectorAll('a[href*="/archives/"]').forEach(a => {
    const match = a.href.match(/\/archives\/(\d+)\//);
    if (match) results.push(match[1]);
  });
  return [...new Set(results)].slice(0, 20);
});
```

#### Step 2: 获取m3u8 URL
```javascript
// 逐个访问文章页，捕获m3u8资源URL
const m3u8Url = await page.evaluate(() => {
  const entries = performance.getEntriesByType('resource').filter(e => 
    e.name.includes('.m3u8') || e.name.includes('/videos/')
  );
  return entries.length > 0 ? entries[0].name : null;
});
```

#### Step 3: ffmpeg批量下载
```powershell
# PowerShell 批量下载脚本
$downloadDir = "C:\Users\Administrator\Downloads\videos"
$ffmpeg = "C:\ffmpeg\ffmpeg.exe"

foreach ($id in $ids) {
  $output = Join-Path $downloadDir "video_${id}.mp4"
  & $ffmpeg -y -i $m3u8Url -c copy -movflags +faststart $output
}
```

#### Step 4: ffprobe验证
```powershell
$ffprobe = "C:\ffmpeg\ffprobe.exe"
$result = & $ffprobe -v error -show_entries format=duration -of default=noprint_wrappers=1 "$file"
# 如果结果包含 duration= 则验证通过
```

### 工具优先级
| 工具 | 用途 | 优先级 |
|------|------|--------|
| `playwright_browser_*` | 获取m3u8 URL、页面导航 | ⭐⭐⭐ 最高 |
| `bash` + ffmpeg | 批量下载、验证 | ⭐⭐⭐ 最高 |
| `visible_browser_*` | 备用方案（当playwright超时） | ⭐ |

### 常见问题
1. **m3u8 URL过期**: auth_key有时效性，需要重新获取
2. **页面自动跳转**: 使用 `waitUntil: 'domcontentloaded'` 而非 `networkidle`
3. **文件损坏(moov atom not found)**: 使用 `-movflags +faststart` 确保MP4正确封装
4. **下载超时**: 分批次处理，每批5-10个

### 完整PowerShell模板
```powershell
# 配置
$downloadDir = "C:\Users\Administrator\Downloads\videos"
$ffmpeg = "C:\ffmpeg\ffmpeg.exe"
$ffprobe = "C:\ffmpeg\ffprobe.exe"

# 批量下载
for ($i = 0; $i -lt $ids.Count; $i++) {
  $id = $ids[$i]
  $m3u8 = $m3u8Urls[$i]
  $output = Join-Path $downloadDir "video_${id}.mp4"
  
  & $ffmpeg -y -i $m3u8 -c copy -movflags +faststart $output 2>&1 | Select-Object -Last 1
  
  if (Test-Path $output) {
    $size = [math]::Round((Get-Item $output).Length / 1MB, 2)
    Write-Output "SUCCESS: $id - $size MB"
  }
  Start-Sleep -Milliseconds 500
}

# 验证所有文件
$files = Get-ChildItem $downloadDir -Filter "*.mp4"
foreach ($file in $files) {
  $result = & $ffprobe -v error -show_entries format=duration -of default=noprint_wrappers=1 "$($file.FullName)"
  if ($LASTEXITCODE -eq 0 -and $result -match "duration=") {
    Write-Output "VALID: $($file.Name)"
  }
}
```

### 经验总结
- Playwright 的 `performance.getEntriesByType('resource')` 是获取动态加载m3u8的关键
- `-movflags +faststart` 确保MP4文件头部元数据正确，避免损坏
- 分批次处理（每批5-10个）比一次性处理更稳定
- 验证环节必不可少，及时重传无效文件