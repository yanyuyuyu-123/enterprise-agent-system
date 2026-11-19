# 一键启动：Docker(PostgreSQL/Redis) -> 后端 API -> 定时任务 -> 前端
# 用法：右键“使用 PowerShell 运行”，或在 PowerShell 中执行 .\start-all.ps1
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$Backend = Join-Path $Root "ticket-agent"
$Frontend = Join-Path $Root "ticket-web"
$Python = Join-Path $Backend ".venv\Scripts\python.exe"
# 免安装版 Node 目录；换成你自己的路径即可
$NodeHome = "C:\DevTools\NodeJS"

function Test-Port($port) {
    $null -ne (Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue)
}

# 静默执行外部命令并返回退出码，避免 docker 往 stderr 写日志时被 Stop 策略中断
function Invoke-Quiet([scriptblock]$Command) {
    $previous = $ErrorActionPreference
    $ErrorActionPreference = "SilentlyContinue"
    & $Command *> $null
    $code = $LASTEXITCODE
    $ErrorActionPreference = $previous
    return $code
}

Write-Host "[1/4] 检查 Docker..." -ForegroundColor Cyan
if ((Invoke-Quiet { docker info }) -ne 0) {
    Write-Host "  Docker 未运行，正在启动 Docker Desktop（首次约需 1 分钟）..."
    Start-Process "$env:LOCALAPPDATA\Programs\DockerDesktop\Docker Desktop.exe"
    $ready = $false
    for ($i = 0; $i -lt 30; $i++) {
        Start-Sleep -Seconds 5
        if ((Invoke-Quiet { docker info }) -eq 0) { $ready = $true; break }
    }
    if (-not $ready) { throw "Docker 启动超时，请手动打开 Docker Desktop 后重试" }
}
Push-Location $Backend
docker compose up -d
Pop-Location
Write-Host "  等待 PostgreSQL 就绪..."
for ($i = 0; $i -lt 20; $i++) {
    if ((Invoke-Quiet { docker exec ticket-postgres pg_isready -U ticket }) -eq 0) { break }
    Start-Sleep -Seconds 2
}

Write-Host "[2/4] 启动后端（8000）..." -ForegroundColor Cyan
if (Test-Port 8000) {
    Write-Host "  已在运行，跳过"
} else {
    $env:PYTHONUTF8 = "1"
    $env:OMP_NUM_THREADS = "4"
    Start-Process -FilePath $Python `
        -ArgumentList "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8000" `
        -WorkingDirectory $Backend -WindowStyle Hidden
    for ($i = 0; $i -lt 30; $i++) {
        Start-Sleep -Seconds 2
        try {
            Invoke-WebRequest "http://127.0.0.1:8000/health" -UseBasicParsing -TimeoutSec 3 *> $null
            break
        } catch { }
    }
}

Write-Host "[3/4] 启动定时任务..." -ForegroundColor Cyan
$scheduler = Get-CimInstance Win32_Process -Filter "Name='python.exe'" |
    Where-Object { $_.CommandLine -match "app.tasks.scheduler" }
if ($scheduler) {
    Write-Host "  已在运行，跳过"
} else {
    Start-Process -FilePath $Python -ArgumentList "-m", "app.tasks.scheduler" `
        -WorkingDirectory $Backend -WindowStyle Hidden
}

Write-Host "[4/4] 启动前端（5173）..." -ForegroundColor Cyan
if (Test-Port 5173) {
    Write-Host "  已在运行，跳过"
} else {
    $npm = Join-Path $NodeHome "npm.cmd"
    if (-not (Test-Path $npm)) {
        throw "找不到 npm：$npm，请修改脚本里的 `$NodeHome"
    }
    Start-Process -FilePath "cmd.exe" -ArgumentList "/c", "`"$npm`" run dev" `
        -WorkingDirectory $Frontend -WindowStyle Hidden
}

Write-Host ""
Write-Host "启动完成：" -ForegroundColor Green
Write-Host "  前端  http://127.0.0.1:5173"
Write-Host "  接口  http://127.0.0.1:8000/docs"
Write-Host "  登录  工号 A0001"
Write-Host ""
Write-Host "停止：关闭对应窗口，或运行 .\stop-all.ps1" -ForegroundColor DarkGray

