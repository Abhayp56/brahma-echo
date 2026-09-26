@echo off
title Brahma Hermes Worker Agent Node
echo ========================================================
echo   Starting Hermes Agent Worker Node for Brahma Web AI
echo ========================================================
echo.

cd /d "%~dp0"
if exist "hermes-agent-main\hermes_brahma_worker.py" (
    cd hermes-agent-main
    python hermes_brahma_worker.py
) else if exist "hermes_brahma_worker.py" (
    python hermes_brahma_worker.py
) else (
    echo [ERROR] Could not find hermes_brahma_worker.py!
    pause
    exit /b 1
)

pause
