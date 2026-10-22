# One terminal stays open while the Python supervisor owns every component.
$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location -LiteralPath $projectRoot
[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false)
$OutputEncoding = [Console]::OutputEncoding
$env:PYTHONUTF8 = "1"
$pythonExe = if ($env:OPENTRADING_PYTHON) { $env:OPENTRADING_PYTHON } else { Join-Path $projectRoot "venv\Scripts\python.exe" }
if (-not (Test-Path -LiteralPath $pythonExe)) {
    Write-Error "Project Python was not found. Set up venv with Python 3.12 according to README.md."
    exit 1
}
& $pythonExe -u -m scripts.dev_launcher @args
exit $LASTEXITCODE
