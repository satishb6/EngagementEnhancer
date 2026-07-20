@echo off
REM ============================================================
REM  WIRE - start the app. NO Docker needed.
REM  Two small windows open (the engine + the website) - keep
REM  them open (minimised is fine) while you use WIRE.
REM ============================================================
cd /d "%~dp0"

echo  Starting the engine (API + built-in worker)...
start "WIRE API" "%~dp0scripts\windows\run-api.cmd"

echo  Starting the website...
start "WIRE Web" "%~dp0scripts\windows\run-web.cmd"

echo  Waiting 15 seconds, then opening WIRE in your browser...
timeout /t 15 /nobreak >nul
start http://localhost:3000

echo.
echo  WIRE is up. To stop: double-click STOP-WIRE.bat
echo  (you can close THIS window - keep the other two open).
pause
