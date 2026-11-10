@echo off
setlocal
cd /d "%~dp0"
if not exist "dist\DataFlowAI.exe" (
  echo Run build-desktop.bat first.
  exit /b 1
)
where ISCC.exe >nul 2>nul
if errorlevel 1 (
  echo Inno Setup 6 must be installed and ISCC.exe must be on PATH.
  exit /b 1
)
ISCC.exe deployment\desktop\DataFlowAI.iss
if errorlevel 1 exit /b %errorlevel%
echo Installer created: dist\DataFlowAI-Setup.exe
