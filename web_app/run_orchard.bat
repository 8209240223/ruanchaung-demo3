@echo off
setlocal
cd /d "%~dp0"

echo [orchard] stopping any process on :5000 ...
for /f "tokens=5" %%a in ('netstat -ano ^| findstr :5000 ^| findstr LISTENING') do (
  taskkill /F /PID %%a >nul 2>nul
)

echo [orchard] starting latest backend ...
set APP_DEBUG=0
set APP_RELOAD=0
py app.py

