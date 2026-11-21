@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo.
echo   TypeWords - local source build
echo   URL: http://localhost:5567
echo.
echo   Use localhost, NOT 127.0.0.1 (tracking checks hostname).
echo.
start "" "http://localhost:5567"
call pnpm.cmd run dev
pause
