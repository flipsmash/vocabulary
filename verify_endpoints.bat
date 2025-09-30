@echo off
echo Starting Vocabulary App Endpoint Verification...
echo.

REM Check if the app is running
curl -s http://localhost:8000/ >nul 2>&1
if %errorlevel% neq 0 (
    echo ERROR: Vocabulary app is not running on localhost:8000
    echo Please start the app first with: python working_vocab_app.py
    echo.
    pause
    exit /b 1
)

echo App is running, starting verification...
python endpoint_verification.py

echo.
echo Verification complete. Check endpoint_verification_report.txt for details.
echo.
pause