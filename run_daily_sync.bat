@echo off
REM Daily maternity leave hours sync (Windows Task Scheduler).
REM Set "Start in" to this folder; ensure .env exists and SYNC_PRODUCTION=1 for prod.
cd /d "%~dp0"
py -3 main.py
exit /b %ERRORLEVEL%
