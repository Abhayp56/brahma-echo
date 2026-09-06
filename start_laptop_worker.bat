@echo off
title Brahma Echo — Laptop Task Worker
echo ==========================================================
echo       Starting Brahma Echo Laptop Task Worker...
echo ==========================================================
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" (
    echo Using virtual environment Python...
    .venv\Scripts\python.exe laptop_worker.py
) else (
    echo Using system Python...
    python laptop_worker.py
)
if errorlevel 1 (
    echo.
    echo Worker encountered an error. Press any key to close.
    pause
)
