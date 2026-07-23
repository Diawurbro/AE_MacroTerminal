@echo off
setlocal
cd /d "%~dp0"

echo ====================================
echo  Building AE_MacroTerminal_Setup.exe
echo ====================================
echo.

echo [1/2] Building run.exe (PyInstaller)...
call build.bat
if errorlevel 1 goto :failed

echo.
echo [2/2] Compiling installer (Inno Setup)...
set ISCC=""
where iscc >nul 2>nul
if not errorlevel 1 (
    set ISCC=iscc
) else if exist "%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe" (
    set ISCC="%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
) else if exist "%ProgramFiles%\Inno Setup 6\ISCC.exe" (
    set ISCC="%ProgramFiles%\Inno Setup 6\ISCC.exe"
)

if %ISCC%=="" goto :noinno

call %ISCC% installer.iss
if errorlevel 1 goto :failed

echo.
echo ====================================
echo  Done.  ->  dist\AE_MacroTerminal_Setup.exe
echo ====================================
echo.
echo Send that one file. Users double-click it - no Python, nothing else needed.
pause
exit /b 0

:noinno
echo.
echo ERROR: Inno Setup not found.
echo Install it once (free): https://jrsoftware.org/isdl.php
echo Then run this script again.
pause
exit /b 1

:failed
echo.
echo ERROR: build failed. Scroll up for the message.
pause
exit /b 1
