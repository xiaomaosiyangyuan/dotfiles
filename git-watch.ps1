$dotfiles = "$env:USERPROFILE\dotfiles"
$logFile = "$env:TEMP\dotfiles-watch.log"
$cooldown = @{}

function Write-Log { param($msg) "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') $msg" | Out-File $logFile -Append }

Write-Log "Watcher started"

while ($true) {
    try {
        git -C $dotfiles add -A 2>&1 | Out-Null
        $status = git -C $dotfiles status --porcelain 2>&1
        if ($status -and $status -isnot [string]) { $status = $status -join "`n" }

        if ($status.Trim()) {
            $lines = ($status -split "`n").Count
            Write-Log "Detected $lines changed files"

            if (-not $cooldown["lastPush"] -or ((Get-Date) - $cooldown["lastPush"]).TotalMinutes -ge 5) {
                $msg = "auto-sync $(Get-Date -Format 'yyyy-MM-dd HH:mm')"
                git -C $dotfiles add -A 2>&1 | Out-Null
                git -C $dotfiles commit -m $msg 2>&1 | Out-Null

                $pushResult = git -C $dotfiles push origin main 2>&1
                if ($?) {
                    Write-Log "Pushed: $msg"
                    $cooldown["lastPush"] = Get-Date
                } else {
                    Write-Log "Push failed: $pushResult"
                }
            } else {
                Write-Log "Cooldown, skipping push (last was $(($cooldown["lastPush"])))"
            }
        }
    } catch {
        Write-Log "Error: $_"
    }
    Start-Sleep -Seconds 60
}