@echo off
setlocal
cd /d "%~dp0"
if not exist "backend\venv\Scripts\python.exe" (
  echo backend\venv\Scripts\python.exe not found. Create the project virtual environment first.
  exit /b 1
)
"backend\venv\Scripts\python.exe" -m pip install pyinstaller
if errorlevel 1 exit /b %errorlevel%
"backend\venv\Scripts\python.exe" -m PyInstaller --clean --noconfirm desktop.spec
if errorlevel 1 exit /b %errorlevel%
echo Desktop package created: dist\DataFlowAI.exe
