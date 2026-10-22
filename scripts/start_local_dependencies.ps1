# Start the required database service without opening component terminals.
$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $projectRoot
[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false)
$OutputEncoding = [Console]::OutputEncoding

function Get-OpenTradingEnvValue {
    param(
        [string]$Name,
        [string]$DefaultValue = ""
    )

    $processValue = [Environment]::GetEnvironmentVariable($Name, "Process")
    if ($processValue) {
        return $processValue
    }
    $envPath = Join-Path $projectRoot ".env"
    if (Test-Path $envPath) {
        $line = Get-Content -LiteralPath $envPath | Where-Object {
            $_ -match "^\s*$([regex]::Escape($Name))\s*="
        } | Select-Object -Last 1
        if ($line) {
            return (($line -split "=", 2)[1]).Trim().Trim('"').Trim("'")
        }
    }
    return $DefaultValue
}

function Start-OpenTradingServiceElevated {
    param(
        [string]$Label,
        [string]$ServiceName
    )

    $escapedName = $ServiceName.Replace("'", "''")
    $command = "Start-Service -Name '$escapedName' -ErrorAction Stop"
    $encodedCommand = [Convert]::ToBase64String([Text.Encoding]::Unicode.GetBytes($command))
    Write-Host "$Label needs Windows administrator permission. Confirm the UAC prompt to start '$ServiceName'; OpenTrading itself will continue without administrator rights." -ForegroundColor Yellow
    try {
        $process = Start-Process powershell.exe -Verb RunAs -WindowStyle Hidden -Wait -PassThru -ArgumentList @(
            "-NoLogo",
            "-NoProfile",
            "-EncodedCommand",
            $encodedCommand
        )
    }
    catch {
        throw "Administrator permission was not granted. Start Windows service '$ServiceName' manually, or run dev_start.bat again and accept the UAC prompt."
    }
    if ($process.ExitCode -ne 0) {
        throw "Windows could not start $Label service '$ServiceName' (elevated process exit code $($process.ExitCode)). Check the service in services.msc, then run dev_start.bat again."
    }
}

function Start-OpenTradingDependencyService {
    param(
        [string]$Label,
        [string]$ConfiguredName,
        [string]$DiscoveryPattern,
        [bool]$Required
    )

    $service = $null
    if ($ConfiguredName) {
        $service = Get-Service -Name $ConfiguredName -ErrorAction SilentlyContinue
    }
    if (-not $service) {
        $service = Get-Service -ErrorAction SilentlyContinue | Where-Object {
            $_.Name -like $DiscoveryPattern
        } | Select-Object -First 1
    }
    if (-not $service) {
        $message = "$Label Windows service was not found."
        if ($Required) { throw $message }
        Write-Host "$message The application will use its built-in fallback." -ForegroundColor DarkYellow
        return
    }
    if ($service.Status -eq "Running") {
        Write-Host "$Label service is already running ($($service.Name))." -ForegroundColor DarkGray
        return
    }

    try {
        Write-Host "Starting $Label service ($($service.Name))..." -ForegroundColor Green
        Start-Service -Name $service.Name -ErrorAction Stop
        $service.WaitForStatus("Running", [TimeSpan]::FromSeconds(20))
    }
    catch {
        $message = "Unable to start $Label service '$($service.Name)': $($_.Exception.Message)"
        if ($Required) {
            Start-OpenTradingServiceElevated -Label $Label -ServiceName $service.Name
            $service = Get-Service -Name $service.Name -ErrorAction Stop
            $service.WaitForStatus("Running", [TimeSpan]::FromSeconds(20))
            Write-Host "$Label service is running ($($service.Name))." -ForegroundColor Green
            return
        }
        Write-Host "$message The application will use its built-in fallback." -ForegroundColor DarkYellow
    }
}

$databaseUrl = Get-OpenTradingEnvValue -Name "DATABASE_URL"
$usesLocalPostgres = $databaseUrl -match "^postgresql" -and $databaseUrl -match "@(localhost|127\.0\.0\.1)(:|/)"
if ($usesLocalPostgres) {
    Start-OpenTradingDependencyService `
        -Label "PostgreSQL" `
        -ConfiguredName (Get-OpenTradingEnvValue -Name "OPENTRADING_POSTGRES_SERVICE") `
        -DiscoveryPattern "postgresql*" `
        -Required $true
}
