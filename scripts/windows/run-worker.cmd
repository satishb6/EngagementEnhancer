@echo off
title WIRE Worker - keep open
cd /d "%~dp0..\..\services\api"
.venv\Scripts\python.exe -m celery -A wire_api.worker.celery_app worker --beat --loglevel=info --pool=solo
pause
