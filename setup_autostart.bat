@echo off
set STARTUP_DIR=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup
set LAUNCHER_VBS=%STARTUP_DIR%\BrahmaEchoWorker.vbs
set TARGET_VBS=%~dp0start_worker_silent.vbs

if "%1"=="disable" goto disable
if "%1"=="remove" goto disable

:enable
echo ==========================================================
echo    Enabling Brahma Echo Background Autostart at Boot...
echo ==========================================================
(
echo Set shell = CreateObject("WScript.Shell"^)
echo shell.Run "wscript.exe ""%TARGET_VBS%""", 0, False
) > "%LAUNCHER_VBS%"

if exist "%LAUNCHER_VBS%" (
    echo [SUCCESS] Brahma Echo auto-start enabled!
    echo Launcher placed at: %LAUNCHER_VBS%
    echo It will now run silently whenever Windows starts.
) else (
    echo [ERROR] Failed to write startup launcher.
)
goto end

:disable
if exist "%LAUNCHER_VBS%" (
    del /f /q "%LAUNCHER_VBS%"
    echo [SUCCESS] Brahma Echo auto-start disabled.
) else (
    echo Auto-start is already disabled.
)

:end
echo.
pause
