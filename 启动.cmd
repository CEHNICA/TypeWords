@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo.
echo   TypeWords - local source build
echo   URL: http://localhost:5567
echo.
echo   Use localhost, NOT 127.0.0.1 (tracking checks hostname).
echo.

REM Build the offline word-lookup index on first run.
REM data\ is gitignored, so a fresh clone has no index -> word lookup would
REM always fall through to "not found". Takes ~5s, only when missing.
if not exist "data\word-index.json" (
  echo   Building word lookup index (first run, ~5s)...
  call node scripts\build-word-index.mjs
  echo.
)

start "" "http://localhost:5567"
call pnpm.cmd run dev
pause
