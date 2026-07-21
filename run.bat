@echo off
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo First run - setting up. This takes a few minutes.
    echo.
    python -m venv .venv
    if errorlevel 1 goto :nopython
    call .venv\Scripts\activate.bat
    python -m pip install --upgrade pip --quiet
    python -m pip install -r requirements.txt
    if errorlevel 1 goto :failed
    echo.
    echo Setup complete.
    echo.
) else (
    call .venv\Scripts\activate.bat
)

start "" .venv\Scripts\pythonw.exe main.py
exit /b 0

:nopython
echo.
echo ERROR: Python not found on PATH.
echo Install Python 3.11 or 3.12 and tick "Add Python to PATH".
pause
exit /b 1

:failed
echo.
echo ERROR: dependency install failed.
pause
exit /b 1
