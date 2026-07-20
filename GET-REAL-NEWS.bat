@echo off
REM ============================================================
REM  WIRE - pull real news right now (instead of waiting for the
REM  automatic 5-minute cycle). Needs your API keys in
REM  services\api\.env  (ANTHROPIC_API_KEY + OPENAI_API_KEY).
REM ============================================================
cd /d "%~dp0services\api"
echo  Fetching from your sources and writing briefings...
.venv\Scripts\python.exe -m wire_api.ingestion.run_once
echo.
echo  Done. Refresh the website - the deck now has real news.
pause
