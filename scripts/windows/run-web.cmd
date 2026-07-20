@echo off
title WIRE Web - keep open
cd /d "%~dp0..\.."
set "PATH=%LOCALAPPDATA%\Microsoft\WinGet\Packages\OpenJS.NodeJS.LTS_Microsoft.Winget.Source_8wekyb3d8bbwe\node-v24.18.0-win-x64;%APPDATA%\npm;%PATH%"
call pnpm --filter web dev
pause
