@echo off
setlocal
cd /d "%~dp0"

echo ====================================
echo  Building run.exe
echo ====================================
echo.

if not exist ".venv\Scripts\python.exe" (
    echo [1/4] Creating virtual environment...
    python -m venv .venv
    if errorlevel 1 goto :nopython
) else (
    echo [1/4] Virtual environment found.
)

echo [2/4] Installing dependencies...
call .venv\Scripts\activate.bat
python -m pip install --upgrade pip --quiet
python -m pip install -r requirements.txt --quiet
python -m pip install pyinstaller --quiet
if errorlevel 1 goto :failed

echo [3/4] Cleaning previous build...
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist

echo [4/4] Running PyInstaller (this takes a few minutes)...
pyinstaller run.spec --noconfirm
if errorlevel 1 goto :failed

echo.
echo Copying working folders into dist...
if not exist "dist\run\profiles" mkdir "dist\run\profiles"
if not exist "dist\run\logs\screenshots" mkdir "dist\run\logs\screenshots"
if not exist "dist\run\vision\templates\states" mkdir "dist\run\vision\templates\states"
if not exist "dist\run\screenshots" mkdir "dist\run\screenshots"
if exist "profiles\*.json" copy /y "profiles\*.json" "dist\run\profiles\" >nul
if exist "profiles\*.png" copy /y "profiles\*.png" "dist\run\profiles\" >nul
if exist "vision\templates\*.png" copy /y "vision\templates\*.png" "dist\run\vision\templates\" >nul
copy /y "vision\templates\README.txt" "dist\run\vision\templates\README.txt" >nul
if exist "vision\templates\states\*.png" copy /y "vision\templates\states\*.png" "dist\run\vision\templates\states\" >nul
copy /y "vision\templates\states\README.txt" "dist\run\vision\templates\states\README.txt" >nul
copy /y config.yaml "dist\run\config.yaml" >nul

echo.
echo ====================================
echo  Done.  ->  dist\run\run.exe
echo ====================================
echo.
echo Ship the whole dist\run folder, not just the exe.
pause
exit /b 0

:nopython
echo.
echo ERROR: Python not found on PATH.
echo Install Python 3.11 or 3.12 and tick "Add Python to PATH".
pause
exit /b 1

:failed
echo.
echo ERROR: build failed. Scroll up for the message.
pause
exit /b 1
