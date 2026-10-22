@echo off
setlocal
cd /d %~dp0
echo [AI Jukebox] setting up...
if not exist .venv (
    py -3.11 -m venv .venv || goto :err
)
call .venv\Scripts\activate.bat
python -m pip install -q -r requirements.txt || goto :err
set "PORT=%AIJ_PORT%"
if "%PORT%"=="" set "PORT=8000"
echo [AI Jukebox] starting on http://127.0.0.1:%PORT%  (set AIJ_PORT to override)
echo [AI Jukebox] configuration: copy .env.example to .env; AIJ_API_KEY is required
python -m uvicorn app.main:app --host 127.0.0.1 --port %PORT%
goto :eof
:err
echo Setup failed - is Python 3.10+ installed and on PATH?
exit /b 1
