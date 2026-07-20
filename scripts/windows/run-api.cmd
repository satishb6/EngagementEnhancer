@echo off
title WIRE API - keep open
cd /d "%~dp0..\..\services\api"
.venv\Scripts\python.exe -m uvicorn wire_api.main:app --port 8000
pause
