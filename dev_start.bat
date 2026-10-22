@echo off
setlocal
chcp 65001 >nul
title OpenTrading - Unified Console

set "SCRIPT_DIR=%~dp0"
set "PS_SCRIPT=%SCRIPT_DIR%dev_start.ps1"
set "PAUSE_ON_SUCCESS=0"
if /i "%~1"=="--pause" set "PAUSE_ON_SUCCESS=1"
cd /d "%SCRIPT_DIR%"

if not exist "%PS_SCRIPT%" (
  echo dev_start.ps1 not found: "%PS_SCRIPT%"
  if /i not "%~1"=="--no-pause" pause
  exit /b 1
)

echo [OpenTrading] Starting launcher from "%SCRIPT_DIR%"
powershell -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%PS_SCRIPT%" %*
set "EXIT_CODE=%ERRORLEVEL%"

if not "%EXIT_CODE%"=="0" (
  echo [OpenTrading] Launcher failed with exit code %EXIT_CODE%.
  if /i not "%~1"=="--no-pause" pause
) else (
  echo [OpenTrading] Launcher command finished.
  if "%PAUSE_ON_SUCCESS%"=="1" pause
)

exit /b %EXIT_CODE%
