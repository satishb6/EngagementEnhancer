@echo off
REM ============================================================
REM  WIRE - one-time setup. Double-click me AFTER installing
REM  Docker Desktop (see docs/GETTING-STARTED-SIMPLE.md, Step 1).
REM  Safe to run again any time - it skips what's already done.
REM ============================================================
setlocal
cd /d "%~dp0"
set "PATH=%LOCALAPPDATA%\Microsoft\WinGet\Packages\OpenJS.NodeJS.LTS_Microsoft.Winget.Source_8wekyb3d8bbwe\node-v24.18.0-win-x64;%APPDATA%\npm;%PATH%"

echo.
echo  [1/5] Checking Docker...
docker --version >nul 2>&1
if errorlevel 1 (
  echo.
  echo   Docker is not installed or not running.
  echo   Open Docker Desktop first ^(whale icon in the taskbar^),
  echo   or install it: https://www.docker.com/products/docker-desktop
  echo.
  pause
  exit /b 1
)
echo        Docker OK.

echo  [2/5] Starting the database and queue...
docker compose up -d db redis
if errorlevel 1 ( echo   Could not start containers. Is Docker Desktop running? & pause & exit /b 1 )
echo        Waiting 10 seconds for the database to be ready...
timeout /t 10 /nobreak >nul

echo  [3/5] Creating your settings file if needed...
if not exist "services\api\.env" (
  copy ".env.example" "services\api\.env" >nul
  echo        Created services\api\.env - Notepad will open it now.
  echo        Paste your API keys next to the = signs, then Save and close.
  start /wait notepad "services\api\.env"
) else (
  echo        services\api\.env already exists - keeping it.
)

echo  [4/5] Building the database tables...
cd services\api
if not exist ".venv\Scripts\python.exe" (
  echo        First run on this machine - preparing Python parts ^(~3 min^)...
  python -m venv .venv
  .venv\Scripts\python.exe -m pip install --quiet --upgrade pip
  .venv\Scripts\pip.exe install --quiet -e ".[dev]"
)
.venv\Scripts\python.exe -m alembic upgrade head
if errorlevel 1 ( echo   Database setup failed - see the message above. & pause & exit /b 1 )

echo  [5/5] Adding demo users and demo news...
.venv\Scripts\python.exe -m wire_api.seed
cd ..\..

echo.
echo  ============================================
echo   Setup complete. Now double-click START-WIRE.bat
echo   Demo login:  pro@wire.dev  /  wire-dev-password
echo  ============================================
echo.
pause
