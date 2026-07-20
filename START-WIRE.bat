@echo off
REM ============================================================
REM  WIRE - start everything. Double-click me each time you want
REM  to use the app. Three small windows will open - keep them
REM  open (minimised is fine) while you use WIRE.
REM  Run SETUP-WIRE.bat once before the first start.
REM ============================================================
cd /d "%~dp0"

echo  Starting database...
docker compose up -d db redis
if errorlevel 1 (
  echo   Docker isn't running - open Docker Desktop, wait for the whale, try again.
  pause
  exit /b 1
)

echo  Starting the API...
start "WIRE API" "%~dp0scripts\windows\run-api.cmd"

echo  Starting the background worker...
start "WIRE Worker" "%~dp0scripts\windows\run-worker.cmd"

echo  Starting the website...
start "WIRE Web" "%~dp0scripts\windows\run-web.cmd"

echo  Waiting 15 seconds, then opening WIRE in your browser...
timeout /t 15 /nobreak >nul
start http://localhost:3000

echo.
echo  WIRE is up. To stop everything later, double-click STOP-WIRE.bat
echo  (you can close THIS window now - keep the other three open).
pause
