@echo off
title Stop Ticket System - Full Shutdown

echo [1/4] Stopping app processes (8000 / 5173 / scheduler) ...
powershell -NoProfile -Command "$ports=8000,5173; foreach($p in $ports){ Get-NetTCPConnection -LocalPort $p -State Listen -ErrorAction SilentlyContinue | Select-Object -ExpandProperty OwningProcess -Unique | ForEach-Object { Stop-Process -Id $_ -Force -ErrorAction SilentlyContinue } }; Get-CimInstance Win32_Process | Where-Object { $_.Name -eq 'python.exe' -and $_.CommandLine -match 'app.tasks.scheduler' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }"

echo [2/4] Stopping containers ...
docker stop kangban-funasr ticket-postgres ticket-redis >nul 2>&1

echo [3/4] Quitting Docker Desktop ...
powershell -NoProfile -Command "Get-Process 'Docker Desktop' -ErrorAction SilentlyContinue | ForEach-Object { $_.CloseMainWindow() | Out-Null }"
ping -n 9 127.0.0.1 >nul
powershell -NoProfile -Command "Get-Process 'Docker Desktop' -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue"

echo [4/4] Shutting down WSL ...
wsl --shutdown

echo.
echo [OK] App, containers, Docker and WSL all stopped. Memory released.
ping -n 4 127.0.0.1 >nul
exit
