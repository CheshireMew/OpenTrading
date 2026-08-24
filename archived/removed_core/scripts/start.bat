@echo off
setlocal

set "ROOT_DIR=%~dp0.."
set "LAUNCHER=%ROOT_DIR%\dev_start.bat"

if not exist "%LAUNCHER%" (
  echo Launcher not found: "%LAUNCHER%"
  exit /b 1
)

call "%LAUNCHER%" %*
exit /b %ERRORLEVEL%
