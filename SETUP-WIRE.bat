@echo off
REM ============================================================
REM  WIRE - one-time setup. NO Docker needed (lite mode:
REM  SQLite database + built-in background worker).
REM  Safe to run again any time - it skips what's already done.
REM ============================================================
setlocal
cd /d "%~dp0"
set "PATH=%LOCALAPPDATA%\Microsoft\WinGet\Packages\OpenJS.NodeJS.LTS_Microsoft.Winget.Source_8wekyb3d8bbwe\node-v24.18.0-win-x64;%APPDATA%\npm;%PATH%"

echo.
echo  [1/3] Preparing the Python engine...
cd services\api
if not exist ".venv\Scripts\python.exe" (
  echo        First run - installing parts ^(~3 min^)...
  python -m venv .venv
  .venv\Scripts\python.exe -m pip install --quiet --upgrade pip
  .venv\Scripts\pip.exe install --quiet -e ".[dev]"
)

echo  [2/3] Building the database (a simple local file - wire.db)...
.venv\Scripts\python.exe -m alembic upgrade head
if errorlevel 1 ( echo   Database setup failed - see above. & pause & exit /b 1 )

echo  [3/3] Adding demo users and demo news...
.venv\Scripts\python.exe -m wire_api.seed
cd ..\..

echo.
echo  ============================================
echo   Setup complete. Now double-click START-WIRE.bat
echo   Demo login:  pro@wire.dev  /  wire-dev-password
echo   No API keys needed - Demo mode works instantly.
echo   Add free keys later inside the app: Studio - Engine.
echo  ============================================
echo.
pause
