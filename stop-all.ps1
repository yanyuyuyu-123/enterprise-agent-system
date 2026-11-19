# 停止后端、定时任务、前端；Docker 数据库默认保留（加 -StopDatabase 一并停止）
param([switch]$StopDatabase)

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path

foreach ($port in 8000, 5173) {
    $conn = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue
    if ($conn) {
        Stop-Process -Id $conn.OwningProcess -Force -ErrorAction SilentlyContinue
        Write-Host "已停止端口 $port 的进程"
    }
}

Get-CimInstance Win32_Process -Filter "Name='python.exe'" |
    Where-Object { $_.CommandLine -match "app.tasks.scheduler" } |
    ForEach-Object {
        Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
        Write-Host "已停止定时任务"
    }

if ($StopDatabase) {
    Push-Location (Join-Path $Root "ticket-agent")
    docker compose stop
    Pop-Location
    Write-Host "已停止数据库容器"
} else {
    Write-Host "数据库容器保持运行（如需停止：.\stop-all.ps1 -StopDatabase）"
}

