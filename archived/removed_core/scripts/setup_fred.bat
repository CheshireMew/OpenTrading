@echo off
chcp 65001 >nul
echo ======================================================================
echo             FRED API Key Setup Guide
echo ======================================================================
echo.
echo [Step 1] Open Browser
echo.
echo Please visit: https://fred.stlouisfed.org/
echo.
echo [Step 2] Register or Login
echo   - Click "Sign Up" if you don't have an account
echo   - Or "Log In" if you already registered
echo.
echo [Step 3] Get API Key
echo.
echo Visit: https://fredaccount.stlouisfed.org/apikeys
echo.
echo   - Click "Request API Key" button
echo   - Fill in:
echo     * Description: Heimdall Market Analysis
echo     * Purpose: Research or Education
echo   - Copy your API Key (32 characters)
echo.
echo [Step 4] Configure .env file
echo.
set /p API_KEY="Paste your FRED API Key here (or press Enter to skip): "

if "%API_KEY%"=="" (
    echo.
    echo Skipped. You can manually edit .env file later.
    echo Add this line:
    echo FRED_API_KEY=your_api_key_here
    goto :end
)

echo.
echo Saving to .env file...

if exist .env (
    echo FRED_API_KEY=%API_KEY% >> .env
    echo.
    echo Configuration saved to .env
) else (
    echo # FRED API Configuration > .env
    echo FRED_API_KEY=%API_KEY% >> .env
    echo.
    echo .env file created with FRED_API_KEY
)

echo.
echo ======================================================================
echo Configuration Complete!
echo ======================================================================
echo.
echo Next Steps:
echo   1. Update market_cron.py to use MacroProviderV2
echo   2. Run: python -m app.infra.persistence.market_cron
echo   3. Check: python -m scripts.check_indicators
echo.
echo See detailed guide: docs\FRED_API_SETUP_GUIDE.md
echo.

:end
pause
