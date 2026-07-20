@echo off
REM  WIRE - stop everything.
cd /d "%~dp0"
echo  Closing the WIRE windows...
taskkill /fi "WINDOWTITLE eq WIRE API*" /t /f >nul 2>&1
taskkill /fi "WINDOWTITLE eq WIRE Web*" /t /f >nul 2>&1
taskkill /fi "WINDOWTITLE eq WIRE Worker*" /t /f >nul 2>&1
echo  Done. Everything is stopped.
pause
