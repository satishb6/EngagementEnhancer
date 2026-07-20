@echo off
REM ============================================================
REM  WIRE - send the latest code to GitHub.
REM  FIRST TIME: a browser window will open asking you to sign
REM  in to GitHub - click "Sign in with your browser", log in,
REM  and click Authorize. After that it's automatic forever.
REM ============================================================
cd /d "%~dp0"
echo  Pushing to https://github.com/satishb6/EngagementEnhancer ...
git push -u origin main
if errorlevel 1 (
  echo.
  echo  Push did not complete. If a browser window opened, finish the
  echo  sign-in there and double-click this file again.
) else (
  echo.
  echo  Done! GitHub now has the latest code.
  echo  Vercel and Hugging Face will update automatically
  echo  once they are connected (see the guide).
)
pause
