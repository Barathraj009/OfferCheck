@echo off
REM Start OfferCheck (dev): backend API + frontend dev server, opens browser
cd /d %~dp0

set PYTHON=python
if exist "%~dp0backend\.venv\Scripts\python.exe" (
    set PYTHON="%~dp0backend\.venv\Scripts\python.exe"
)
set NODE=node

echo [1/4] Starting backend API on http://127.0.0.1:8000
start "OfferCheck-Backend" cmd /c "cd /d %~dp0backend && %PYTHON% -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --log-level info"

timeout /t 3 /nobreak >nul

echo [2/4] Starting frontend dev server on http://127.0.0.1:5173
start "OfferCheck-Frontend" cmd /c "cd /d %~dp0frontend && %NODE% node_modules\vite\bin\vite.js --host 127.0.0.1 --port 5173"

timeout /t 3 /nobreak >nul

echo [3/4] Opening browser...
start "" http://127.0.0.1:5173

echo [4/4] Done. Close these two windows to stop OfferCheck.
exit /b 0
