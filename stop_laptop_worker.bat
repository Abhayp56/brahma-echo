@echo off
title Stop Brahma Echo Laptop Worker
echo ==========================================================
echo        Stopping Brahma Echo Laptop Task Worker...
echo ==========================================================
powershell -NoProfile -ExecutionPolicy Bypass -Command "Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like '*laptop_worker.py*' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue; Write-Host 'Stopped Worker Process (PID:' $_.ProcessId ')' }"
echo.
echo Worker stopped successfully.
timeout /t 2 >nul
